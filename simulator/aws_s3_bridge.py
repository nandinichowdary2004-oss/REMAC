import time
import json
import requests
import joblib
from pathlib import Path

# Try to import AWS SDKs
try:
    import boto3
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

try:
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder
    HAS_AWS_IOT = True
except ImportError:
    HAS_AWS_IOT = False

# ============================================================
# CONFIGURATION
# ============================================================
S3_BUCKET_NAME = "your-remac-telemetry-bucket"  # <-- Replace with your AWS S3 bucket name
AWS_REGION = "us-east-1"                       # <-- Replace with your AWS region

# Set AWS Credentials if not using environment variables/IAM roles
# boto3 will automatically pick up AWS_ACCESS_KEY_ID & AWS_SECRET_ACCESS_KEY from env
AWS_ACCESS_KEY = None 
AWS_SECRET_KEY = None

# AWS IoT Config
ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"
CLIENT_ID = "REMAC-S3-Bridge"
TOPIC_SUBSCRIBE = "remac/+/data"  # Subscribes to all nodes (remac/node1/data, etc.)

# Project Paths
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "ml_models"
CERT_DIR = BASE_DIR / "CERTIFICATES" / "Remac-Node-1"

# ============================================================
# INITIALIZE ML MODELS
# ============================================================
print("🤖 Loading ML Models...")
try:
    isolation_model = joblib.load(MODEL_DIR / "isolation_forest_model.pkl")
    rf_model = joblib.load(MODEL_DIR / "random_forest_model.pkl")
    encoder = joblib.load(MODEL_DIR / "status_encoder.pkl")
    print("✅ Models loaded successfully!")
except Exception as e:
    print(f"❌ Failed to load ML models: {e}")
    exit(1)

# ============================================================
# INITIALIZE S3 CLIENT
# ============================================================
s3_client = None
if HAS_BOTO3:
    try:
        if AWS_ACCESS_KEY and AWS_SECRET_KEY:
            s3_client = boto3.client(
                's3',
                region_name=AWS_REGION,
                aws_access_key_id=AWS_ACCESS_KEY,
                aws_secret_access_key=AWS_SECRET_KEY
            )
        else:
            # Fallback to default credentials chain (env vars, ~/.aws/credentials, or IAM)
            s3_client = boto3.client('s3', region_name=AWS_REGION)
        print("✅ AWS S3 Client initialized successfully!")
    except Exception as e:
        print(f"⚠️ S3 Initialization failed: {e}. Check credentials.")
else:
    print("❌ 'boto3' library not found! Install it using 'pip install boto3'")

# Local running cache for history compilation
history_cache = {}

# ============================================================
# PROCESS & UPLOAD TELEMETRY TO S3
# ============================================================
def process_and_upload(raw_data, unit_id):
    """
    Takes raw hardware payload, runs scikit-learn models,
    compiles history, and uploads JSON artifacts to S3.
    """
    if not s3_client:
        print("❌ S3 client not ready. Skipping upload.")
        return

    try:
        # 1. Parse raw measurements
        temp = float(raw_data.get("Temperature_C", raw_data.get("temperature", 0.0)))
        humid = float(raw_data.get("Humidity_%", raw_data.get("humidity", 0.0)))
        distance = float(raw_data.get("Distance_cm", raw_data.get("distance", 0.0)))
        level = float(raw_data.get("Material_Level_%", raw_data.get("material_level", 0.0)))
        device = raw_data.get("Device_ID", raw_data.get("device", f"REMAC_UNIT_{unit_id}"))
        
        # 2. Run Edge ML Inference
        features = [[temp, humid, distance, level]]
        iso_pred = isolation_model.predict(features)[0]
        iso_result = "NORMAL" if iso_pred == 1 else "ANOMALY"
        
        rf_pred = rf_model.predict(features)[0]
        rf_result = encoder.inverse_transform([rf_pred])[0]
        
        # 3. Compute Risk Thresholds
        temp_risk = round((temp / 40.0) * 100, 2)
        humid_risk = round((humid / 60.0) * 100, 2)
        
        # 4. Formulate Enriched Dashboard Payload
        enriched_payload = {
            "device": device,
            "timestamp": time.strftime("%H:%M:%S"),
            "temperature": temp,
            "humidity": humid,
            "distance": distance,
            "material_level": level,
            "status": rf_result,
            "active_alert": "None" if rf_result == "SAFE" else f"Triggered by Sensor Flags",
            "random_forest": rf_result,
            "isolation_forest": iso_result,
            "temperature_risk": temp_risk,
            "humidity_risk": humid_risk
        }
        
        # 5. Upload latest reading to S3
        latest_key = f"latest_{unit_id}.json"
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=latest_key,
            Body=json.dumps(enriched_payload, indent=4),
            ContentType='application/json',
            ACL='public-read'  # Enable public access so Vite dashboard can fetch it directly
        )
        print(f"🚀 Uploaded: {latest_key} to S3 bucket '{S3_BUCKET_NAME}'")
        
        # 6. Update historical series in S3
        if unit_id not in history_cache:
            # Try to fetch existing history from S3 first to preserve data
            try:
                hist_obj = s3_client.get_object(Bucket=S3_BUCKET_NAME, Key=f"history_{unit_id}.json")
                history_cache[unit_id] = json.loads(hist_obj['Body'].read().decode('utf-8'))
            except Exception:
                history_cache[unit_id] = []
                
        # Append new point and keep last 20 readings
        new_point = {
            "Timestamp": enriched_payload["timestamp"],
            "Temperature": temp,
            "Humidity": humid,
            "Distance": distance,
            "Material_Level": level
        }
        history_cache[unit_id].append(new_point)
        history_cache[unit_id] = history_cache[unit_id][-20:]
        
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=f"history_{unit_id}.json",
            Body=json.dumps(history_cache[unit_id], indent=4),
            ContentType='application/json',
            ACL='public-read'
        )
        print(f"📊 Uploaded: history_{unit_id}.json to S3")
        
    except Exception as e:
        print(f"❌ Error compiling/uploading payload: {e}")

