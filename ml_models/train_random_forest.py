import pandas as pd
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import LabelEncoder
import joblib

training_folder = Path("datasets") / "training"

training_files = [
    "Node1_001.csv",
    "Node1_002.csv",
    "Node1_003.csv",
    "Node2.csv"
]

all_data = []

for file in training_files:
    file_path = training_folder / file

    print(file_path)

    df = pd.read_csv(file_path)

    all_data.append(df)

combined_data = pd.concat(all_data, ignore_index=True)

X = combined_data[
    [
        "Temperature_C",
        "Humidity_%",
        "Distance_cm",
        "Material_Level_%"
    ]
]

y = combined_data["Status"]

encoder = LabelEncoder()
y = encoder.fit_transform(y)

model = RandomForestClassifier(
    n_estimators=200,
    random_state=42
)

model.fit(X, y)

joblib.dump(model, "ml_models/random_forest_model.pkl")
joblib.dump(encoder, "ml_models/status_encoder.pkl")

print("Random Forest Trained Successfully")