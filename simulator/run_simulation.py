import time
import json
import math
import requests
from pathlib import Path
import pandas as pd
import joblib

# ============================================================
# PROJECT PATHS
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = BASE_DIR / "ml_models"
DATA_DIR = BASE_DIR / "datasets" / "training"

# ============================================================
# STORAGE UNITS CONFIGURATION
# ============================================================
STORAGE_UNITS = [
    {"id": 1, "name": "Storage Unit 1", "material": "PET (Polyethylene Terephthalate)", "device_id": "REMAC_PET_001", "default_temp": 35.0, "default_humid": 40.0},
    {"id": 2, "name": "Storage Unit 2", "material": "HDPE (High-Density Polyethylene)", "device_id": "REMAC_HDPE_002", "default_temp": 40.0, "default_humid": 65.0},
    {"id": 3, "name": "Storage Unit 3", "material": "PVC (Polyvinyl Chloride)", "device_id": "REMAC_PVC_003", "default_temp": 30.0, "default_humid": 50.0},
    {"id": 4, "name": "Storage Unit 4", "material": "LDPE (Low-Density Polyethylene)", "device_id": "REMAC_LDPE_004", "default_temp": 35.0, "default_humid": 65.0},
    {"id": 5, "name": "Storage Unit 5", "material": "PP (Polypropylene)", "device_id": "REMAC_PP_005", "default_temp": 40.0, "default_humid": 65.0},
    {"id": 6, "name": "Storage Unit 6", "material": "PS (Polystyrene)", "device_id": "REMAC_PS_006", "default_temp": 35.0, "default_humid": 55.0},
    {"id": 7, "name": "Storage Unit 7", "material": "ABS (Acrylonitrile Butadiene Styrene)", "device_id": "REMAC_ABS_007", "default_temp": 35.0, "default_humid": 50.0},
    {"id": 8, "name": "Storage Unit 8", "material": "PC (Polycarbonate)", "device_id": "REMAC_PC_008", "default_temp": 35.0, "default_humid": 45.0},
    {"id": 9, "name": "Storage Unit 9", "material": "PMMA (Acrylic)", "device_id": "REMAC_PMMA_009", "default_temp": 30.0, "default_humid": 50.0},
    {"id": 10, "name": "Storage Unit 10", "material": "Nylon (Polyamide)", "device_id": "REMAC_NYLON_010", "default_temp": 30.0, "default_humid": 35.0},
]

# ============================================================
# AWS IOT CONNECT (OPTIONAL)
# ============================================================
try:
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder
    HAS_AWS = True
except ImportError:
    HAS_AWS = False

