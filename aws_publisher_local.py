import os
import json
from awscrt import mqtt
from awsiot import mqtt_connection_builder

ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"
CLIENT_ID = "Remac-Node-1"
TOPIC = "remac/node1/data"

# Paths to your certificates inside the repository CERTIFICATES/ directory
PATH_TO_ROOT = os.path.join("CERTIFICATES", "Remac-Node-1", "AmazonRootCA1.pem")
PATH_TO_CERT = os.path.join("CERTIFICATES", "Remac-Node-1", "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt")
PATH_TO_KEY = os.path.join("CERTIFICATES", "Remac-Node-1", "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key")

mqtt_connection = mqtt_connection_builder.mtls_from_path(
    endpoint=ENDPOINT,
    cert_filepath=PATH_TO_CERT,
    pri_key_filepath=PATH_TO_KEY,
    ca_filepath=PATH_TO_ROOT,
    client_id=CLIENT_ID,
    clean_session=False,
    keep_alive_secs=30,
)

print("Connecting to AWS IoT Core...")
connect_future = mqtt_connection.connect()
connect_future.result()
print("Connected Successfully!")

# Publish a mock data point
payload = {
    "device_id": "REMAC_PET_001",
    "temperature": 28.5,
    "humidity": 60.0,
    "proximity": 15.0,
    "material_level": 75.0,
    "status": "SAFE",
    "active_alerts": "None"
}

print(f"Publishing to topic '{TOPIC}': {payload}")
mqtt_connection.publish(
    topic=TOPIC,
    payload=json.dumps(payload),
    qos=mqtt.QoS.AT_LEAST_ONCE
)
print("Message Published!")

mqtt_connection.disconnect().result()
print("Disconnected.")
