import math
import socket
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import firebase_admin
from firebase_admin import credentials, db
from twilio.rest import Client
import time
# =====================================
# Gmail Configuration
# =====================================

SENDER_EMAIL    = "omarelstawy411@gmail.com"        
APP_PASSWORD    = "***************************"              
RECEIVER_EMAILS = [
    "omarelstawy411@gmail.com",
    "ahmed01066036829@gmail.com",
    "asdabdo35s3@gmail.com",
    "aliibra670@gmail.com",
    "abdomoabdohhh@gmail.com",
]

# =====================================
# Firebase Configuration
# =====================================

cred = credentials.Certificate(
    r"C:\Users\dell\prediction-of-forests-fire-firebase-adminsdk-fbsvc-160bfca034.json"
)

firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://prediction-of-forests-fire-default-rtdb.firebaseio.com/'
})

# =====================================
# TCP Server Configuration
# =====================================

HOST = "127.0.0.1"
PORT = 5000
LABVIEW_PORT = 5005

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.bind((HOST, PORT))
server.listen(1)

print("Waiting for LabVIEW connection on port 5000...")
conn, addr = server.accept()
print("Connected from:", addr)
conn.settimeout(20)

print(f"Connecting to LabVIEW on port {LABVIEW_PORT} to send risk level...")
time.sleep(0.5)  # Small delay to ensure LabVIEW is listening
client_sender = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    client_sender.connect((HOST, LABVIEW_PORT))
    print(f"Connected to LabVIEW on port {LABVIEW_PORT}.")
except Exception as e:
    print(f"Could not connect to LabVIEW on port {LABVIEW_PORT}: {e}")
    client_sender = None

# =====================================
# Send Email Function
# =====================================

def send_alert_email(status, description, soil_moisture, mq135_co2, mq7_co, soil_temp, air_temp):
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔥 Forest Fire Alert — {status}"
        msg["From"]    = SENDER_EMAIL
        msg["To"]      = ", ".join(RECEIVER_EMAILS)

        body = f"""
🌲 FOREST FIRE DETECTION SYSTEM — ALERT
{'=' * 45}

⚠️  STATUS      : {status}
📋  INFO        : {description}

{'=' * 45}
📊  SENSOR READINGS:

  🌱 Soil Moisture    : {soil_moisture:.2f} %
  💨 MQ135 (CO2)      : {mq135_co2:.2f} PPM
  🔥 MQ7   (CO)       : {mq7_co:.2f} PPM
  🌡️  Soil Temperature : {soil_temp:.2f} °C
  🌡️  Air Temperature  : {air_temp:.2f} °C

{'=' * 45}
⚡ Immediate action may be required.
🤖 This is an automated alert from your WSN system.
        """

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, APP_PASSWORD)
            smtp.sendmail(SENDER_EMAIL, RECEIVER_EMAILS, msg.as_string())

        print(f"✅ Alert email sent to: {RECEIVER_EMAILS}")

    except Exception as e:
        print(f"❌ Email Error: {e}")

def send_sensor_error_email(bad_sensors):
    """يبعت إيميل يخبر بمشكلة اتصال سنسور."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "⚠️ Sensor Connectivity Problem — WSN System"
        msg["From"]    = SENDER_EMAIL
        msg["To"]      = ", ".join(RECEIVER_EMAILS)

        sensors_list = ", ".join(bad_sensors)
        body = f"""
🚨 SENSOR CONNECTIVITY ALERT
{'=' * 45}

The following sensor(s) returned invalid readings (nan/inf):
  ✖  {sensors_list}

Possible causes:
  - Sensor disconnected or damaged
  - Wiring / power issue
  - LabVIEW signal conversion error

