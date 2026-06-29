import pandas as pd
import joblib
import time
from pathlib import Path

# --------------------------
# Load trained model
# --------------------------

model = joblib.load("ml_models/isolation_forest_model.pkl")

# --------------------------
# Read dashboard CSV
# --------------------------

csv_file = Path("datasets/dashboard/Node3.csv")

data = pd.read_csv(csv_file)

# --------------------------
# Select sensor columns
# --------------------------

X = data[
    [
        "Temperature_C",
        "Humidity_%",
        "Distance_cm",
        "Material_Level_%"
    ]
]

print("Starting Live Prediction...\n")

# --------------------------
# Predict one row every 5 sec
# --------------------------

for i in range(len(X)):

    sample = X.iloc[[i]]

    prediction = model.predict(sample)[0]

    if prediction == 1:
        result = "NORMAL"

    else:
        result = "ANOMALY"

    print("-----------------------------------")
    print(f"Row : {i+1}")
    print(f"Temperature : {sample.iloc[0]['Temperature_C']} °C")
    print(f"Humidity : {sample.iloc[0]['Humidity_%']} %")
    print(f"Distance : {sample.iloc[0]['Distance_cm']} cm")
    print(f"Material Level : {sample.iloc[0]['Material_Level_%']} %")
    print(f"Isolation Forest : {result}")

    time.sleep(5)

print("\nPrediction Completed.")