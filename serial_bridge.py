import os
import sys
import time
import json
from pathlib import Path

# Try to import serial library
try:
    import serial
except ImportError:
    print("Error: 'pyserial' library is not installed.")
    print("Please install it on your PC by running: pip install pyserial")
    sys.exit(1)

# Try to import AWS IoT Core libraries
try:
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder
except ImportError:
    print("Warning: AWS IoT SDK not found. Running in Local-Only Dashboard mode.")
    print("To enable AWS Core, install the SDK on your PC: pip install awsiotsdk")
    mqtt = None

# ==========================================
# 1. CONFIGURATION
# ==========================================
# Serial port configuration - Change to match your Arduino port (e.g., 'COM5' on Windows or '/dev/ttyUSB0' on Linux)
SERIAL_PORT = "COM5" 
BAUD_RATE = 115200

# AWS IoT Core configuration
AWS_ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"
CLIENT_ID = "Remac-Node-1"
AWS_TOPIC = "remac/node1/data"

# Certificate paths relative to the project root
PATH_TO_ROOT = os.path.join("CERTIFICATES", "Remac-Node-1", "AmazonRootCA1.pem")
PATH_TO_CERT = os.path.join("CERTIFICATES", "Remac-Node-1", "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt")
PATH_TO_KEY = os.path.join("CERTIFICATES", "Remac-Node-1", "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key")

# ==========================================
# 2. CONNECT TO AWS IOT CORE
# ==========================================
mqtt_connection = None
if mqtt is not None:
    try:
        print("Connecting to AWS IoT Core...")
        mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=AWS_ENDPOINT,
            cert_filepath=PATH_TO_CERT,
            pri_key_filepath=PATH_TO_KEY,
            ca_filepath=PATH_TO_ROOT,
            client_id=CLIENT_ID,
            clean_session=False,
            keep_alive_secs=30,
        )
        connect_future = mqtt_connection.connect()
        connect_future.result()
        print("✅ Connected to AWS IoT Core successfully!")
    except Exception as e:
        print(f"❌ Failed to connect to AWS: {e}")
        print("Continuing in Local Dashboard-Only mode.")
        mqtt_connection = None

# ==========================================
# 3. CONNECT TO SERIAL PORT
# ==========================================
print(f"Opening Serial Port {SERIAL_PORT}...")
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    time.sleep(2) # Wait for connection to initialize
    print(f"✅ Serial Port {SERIAL_PORT} connected successfully!")
except Exception as e:
    print(f"❌ Error opening Serial Port {SERIAL_PORT}: {e}")
    print("\nPlease verify:")
    print("1. Your NodeMCU is plugged in via USB.")
    print("2. The Arduino Serial Monitor is CLOSED (only one program can use COM5 at a time).")
    print(f"3. Your COM port is actually {SERIAL_PORT} (check Device Manager).")
    sys.exit(1)

# Ensure live_data directory exists
live_data_dir = Path("live_data")
live_data_dir.mkdir(exist_ok=True)

print("\n--- Listening for Sensor Data from NodeMCU ---")
print("Press Ctrl+C to stop.")

try:
    while True:
        if ser.in_waiting > 0:
            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("DATA:"):
                    # Extract JSON string
                    json_str = line[5:]
                    data = json.loads(json_str)
                    
                    # Read current values
                    temperature = float(data.get("temperature", 0.0))
                    humidity = float(data.get("humidity", 0.0))
                    distance = float(data.get("distance", 0.0))
                    level = float(data.get("material_level", 0.0))
                    
                    # Define alarms/warning status
                    is_temp_alert = temperature > 30.0
                    is_hum_alert = humidity > 60.0
                    is_level_alert = level < 15.0
                    has_alert = is_temp_alert or is_hum_alert or is_level_alert
                    
                    status_str = "DANGER" if has_alert else "SAFE"
                    
                    alert_desc = "None"
                    if is_temp_alert and is_hum_alert and is_level_alert:
                        alert_desc = "High Temp + High Humid + Low Material"
                    elif is_temp_alert and is_hum_alert:
                        alert_desc = "High Temperature + High Humidity"
                    elif is_temp_alert and is_level_alert:
                        alert_desc = "High Temperature + Low Material"
                    elif is_hum_alert and is_level_alert:
                        alert_desc = "High Humidity + Low Material"
                    elif is_temp_alert:
                        alert_desc = "High Temperature"
                    elif is_hum_alert:
                        alert_desc = "High Humidity"
                    elif is_level_alert:
                        alert_desc = "Low Material Level"

                    # Generate Dashboard Payload
                    payload = {
                        "device": "REMAC_PET_001",
                        "timestamp": time.strftime("%H:%M:%S"),
                        "temperature": temperature,
                        "humidity": humidity,
                        "distance": distance,
                        "material_level": level,
                        "status": status_str,
                        "active_alert": alert_desc,
                        "random_forest": status_str,
                        "isolation_forest": "ANOMALY" if has_alert else "NORMAL",
                        "temperature_risk": round((temperature / 40.0) * 100, 1),
                        "humidity_risk": round((humidity / 60.0) * 100, 1)
                    }
                    
                    # 1. Update local files for the React Dashboard
                    for filename in ["latest.json", "latest_1.json"]:
                        with open(live_data_dir / filename, "w") as f:
                            json.dump(payload, f, indent=4)
                    
                    # 2. Publish to AWS IoT Core (if connected)
                    aws_status = "Skipped"
                    if mqtt_connection is not None:
                        try:
                            aws_payload = {
                                "device_id": "REMAC_PET_001",
                                "temperature": temperature,
                                "humidity": humidity,
                                "proximity": distance,
                                "material_level": level,
                                "status": status_str,
                                "active_alerts": alert_desc
                            }
                            mqtt_connection.publish(
                                topic=AWS_TOPIC,
                                payload=json.dumps(aws_payload),
                                qos=mqtt.QoS.AT_LEAST_ONCE
                            )
                            aws_status = "OK"
                        except Exception as e:
                            aws_status = f"Failed ({e})"
                            
                    # Print status to Console
                    print(f"[{time.strftime('%H:%M:%S')}] Temp: {temperature}°C | Hum: {humidity}% | Level: {level}% | Uploading to Dashboard... 200 | AWS Publish... {aws_status}")
            except Exception as e:
                print(f"Error parsing line: {e}")
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nStopping Serial Bridge...")
finally:
    ser.close()
    if mqtt_connection is not None:
        mqtt_connection.disconnect().result()
    print("Disconnected.")