def clean_nan(val):
    if isinstance(val, dict):
        return {k: clean_nan(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_nan(x) for x in val]
    elif isinstance(val, float) and math.isnan(val):
        return None
    return val

def run_simulator():
    print("============================================================")
    print("📡 R.E.M.A.C Standalone Cloud-Sync Simulator")
    print("============================================================\n")

    # 1. Load ML Models
    print("🤖 Loading ML models...")
    try:
        isolation_model = joblib.load(MODEL_DIR / "isolation_forest_model.pkl")
        rf_model = joblib.load(MODEL_DIR / "random_forest_model.pkl")
        encoder = joblib.load(MODEL_DIR / "status_encoder.pkl")
        print("✅ Models loaded successfully!")
    except Exception as e:
        print(f"❌ Failed to load ML models: {e}")
        return

    # 2. Load Training Data
    print("📊 Loading training datasets...")
    try:
        csv_files = list(DATA_DIR.glob("*.csv"))
        all_data = []
        for fp in csv_files:
            all_data.append(pd.read_csv(fp))
        if not all_data:
            raise FileNotFoundError("No CSV files found in datasets/training")
        combined_data = pd.concat(all_data, ignore_index=True)
        total_rows = len(combined_data)
        print(f"✅ Loaded {total_rows} rows from {len(csv_files)} datasets.")
    except Exception as e:
        print(f"❌ Failed to load datasets: {e}")
        return

    # 3. AWS Setup
    mqtt_connections = {}
    if HAS_AWS:
        print("☁️ Setting up AWS IoT connections...")
        CERT_DIR = BASE_DIR / "CERTIFICATES" / "Remac-Node-1"
        ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"
        
        # Connect Node 1 AWS MQTT connection as proof of concept
        try:
            conn = mqtt_connection_builder.mtls_from_path(
                endpoint=ENDPOINT,
                cert_filepath=str(CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt"),
                pri_key_filepath=str(CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key"),
                ca_filepath=str(CERT_DIR / "AmazonRootCA1.pem"),
                client_id="Remac-Node-1-Simulator",
                clean_session=False,
                keep_alive_secs=30
            )
            conn.connect().result()
            mqtt_connections[1] = conn
            print("✅ AWS IoT Core Node 1 Connected!")
        except Exception as e:
            print(f"⚠️ AWS Connection skipped: {e}")
    else:
        print("ℹ️ AWS IoT SDK not installed, skipping AWS publication.")

    # 4. History Tracking for kvdb.io Sync
    history_tracks = {u["id"]: [] for u in STORAGE_UNITS}

    print("\n🟢 Simulation Started! Pushing telemetry to Cloud KV (kvdb.io) every 5 seconds...")
    print("Press Ctrl+C to stop.\n")

    current_index = 0
    try:
        while True:
            # Check Cloud Command to see if simulation was stopped
            try:
                cmd_res = requests.get("https://kvdb.io/GXrQha8LsrxhmL2EL7TNGC/sim_command", timeout=2)
                if cmd_res.status_code == 200:
                    cmd_data = cmd_res.json()
                    if not cmd_data.get("running", True):
                        print("⏸️ Simulation paused by cloud command. Standby active...")
                        time.sleep(5)
                        continue
            except Exception:
                pass

            for unit in STORAGE_UNITS:
                u_id = unit["id"]
                idx = (current_index + u_id * 100) % total_rows
                row = combined_data.iloc[idx]

                # Run Predictions
                features = [[
                    float(row["Temperature_C"]),
                    float(row["Humidity_%"]),
                    float(row["Distance_cm"]),
                    float(row["Material_Level_%"])
                ]]
                
                iso_prediction = isolation_model.predict(features)[0]
                isolation_result = "NORMAL" if iso_prediction == 1 else "ANOMALY"

                rf_prediction = rf_model.predict(features)[0]
                rf_result = encoder.inverse_transform([rf_prediction])[0]

                # Risk calculations
                temperature_risk = round((float(row["Temperature_C"]) / 40.0) * 100, 2)
                humidity_risk = round((float(row["Humidity_%"]) / 60.0) * 100, 2)

                payload = {
                    "device": unit["device_id"],
                    "timestamp": str(row["Timestamp"]),
                    "temperature": float(row["Temperature_C"]),
                    "humidity": float(row["Humidity_%"]),
                    "distance": float(row["Distance_cm"]),
                    "material_level": float(row["Material_Level_%"]),
                    "status": str(row["Status"]),
                    "active_alert": str(row["Active_Alerts"]),
                    "random_forest": str(rf_result),
                    "isolation_forest": str(isolation_result),
                    "temperature_risk": float(temperature_risk),
                    "humidity_risk": float(humidity_risk)
                }
                payload = clean_nan(payload)

                # Append to History Track
                h_item = {
                    "Timestamp": payload["timestamp"],
                    "Temperature": payload["temperature"],
                    "Humidity": payload["humidity"],
                    "Distance": payload["distance"],
                    "Material_Level": payload["material_level"]
                }
                history_tracks[u_id].append(h_item)
                if len(history_tracks[u_id]) > 20:
                    history_tracks[u_id].pop(0)

                # POST Latest to Cloud KV
                try:
                    res_lat = requests.post(f"https://kvdb.io/GXrQha8LsrxhmL2EL7TNGC/latest_{u_id}", json=payload, timeout=2)
                    res_hist = requests.post(f"https://kvdb.io/GXrQha8LsrxhmL2EL7TNGC/history_{u_id}", json=history_tracks[u_id], timeout=2)
                except Exception as e:
                    pass

                # Publish to AWS IoT (if connected)
                if u_id in mqtt_connections:
                    try:
                        mqtt_connections[u_id].publish(
                            topic=f"remac/node{u_id}/data",
                            payload=json.dumps(payload),
                            qos=mqtt.QoS.AT_LEAST_ONCE
                        )
                    except Exception:
                        pass

                print(f"[Unit {u_id:02d}] Temp: {payload['temperature']}°C | Humid: {payload['humidity']}% | Level: {payload['material_level']}% | Status: {payload['random_forest']}")

            print(f"--- Cycle {current_index + 1} Completed (Data Synchronized) ---")
            current_index += 1
            time.sleep(5)

    except KeyboardInterrupt:
        print("\n🛑 Simulation stopped by user.")
    finally:
        # Disconnect AWS connections
        for u_id, conn in mqtt_connections.items():
            try:
                conn.disconnect().result()
            except Exception:
                pass
        print("👋 Goodbye!")

if __name__ == "__main__":
    run_simulator()
