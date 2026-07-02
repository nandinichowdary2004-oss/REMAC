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
        training_folder = BASE_DIR / "datasets" / "training"
        csv_files = list(training_folder.glob("*.csv"))
        all_data = []
        for file_path in csv_files:
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
        training_folder = BASE_DIR / "datasets" / "training"
        csv_files = list(training_folder.glob("*.csv"))
        all_data = []
        for file_path in csv_files:
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

# Subtle visual stability style overrides to prevent dimming and flicker on 5-second reruns
st.markdown("""
<style>
    /* Block default Streamlit running/dimming effect during script execution and prevent flickering/blinking of charts/metrics */
    [data-testid="stAppViewContainer"], [data-testid="stSidebar"], div.element-container, .stApp, .stMetric, .stPlotlyChart, [data-testid="stPlotlyChart"] {
        opacity: 1 !important;
        filter: none !important;
        transition: none !important;
        animation: none !important;
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
    def create_gauge(title, value, maximum, color, steps=None):
        if steps is None:
            steps = [
                {"range": [0, maximum * 0.5], "color": "#E8F5E9"},
                {"range": [maximum * 0.5, maximum * 0.8], "color": "#FFF3CD"},
                {"range": [maximum * 0.8, maximum], "color": "#F8D7DA"}
            ]
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=float(value),
                title={"text": title},
                gauge={
                    "axis": {"range": [0, maximum]},
                    "bar": {"color": color},
                    "steps": steps
                }
            )
        )
        fig.update_layout(
            height=270,
            margin=dict(l=20, r=20, t=50, b=20),
            transition={'duration': 0}
        )
        return fig
        
    # Dynamic values and threshold color calculations
    temp_threshold = float(st.session_state.get(f"temp_threshold_{selected_unit_id}", 40.0))
    humidity_threshold = float(st.session_state.get(f"humidity_threshold_{selected_unit_id}", 60.0))

    temp_val = float(data["temperature"])
    if temp_val <= temp_threshold:
        temp_color = "green"
    elif temp_val <= (temp_threshold + 5.0):
        temp_color = "yellow"
    else:
        temp_color = "red"
    temp_steps = [
        {"range": [0, temp_threshold], "color": "#E8F5E9"},
        {"range": [temp_threshold, temp_threshold + 5.0], "color": "#FFF3CD"},
        {"range": [temp_threshold + 5.0, 50.0], "color": "#F8D7DA"}
    ]

    humidity_val = float(data["humidity"])
    if humidity_val <= humidity_threshold:
        humidity_color = "green"
    elif humidity_val <= (humidity_threshold + 10.0):
        humidity_color = "yellow"
    else:
        humidity_color = "red"
    humidity_steps = [
        {"range": [0, humidity_threshold], "color": "#E8F5E9"},
        {"range": [humidity_threshold, humidity_threshold + 10.0], "color": "#FFF3CD"},
        {"range": [humidity_threshold + 10.0, 100.0], "color": "#F8D7DA"}
    ]

    material_percent_val = float(data["material_level"])
    if material_percent_val > 50.0:
        material_percent_color = "green"
    elif material_percent_val > 20.0:
        material_percent_color = "yellow"
    else:
        material_percent_color = "red"
    material_percent_steps = [
        {"range": [0, 20.0], "color": "#F8D7DA"},
        {"range": [20.0, 50.0], "color": "#FFF3CD"},
        {"range": [50.0, 100.0], "color": "#E8F5E9"}
    ]

    # Material level in cm = 40.0 - distance
    material_level_cm_val = 40.0 - float(data["distance"])
    if material_level_cm_val > 10.0:
        material_level_cm_color = "green"
    elif material_level_cm_val >= 5.0:
        material_level_cm_color = "yellow"
    else:
        material_level_cm_color = "red"
    material_level_cm_steps = [
        {"range": [0, 5.0], "color": "#F8D7DA"},
        {"range": [5.0, 10.0], "color": "#FFF3CD"},
        {"range": [10.0, 40.0], "color": "#E8F5E9"}
    ]

    # Helper to render custom HTML progress bars for smooth, blink-free transitions
    def render_sensor_card(title, value, max_val, unit, color, threshold_info=""):
        pct = min(100.0, max(0.0, (float(value) / max_val) * 100.0))
        color_map = {
            "green": "#2ecc71",
            "yellow": "#f1c40f",
            "red": "#e74c3c"
        }
        hex_color = color_map.get(color, color)
        return f"""
        <div style="
            background: rgba(30, 30, 47, 0.85);
            border: 1px solid rgba(58, 58, 92, 0.5);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            margin-bottom: 15px;
        ">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span style="color: #a0a0c0; font-size: 14px; font-weight: 600; font-family: sans-serif;">{title}</span>
                <span style="color: {hex_color}; font-size: 11px; font-weight: 700; background: {hex_color}1a; border: 1px solid {hex_color}33; padding: 2px 8px; border-radius: 20px; font-family: sans-serif; text-transform: uppercase;">
                    {color}
                </span>
            </div>
            <div style="font-size: 28px; font-weight: 700; color: #ffffff; font-family: sans-serif; margin-bottom: 15px; display: flex; align-items: baseline;">
                {value:.1f}
                <span style="font-size: 14px; color: #8888a8; margin-left: 4px; font-weight: 500;">{unit}</span>
            </div>
            <div style="
                background: rgba(255, 255, 255, 0.05);
                border-radius: 10px;
                height: 10px;
                width: 100%;
                overflow: hidden;
                position: relative;
            ">
                <div style="
                    background: {hex_color};
                    width: {pct}%;
                    height: 100%;
                    border-radius: 10px;
                    transition: width 1.5s cubic-bezier(0.2, 0.8, 0.2, 1);
                    box-shadow: 0 0 8px {hex_color}aa;
                "></div>
            </div>
            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #6e6e8c; font-family: sans-serif; margin-top: 8px;">
                <span>0 {unit}</span>
                <span>{threshold_info}</span>
                <span>{max_val} {unit}</span>
            </div>
        </div>
        """

    # Live Sensor Dashboard Indicators
    st.subheader("📊 Live Sensor Dashboard")
    col1, col2 = st.columns(2)
    with col1:
        temp_card_html = render_sensor_card(
            "🌡 Temperature",
            temp_val,
            50.0,
            "°C",
            temp_color,
            f"Limit: {temp_threshold:.0f}°C"
        )
        st.markdown(temp_card_html, unsafe_allow_html=True)
    with col2:
        humidity_card_html = render_sensor_card(
            "💧 Humidity",
            humidity_val,
            100.0,
            "%",
            humidity_color,
            f"Limit: {humidity_threshold:.0f}%"
        )
        st.markdown(humidity_card_html, unsafe_allow_html=True)
        
    col3, col4 = st.columns(2)
    with col3:
        material_pct_card_html = render_sensor_card(
            "📦 Material Percentage",
            material_percent_val,
            100.0,
            "%",
            material_percent_color,
            "Limit: > 50%"
        )
        st.markdown(material_pct_card_html, unsafe_allow_html=True)
    with col4:
        material_cm_card_html = render_sensor_card(
            "📦 Material Level",
            material_level_cm_val,
            40.0,
            "cm",
            material_level_cm_color,
            "Limit: > 10cm"
        )
        st.markdown(material_cm_card_html, unsafe_allow_html=True)
        
    st.markdown("---")
    
    # AI Predictions
    st.subheader("🤖 AI Prediction Engine")
    rf = data["random_forest"]
    st.markdown("### Raw Material Status")
    if rf == "SAFE":
        st.success(f"Prediction : {rf}")
    elif rf == "WARNING":
        st.warning(f"Prediction : {rf}")
    else:
        st.error(f"Prediction : {rf}")
            
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
        "📦 Material Percentage",
        "📦 Material Level (cm)"
    ])
    
    # Helper to render dynamic, blink-free SVG trend charts with smooth line/marker transitions
    def render_svg_chart(x_data, y_data, title, yaxis_label, sensor_type, temp_thresh=40.0, humid_thresh=60.0):
        x_list = list(x_data)
        y_list = list(y_data)
        
        if len(x_list) < 2:
            return f"<div style='color:#888;padding:40px;text-align:center;background:rgba(30, 30, 47, 0.85);border: 1px solid rgba(58, 58, 92, 0.5);border-radius:12px;'>Awaiting trend data for {title}...</div>"
            
        # Scale dimensions
        width = 800
        height = 250
        padding_left = 60
        padding_right = 20
        padding_top = 20
        padding_bottom = 40
        
        chart_width = width - padding_left - padding_right
        chart_height = height - padding_top - padding_bottom
        
        # Scale range limits to last 50 points for cleanliness
        n = len(x_list)
        max_points = 50
        if n > max_points:
            x_list = x_list[-max_points:]
            y_list = y_list[-max_points:]
            n = len(x_list)
        
        x_max = n - 1
        y_min_val = min(y_list)
        y_max_val = max(y_list)
        y_range = y_max_val - y_min_val
        
        if y_range == 0:
            y_min = y_min_val - 5.0
            y_max = y_max_val + 5.0
        else:
            y_min = y_min_val - 0.1 * y_range
            y_max = y_max_val + 0.1 * y_range
            
        # Coordinates mapper helpers
        def get_x_pixel(idx):
            if x_max == 0:
                return padding_left
            return padding_left + (idx / x_max) * chart_width
            
        def get_y_pixel(val):
            y_span = y_max - y_min
            if y_span == 0:
                return padding_top + chart_height / 2
            return padding_top + chart_height - ((val - y_min) / y_span) * chart_height
            
        # Grid lines and y-axis ticks
        grid_html = ""
        for k in range(5):
            val = y_min + (k / 4.0) * (y_max - y_min)
            y_px = get_y_pixel(val)
            grid_html += f'<line x1="{padding_left}" y1="{y_px}" x2="{width - padding_right}" y2="{y_px}" stroke="#2e2e4a" stroke-width="1" stroke-dasharray="4,4" />'
            grid_html += f'<text x="{padding_left - 10}" y="{y_px + 4}" fill="#a0a0c0" font-size="11" text-anchor="end" font-family="sans-serif">{val:.1f}</text>'
            
        # Time axis labels
        def format_time(t_str):
            if " " in t_str:
                return t_str.split(" ")[1]
            return t_str
            
        x_label_start = format_time(x_list[0])
        x_label_end = format_time(x_list[-1])
        mid_idx = n // 2
        x_label_mid = format_time(x_list[mid_idx])
        
        grid_html += f'<text x="{padding_left}" y="{height - 12}" fill="#a0a0c0" font-size="11" text-anchor="start" font-family="sans-serif">{x_label_start}</text>'
        grid_html += f'<text x="{get_x_pixel(mid_idx)}" y="{height - 12}" fill="#a0a0c0" font-size="11" text-anchor="middle" font-family="sans-serif">{x_label_mid}</text>'
        grid_html += f'<text x="{width - padding_right}" y="{height - 12}" fill="#a0a0c0" font-size="11" text-anchor="end" font-family="sans-serif">{x_label_end}</text>'
        
        # Color coding logic
        def get_color_for_value(val):
            val = float(val)
            if sensor_type == "temp":
                if val <= temp_thresh:
                    return "#77DD77"  # Safe: green
                elif val <= (temp_thresh + 5.0):
                    return "#FFF2A3"  # Risk: pale yellow
                else:
                    return "#FF9F9F"  # Danger: pale red
            elif sensor_type == "humidity":
                if val <= humid_thresh:
                    return "#77DD77"  # Safe: green
                elif val <= (humid_thresh + 10.0):
                    return "#FFF2A3"  # Risk: pale yellow
                else:
                    return "#FF9F9F"  # Danger: pale red
            elif sensor_type == "material_pct":
                if val > 50.0:
                    return "#77DD77"  # Safe: green
                elif val > 20.0:
                    return "#FFF2A3"  # Risk: pale yellow
                else:
                    return "#FF9F9F"  # Danger: pale red
            elif sensor_type == "material_cm":
                if val > 10.0:
                    return "#77DD77"  # Safe: green
                elif val >= 5.0:
                    return "#FFF2A3"  # Risk: pale yellow
                else:
                    return "#FF9F9F"  # Danger: pale red
            return "#77DD77"
            
        paths_html = ""
        markers_html = ""
        
        # Render line segments
        for i in range(n - 1):
            x1_px = get_x_pixel(i)
            y1_px = get_y_pixel(y_list[i])
            x2_px = get_x_pixel(i+1)
            y2_px = get_y_pixel(y_list[i+1])
            avg_val = (y_list[i] + y_list[i+1]) / 2.0
            color = get_color_for_value(avg_val)
            paths_html += f'<line x1="{x1_px}" y1="{y1_px}" x2="{x2_px}" y2="{y2_px}" stroke="{color}" stroke-width="3" stroke-linecap="round" style="transition: all 0.5s ease-in-out;" />'
            
        # Render markers (points)
        for i in range(n):
            x_px = get_x_pixel(i)
            y_px = get_y_pixel(y_list[i])
            color = get_color_for_value(y_list[i])
            markers_html += f'<circle cx="{x_px}" cy="{y_px}" r="4.5" fill="{color}" stroke="#1e1e2f" stroke-width="1.5" style="transition: all 0.5s ease-in-out;" />'
            
        return f"""
        <div style="
            background: rgba(30, 30, 47, 0.85);
            border: 1px solid rgba(58, 58, 92, 0.5);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.3);
            backdrop-filter: blur(10px);
            margin-top: 15px;
        ">
            <h4 style="color:#ffffff;margin-top:0;margin-bottom:15px;font-family:sans-serif;font-weight:600;">{title} ({yaxis_label})</h4>
            <svg viewBox="0 0 {width} {height}" width="100%" height="auto" style="overflow: visible;">
                {grid_html}
                <line x1="{padding_left}" y1="{padding_top}" x2="{padding_left}" y2="{height - padding_bottom}" stroke="#3a3a5c" stroke-width="1.5" />
                <line x1="{padding_left}" y1="{height - padding_bottom}" x2="{width - padding_right}" y2="{height - padding_bottom}" stroke="#3a3a5c" stroke-width="1.5" />
                {paths_html}
                {markers_html}
            </svg>
        </div>
        """

    # Get threshold values for temp/humidity
    temp_threshold = float(st.session_state.get(f"temp_threshold_{selected_unit_id}", 40.0))
    humidity_threshold = float(st.session_state.get(f"humidity_threshold_{selected_unit_id}", 60.0))

    with tab1:
        temp_chart_html = render_svg_chart(
            history["Timestamp"],
            history["Temperature"],
            "Temperature Trend",
            "°C",
            "temp",
            temp_threshold,
            humidity_threshold
        )
        st.markdown(temp_chart_html, unsafe_allow_html=True)
        
    with tab2:
        humidity_chart_html = render_svg_chart(
            history["Timestamp"],
            history["Humidity"],
            "Humidity Trend",
            "%",
            "humidity",
            temp_threshold,
            humidity_threshold
        )
        st.markdown(humidity_chart_html, unsafe_allow_html=True)
        
    with tab3:
        material_chart_html = render_svg_chart(
            history["Timestamp"],
            history["Material_Level"],
            "Material Percentage Trend",
            "%",
            "material_pct",
            temp_threshold,
            humidity_threshold
        )
        st.markdown(material_chart_html, unsafe_allow_html=True)
        
    with tab4:
        # Convert Distance history to Material Level (cm)
        history_cm = 40.0 - history["Distance"]
        material_cm_chart_html = render_svg_chart(
            history["Timestamp"],
            history_cm,
            "Material Level (cm) Trend",
            "cm",
            "material_cm",
            temp_threshold,
            humidity_threshold
        )
        st.markdown(material_cm_chart_html, unsafe_allow_html=True)
        
    st.markdown("---")
    
    # System Health
    st.subheader("🖥 System Health")
    h1, h2, h3 = st.columns(3)
    with h1:
        st.success("☁ AWS IoT Core")
        st.caption("Connected")
    with h2:
        st.success("🤖 R.E.M.A.C System")
        st.caption("Running")
    with h3:
        st.success("📡 Dashboard")
        st.caption("Online")
        
    st.markdown("---")
    st.caption("REMAC Intelligent Raw Material Storage Monitoring System")
    st.caption("Powered by Python • Streamlit • AWS IoT Core • Random Forest")
    st.caption("Version 1.0 | Academic MVP Demonstration")
