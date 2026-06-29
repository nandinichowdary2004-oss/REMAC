import pandas as pd
import time
import json
from pathlib import Path
from openpyxl import Workbook, load_workbook

from awscrt import mqtt
from awsiot import mqtt_connection_builder


# =======================
# AWS CONFIG
# =======================

ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"
CLIENT_ID = "REMAC-Node-1"
TOPIC = "remac/node1/data"

ROOT_CA = "certificates/Remac-Node-1/AmazonRootCA1.pem"
CERT = "certificates/Remac-Node-1/dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt"
KEY = "certificates/Remac-Node-1/dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key"


# =======================
# FILE PATHS
# =======================

csv_file = Path("datasets/Node1.csv")
excel_file = Path("excel_logs/Node1_Output.xlsx")


# =======================
# AWS CONNECT
# =======================

print("Connecting to AWS IoT Core...")

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

print("Connected to AWS IoT Core")


# =======================
# LOAD CSV
# =======================

df = pd.read_csv(csv_file)


# =======================
# SETUP EXCEL
# =======================

if excel_file.exists():
    wb = load_workbook(excel_file)
    ws = wb.active
else:
    wb = Workbook()
    ws = wb.active
    ws.title = "Node1 Data"
    ws.append(list(df.columns))  # headers


# =======================
# MAIN LOOP
# =======================

for index, row in df.iterrows():

    data = row.to_dict()

    # 1. Write to Excel
    ws.append(list(data.values()))
    wb.save(excel_file)

    # 2. Convert to JSON & Update latest.json for Dashboard
    dashboard_payload = {
        "device": data.get("Device_ID"),
        "timestamp": str(data.get("Timestamp")),
        "temperature": float(data.get("Temperature_C", 0.0)),
        "humidity": float(data.get("Humidity_%", 0.0)),
        "distance": float(data.get("Distance_cm", 0.0)),
        "material_level": float(data.get("Material_Level_%", 0.0)),
        "status": data.get("Status", "SAFE"),
        "active_alert": data.get("Active_Alerts"),
        "random_forest": data.get("Status", "SAFE"),
        "isolation_forest": "NORMAL" if data.get("Status") == "SAFE" else "ANOMALY",
        "temperature_risk": round((float(data.get("Temperature_C", 0.0)) / 40.0) * 100, 2),
        "humidity_risk": round((float(data.get("Humidity_%", 0.0)) / 60.0) * 100, 2)
    }

    live_data_dir = Path("live_data")
    live_data_dir.mkdir(exist_ok=True)
    for attempt in range(5):
        try:
            with open(live_data_dir / "latest.json", "w") as file:
                json.dump(dashboard_payload, file, indent=4)
            break
        except PermissionError:
            time.sleep(0.1)

    payload = json.dumps(data)

    # 3. Publish to AWS
    mqtt_connection.publish(
        topic=TOPIC,
        payload=payload,
        qos=mqtt.QoS.AT_LEAST_ONCE
    )

    print(f"Published Row {index + 1}")

    # 4. Wait 5 seconds
    time.sleep(5)


# =======================
# DISCONNECT
# =======================

mqtt_connection.disconnect().result()

print("Simulation Completed")