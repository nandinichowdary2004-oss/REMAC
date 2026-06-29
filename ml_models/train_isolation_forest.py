import pandas as pd
import joblib
from pathlib import Path
from sklearn.ensemble import IsolationForest

# Folder containing all training CSV files
training_folder = Path("datasets/training")

# Find every CSV in the folder
csv_files = list(training_folder.glob("*.csv"))

if not csv_files:
    raise FileNotFoundError("No CSV files found in datasets/training")

# Read and combine all CSV files
all_data = []

for file in csv_files:
    print(f"Loading {file.name}")
    df = pd.read_csv(file)
    all_data.append(df)

combined_data = pd.concat(all_data, ignore_index=True)

print(f"Total rows loaded: {len(combined_data)}")

# Select numerical sensor columns
X = combined_data[
    [
        "Temperature_C",
        "Humidity_%",
        "Distance_cm",
        "Material_Level_%"
    ]
]

# Create Isolation Forest model
model = IsolationForest(
    n_estimators=100,
    contamination=0.05,
    random_state=42
)

print("Training model...")

model.fit(X)

# Save model
joblib.dump(
    model,
    "ml_models/isolation_forest_model.pkl"
)

print("Isolation Forest trained successfully.")