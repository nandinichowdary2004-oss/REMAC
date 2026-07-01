import json
import time
import requests
from pathlib import Path

import joblib
import pandas as pd

from awscrt import mqtt
from awsiot import mqtt_connection_builder

# =====================================================
# PROJECT PATHS
# =====================================================

BASE_DIR = Path(__file__).resolve().parent.parent

MODEL_DIR = BASE_DIR / "ml_models"
DATASET_DIR = BASE_DIR / "datasets" / "training"
CERT_DIR = BASE_DIR / "CERTIFICATES" / "Remac-Node-1"
LIVE_DATA_DIR = BASE_DIR / "live_data"

LIVE_DATA_DIR.mkdir(exist_ok=True)

# =====================================================
# LOAD ML MODELS
# =====================================================

print("Loading ML Models...")

isolation_model = joblib.load(MODEL_DIR / "isolation_forest_model.pkl")
rf_model = joblib.load(MODEL_DIR / "random_forest_model.pkl")
encoder = joblib.load(MODEL_DIR / "status_encoder.pkl")

print("Models Loaded Successfully.\n")

# =====================================================
# LOAD TRAINING DATA
# =====================================================

training_files = [
    "Node1_001.csv",
    "Node1_002.csv",
    "Node1_003.csv",
    "Node2.csv"
]

all_data = []

for file in training_files:

    print("Loading :", file)

    file_path = DATASET_DIR / file

    if not file_path.exists():
        raise FileNotFoundError(f"Cannot find {file_path}")

    df = pd.read_csv(file_path)

    all_data.append(df)

combined_data = pd.concat(
    all_data,
    ignore_index=True
)

print(f"\nTotal Rows : {len(combined_data)}\n")

# =====================================================
# AWS IoT CONFIGURATION
# =====================================================

ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"

CLIENT_ID = "Remac-Node-1"

TOPIC = "remac/node1/data"

PATH_TO_CERTIFICATE = str(
    CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt"
)

PATH_TO_PRIVATE_KEY = str(
    CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key"
)

PATH_TO_ROOT = str(
    CERT_DIR / "AmazonRootCA1.pem"
)

print("Connecting to AWS IoT Core...")

mqtt_connection = mqtt_connection_builder.mtls_from_path(

    endpoint=ENDPOINT, 

    cert_filepath=PATH_TO_CERTIFICATE,

    pri_key_filepath=PATH_TO_PRIVATE_KEY,

    ca_filepath=PATH_TO_ROOT,

    client_id=CLIENT_ID,

    clean_session=False,

    keep_alive_secs=30

)

mqtt_connection.connect().result()

print("Connected Successfully!\n")

# =====================================================
# LOOP THROUGH DATA
# =====================================================

for index, row in combined_data.iterrows():

    features = [[
        row["Temperature_C"],
        row["Humidity_%"],
        row["Distance_cm"],
        row["Material_Level_%"]
    ]]

    # ----------------------------
    # Isolation Forest
    # ----------------------------

    iso_prediction = isolation_model.predict(features)[0]

    if iso_prediction == 1:
        isolation_result = "NORMAL"
    else:
        isolation_result = "ANOMALY"

    # ----------------------------
    # Random Forest
    # ----------------------------

    rf_prediction = rf_model.predict(features)[0]

    rf_result = encoder.inverse_transform([rf_prediction])[0]

    # ----------------------------
    # Risk Calculation
    # ----------------------------

    temperature_risk = round(
        (row["Temperature_C"] / 40) * 100,
        2
    )

    humidity_risk = round(
        (row["Humidity_%"] / 60) * 100,
        2
    )

    # ----------------------------
    # Payload
    # ----------------------------

    payload = {

        "device": row["Device_ID"],

        "timestamp": str(row["Timestamp"]),

        "temperature": float(row["Temperature_C"]),

        "humidity": float(row["Humidity_%"]),

        "distance": float(row["Distance_cm"]),

        "material_level": float(row["Material_Level_%"]),

        "status": row["Status"],

        "active_alert": row["Active_Alerts"],

        "random_forest": rf_result,

        "isolation_forest": isolation_result,

        "temperature_risk": temperature_risk,

        "humidity_risk": humidity_risk

    }

    # ----------------------------
    # Save latest reading (with retries for Windows file lock robustness)
    # ----------------------------

    for filename in ["latest.json", "latest_1.json"]:
        for attempt in range(5):
            try:
                with open(LIVE_DATA_DIR / filename, "w") as file:
                    json.dump(payload, file, indent=4)
                break
            except PermissionError:
                time.sleep(0.1)

    # Sync to Cloud KV store for Render hosting compatibility
    for endpoint_suffix in ["latest", "latest_1"]:
        try:
            requests.post(f"https://kvdb.io/remac_mvp_7bf9bd4f/{endpoint_suffix}", json=payload, timeout=2)
        except Exception:
            pass

    # ----------------------------
    # Publish to AWS
    # ----------------------------

    mqtt_connection.publish(

        topic=TOPIC,

        payload=json.dumps(payload),

        qos=mqtt.QoS.AT_LEAST_ONCE

    )

    print(payload)

    time.sleep(5)

# =====================================================
# DISCONNECT
# =====================================================

print("\nFinished Publishing.")

mqtt_connection.disconnect().result()

print("Disconnected Successfully.")