# ============================================================
# PATHWAY A: AWS IOT CORE MQTT CONSUMER
# ============================================================
def on_message_received(topic, payload, dup, qos, retain, **kwargs):
    print(f"\n📩 Message received on topic '{topic}'")
    try:
        data = json.loads(payload.decode('utf-8'))
        # Parse Node ID from topic e.g. "remac/node1/data" -> 1
        parts = topic.split('/')
        unit_id = 1
        if len(parts) >= 2:
            num_str = ''.join(filter(str.isdigit, parts[1]))
            if num_str:
                unit_id = int(num_str)
                
        process_and_upload(data, unit_id)
    except Exception as e:
        print(f"Error parsing MQTT JSON: {e}")

def run_mqtt_listener():
    if not HAS_AWS_IOT:
        print("❌ 'awscrt' or 'awsiot' not installed. Cannot run MQTT listener.")
        return
        
    print("☁️ Connecting to AWS IoT Core MQTT Broker...")
    try:
        connection = mqtt_connection_builder.mtls_from_path(
            endpoint=ENDPOINT,
            cert_filepath=str(CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt"),
            pri_key_filepath=str(CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key"),
            ca_filepath=str(CERT_DIR / "AmazonRootCA1.pem"),
            client_id=CLIENT_ID,
            clean_session=False,
            keep_alive_secs=30
        )
        connection.connect().result()
        print("✅ Connected to AWS IoT Core successfully!")
        
        # Subscribe to topic
        subscribe_future, packet_id = connection.subscribe(
            topic=TOPIC_SUBSCRIBE,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_message_received
        )
        subscribe_future.result()
        print(f"📡 Subscribed to topic: {TOPIC_SUBSCRIBE}. Waiting for hardware events...")
        
        while True:
            time.sleep(1)
            
    except Exception as e:
        print(f"❌ MQTT Broker connection failed: {e}")

# ============================================================
# PATHWAY B: POLLING KVDB (FALLBACK GATEWAY)
# ============================================================
def run_kvdb_polling():
    print("📡 Running KVDB Gateway Poller... polling for hardware changes.")
    last_timestamps = {}
    
    while True:
        for unit_id in range(1, 11):
            try:
                res = requests.get(f"https://kvdb.io/4fm9CKFheYEj7fqeaijvJz/latest_{unit_id}", timeout=3)
                if res.ok:
                    data = res.json()
                    ts = data.get("timestamp")
                    
                    # Upload only when a new reading arrives
                    if last_timestamps.get(unit_id) != ts:
                        print(f"\n✨ New reading detected for Unit {unit_id} on KVDB")
                        last_timestamps[unit_id] = ts
                        process_and_upload(data, unit_id)
            except Exception:
                pass
        time.sleep(5)

# ============================================================
# ENTRYPOINT
# ============================================================
if __name__ == "__main__":
    import sys
    mode = "poll"
    if len(sys.argv) > 1:
        mode = sys.argv[1].lower()
        
    print("============================================================")
    print("📡 R.E.M.A.C AWS S3 Data Bridge")
    print("============================================================\n")
    
    if mode == "mqtt" and HAS_AWS_IOT:
        run_mqtt_listener()
    else:
        if mode == "mqtt":
            print("⚠️ Falling back to KVDB polling because AWS IoT dependencies are missing.")
        run_kvdb_polling()
