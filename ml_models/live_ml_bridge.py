import json
import time
import requests
import joblib
from pathlib import Path
from awscrt import mqtt
from awsiot import mqtt_connection_builder

# ==========================================
# 1. AWS CONFIGURATION
# ==========================================
ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"
CLIENT_ID = "REMAC-ML-Bridge"
TOPIC = "remac/node1/data"

ROOT_CA = "certificates/Remac-Node-1/AmazonRootCA1.pem"
CERT = "certificates/Remac-Node-1/dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt"
KEY = "certificates/Remac-Node-1/dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key"

# ==========================================
# 2. LOAD TRAINED ML MODELS
# ==========================================
print("Loading Machine Learning Models...")
isolation_model = joblib.load("ml_models/isolation_forest_model.pkl")
rf_model = joblib.load("ml_models/random_forest_model.pkl")
encoder = joblib.load("ml_models/status_encoder.pkl")
print("ML Models loaded successfully!")

# Cloud database URL
JSONBLOB_URL = "https://jsonblob.com/api/jsonBlob/019f4ab1-f7e9-7797-aad7-e56a4a77fc86"

# Thresholds
TEMP_THRESHOLD = 40.0
HUMIDITY_THRESHOLD = 60.0

# ==========================================
# 3. MQTT INCOMING MESSAGE HANDLER
# ==========================================
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    try:
        # Decode incoming raw JSON sensor data
        data_str = payload.decode('utf-8')
        raw_data = json.loads(data_str)
        
        print("\n-------------------------------------------")
        print(f"Received raw data from AWS IoT Core ({topic})")
        
        # Extract features
        temp = float(raw_data.get("Temperature_C", 0.0))
        hum = float(raw_data.get("Humidity_%", 0.0))
        dist = float(raw_data.get("Distance_cm", 0.0))
        lvl = float(raw_data.get("Material_Level_%", 0.0))
        timestamp = raw_data.get("Timestamp", "N/A")
        device_id = raw_data.get("Device_ID", "REMAC_PET_001")
        
        features = [[temp, hum, dist, lvl]]
        
        # A. Isolation Forest Prediction (Anomaly Detection)
        iso_pred = isolation_model.predict(features)[0]
        iso_result = "NORMAL" if iso_pred == 1 else "ANOMALY"
        
        # B. Random Forest Prediction (Alert Status)
        rf_pred = rf_model.predict(features)[0]
        rf_result = encoder.inverse_transform([rf_pred])[0]
        
        # C. Alert Details
        active_alert = "None"
        if rf_result != "SAFE":
            active_alert = raw_data.get("Active_Alerts", "Anomaly Detected")
            
        # D. Risk Calculations
        temp_risk = round(max(0.0, (temp / TEMP_THRESHOLD) * 100), 2)
        hum_risk = round(max(0.0, (hum / HUMIDITY_THRESHOLD) * 100), 2)
        
        # E. Construct Unified Dashboard Payload
        dashboard_payload = {
            "device": device_id,
            "timestamp": str(timestamp),
            "temperature": temp,
            "humidity": hum,
            "distance": dist,
            "material_level": lvl,
            "status": rf_result,
            "active_alert": active_alert,
            "random_forest": rf_result,
            "isolation_forest": iso_result,
            "temperature_risk": temp_risk,
            "humidity_risk": hum_risk
        }
        
        print(f"Timestamp        : {timestamp}")
        print(f"Temperature      : {temp} °C (Risk: {temp_risk}%)")
        print(f"Humidity         : {hum} % (Risk: {hum_risk}%)")
        print(f"Isolation Forest : {iso_result}")
        print(f"Random Forest    : {rf_result}")
        print(f"Active Alert     : {active_alert}")
        
        # 1. Update Local Dashboard Files (for local PC server)
        live_data_dir = Path("live_data")
        live_data_dir.mkdir(exist_ok=True)
        for filename in ["latest.json", "latest_1.json"]:
            try:
                with open(live_data_dir / filename, "w") as file:
                    json.dump(dashboard_payload, file, indent=4)
            except Exception as e:
                print(f"Error writing to local file {filename}: {e}")
                
        # 2. Upload to JSONBlob Cloud Database (for serverless dashboard)
        try:
            res = requests.put(JSONBLOB_URL, json=dashboard_payload, headers={"Content-Type": "application/json"}, timeout=3)
            print(f"Uploaded predictions to Cloud Dashboard. Response: {res.status_code}")
        except Exception as e:
            print(f"Error uploading to cloud JSONBlob: {e}")
            
    except Exception as e:
        print(f"Error processing message: {e}")

# ==========================================
# 4. AWS IOT CORE SUBSCRIPTION & RUN
# ==========================================
print("Connecting to AWS IoT Core as subscriber...")
mqtt_connection = mqtt_connection_builder.mtls_from_path(
    endpoint=ENDPOINT,
    cert_filepath=CERT,
    pri_key_filepath=KEY,
    ca_filepath=ROOT_CA,
    client_id=CLIENT_ID,
    clean_session=False,
    keep_alive_secs=30,
)

mqtt_connection.connect().result()
print("Connected to AWS IoT Core successfully!")

# Subscribe to topic
subscribe_future, packet_id = mqtt_connection.subscribe(
    topic=TOPIC,
    qos=mqtt.QoS.AT_LEAST_ONCE,
    callback=on_message_received
)
subscribe_result = subscribe_future.result()
print(f"Subscribed to topic '{TOPIC}' successfully. Awaiting telemetry...")

# Keep running to listen for messages
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDisconnecting...")
    mqtt_connection.disconnect().result()
    print("Disconnected.")