{'=' * 45}
Please check your sensor connections.
🤖 This is an automated alert from your WSN system.
        """

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, APP_PASSWORD)
            smtp.sendmail(SENDER_EMAIL, RECEIVER_EMAILS, msg.as_string())

        print(f"✅ Sensor error email sent — bad sensors: {sensors_list}")

    except Exception as e:
        print(f"❌ Sensor Error Email failed: {e}")

# =====================================
# Twilio Configuration
# =====================================

TWILIO_ACCOUNT_SID = "AC26cf032aa49d7feade8c7cfbe4b4f727"
TWILIO_AUTH_TOKEN  = "5f787fc0868009af883ec6f7686b887a"
TWILIO_FROM        = "+14648001232"          # رقم Twilio

CALL_RECIPIENTS = [
    "+201141046007",                          # ضيف أرقام تانية هنا لو حابب
]

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def make_phone_call(status, description):
    """يرن على كل الأرقام في CALL_RECIPIENTS برسالة صوتية عن حالة الخطر."""
    twiml = f"""
    <Response>
        <Say language="en-US" voice="alice">
            Forest Fire Alert! Status: {status}. {description}
            Repeat: {status}. Please take immediate action.
        </Say>
    </Response>
    """
    for number in CALL_RECIPIENTS:
        try:
            call = twilio_client.calls.create(
                twiml=twiml,
                to=number,
                from_=TWILIO_FROM
            )
            print(f"✅ Phone call initiated to {number} — SID: {call.sid}")
        except Exception as e:
            print(f"❌ Phone Call Error to {number}: {e}")


# =====================================
# Helper Flags
# =====================================

# Message written to Firebase when a sensor returns nan / inf
SENSOR_ERROR_MSG = "No sensor / connectivity problem"


def is_bad(value):
    """Return True if value is nan, ±inf, or None."""
    if value is None:
        return True
    try:
        return math.isnan(value) or math.isinf(value)
    except (TypeError, ValueError):
        return True


def sanitize_value(value, fallback=None):
    """
    Return `fallback` when value is nan / ±Infinity / None.
    Pass fallback=SENSOR_ERROR_MSG for Firebase uploads so the
    dashboard shows a human-readable error instead of null.
    """
    return fallback if is_bad(value) else value


def classify_sensors(soil_moisture, mq135_co2, mq7_co, soil_temp, air_temp):

    # Guard: replace nan/inf with safe defaults so comparisons never raise
    soil_moisture = sanitize_value(soil_moisture, fallback=100)  # safe → no drought alarm
    mq135_co2     = sanitize_value(mq135_co2,     fallback=0)
    mq7_co        = sanitize_value(mq7_co,        fallback=0)
    soil_temp     = sanitize_value(soil_temp,      fallback=0)
    air_temp      = sanitize_value(air_temp,       fallback=0)

    # --- Individual flags ---
    heavy_smoldering  = mq7_co > 100
    light_smoldering  = 25 < mq7_co <= 100

    co2_danger        = mq135_co2 > 2000
    co2_high          = 500 < mq135_co2 <= 2000

    temp_critical     = air_temp > 60 or soil_temp > 60
    temp_high_warning = 40 < air_temp <= 60
    temp_warning      = 20 < air_temp <= 40

    moisture_critical = soil_moisture < 40
    moisture_low      = 40 <= soil_moisture < 60

    # --- LEVEL 4 : CRITICAL ---
    if co2_danger:
        return ("CRITICAL", 4, "FIRE DETECTED — CO2 at fire level (>2000 PPM). Immediate action required.")

    if temp_critical:
        return ("CRITICAL", 4, "CRITICAL — Extreme temperature (>60°C). Very high fire probability.")

    if heavy_smoldering and (temp_high_warning or temp_warning):
        return ("CRITICAL", 4, "CRITICAL — Heavy smoldering combustion with elevated temperature. Fire imminent.")

    # --- LEVEL 3 : HIGH DANGER ---
    if heavy_smoldering and moisture_critical:
        return ("HIGH DANGER", 3, "HIGH DANGER — Heavy smoldering with critically dry soil. Fire risk imminent.")

    if heavy_smoldering:
        return ("HIGH DANGER", 3, "HIGH DANGER — Heavy smoldering combustion detected (CO >100 PPM).")

    if co2_high and temp_high_warning:
        return ("HIGH DANGER", 3, "HIGH DANGER — Elevated CO2 with high temperature warning.")

    # --- LEVEL 2 : MEDIUM DANGER ---
    if light_smoldering and (temp_high_warning or temp_warning):
        return ("MEDIUM DANGER", 2, "MEDIUM DANGER — Light smoldering with temperature warning. Conditions worsening.")

    if light_smoldering and moisture_critical:
        return ("MEDIUM DANGER", 2, "MEDIUM DANGER — Light smoldering with critically dry soil.")

    if co2_high and moisture_critical:
        return ("MEDIUM DANGER", 2, "MEDIUM DANGER — Elevated CO2 with very dry soil. High ignition risk.")

    # --- LEVEL 1 : LOW WARNING ---
    if light_smoldering:
        return ("LOW WARNING", 1, "LOW WARNING — Light smoldering detected (CO 25–100 PPM). Monitor closely.")

    if moisture_critical and temp_warning:
        return ("LOW WARNING", 1, "LOW WARNING — Dry soil with temperature in warning zone. Pre-fire conditions.")

    if moisture_low and co2_high:
        return ("LOW WARNING", 1, "LOW WARNING — Low soil moisture with elevated CO2.")

    if temp_high_warning:
        return ("LOW WARNING", 1, "LOW WARNING — High temperature detected (>40°C) without other indicators.")

    # --- LEVEL 0 : NORMAL ---
    return ("NORMAL", 0, "All readings within normal range. No fire risk detected.")

# =====================================
# Main Loop
# =====================================

import time

# Cooldowns (in seconds)
NAN_EMAIL_COOLDOWN = 15 * 60
ALERT_EMAIL_COOLDOWN = 5 * 60     # 5 دقائق للرسائل التحذيرية
PHONE_CALL_COOLDOWN = 5 * 60      # 5 دقائق للمكالمات الهاتفية

_last_nan_email_time = 0
_last_alert_email_time = 0
_last_phone_call_time = 0

while True:

    try:
        data = conn.recv(1024)

        if not data:
            print("ERROR: Connection closed by LabVIEW")
            break

        message = data.decode().strip()

        for line in message.splitlines():

            try:
                soil_moisture, mq135_co2, mq7_co, soil_temp, air_temp = map(
                    float, line.split(",")
                )

                # === Classify ===
                status, danger_level, description = classify_sensors(
                    soil_moisture, mq135_co2, mq7_co, soil_temp, air_temp
                )

                # === Send Status back to LabVIEW ===
                try:
                    conn.send((str(danger_level) + '\r\n').encode())
                    print(f"--> Sent danger level {danger_level} to LabVIEW via conn")
                except Exception as e:
                    print("Error sending danger level to LabVIEW:", e)

                # === Terminal Output ===
                print("\n" + "=" * 50)
                print(f"  Soil Moisture    : {soil_moisture:.2f} %")
                print(f"  MQ135 (CO2)      : {mq135_co2:.2f} PPM")
                print(f"  MQ7   (CO)       : {mq7_co:.2f} PPM")
                print(f"  Soil Temperature : {soil_temp:.2f} °C")
                print(f"  Air Temperature  : {air_temp:.2f} °C")
                print(f"  STATUS           : {status}")
                print(f"  INFO             : {description}")
                print("=" * 50)

                # === Detect bad sensor readings before upload ===
                bad_sensors = [
                    name for name, val in [
                        ("soil_moisture",    soil_moisture),
                        ("mq135_co2",        mq135_co2),
                        ("mq7_co",           mq7_co),
                        ("soil_temperature", soil_temp),
                        ("air_temperature",  air_temp),
                    ] if is_bad(val)
                ]
                if bad_sensors:
                    print(f"  ⚠  SENSOR WARNING — invalid reading (nan/inf) on: {', '.join(bad_sensors)}")
                    now = time.time()
                    if now - _last_nan_email_time >= NAN_EMAIL_COOLDOWN:
                        _last_nan_email_time = now
                        send_sensor_error_email(bad_sensors)
                    else:
                        remaining = int(NAN_EMAIL_COOLDOWN - (now - _last_nan_email_time))
                        print(f"     📧 Sensor-error email cooldown — next in {remaining // 60}m {remaining % 60}s")

                # === Danger Alerts ===
                # Send email for LOW WARNING (1) and above
                # Make phone calls for MEDIUM DANGER (2) and above
                now = time.time()
                
                if danger_level >= 1:
                    if now - _last_alert_email_time >= ALERT_EMAIL_COOLDOWN:
                        _last_alert_email_time = now
                        safe_moisture = sanitize_value(soil_moisture, 0)
                        safe_co2      = sanitize_value(mq135_co2,    0)
                        safe_co       = sanitize_value(mq7_co,        0)
                        safe_stemp    = sanitize_value(soil_temp,     0)
                        safe_atemp    = sanitize_value(air_temp,      0)
                        send_alert_email(
                            status, description,
                            safe_moisture, safe_co2, safe_co, safe_stemp, safe_atemp
                        )
                    else:
                        remaining = int(ALERT_EMAIL_COOLDOWN - (now - _last_alert_email_time))
                        print(f"     📧 Alert email cooldown — next in {remaining // 60}m {remaining % 60}s")

                if danger_level >= 2:
                    if now - _last_phone_call_time >= PHONE_CALL_COOLDOWN:
                        _last_phone_call_time = now
                        make_phone_call(status, description)
                    else:
                        remaining = int(PHONE_CALL_COOLDOWN - (now - _last_phone_call_time))
                        print(f"     📞 Phone call cooldown — next in {remaining // 60}m {remaining % 60}s")

                # === Upload to Firebase ===
                # Bad values (nan/inf) are stored as SENSOR_ERROR_MSG string
                # so the dashboard shows a human-readable error, not null.
                db.reference("sensors").set({
                    "soil_moisture":    sanitize_value(soil_moisture, SENSOR_ERROR_MSG),
                    "mq135_co2":        sanitize_value(mq135_co2,    SENSOR_ERROR_MSG),
                    "mq7_co":           sanitize_value(mq7_co,        SENSOR_ERROR_MSG),
                    "soil_temperature": sanitize_value(soil_temp,     SENSOR_ERROR_MSG),
                    "air_temperature":  sanitize_value(air_temp,      SENSOR_ERROR_MSG),
                    "status":           status,
                    "danger_level":     danger_level,
                    "description":      description
                })

            except Exception as e:
                print("Parse Error:", e)

    except socket.timeout:
        print("\n" + "*" * 50)
        print("ERROR: No data received from LabVIEW for 20 seconds!")
        print("Communication Lost.")
        print("*" * 50)

    except Exception as e:
        print("Connection Error:", e)
        break

# =====================================
# Close Connections
# =====================================

if 'client_sender' in locals() and client_sender:
    client_sender.close()
conn.close()
server.close()
print("Server Closed.")