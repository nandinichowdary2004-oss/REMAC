import json
from pathlib import Path
import time
import math
import requests
import threading

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
LIVE_DATA_DIR = BASE_DIR / "live_data"
LIVE_DATA_DIR.mkdir(exist_ok=True)

# ============================================================
# AWS IOT CONFIGURATION (OPTIONAL)
# ============================================================
try:
    from awscrt import mqtt
    from awsiot import mqtt_connection_builder
    HAS_AWS = True
except ImportError:
    HAS_AWS = False

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
# GLOBAL SIMULATION STATE & WORKER THREAD
# ============================================================
if not hasattr(st, "_sim_state"):
    st._sim_state = {
        "running": False,
        "thread": None,
        "status_text": "Stopped",
        "current_index": 0
    }

def clean_nan(val):
    if isinstance(val, dict):
        return {k: clean_nan(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_nan(x) for x in val]
    elif isinstance(val, float) and math.isnan(val):
        return None
    return val

def simulation_worker():
    import joblib
    
    st._sim_state["status_text"] = "Initializing models & data..."
    
    # Load ML Models
    try:
        isolation_model = joblib.load(BASE_DIR / "ml_models" / "isolation_forest_model.pkl")
        rf_model = joblib.load(BASE_DIR / "ml_models" / "random_forest_model.pkl")
        encoder = joblib.load(BASE_DIR / "ml_models" / "status_encoder.pkl")
    except Exception as e:
        st._sim_state["status_text"] = f"Failed to load ML models: {e}"
        st._sim_state["running"] = False
        return
        
    # Load training data
    try:
        training_files = ["Node1_001.csv", "Node1_002.csv", "Node1_003.csv", "Node2.csv"]
        all_data = []
        for file in training_files:
            file_path = BASE_DIR / "datasets" / "training" / file
            if file_path.exists():
                all_data.append(pd.read_csv(file_path))
        if not all_data:
            raise FileNotFoundError("No training CSV files found.")
        combined_data = pd.concat(all_data, ignore_index=True)
    except Exception as e:
        st._sim_state["status_text"] = f"Failed to load training data: {e}"
        st._sim_state["running"] = False
        return
        
    # AWS IoT Setup (Optional)
    mqtt_connection = None
    if HAS_AWS:
        try:
            st._sim_state["status_text"] = "Connecting to AWS IoT..."
            ENDPOINT = "a1kneu9xpfe402-ats.iot.eu-north-1.amazonaws.com"
            CLIENT_ID = "Remac-Node-1-Cloud"
            CERT_DIR = BASE_DIR / "CERTIFICATES" / "Remac-Node-1"
            
            mqtt_connection = mqtt_connection_builder.mtls_from_path(
                endpoint=ENDPOINT,
                cert_filepath=str(CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-certificate.pem.crt"),
                pri_key_filepath=str(CERT_DIR / "dac48685c1e6abf330c38be199ba904aa71eebd042d0d78ec0685dd5e06f8909-private.pem.key"),
                ca_filepath=str(CERT_DIR / "AmazonRootCA1.pem"),
                client_id=CLIENT_ID,
                clean_session=False,
                keep_alive_secs=30
            )
            mqtt_connection.connect().result()
        except Exception:
            mqtt_connection = None
            
    st._sim_state["status_text"] = "Running"
    
    total_rows = len(combined_data)
    while st._sim_state["running"]:
        current_idx = st._sim_state["current_index"]
        
        for unit in STORAGE_UNITS:
            u_id = unit["id"]
            idx = (current_idx + u_id * 100) % total_rows
            row = combined_data.iloc[idx]
            
            # Features
            features = [[
                row["Temperature_C"],
                row["Humidity_%"],
                row["Distance_cm"],
                row["Material_Level_%"]
            ]]
            
            # Predictions
            iso_prediction = isolation_model.predict(features)[0]
            isolation_result = "NORMAL" if iso_prediction == 1 else "ANOMALY"
            
            rf_prediction = rf_model.predict(features)[0]
            rf_result = encoder.inverse_transform([rf_prediction])[0]
            
            # Risks
            temperature_risk = round((row["Temperature_C"] / 40.0) * 100, 2)
            humidity_risk = round((row["Humidity_%"] / 60.0) * 100, 2)
            
            payload = {
                "device": unit["device_id"],
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
            
            # Save locally with retries
            u_live_file = LIVE_DATA_DIR / f"latest_{u_id}.json"
            for attempt in range(5):
                try:
                    with open(u_live_file, "w") as file:
                        json.dump(payload, file, indent=4)
                    break
                except Exception:
                    time.sleep(0.05)
                    
            # POST to Cloud KV
            try:
                requests.post(f"https://kvdb.io/remac_mvp_7bf9bd4f/latest_{u_id}", json=payload, timeout=2)
            except Exception:
                pass
                
            # Publish to AWS
            if mqtt_connection is not None:
                try:
                    mqtt_connection.publish(
                        topic=f"remac/node{u_id}/data",
                        payload=json.dumps(payload),
                        qos=mqtt.QoS.AT_LEAST_ONCE
                    )
                except Exception:
                    pass
                    
            # Update history files
            u_hist_file = LIVE_DATA_DIR / f"history_{u_id}.csv"
            new_row = pd.DataFrame([{
                "Timestamp": payload["timestamp"],
                "Temperature": payload["temperature"],
                "Humidity": payload["humidity"],
                "Distance": payload["distance"],
                "Material_Level": payload["material_level"]
            }])
            
            u_hist = None
            for attempt in range(5):
                try:
                    if u_hist_file.exists():
                        u_hist = pd.read_csv(u_hist_file)
                    else:
                        u_hist = pd.DataFrame(columns=["Timestamp", "Temperature", "Humidity", "Distance", "Material_Level"])
                    break
                except PermissionError:
                    time.sleep(0.05)
                    
            if u_hist is not None:
                if payload["timestamp"] not in u_hist["Timestamp"].values:
                    u_hist = pd.concat([u_hist, new_row], ignore_index=True)
                    u_hist = u_hist.sort_values(by="Timestamp").tail(100)
                    for attempt in range(5):
                        try:
                            u_hist.to_csv(u_hist_file, index=False)
                            break
                        except PermissionError:
                            time.sleep(0.05)
                            
        st._sim_state["current_index"] += 1
        
        # Sleep in small steps to react quickly to shutdown requests
        for _ in range(50):
            if not st._sim_state["running"]:
                break
            time.sleep(0.1)
            
    # Disconnect AWS if connected
    if mqtt_connection is not None:
        try:
            mqtt_connection.disconnect().result()
        except Exception:
            pass
            
    st._sim_state["status_text"] = "Stopped"

def trigger_rerun():
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

# ============================================================
# DATA INITIALIZATION & UTILITIES
# ============================================================
def initialize_fallback_data():
    try:
        training_files = ["Node1_001.csv", "Node1_002.csv", "Node1_003.csv", "Node2.csv"]
        all_data = []
        for file in training_files:
            file_path = BASE_DIR / "datasets" / "training" / file
            if file_path.exists():
                all_data.append(pd.read_csv(file_path))
        if not all_data:
            return
        combined_data = pd.concat(all_data, ignore_index=True)
        total_rows = len(combined_data)
        
        # Try loading ML models, fallback to raw CSV values if fail
        has_models = False
        try:
            import joblib
            isolation_model = joblib.load(BASE_DIR / "ml_models" / "isolation_forest_model.pkl")
            rf_model = joblib.load(BASE_DIR / "ml_models" / "random_forest_model.pkl")
            encoder = joblib.load(BASE_DIR / "ml_models" / "status_encoder.pkl")
            has_models = True
        except Exception:
            pass
            
        for u in STORAGE_UNITS:
            u_id = u["id"]
            u_live_file = LIVE_DATA_DIR / f"latest_{u_id}.json"
            u_hist_file = LIVE_DATA_DIR / f"history_{u_id}.csv"
            
            # 1. Initialize latest file if missing
            if not u_live_file.exists():
                idx = (u_id * 100) % total_rows
                row = combined_data.iloc[idx]
                
                if has_models:
                    features = [[
                        row["Temperature_C"],
                        row["Humidity_%"],
                        row["Distance_cm"],
                        row["Material_Level_%"]
                    ]]
                    iso_prediction = isolation_model.predict(features)[0]
                    isolation_result = "NORMAL" if iso_prediction == 1 else "ANOMALY"
                    
                    rf_prediction = rf_model.predict(features)[0]
                    rf_result = encoder.inverse_transform([rf_prediction])[0]
                else:
                    isolation_result = "NORMAL" if row["Status"] == "SAFE" else "ANOMALY"
                    rf_result = row["Status"]
                    
                temperature_risk = round((row["Temperature_C"] / 40.0) * 100, 2)
                humidity_risk = round((row["Humidity_%"] / 60.0) * 100, 2)
                
                payload = {
                    "device": u["device_id"],
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
                
                with open(u_live_file, "w") as f:
                    json.dump(payload, f, indent=4)
                    
            # 2. Initialize history file if missing
            if not u_hist_file.exists():
                hist_rows = []
                for i in range(15):
                    idx = (u_id * 100 - 15 + i) % total_rows
                    row = combined_data.iloc[idx]
                    hist_rows.append({
                        "Timestamp": str(row["Timestamp"]),
                        "Temperature": float(row["Temperature_C"]),
                        "Humidity": float(row["Humidity_%"]),
                        "Distance": float(row["Distance_cm"]),
                        "Material_Level": float(row["Material_Level_%"])
                    })
                pd.DataFrame(hist_rows).to_csv(u_hist_file, index=False)
    except Exception as e:
        print(f"Error in initialize_fallback_data: {e}")

def get_unit_summary(unit_id):
    u_live_file = LIVE_DATA_DIR / f"latest_{unit_id}.json"
    if u_live_file.exists():
        try:
            with open(u_live_file, "r") as f:
                data = json.load(f)
            return {
                "temp": f"{data.get('temperature', 0.0):.1f}°C",
                "humid": f"{data.get('humidity', 0.0):.1f}%",
                "level": f"{data.get('material_level', 0.0):.1f}%",
                "status": data.get("status", "UNKNOWN")
            }
        except Exception:
            pass
    return {"temp": "--", "humid": "--", "level": "--", "status": "UNKNOWN"}

def update_all_units_states():
    # Calculate global elapsed time for runtime accumulation
    current_time = time.time()
    elapsed = 0
    if "last_time" in st.session_state:
        elapsed = current_time - st.session_state.last_time
    st.session_state.last_time = current_time
    
    for u in STORAGE_UNITS:
        u_id = u["id"]
        # Default state initialization for each unit
        if f"ac_runtime_{u_id}" not in st.session_state:
            st.session_state[f"ac_runtime_{u_id}"] = 0
        if f"dryer_runtime_{u_id}" not in st.session_state:
            st.session_state[f"dryer_runtime_{u_id}"] = 0
        if f"ac_status_{u_id}" not in st.session_state:
            st.session_state[f"ac_status_{u_id}"] = "OFF"
        if f"dryer_status_{u_id}" not in st.session_state:
            st.session_state[f"dryer_status_{u_id}"] = "OFF"
        if f"ac_mode_{u_id}" not in st.session_state:
            st.session_state[f"ac_mode_{u_id}"] = "Auto"
        if f"dryer_mode_{u_id}" not in st.session_state:
            st.session_state[f"dryer_mode_{u_id}"] = "Auto"
        if f"temp_threshold_{u_id}" not in st.session_state:
            st.session_state[f"temp_threshold_{u_id}"] = u.get("default_temp", 40.0)
        if f"humidity_threshold_{u_id}" not in st.session_state:
            st.session_state[f"humidity_threshold_{u_id}"] = u.get("default_humid", 60.0)

        # Runtime accumulation for active environmental systems
        if 0 < elapsed < 15:
            if st.session_state[f"ac_status_{u_id}"] == "ON":
                st.session_state[f"ac_runtime_{u_id}"] += int(elapsed)
            if st.session_state[f"dryer_status_{u_id}"] == "ON":
                st.session_state[f"dryer_runtime_{u_id}"] += int(elapsed)

        # Automatic status updates based on live reading thresholds
        u_live_file = LIVE_DATA_DIR / f"latest_{u_id}.json"
        if u_live_file.exists():
            try:
                with open(u_live_file, "r") as f:
                    u_data = json.load(f)
                u_temp = float(u_data.get("temperature", 0.0))
                u_humid = float(u_data.get("humidity", 0.0))
                
                if st.session_state[f"ac_mode_{u_id}"] == "Auto":
                    if u_temp > st.session_state[f"temp_threshold_{u_id}"]:
                        st.session_state[f"ac_status_{u_id}"] = "ON"
                    else:
                        st.session_state[f"ac_status_{u_id}"] = "OFF"
                        
                if st.session_state[f"dryer_mode_{u_id}"] == "Auto":
                    if u_humid > st.session_state[f"humidity_threshold_{u_id}"]:
                        st.session_state[f"dryer_status_{u_id}"] = "ON"
                    else:
                        st.session_state[f"dryer_status_{u_id}"] = "OFF"
            except Exception:
                pass

# ============================================================
# PAGE CONFIGURATION
# ============================================================
st.set_page_config(
    page_title="REMAC Multi-Storage Monitor",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Subtle flash effect on page refresh (indicator of data feed) and smooth transitions
st.markdown("""
<style>
    /* Subtle flash glow overlay on page refresh */
    @keyframes refresh-flash {
        0% {
            background-color: rgba(255, 255, 255, 0.04);
        }
        100% {
            background-color: rgba(255, 255, 255, 0.0);
        }
    }
    
    .stApp {
        animation: refresh-flash 1.5s ease-out;
    }
    
    /* Smooth transitions for readings, metrics, and charts */
    @keyframes fade-in {
        from {
            opacity: 0.75;
            transform: translateY(3px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .stMetric, .stPlotlyChart, div[data-testid="stMetricValue"], div[data-testid="metric-container"], .element-container {
        animation: fade-in 0.8s cubic-bezier(0.4, 0, 0.2, 1);
    }
</style>
""", unsafe_allow_html=True)

# ============================================================
# LOGIN PAGE
# ============================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<div style='height: 80px;'></div>", unsafe_allow_html=True)
        st.markdown("""
        <div style="background-color: #1e1e2f; padding: 30px; border-radius: 15px; border: 1px solid #3a3a5c; box-shadow: 0px 4px 15px rgba(0,0,0,0.5);">
            <h2 style="text-align: center; color: #4e8cff; margin-bottom: 5px; font-family: sans-serif;">📡 R.E.M.A.C</h2>
            <p style="text-align: center; color: #a0a0c0; font-size: 14px; margin-bottom: 25px; font-family: sans-serif;">Intelligent Raw Material Monitoring System</p>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            st.markdown("<p style='color: #a0a0c0; margin-bottom: 5px; font-family: sans-serif;'>Please enter your credentials to access the dashboard.</p>", unsafe_allow_html=True)
            username = st.text_input("Username", key="login_username", placeholder="Enter username")
            password = st.text_input("Password", type="password", key="login_password", placeholder="Enter password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            
            if submitted:
                if username == "admin" and password == "admin123":
                    st.session_state.logged_in = True
                    st.success("Login successful! Redirecting...")
                    time.sleep(0.5)
                    trigger_rerun()
                else:
                    st.error("Access Denied: Invalid username or password.")
        
        st.markdown("<p style='text-align: center; color: #707090; font-size: 12px; margin-top: 15px; font-family: sans-serif;'>Default credentials: <code>admin</code> / <code>admin123</code></p>", unsafe_allow_html=True)
    st.stop()

# ============================================================
# AUTO REFRESH (Runs after successful login)
# ============================================================
st_autorefresh(
    interval=5000,
    key="dashboard_refresh"
)

# Initialize Selected Storage Unit State
if "selected_storage_unit" not in st.session_state:
    st.session_state.selected_storage_unit = None

# Initialize fallback data and run runtime calculations
initialize_fallback_data()
update_all_units_states()

# ============================================================
# HOMEPAGE LAYOUT
# ============================================================
if st.session_state.selected_storage_unit is None:
    st.title("📡 R.E.M.A.C Intelligent Storage Hub")
    st.caption("Industrial IoT • Machine Learning • Real-Time Multi-Unit Raw Material Monitoring")
    
    st.markdown("### 🏢 Storage Unit Overview")
    st.markdown("Select a solid plastic raw material storage unit below to access its live telemetry, AI analytics, and environmental controls.")
    
    # 5 Columns Row 1 (Units 1-5)
    cols1 = st.columns(5)
    for idx, unit in enumerate(STORAGE_UNITS[:5]):
        with cols1[idx]:
            summary = get_unit_summary(unit["id"])
            status_color = "#2ecc71" if summary["status"] == "SAFE" else "#f1c40f" if summary["status"] == "WARNING" else "#e74c3c" if summary["status"] == "DANGER" else "#7f8c8d"
            
            st.markdown(f"""
            <div style="background-color: #1e1e2f; padding: 15px; border-radius: 12px; border: 1px solid #3a3a5c; text-align: center; margin-bottom: 8px; box-shadow: 0px 4px 10px rgba(0,0,0,0.3); min-height: 190px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 11px; color: #888; font-weight: bold;">UNIT {unit['id']}</span>
                    <span style="font-size: 10px; background-color: {status_color}22; color: {status_color}; padding: 2px 6px; border-radius: 4px; font-weight: bold; border: 1px solid {status_color}55;">{summary['status']}</span>
                </div>
                <h4 style="color: #ffffff; margin: 5px 0; font-size: 15px; font-family: sans-serif; height: 45px; display: flex; align-items: center; justify-content: center; font-weight: 600;">{unit['material']}</h4>
                <div style="display: flex; justify-content: space-around; margin-top: 15px; font-size: 11px; border-top: 1px solid #2e2e4a; padding-top: 10px;">
                    <div>
                        <div style="color: #888; font-size: 9px; font-weight: 600;">TEMP</div>
                        <div style="color: #ff4d4d; font-weight: bold; font-size: 12px;">{summary['temp']}</div>
                    </div>
                    <div>
                        <div style="color: #888; font-size: 9px; font-weight: 600;">HUMID</div>
                        <div style="color: #4da6ff; font-weight: bold; font-size: 12px;">{summary['humid']}</div>
                    </div>
                    <div>
                        <div style="color: #888; font-size: 9px; font-weight: 600;">LEVEL</div>
                        <div style="color: #2ecc71; font-weight: bold; font-size: 12px;">{summary['level']}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Access Unit {unit['id']} 📡", key=f"btn_h_{unit['id']}", use_container_width=True):
                st.session_state.selected_storage_unit = unit["id"]
                st.session_state[f"temp_threshold_{unit['id']}"] = unit["default_temp"]
                st.session_state[f"humidity_threshold_{unit['id']}"] = unit["default_humid"]
                trigger_rerun()
                
    # 5 Columns Row 2 (Units 6-10)
    cols2 = st.columns(5)
    for idx, unit in enumerate(STORAGE_UNITS[5:]):
        with cols2[idx]:
            summary = get_unit_summary(unit["id"])
            status_color = "#2ecc71" if summary["status"] == "SAFE" else "#f1c40f" if summary["status"] == "WARNING" else "#e74c3c" if summary["status"] == "DANGER" else "#7f8c8d"
            
            st.markdown(f"""
            <div style="background-color: #1e1e2f; padding: 15px; border-radius: 12px; border: 1px solid #3a3a5c; text-align: center; margin-bottom: 8px; box-shadow: 0px 4px 10px rgba(0,0,0,0.3); min-height: 190px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 11px; color: #888; font-weight: bold;">UNIT {unit['id']}</span>
                    <span style="font-size: 10px; background-color: {status_color}22; color: {status_color}; padding: 2px 6px; border-radius: 4px; font-weight: bold; border: 1px solid {status_color}55;">{summary['status']}</span>
                </div>
                <h4 style="color: #ffffff; margin: 5px 0; font-size: 15px; font-family: sans-serif; height: 45px; display: flex; align-items: center; justify-content: center; font-weight: 600;">{unit['material']}</h4>
                <div style="display: flex; justify-content: space-around; margin-top: 15px; font-size: 11px; border-top: 1px solid #2e2e4a; padding-top: 10px;">
                    <div>
                        <div style="color: #888; font-size: 9px; font-weight: 600;">TEMP</div>
                        <div style="color: #ff4d4d; font-weight: bold; font-size: 12px;">{summary['temp']}</div>
                    </div>
                    <div>
                        <div style="color: #888; font-size: 9px; font-weight: 600;">HUMID</div>
                        <div style="color: #4da6ff; font-weight: bold; font-size: 12px;">{summary['humid']}</div>
                    </div>
                    <div>
                        <div style="color: #888; font-size: 9px; font-weight: 600;">LEVEL</div>
                        <div style="color: #2ecc71; font-weight: bold; font-size: 12px;">{summary['level']}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"Access Unit {unit['id']} 📡", key=f"btn_h_{unit['id']}", use_container_width=True):
                st.session_state.selected_storage_unit = unit["id"]
                st.session_state[f"temp_threshold_{unit['id']}"] = unit["default_temp"]
                st.session_state[f"humidity_threshold_{unit['id']}"] = unit["default_humid"]
                trigger_rerun()
                
    # Sidebar control (Homepage)
    st.sidebar.title("🛰️ Cloud Simulator")
    st.sidebar.markdown("Run the ML data publisher directly in the cloud.")
    sim_status = st._sim_state["status_text"]
    st.sidebar.metric("Simulator Status", sim_status)
    
    if st._sim_state["running"]:
        if st.sidebar.button("🔴 Stop Simulation", key="stop_sim_btn_home"):
            st._sim_state["running"] = False
            trigger_rerun()
    else:
        if st.sidebar.button("🟢 Start Simulation", key="start_sim_btn_home"):
            st._sim_state["running"] = True
            st._sim_state["status_text"] = "Starting..."
            st._sim_state["thread"] = threading.Thread(target=simulation_worker, daemon=True)
            st._sim_state["thread"].start()
            trigger_rerun()
            
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout 🚪", key="logout_btn_home", use_container_width=True):
        st.session_state.logged_in = False
        trigger_rerun()

# ============================================================
# SPECIFIC UNIT DASHBOARD LAYOUT
# ============================================================
else:
    selected_unit_id = st.session_state.selected_storage_unit
    selected_unit = next(u for u in STORAGE_UNITS if u["id"] == selected_unit_id)
    
    # Left Navigation Panel Sidebar
    st.sidebar.markdown("### 🏠 Navigation")
    if st.sidebar.button("🏠 Back to Homepage", use_container_width=True):
        st.session_state.selected_storage_unit = None
        trigger_rerun()
        
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🏢 Storage Units")
    for unit in STORAGE_UNITS:
        is_selected = (selected_unit_id == unit["id"])
        btn_label = f"🔵 Unit {unit['id']} ({unit['material'].split(' ')[0]})" if is_selected else f"⚪ Unit {unit['id']} ({unit['material'].split(' ')[0]})"
        if st.sidebar.button(btn_label, key=f"sidebar_nav_{unit['id']}", use_container_width=True):
            st.session_state.selected_storage_unit = unit["id"]
            st.session_state[f"temp_threshold_{unit['id']}"] = unit["default_temp"]
            st.session_state[f"humidity_threshold_{unit['id']}"] = unit["default_humid"]
            trigger_rerun()
            
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🛰️ Cloud Simulator")
    sim_status = st._sim_state["status_text"]
    st.sidebar.metric("Simulator Status", sim_status)
    
    if st._sim_state["running"]:
        if st.sidebar.button("🔴 Stop Simulation", key="stop_sim_btn_dash"):
            st._sim_state["running"] = False
            trigger_rerun()
    else:
        if st.sidebar.button("🟢 Start Simulation", key="start_sim_btn_dash"):
            st._sim_state["running"] = True
            st._sim_state["status_text"] = "Starting..."
            st._sim_state["thread"] = threading.Thread(target=simulation_worker, daemon=True)
            st._sim_state["thread"].start()
            trigger_rerun()
            
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout 🚪", key="logout_btn_dash", use_container_width=True):
        st.session_state.logged_in = False
        trigger_rerun()
        
    # Main Dashboard Page Content
    st.title(f"📡 Storage Unit {selected_unit['id']} - {selected_unit['material']}")
    st.caption(f"Industrial IoT • Machine Learning • Real-Time Monitoring • Device: {selected_unit['device_id']}")
    st.markdown("---")
    
    # Load unit specific live data
    LIVE_FILE = LIVE_DATA_DIR / f"latest_{selected_unit_id}.json"
    HISTORY_FILE = LIVE_DATA_DIR / f"history_{selected_unit_id}.csv"
    
    data = None
    try:
        response = requests.get(f"https://kvdb.io/remac_mvp_7bf9bd4f/latest_{selected_unit_id}", timeout=2)
        if response.status_code == 200:
            data = clean_nan(response.json())
    except Exception:
        pass
        
    if data is None:
        for attempt in range(5):
            try:
                with open(LIVE_FILE, "r") as file:
                    raw_data = json.load(file)
                if raw_data and "timestamp" in raw_data:
                    data = clean_nan(raw_data)
                    break
            except (PermissionError, json.JSONDecodeError, KeyError, ValueError):
                time.sleep(0.1)
                
    if data is None:
        try:
            with open(LIVE_FILE, "r") as file:
                data = clean_nan(json.load(file))
        except Exception as e:
            st.error(f"Unable to read latest_{selected_unit_id}.json after multiple attempts.\n\n{e}")
            st.stop()
            
    # History file management
    new_row = pd.DataFrame([{
        "Timestamp": data["timestamp"],
        "Temperature": data["temperature"],
        "Humidity": data["humidity"],
        "Distance": data["distance"],
        "Material_Level": data["material_level"]
    }])
    
    history = None
    for attempt in range(5):
        try:
            if HISTORY_FILE.exists():
                history = pd.read_csv(HISTORY_FILE)
            else:
                history = pd.DataFrame(columns=["Timestamp", "Temperature", "Humidity", "Distance", "Material_Level"])
            break
        except PermissionError:
            time.sleep(0.1)
            
    if history is not None:
        if data["timestamp"] not in history["Timestamp"].values:
            history = pd.concat([history, new_row], ignore_index=True)
        history = history.sort_values(by="Timestamp").tail(100)
        for attempt in range(5):
            try:
                history.to_csv(HISTORY_FILE, index=False)
                break
            except PermissionError:
                time.sleep(0.1)
    else:
        history = new_row
        
    # Alert Banner
    if data["status"] == "SAFE":
        st.success("🟢 System Healthy")
    elif data["status"] == "WARNING":
        st.warning("🟡 Warning Condition")
    else:
        st.error("🔴 Danger Condition")
        
    # Gauge rendering function
    def create_gauge(title, value, maximum, color):
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=float(value),
                title={"text": title},
                gauge={
                    "axis": {"range": [0, maximum]},
                    "bar": {"color": color},
                    "steps": [
                        {"range": [0, maximum * 0.5], "color": "#E8F5E9"},
                        {"range": [maximum * 0.5, maximum * 0.8], "color": "#FFF3CD"},
                        {"range": [maximum * 0.8, maximum], "color": "#F8D7DA"}
                    ]
                }
            )
        )
        fig.update_layout(
            height=270,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        return fig
        
    # Live Sensor Dashboard Indicators
    st.subheader("📊 Live Sensor Dashboard")
    col1, col2 = st.columns(2)
    with col1:
        fig_temp = create_gauge("🌡 Temperature (°C)", data["temperature"], 50, "red")
        st.plotly_chart(fig_temp, use_container_width=True, key=f"temp_gauge_{selected_unit_id}")
    with col2:
        fig_humidity = create_gauge("💧 Humidity (%)", data["humidity"], 100, "blue")
        st.plotly_chart(fig_humidity, use_container_width=True, key=f"humidity_gauge_{selected_unit_id}")
        
    col3, col4 = st.columns(2)
    with col3:
        fig_material = create_gauge("📦 Material Level (%)", data["material_level"], 100, "green")
        st.plotly_chart(fig_material, use_container_width=True, key=f"material_gauge_{selected_unit_id}")
    with col4:
        fig_distance = create_gauge("📏 Distance (cm)", data["distance"], 30, "orange")
        st.plotly_chart(fig_distance, use_container_width=True, key=f"distance_gauge_{selected_unit_id}")
        
    st.markdown("---")
    
    # AI Predictions
    st.subheader("🤖 AI Prediction Engine")
    col_rf, col_iso = st.columns(2)
    with col_rf:
        st.markdown("### 🌲 Random Forest")
        rf = data["random_forest"]
        if rf == "SAFE":
            st.success(f"Prediction : {rf}")
        elif rf == "WARNING":
            st.warning(f"Prediction : {rf}")
        else:
            st.error(f"Prediction : {rf}")
            
    with col_iso:
        st.markdown("### 🔍 Isolation Forest")
        iso = data["isolation_forest"]
        if iso == "NORMAL":
            st.success(f"Result : {iso}")
        else:
            st.error(f"Result : {iso}")
            
    st.markdown("---")
    
    # Risk Indicators
    st.subheader("⚠ Risk Indicators")
    left, right = st.columns(2)
    with left:
        temp_risk = float(data["temperature_risk"])
        st.metric("Temperature Risk", f"{temp_risk:.1f}%")
        st.progress(min(int(temp_risk), 100))
    with right:
        humidity_risk = float(data["humidity_risk"])
        st.metric("Humidity Risk", f"{humidity_risk:.1f}%")
        st.progress(min(int(humidity_risk), 100))
        
    st.markdown("---")
    
    # Automatic Environmental Control
    st.subheader("❄️ Automatic Environmental Control")
    current_temp = float(data["temperature"])
    current_humidity = float(data["humidity"])
    
    # Display notification banner inside environmental controls
    if st.session_state[f"ac_mode_{selected_unit_id}"] == "Auto" and current_temp > st.session_state[f"temp_threshold_{selected_unit_id}"]:
        st.warning("⚠️ **Notification:** AC Activated - High Temperature Detected ({:.1f}°C > {:.1f}°C)".format(current_temp, st.session_state[f"temp_threshold_{selected_unit_id}"]))
    if st.session_state[f"dryer_mode_{selected_unit_id}"] == "Auto" and current_humidity > st.session_state[f"humidity_threshold_{selected_unit_id}"]:
        st.warning("⚠️ **Notification:** Dryer Activated - High Humidity Detected ({:.1f}% > {:.1f}%)".format(current_humidity, st.session_state[f"humidity_threshold_{selected_unit_id}"]))
        
    col_ctrl, col_ac, col_dry = st.columns(3)
    
    with col_ctrl:
        st.markdown("#### 🎛️ Threshold Configuration")
        temp_thresh = st.slider("AC Temp Threshold (°C)", min_value=15.0, max_value=50.0, value=st.session_state[f"temp_threshold_{selected_unit_id}"], step=0.5, key=f"temp_thresh_slider_{selected_unit_id}")
        humid_thresh = st.slider("Dryer Humidity Threshold (%)", min_value=20.0, max_value=90.0, value=st.session_state[f"humidity_threshold_{selected_unit_id}"], step=1.0, key=f"humid_thresh_slider_{selected_unit_id}")
        
        st.session_state[f"temp_threshold_{selected_unit_id}"] = temp_thresh
        st.session_state[f"humidity_threshold_{selected_unit_id}"] = humid_thresh
        
        st.markdown("---")
        st.markdown("**Cloud Rule Engine Commands**")
        ac_flow = f"⚡ `Cloud AI/Rule Engine` ➔ `[CMD: TURN_ON]` ➔ `AC Device`" if st.session_state[f"ac_status_{selected_unit_id}"] == "ON" else f"💤 `Cloud AI/Rule Engine` ➔ `[CMD: TURN_OFF]` ➔ `AC Device`"
        dryer_flow = f"⚡ `Cloud AI/Rule Engine` ➔ `[CMD: TURN_ON]` ➔ `Dryer Device`" if st.session_state[f"dryer_status_{selected_unit_id}"] == "ON" else f"💤 `Cloud AI/Rule Engine` ➔ `[CMD: TURN_OFF]` ➔ `Dryer Device`"
        st.markdown(ac_flow)
        st.markdown(dryer_flow)
        
    with col_ac:
        st.markdown("#### ❄️ Air Conditioner (AC)")
        ac_mode = st.radio("AC Mode Select", ["Auto", "Manual"], index=0 if st.session_state[f"ac_mode_{selected_unit_id}"] == "Auto" else 1, key=f"ac_mode_radio_btn_{selected_unit_id}")
        st.session_state[f"ac_mode_{selected_unit_id}"] = ac_mode
        
        if ac_mode == "Auto":
            if current_temp > st.session_state[f"temp_threshold_{selected_unit_id}"]:
                st.session_state[f"ac_status_{selected_unit_id}"] = "ON"
            else:
                st.session_state[f"ac_status_{selected_unit_id}"] = "OFF"
        else:
            ac_manual = st.checkbox("Turn AC ON (Manual)", value=(st.session_state[f"ac_status_{selected_unit_id}"] == "ON"), key=f"ac_manual_check_box_{selected_unit_id}")
            st.session_state[f"ac_status_{selected_unit_id}"] = "ON" if ac_manual else "OFF"
            
        status_indicator = "🟢 ON" if st.session_state[f"ac_status_{selected_unit_id}"] == "ON" else "🔴 OFF"
        st.markdown(f"**Status:** {status_indicator}")
        
        runtime_m, runtime_s = divmod(st.session_state[f"ac_runtime_{selected_unit_id}"], 60)
        runtime_h, runtime_m = divmod(runtime_m, 60)
        st.markdown(f"⏱️ **Runtime:** {runtime_h:02d}h:{runtime_m:02d}m:{runtime_s:02d}s")
        
    with col_dry:
        st.markdown("#### 💧 Dryer / Dehumidifier")
        dryer_mode = st.radio("Dryer Mode Select", ["Auto", "Manual"], index=0 if st.session_state[f"dryer_mode_{selected_unit_id}"] == "Auto" else 1, key=f"dryer_mode_radio_btn_{selected_unit_id}")
        st.session_state[f"dryer_mode_{selected_unit_id}"] = dryer_mode
        
        if dryer_mode == "Auto":
            if current_humidity > st.session_state[f"humidity_threshold_{selected_unit_id}"]:
                st.session_state[f"dryer_status_{selected_unit_id}"] = "ON"
            else:
                st.session_state[f"dryer_status_{selected_unit_id}"] = "OFF"
        else:
            dryer_manual = st.checkbox("Turn Dryer ON (Manual)", value=(st.session_state[f"dryer_status_{selected_unit_id}"] == "ON"), key=f"dryer_manual_check_box_{selected_unit_id}")
            st.session_state[f"dryer_status_{selected_unit_id}"] = "ON" if dryer_manual else "OFF"
            
        status_indicator = "🟢 ON" if st.session_state[f"dryer_status_{selected_unit_id}"] == "ON" else "🔴 OFF"
        st.markdown(f"**Status:** {status_indicator}")
        
        runtime_m, runtime_s = divmod(st.session_state[f"dryer_runtime_{selected_unit_id}"], 60)
        runtime_h, runtime_m = divmod(runtime_m, 60)
        st.markdown(f"⏱️ **Runtime:** {runtime_h:02d}h:{runtime_m:02d}m:{runtime_s:02d}s")
        
    st.markdown("---")
    
    # Device Information
    st.subheader("🛰 Device Information")
    c1, c2 = st.columns(2)
    with c1:
        st.write(f"**Device ID :** {data['device']}")
        st.write(f"**Timestamp :** {data['timestamp']}")
    with c2:
        st.write(f"**Status :** {data['status']}")
        st.write(f"**Active Alert :** {data['active_alert']}")
        
    st.markdown("---")
    
    # Live Trend Charts
    st.subheader("📈 Live Trends")
    tab1, tab2, tab3, tab4 = st.tabs([
        "🌡 Temperature",
        "💧 Humidity",
        "📦 Material Level",
        "📏 Distance"
    ])
    
    with tab1:
        temp_fig = go.Figure()
        temp_fig.add_trace(go.Scatter(x=history["Timestamp"], y=history["Temperature"], mode="lines+markers", name="Temperature"))
        temp_fig.update_layout(title="Temperature Trend", xaxis_title="Time", yaxis_title="°C", height=350)
        st.plotly_chart(temp_fig, use_container_width=True, key=f"temperature_trend_chart_{selected_unit_id}")
        
    with tab2:
        humidity_fig = go.Figure()
        humidity_fig.add_trace(go.Scatter(x=history["Timestamp"], y=history["Humidity"], mode="lines+markers", name="Humidity"))
        humidity_fig.update_layout(title="Humidity Trend", xaxis_title="Time", yaxis_title="%", height=350)
        st.plotly_chart(humidity_fig, use_container_width=True, key=f"humidity_trend_chart_{selected_unit_id}")
        
    with tab3:
        material_fig = go.Figure()
        material_fig.add_trace(go.Scatter(x=history["Timestamp"], y=history["Material_Level"], mode="lines+markers", name="Material Level"))
        material_fig.update_layout(title="Material Level Trend", xaxis_title="Time", yaxis_title="%", height=350)
        st.plotly_chart(material_fig, use_container_width=True, key=f"material_trend_chart_{selected_unit_id}")
        
    with tab4:
        distance_fig = go.Figure()
        distance_fig.add_trace(go.Scatter(x=history["Timestamp"], y=history["Distance"], mode="lines+markers", name="Distance"))
        distance_fig.update_layout(title="Distance Trend", xaxis_title="Time", yaxis_title="cm", height=350)
        st.plotly_chart(distance_fig, use_container_width=True, key=f"distance_trend_chart_{selected_unit_id}")
        
    st.markdown("---")
    
    # System Health
    st.subheader("🖥 System Health")
    h1, h2, h3 = st.columns(3)
    with h1:
        st.success("☁ AWS IoT Core")
        st.caption("Connected")
    with h2:
        st.success("🤖 Machine Learning")
        st.caption("Running")
    with h3:
        st.success("📡 Dashboard")
        st.caption("Online")
        
    st.markdown("---")
    st.caption("REMAC Intelligent Raw Material Storage Monitoring System")
    st.caption("Powered by Python • Streamlit • AWS IoT Core • Random Forest • Isolation Forest")
    st.caption("Version 1.0 | Academic MVP Demonstration")
