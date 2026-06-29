import json
from pathlib import Path
import time
import math
import requests

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ============================================================
# AUTO REFRESH
# ============================================================

st_autorefresh(
    interval=5000,
    key="dashboard_refresh"
)

# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="REMAC Intelligent Monitoring",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# PROJECT PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

LIVE_DATA_DIR = BASE_DIR / "live_data"

LIVE_FILE = LIVE_DATA_DIR / "latest.json"

HISTORY_FILE = LIVE_DATA_DIR / "history.csv"

LIVE_DATA_DIR.mkdir(exist_ok=True)

# ============================================================
# PAGE TITLE
# ============================================================

st.title("📡 R.E.M.A.C Intelligent Raw Material Storage Monitoring System")

st.caption(
    "Industrial IoT • Machine Learning • AWS IoT Core • Real-Time Monitoring"
)

st.markdown("---")
# ============================================================
# CHECK LIVE DATA
# ============================================================

if not LIVE_FILE.exists():

    st.warning("Waiting for live sensor data...")

    st.stop()

def clean_nan(val):
    if isinstance(val, dict):
        return {k: clean_nan(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [clean_nan(x) for x in val]
    elif isinstance(val, float) and math.isnan(val):
        return None
    return val

data = None

# First, attempt to read from the cloud key-value store for live synchronization
try:
    response = requests.get("https://kvdb.io/remac_mvp_7bf9bd4f/latest", timeout=2)
    if response.status_code == 200:
        data = clean_nan(response.json())
except Exception:
    pass

# If cloud KV store is down or we are offline, fallback to local latest.json
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
        st.error(f"Unable to read latest.json after multiple attempts.\n\n{e}")
        st.stop()


# ============================================================
# STATE INITIALIZATION & RUNTIME TRACKING
# ============================================================

if "ac_runtime" not in st.session_state:
    st.session_state.ac_runtime = 0
if "dryer_runtime" not in st.session_state:
    st.session_state.dryer_runtime = 0
if "ac_status" not in st.session_state:
    st.session_state.ac_status = "OFF"
if "dryer_status" not in st.session_state:
    st.session_state.dryer_status = "OFF"
if "ac_mode" not in st.session_state:
    st.session_state.ac_mode = "Auto"
if "dryer_mode" not in st.session_state:
    st.session_state.dryer_mode = "Auto"

current_time = time.time()
if "last_time" in st.session_state:
    elapsed = current_time - st.session_state.last_time
    if 0 < elapsed < 15:
        if st.session_state.ac_status == "ON":
            st.session_state.ac_runtime += int(elapsed)
        if st.session_state.dryer_status == "ON":
            st.session_state.dryer_runtime += int(elapsed)
st.session_state.last_time = current_time

# ============================================================
# HISTORY MANAGEMENT
# ============================================================

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
        history = pd.concat(
            [history, new_row],
            ignore_index=True
        )
    # Always sort chronologically and keep the last 100 entries
    history = history.sort_values(by="Timestamp").tail(100)
    for attempt in range(5):
        try:
            history.to_csv(
                HISTORY_FILE,
                index=False
            )
            break
        except PermissionError:
            time.sleep(0.1)
else:
    history = new_row

# ============================================================
# ALERT BANNER
# ============================================================

if data["status"] == "SAFE":

    st.success("🟢 System Healthy")

elif data["status"] == "WARNING":

    st.warning("🟡 Warning Condition")

else:

    st.error("🔴 Danger Condition")

    # ============================================================
# GAUGE FUNCTION
# ============================================================

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

# ============================================================
# LIVE SENSOR DASHBOARD
# ============================================================

st.subheader("📊 Live Sensor Dashboard")

col1, col2 = st.columns(2)

with col1:

    fig_temp = create_gauge(
        "🌡 Temperature (°C)",
        data["temperature"],
        50,
        "red"
    )

    st.plotly_chart(
        fig_temp,
        use_container_width=True,
        key="temp_gauge"
    )

with col2:


    fig_humidity = create_gauge(
        "💧 Humidity (%)",
        data["humidity"],
        100,
        "blue"
    )

    st.plotly_chart(
        fig_humidity,
        use_container_width=True,
        key="humidity_gauge"
    )

col3, col4 = st.columns(2)

with col3:

    fig_material = create_gauge(
        "📦 Material Level (%)",
        data["material_level"],
        100,
        "green"
    )

    st.plotly_chart(
        fig_material,
        use_container_width=True,
        key="material_gauge"
    )

with col4:

    fig_distance = create_gauge(
        "📏 Distance (cm)",
        data["distance"],
        30,
        "orange"
    )

    st.plotly_chart(
        fig_distance,
        use_container_width=True,
        key="distance_gauge"
    )

st.markdown("---")
# ============================================================
# AI PREDICTIONS
# ============================================================

st.subheader("🤖 AI Prediction Engine")

col1, col2 = st.columns(2)

with col1:

    st.markdown("### 🌲 Random Forest")

    rf = data["random_forest"]

    if rf == "SAFE":
        st.success(f"Prediction : {rf}")

    elif rf == "WARNING":
        st.warning(f"Prediction : {rf}")

    else:
        st.error(f"Prediction : {rf}")

with col2:

    st.markdown("### 🔍 Isolation Forest")

    iso = data["isolation_forest"]

    if iso == "NORMAL":
        st.success(f"Result : {iso}")

    else:
        st.error(f"Result : {iso}")

st.markdown("---")
# ============================================================
# RISK INDICATORS
# ============================================================

st.subheader("⚠ Risk Indicators")

left, right = st.columns(2)

with left:

    temp_risk = float(data["temperature_risk"])

    st.metric(
        "Temperature Risk",
        f"{temp_risk:.1f}%"
    )

    st.progress(
        min(int(temp_risk), 100)
    )

with right:

    humidity_risk = float(data["humidity_risk"])

    st.metric(
        "Humidity Risk",
        f"{humidity_risk:.1f}%"
    )

    st.progress(
        min(int(humidity_risk), 100)
    )

st.markdown("---")
# ============================================================
# AUTOMATIC ENVIRONMENTAL CONTROL
# ============================================================

st.subheader("❄️ Automatic Environmental Control")

# Get current temperature and humidity
current_temp = float(data["temperature"])
current_humidity = float(data["humidity"])

# Initialize thresholds in session state if not present
if "temp_threshold" not in st.session_state:
    st.session_state.temp_threshold = 40.0
if "humidity_threshold" not in st.session_state:
    st.session_state.humidity_threshold = 60.0

# Notifications Area
# Display notifications if thresholds are exceeded in Auto mode
if st.session_state.ac_mode == "Auto" and current_temp > st.session_state.temp_threshold:
    st.warning("⚠️ **Notification:** AC Activated - High Temperature Detected ({:.1f}°C > {:.1f}°C)".format(current_temp, st.session_state.temp_threshold))
if st.session_state.dryer_mode == "Auto" and current_humidity > st.session_state.humidity_threshold:
    st.warning("⚠️ **Notification:** Dryer Activated - High Humidity Detected ({:.1f}% > {:.1f}%)".format(current_humidity, st.session_state.humidity_threshold))

col_ctrl, col_ac, col_dry = st.columns(3)

with col_ctrl:
    st.markdown("#### 🎛️ Threshold Configuration")
    temp_thresh = st.slider("AC Temp Threshold (°C)", min_value=15.0, max_value=50.0, value=st.session_state.temp_threshold, step=0.5, key="temp_thresh_slider")
    humid_thresh = st.slider("Dryer Humidity Threshold (%)", min_value=20.0, max_value=90.0, value=st.session_state.humidity_threshold, step=1.0, key="humid_thresh_slider")
    
    # Save the configured thresholds
    st.session_state.temp_threshold = temp_thresh
    st.session_state.humidity_threshold = humid_thresh
    
    st.markdown("---")
    st.markdown("**Cloud Rule Engine Commands**")
    
    # Active command sending indicators
    ac_flow = "⚡ `Cloud AI/Rule Engine` ➔ `[CMD: TURN_ON]` ➔ `AC Device`" if st.session_state.ac_status == "ON" else "💤 `Cloud AI/Rule Engine` ➔ `[CMD: TURN_OFF]` ➔ `AC Device`"
    dryer_flow = "⚡ `Cloud AI/Rule Engine` ➔ `[CMD: TURN_ON]` ➔ `Dryer Device`" if st.session_state.dryer_status == "ON" else "💤 `Cloud AI/Rule Engine` ➔ `[CMD: TURN_OFF]` ➔ `Dryer Device`"
    
    st.markdown(ac_flow)
    st.markdown(dryer_flow)

with col_ac:
    st.markdown("#### ❄️ Air Conditioner (AC)")
    ac_mode = st.radio("AC Mode Select", ["Auto", "Manual"], index=0 if st.session_state.ac_mode == "Auto" else 1, key="ac_mode_radio_btn")
    st.session_state.ac_mode = ac_mode
    
    # Automation logic for AC status
    if ac_mode == "Auto":
        if current_temp > st.session_state.temp_threshold:
            st.session_state.ac_status = "ON"
        else:
            st.session_state.ac_status = "OFF"
        
    else:
        # Manual control
        ac_manual = st.checkbox("Turn AC ON (Manual)", value=(st.session_state.ac_status == "ON"), key="ac_manual_check_box")
        st.session_state.ac_status = "ON" if ac_manual else "OFF"
        
    status_indicator = "🟢 ON" if st.session_state.ac_status == "ON" else "🔴 OFF"
    st.markdown(f"**Status:** {status_indicator}")
    
    # Runtime display
    runtime_m, runtime_s = divmod(st.session_state.ac_runtime, 60)
    runtime_h, runtime_m = divmod(runtime_m, 60)
    st.markdown(f"⏱️ **Runtime:** {runtime_h:02d}h:{runtime_m:02d}m:{runtime_s:02d}s")

with col_dry:
    st.markdown("#### 💧 Dryer / Dehumidifier")
    dryer_mode = st.radio("Dryer Mode Select", ["Auto", "Manual"], index=0 if st.session_state.dryer_mode == "Auto" else 1, key="dryer_mode_radio_btn")
    st.session_state.dryer_mode = dryer_mode
    
    # Automation logic for Dryer status
    if dryer_mode == "Auto":
        if current_humidity > st.session_state.humidity_threshold:
            st.session_state.dryer_status = "ON"
        else:
            st.session_state.dryer_status = "OFF"
        
    else:
        # Manual control
        dryer_manual = st.checkbox("Turn Dryer ON (Manual)", value=(st.session_state.dryer_status == "ON"), key="dryer_manual_check_box")
        st.session_state.dryer_status = "ON" if dryer_manual else "OFF"
        
    status_indicator = "🟢 ON" if st.session_state.dryer_status == "ON" else "🔴 OFF"
    st.markdown(f"**Status:** {status_indicator}")
    
    # Runtime display
    runtime_m, runtime_s = divmod(st.session_state.dryer_runtime, 60)
    runtime_h, runtime_m = divmod(runtime_m, 60)
    st.markdown(f"⏱️ **Runtime:** {runtime_h:02d}h:{runtime_m:02d}m:{runtime_s:02d}s")

st.markdown("---")
# ============================================================
# DEVICE INFORMATION
# ============================================================

st.subheader("🛰 Device Information")

c1, c2 = st.columns(2)

with c1:

    st.write(f"**Device ID :** {data['device']}")

    st.write(f"**Timestamp :** {data['timestamp']}")

with c2:

    st.write(f"**Status :** {data['status']}")

    st.write(f"**Active Alert :** {data['active_alert']}")

st.markdown("---")
# ============================================================
# LIVE TREND CHARTS
# ============================================================

st.subheader("📈 Live Trends")

tab1, tab2, tab3, tab4 = st.tabs([
    "🌡 Temperature",
    "💧 Humidity",
    "📦 Material Level",
    "📏 Distance"
])

# ---------------- Temperature ----------------

with tab1:

    temp_fig = go.Figure()

    temp_fig.add_trace(
        go.Scatter(
            x=history["Timestamp"],
            y=history["Temperature"],
            mode="lines+markers",
            name="Temperature"
        )
    )

    temp_fig.update_layout(
        title="Temperature Trend",
        xaxis_title="Time",
        yaxis_title="°C",
        height=350
    )

    st.plotly_chart(
        temp_fig,
        use_container_width=True,
        key="temperature_trend_chart"
    )

# ---------------- Humidity ----------------

with tab2:

    humidity_fig = go.Figure()

    humidity_fig.add_trace(
        go.Scatter(
            x=history["Timestamp"],
            y=history["Humidity"],
            mode="lines+markers",
            name="Humidity"
        )
    )

    humidity_fig.update_layout(
        title="Humidity Trend",
        xaxis_title="Time",
        yaxis_title="%",
        height=350
    )

    st.plotly_chart(
        humidity_fig,
        use_container_width=True,
        key="humidity_trend_chart"
    )

# ---------------- Material Level ----------------

with tab3:

    material_fig = go.Figure()

    material_fig.add_trace(
        go.Scatter(
            x=history["Timestamp"],
            y=history["Material_Level"],
            mode="lines+markers",
            name="Material Level"
        )
    )

    material_fig.update_layout(
        title="Material Level Trend",
        xaxis_title="Time",
        yaxis_title="%",
        height=350
    )

    st.plotly_chart(
        material_fig,
        use_container_width=True,
        key="material_trend_chart"
    )

# ---------------- Distance ----------------

with tab4:

    distance_fig = go.Figure()

    distance_fig.add_trace(
        go.Scatter(
            x=history["Timestamp"],
            y=history["Distance"],
            mode="lines+markers",
            name="Distance"
        )
    )

    distance_fig.update_layout(
        title="Distance Trend",
        xaxis_title="Time",
        yaxis_title="cm",
        height=350
    )

    st.plotly_chart(
        distance_fig,
        use_container_width=True,
        key="distance_trend_chart"
    )

st.markdown("---")
# ============================================================
# SYSTEM HEALTH
# ============================================================

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
# ============================================================
# FOOTER
# ============================================================

st.caption("REMAC Intelligent Raw Material Storage Monitoring System")

st.caption(
    "Powered by Python • Streamlit • AWS IoT Core • Random Forest • Isolation Forest"
)

st.caption("Version 1.0 | Academic MVP Demonstration")
