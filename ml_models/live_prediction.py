import pandas as pd
import joblib
import time
from pathlib import Path

# ==========================================
# Load Models
# ==========================================

isolation_model = joblib.load("ml_models/isolation_forest_model.pkl")
rf_model = joblib.load("ml_models/random_forest_model.pkl")
encoder = joblib.load("ml_models/status_encoder.pkl")

# ==========================================
# Load Dashboard Dataset
# ==========================================

csv_file = Path("datasets") / "dashboard" / "Node3.csv"

data = pd.read_csv(csv_file)

# ==========================================
# Thresholds
# ==========================================

TEMP_THRESHOLD = 40
HUMIDITY_THRESHOLD = 60

print("======================================")
print(" REMAC LIVE PREDICTION STARTED")
print("======================================")

# ==========================================
# Process One Row Every 5 Seconds
# ==========================================

for index, row in data.iterrows():

    features = [[
        row["Temperature_C"],
        row["Humidity_%"],
        row["Distance_cm"],
        row["Material_Level_%"]
    ]]

    # Isolation Forest
    iso_prediction = isolation_model.predict(features)[0]

    if iso_prediction == 1:
        iso_result = "NORMAL"
    else:
        iso_result = "ANOMALY"

    # Random Forest
    rf_prediction = rf_model.predict(features)[0]
    rf_result = encoder.inverse_transform([rf_prediction])[0]

    # Risk Calculations
    temp_risk = max(0, (row["Temperature_C"] / TEMP_THRESHOLD) * 100)
    humidity_risk = max(0, (row["Humidity_%"] / HUMIDITY_THRESHOLD) * 100)

    print("------------------------------------")
    print("Reading :", index + 1)
    print("Temperature :", row["Temperature_C"])
    print("Humidity :", row["Humidity_%"])
    print("Distance :", row["Distance_cm"])
    print("Material Level :", row["Material_Level_%"])
    print("Isolation Forest :", iso_result)
    print("Random Forest :", rf_result)
    print(f"Temperature Risk : {temp_risk:.2f}%")
    print(f"Humidity Risk : {humidity_risk:.2f}%")

    time.sleep(5)

print("\nSimulation Completed.")