import React, { useState, useEffect, useRef } from 'react';

// ============================================================
// STORAGE UNITS CONFIGURATION
// ============================================================
const STORAGE_UNITS = [
  { id: 1, name: "Storage Unit 1", material: "PET (Polyethylene Terephthalate)", device_id: "REMAC_PET_001", default_temp: 35.0, default_humid: 40.0, blob_id: "019f46e1-3345-7a4a-bea7-c6601ddabfea" },
  { id: 2, name: "Storage Unit 2", material: "HDPE (High-Density Polyethylene)", device_id: "REMAC_HDPE_002", default_temp: 40.0, default_humid: 65.0, blob_id: "019f46e1-3f47-7346-aae4-48e0de4bd33b" },
  { id: 3, name: "Storage Unit 3", material: "PVC (Polyvinyl Chloride)", device_id: "REMAC_PVC_003", default_temp: 30.0, default_humid: 50.0, blob_id: "019f46e1-4885-7bd6-a8cd-3c2866eb0398" },
  { id: 4, name: "Storage Unit 4", material: "LDPE (Low-Density Polyethylene)", device_id: "REMAC_LDPE_004", default_temp: 35.0, default_humid: 65.0, blob_id: "019f46e1-51de-7094-b331-1e2978b9c38a" },
  { id: 5, name: "Storage Unit 5", material: "PP (Polypropylene)", device_id: "REMAC_PP_005", default_temp: 40.0, default_humid: 65.0, blob_id: "019f46e1-5b40-7fff-95eb-d0e6f98312a6" },
  { id: 6, name: "Storage Unit 6", material: "PS (Polystyrene)", device_id: "REMAC_PS_006", default_temp: 35.0, default_humid: 55.0, blob_id: "019f46e1-64ab-7c94-a01c-ddb12f9dbf58" },
  { id: 7, name: "Storage Unit 7", material: "ABS (Acrylonitrile Butadiene Styrene)", device_id: "REMAC_ABS_007", default_temp: 35.0, default_humid: 50.0, blob_id: "019f46e1-960b-7b80-8030-ddfa51529428" },
  { id: 8, name: "Storage Unit 8", material: "PC (Polycarbonate)", device_id: "REMAC_PC_008", default_temp: 35.0, default_humid: 45.0, blob_id: "019f46e1-c76c-776d-80eb-028449bceb01" },
  { id: 9, name: "Storage Unit 9", material: "PMMA (Acrylic)", device_id: "REMAC_PMMA_009", default_temp: 30.0, default_humid: 50.0, blob_id: "019f46e1-d103-7ed2-a9ab-3fda16802731" },
  { id: 10, name: "Storage Unit 10", material: "Nylon (Polyamide)", device_id: "REMAC_NYLON_010", default_temp: 30.0, default_humid: 35.0, blob_id: "019f46e2-0246-73e1-b49b-a7ef5a575eb1" },
];

// ============================================================
// CLOUD STORAGE CONFIGURATION (S3 & KVDB)
// ============================================================
// If you want to use S3, provide your bucket HTTP endpoint here (e.g., "https://remac-telemetry.s3.amazonaws.com")
// Otherwise, leave it empty to fall back to the default KVDB.io cloud bucket.
const AWS_S3_BUCKET_URL = "";

export default function App() {
  // Authentication State
  const [loggedIn, setLoggedIn] = useState(() => {
    return localStorage.getItem('remac_logged_in') === 'true';
  });
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loginError, setLoginError] = useState('');

  // Dashboard States
  const [selectedUnitId, setSelectedUnitId] = useState(null);
  const [unitsData, setUnitsData] = useState({});
  const [unitsHistory, setUnitsHistory] = useState({});
  const [isSimulatorActive, setIsSimulatorActive] = useState(false);
  const [isSimulating, setIsSimulating] = useState(() => {
    return localStorage.getItem('remac_sim_running') === 'true';
  });

  // Toggle Remote and Local Simulation
  const toggleSimulation = async () => {
    const nextVal = !isSimulating;
    setIsSimulating(nextVal);
    localStorage.setItem('remac_sim_running', String(nextVal));
    try {
      await fetch('https://kvdb.io/4fm9CKFheYEj7fqeaijvJz/sim_command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ running: nextVal })
      });
    } catch (e) {
      console.error("Failed to sync simulation state to cloud:", e);
    }
  };

  // Environmental Systems States (persisted per Unit ID)
  const [envStates, setEnvStates] = useState(() => {
    const saved = localStorage.getItem('remac_env_states');
    if (saved) return JSON.parse(saved);
    
    // Default config
    const initial = {};
    STORAGE_UNITS.forEach(u => {
      initial[u.id] = {
        temp_threshold: u.default_temp,
        humidity_threshold: u.default_humid,
        ac_mode: 'Auto',
        ac_status: 'OFF',
        ac_runtime: 0,
        dryer_mode: 'Auto',
        dryer_status: 'OFF',
        dryer_runtime: 0
      };
    });
    return initial;
  });

  // Save environmental states to local storage
  useEffect(() => {
    localStorage.setItem('remac_env_states', JSON.stringify(envStates));
  }, [envStates]);

  // Handle Login
  const handleLogin = (e) => {
    e.preventDefault();
    if (username === 'admin' && password === 'admin123') {
      setLoggedIn(true);
      localStorage.setItem('remac_logged_in', 'true');
      setLoginError('');
    } else {
      setLoginError('Access Denied: Invalid username or password.');
    }
  };

  // Handle Logout
  const handleLogout = () => {
    setLoggedIn(false);
    localStorage.removeItem('remac_logged_in');
    setUsername('');
    setPassword('');
  };


  // Run environmental systems timers (accumulates active AC & Dryer runtimes every second)
  useEffect(() => {
    if (!loggedIn) return;

    const timer = setInterval(() => {
      setEnvStates(prev => {
        const next = { ...prev };
        let updated = false;
        
        STORAGE_UNITS.forEach(unit => {
          const uState = next[unit.id];
          if (!uState) return;

          let acAdded = 0;
          let dryerAdded = 0;

          if (uState.ac_status === 'ON') {
            acAdded = 1;
          }
          if (uState.dryer_status === 'ON') {
            dryerAdded = 1;
          }

          if (acAdded > 0 || dryerAdded > 0) {
            updated = true;
            next[unit.id] = {
              ...uState,
              ac_runtime: uState.ac_runtime + acAdded,
              dryer_runtime: uState.dryer_runtime + dryerAdded
            };
          }
        });

        return updated ? next : prev;
      });
    }, 1000);

    return () => clearInterval(timer);
  }, [loggedIn]);

  // Generate / Fetch data for all units
  useEffect(() => {
    if (!loggedIn) return;

    const updateTelemetry = async () => {
      const newUnitsData = { ...unitsData };
      const newUnitsHistory = { ...unitsHistory };
      let dataChanged = false;

      // Helper to generate a drift-based mock state if cloud fetch fails and simulation is enabled
      const getDriftedState = (unit, prevVal) => {
        const t_drift = (Math.random() - 0.5) * 0.4;
        const h_drift = (Math.random() - 0.5) * 0.6;
        const l_drift = (Math.random() - 0.5) * 0.3;
        
        const temp = prevVal ? Math.min(50, Math.max(15, prevVal.temperature + t_drift)) : unit.default_temp;
        const humid = prevVal ? Math.min(100, Math.max(0, prevVal.humidity + h_drift)) : unit.default_humid;
        const level = prevVal ? Math.min(100, Math.max(0, prevVal.material_level + l_drift)) : 75.0;
        const distance = 40.0 - (level / 100.0) * 40.0;
        
        // Predict Status
        let status = "SAFE";
        let active_alert = "None";
        if (temp > unit.default_temp + 5.0 || humid > unit.default_humid + 10.0) {
          status = "DANGER";
          active_alert = temp > unit.default_temp + 5.0 ? "High Temperature" : "High Humidity";
        } else if (temp > unit.default_temp || humid > unit.default_humid) {
          status = "WARNING";
          active_alert = temp > unit.default_temp ? "Elevated Temperature" : "Elevated Humidity";
        }
        
        const tempRisk = Math.min(100, Math.max(0, (temp / 40.0) * 100));
        const humidRisk = Math.min(100, Math.max(0, (humid / 60.0) * 100));
        
        return {
          device: unit.device_id,
          timestamp: new Date().toLocaleTimeString(),
          temperature: temp,
          humidity: humid,
          distance: distance,
          material_level: level,
          status: status,
          active_alert: active_alert,
          random_forest: status,
          isolation_forest: status === "SAFE" ? "NORMAL" : "ANOMALY",
          temperature_risk: tempRisk,
          humidity_risk: humidRisk
        };
      };

      for (const unit of STORAGE_UNITS) {
        let livePayload = null;
        let historyPayload = null;
        
        // 1. Fetch latest reading from local REMAC Express server API
        try {
          const res = await fetch(`/api/telemetry/${unit.id}`);
          if (res.ok) {
            livePayload = await res.json();
            setIsSimulatorActive(true);
          } else {
            throw new Error("Local API returned error status");
          }
        } catch (e) {
          // Fallback to JSONBlob cloud storage directly in browser (works without local python server!)
          try {
            const res = await fetch(`https://jsonblob.com/api/jsonBlob/019f4ab1-f7e9-7797-aad7-e56a4a77fc86`);
            if (res.ok) {
              livePayload = await res.json();
              setIsSimulatorActive(true);
            }
          } catch (cloudErr) {
            console.warn("Cloud JSONBlob fetch failed:", cloudErr);
          }
        }

        // Only fall back to dummy mock data if simulation is enabled
        if (!livePayload) {
          if (isSimulating) {
            livePayload = getDriftedState(unit, unitsData[unit.id]);
          } else {
            livePayload = null;
          }
        }

        if (livePayload) {
          newUnitsData[unit.id] = livePayload;
          
          // Process historical trend list
          let histList = [];
          if (historyPayload && Array.isArray(historyPayload)) {
            histList = historyPayload;
          } else {
            const prevHist = unitsHistory[unit.id] || [];
            const newPt = {
              Timestamp: livePayload.timestamp,
              Temperature: livePayload.temperature,
              Humidity: livePayload.humidity,
              Distance: livePayload.distance,
              Material_Level: livePayload.material_level
            };

            if (prevHist.length === 0 || prevHist[prevHist.length - 1].Timestamp !== newPt.Timestamp) {
              histList = [...prevHist, newPt].slice(-20);
            } else {
              histList = prevHist;
            }
          }
          newUnitsHistory[unit.id] = histList;
          dataChanged = true;
        } else {
          // If no data is available (device offline and simulation off)
          if (unitsData[unit.id] && unitsData[unit.id].status !== "OFFLINE") {
            newUnitsData[unit.id] = {
              device: unit.device_id,
              timestamp: "--:--:--",
              temperature: 0,
              humidity: 0,
              distance: 0,
              material_level: 0,
              status: "OFFLINE",
              active_alert: "Device Offline / No Data Received",
              random_forest: "OFFLINE",
              isolation_forest: "UNKNOWN",
              temperature_risk: 0,
              humidity_risk: 0
            };
            newUnitsHistory[unit.id] = [];
            dataChanged = true;
          }
        }
      }

      if (dataChanged) {
        setUnitsData(newUnitsData);
        setUnitsHistory(newUnitsHistory);
      }
    };

    // Initial update
    updateTelemetry();

    // Setup 5 second refresh interval
    const interval = setInterval(updateTelemetry, 5000);
    return () => clearInterval(interval);
  }, [loggedIn, unitsData, unitsHistory, isSimulating]);

  // Adjust environmental system status automatically when temperature/humidity changes
  useEffect(() => {
    setEnvStates(prev => {
      const next = { ...prev };
      let changed = false;

      STORAGE_UNITS.forEach(unit => {
        const uState = next[unit.id];
        const uData = unitsData[unit.id];
        if (!uState || !uData) return;

        let targetAcStatus = uState.ac_status;
        let targetDryerStatus = uState.dryer_status;

        // AC Automatic rule
        if (uState.ac_mode === 'Auto') {
          if (uData.temperature > uState.temp_threshold) {
            targetAcStatus = 'ON';
          } else {
            targetAcStatus = 'OFF';
          }
        }

        // Dryer Automatic rule
        if (uState.dryer_mode === 'Auto') {
          if (uData.humidity > uState.humidity_threshold) {
            targetDryerStatus = 'ON';
          } else {
            targetDryerStatus = 'OFF';
          }
        }

        if (targetAcStatus !== uState.ac_status || targetDryerStatus !== uState.dryer_status) {
          changed = true;
          next[unit.id] = {
            ...uState,
            ac_status: targetAcStatus,
            dryer_status: targetDryerStatus
          };
        }
      });

      return changed ? next : prev;
    });
  }, [unitsData]);

  // If not logged in, render the login page
  if (!loggedIn) {
    return (
      <div className="login-wrapper">
        <div className="glass-panel login-card animated-fade">
          <div className="login-header">
            <h2>📡 R.E.M.A.C</h2>
            <p>Intelligent Raw Material Monitoring System</p>
          </div>
          {loginError && <div className="error-banner">{loginError}</div>}
          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label>Username</label>
              <input
                type="text"
                className="form-input"
                placeholder="Enter username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input
                type="password"
                className="form-input"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button type="submit" className="login-btn">Sign In</button>
          </form>
          <div className="login-footer">
            Default Credentials: <code>admin</code> / <code>admin123</code>
          </div>
        </div>
      </div>
    );
  }

  // Selected Unit Info Helper
  const selectedUnit = STORAGE_UNITS.find(u => u.id === selectedUnitId);

  return (
    <div className="app-container animated-fade">
      {/* Dashboard Top Header bar */}
      <header className="dashboard-header">
        <div className="header-brand">
          <h1>📡 R.E.M.A.C</h1>
          <p>Industrial IoT • Cloud Monitor System Hub</p>
        </div>
        <div className="header-actions">
          <div className="sim-indicator">
            <span className={`sim-dot ${!isSimulating ? 'active' : ''}`}></span>
            <span>{isSimulating ? "🧪 Simulation Mode (Demo)" : "🔌 Live Hardware Mode"}</span>
          </div>
          <button 
            className={`btn-secondary ${isSimulating ? 'btn-logout' : 'btn-start-sim'}`} 
            onClick={toggleSimulation}
          >
            {isSimulating ? "🔌 Switch to Live Hardware" : "🧪 Switch to Simulation"}
          </button>
          {selectedUnitId !== null && (
            <button className="btn-secondary" onClick={() => setSelectedUnitId(null)}>
              🏠 Back to Homepage
            </button>
          )}
          <button className="btn-secondary btn-logout" onClick={handleLogout}>
            Logout 🚪
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      {selectedUnitId === null ? (
        // ==========================================
        // HOMEPAGE VIEW
        // ==========================================
        <main className="dashboard-main animated-fade">
          <div className="dashboard-title-section">
            <h2>🏢 Solid Material Storage Hub Overview</h2>
            <p>Select a solid raw plastic material storage unit below to access real-time sensor metrics, ML status classification, and climate controls.</p>
          </div>

          <div className="units-grid">
            {STORAGE_UNITS.map(unit => {
              const uData = unitsData[unit.id] || {};
              const status = uData.status || "UNKNOWN";
              const temp = uData.temperature !== undefined ? `${uData.temperature.toFixed(1)}°C` : "--";
              const humid = uData.humidity !== undefined ? `${uData.humidity.toFixed(1)}%` : "--";
              const level = uData.material_level !== undefined ? `${uData.material_level.toFixed(1)}%` : "--";

              return (
                <div 
                  key={unit.id} 
                  className="glass-panel unit-card"
                  onClick={() => setSelectedUnitId(unit.id)}
                >
                  <div className="unit-card-header">
                    <span className="unit-number">UNIT {unit.id}</span>
                    <span className={`status-badge ${status.toLowerCase()}`}>{status}</span>
                  </div>
                  <h4 className="unit-material">{unit.material}</h4>
                  
                  <div className="unit-metrics">
                    <div className="mini-metric">
                      <div className="mini-metric-label">Temp</div>
                      <div className="mini-metric-value temp">{temp}</div>
                    </div>
                    <div className="mini-metric">
                      <div className="mini-metric-label">Humid</div>
                      <div className="mini-metric-value humid">{humid}</div>
                    </div>
                    <div className="mini-metric">
                      <div className="mini-metric-label">Level</div>
                      <div className="mini-metric-value level">{level}</div>
                    </div>
                  </div>
                  <button className="unit-access-btn">Access Unit {unit.id} ➔</button>
                </div>
              );
            })}
          </div>
        </main>
      ) : (
        // ==========================================
        // INDIVIDUAL UNIT VIEW
        // ==========================================
        <div className="detail-container">
          {/* Detail Left Sidebar Navigation */}
          <aside className="detail-sidebar">
            <div className="sidebar-section">
              <h3>🏢 Storage Units</h3>
              <nav className="nav-list">
                {STORAGE_UNITS.map(unit => (
                  <button
                    key={unit.id}
                    className={`btn-sidebar-nav ${selectedUnitId === unit.id ? 'active' : ''}`}
                    onClick={() => setSelectedUnitId(unit.id)}
                  >
                    <span>Unit {unit.id} ({unit.material.split(' ')[0]})</span>
                    {unitsData[unit.id] && (
                      <span className={`status-badge ${unitsData[unit.id].status.toLowerCase()}`} style={{fontSize: '9px', padding: '1px 5px'}}>
                        {unitsData[unit.id].status}
                      </span>
                    )}
                  </button>
                ))}
              </nav>
            </div>
            
            <div className="sidebar-section" style={{marginTop: 'auto'}}>
              <button className="btn-secondary" style={{width: '100%'}} onClick={() => setSelectedUnitId(null)}>
                🏠 Back to Home
              </button>
            </div>
          </aside>

          {/* Detail Main Panel */}
          <main className="detail-content animated-fade">
            {selectedUnit && unitsData[selectedUnit.id] && (
              <>
                <div className="detail-title-block">
                  <div className="detail-title-left">
                    <h2>📡 Storage Unit {selectedUnit.id} - {selectedUnit.material}</h2>
                    <p>Real-Time Diagnostics • Device ID: {selectedUnit.device_id}</p>
                  </div>
                  <span className={`status-badge ${unitsData[selectedUnit.id].status.toLowerCase()}`} style={{fontSize: '14px', padding: '6px 16px', borderRadius: '8px'}}>
                    System Health: {unitsData[selectedUnit.id].status}
                  </span>
                </div>

                {/* 4 Sensor Cards Grid */}
                <div className="sensor-cards-grid">
                  {/* Temperature Card */}
                  <SensorCard
                    title="🌡 Temperature"
                    value={unitsData[selectedUnit.id].temperature}
                    max={50}
                    unit="°C"
                    alertType={
                      unitsData[selectedUnit.id].temperature <= envStates[selectedUnit.id].temp_threshold ? 'green' :
                      unitsData[selectedUnit.id].temperature <= (envStates[selectedUnit.id].temp_threshold + 5.0) ? 'yellow' : 'red'
                    }
                    limitInfo={`Limit: ${envStates[selectedUnit.id].temp_threshold.toFixed(0)}°C`}
                  />
                  
                  {/* Humidity Card */}
                  <SensorCard
                    title="💧 Humidity"
                    value={unitsData[selectedUnit.id].humidity}
                    max={100}
                    unit="%"
                    alertType={
                      unitsData[selectedUnit.id].humidity <= envStates[selectedUnit.id].humidity_threshold ? 'green' :
                      unitsData[selectedUnit.id].humidity <= (envStates[selectedUnit.id].humidity_threshold + 10.0) ? 'yellow' : 'red'
                    }
                    limitInfo={`Limit: ${envStates[selectedUnit.id].humidity_threshold.toFixed(0)}%`}
                  />
                  
                  {/* Material Percentage Card */}
                  <SensorCard
                    title="📦 Material Percentage"
                    value={unitsData[selectedUnit.id].material_level}
                    max={100}
                    unit="%"
                    alertType={
                      unitsData[selectedUnit.id].material_level > 50.0 ? 'green' :
                      unitsData[selectedUnit.id].material_level > 20.0 ? 'yellow' : 'red'
                    }
                    limitInfo="Limit: > 50%"
                  />
                  
                  {/* Material Level cm Card */}
                  <SensorCard
                    title="📏 Material Level (cm)"
                    value={40.0 - unitsData[selectedUnit.id].distance}
                    max={40}
                    unit="cm"
                    alertType={
                      (40.0 - unitsData[selectedUnit.id].distance) > 10.0 ? 'green' :
                      (40.0 - unitsData[selectedUnit.id].distance) >= 5.0 ? 'yellow' : 'red'
                    }
                    limitInfo="Limit: > 10cm"
                  />
                </div>

                {/* AI Status & Environmental Control split */}
                <div className="dashboard-row-split">
                  
                  {/* Left Column: AI & Risks */}
                  <div className="glass-panel panel-section">
                    <h3>🤖 AI Prediction Engine</h3>
                    
                    <div className="ai-status-row">
                      <span className="ai-status-label">Random Forest Classifier Status</span>
                      <span className={`status-badge ${unitsData[selectedUnit.id].random_forest.toLowerCase()}`}>
                        {unitsData[selectedUnit.id].random_forest}
                      </span>
                    </div>

                    <div className="ai-status-row">
                      <span className="ai-status-label">Isolation Forest Anomaly Check</span>
                      <span className={`status-badge ${unitsData[selectedUnit.id].isolation_forest === 'NORMAL' ? 'safe' : 'danger'}`}>
                        {unitsData[selectedUnit.id].isolation_forest}
                      </span>
                    </div>

                    <div className="risk-metrics">
                      <h3>⚠️ Risk Indicators</h3>
                      <div className="risk-metric-group">
                        <div className="risk-metric-header">
                          <span>Temperature Risk</span>
                          <span>{unitsData[selectedUnit.id].temperature_risk.toFixed(1)}%</span>
                        </div>
                        <div className="risk-bar-track">
                          <div className="risk-bar-fill" style={{width: `${Math.min(100, unitsData[selectedUnit.id].temperature_risk)}%`}}></div>
                        </div>
                      </div>

                      <div className="risk-metric-group">
                        <div className="risk-metric-header">
                          <span>Humidity Risk</span>
                          <span>{unitsData[selectedUnit.id].humidity_risk.toFixed(1)}%</span>
                        </div>
                        <div className="risk-bar-track">
                          <div className="risk-bar-fill" style={{width: `${Math.min(100, unitsData[selectedUnit.id].humidity_risk)}%`}}></div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Right Column: Environmental System */}
                  <div className="glass-panel panel-section">
                    <h3>❄️ Environmental System Controls</h3>
                    
                    {/* Environmental Warnings */}
                    {envStates[selectedUnit.id].ac_mode === 'Auto' && unitsData[selectedUnit.id].temperature > envStates[selectedUnit.id].temp_threshold && (
                      <div className="env-alert-banner">
                        <span>⚠️</span>
                        <span><strong>Warning:</strong> High Temp Detected. AC System Activated automatically ({unitsData[selectedUnit.id].temperature.toFixed(1)}°C &gt; {envStates[selectedUnit.id].temp_threshold.toFixed(1)}°C)</span>
                      </div>
                    )}

                    {envStates[selectedUnit.id].dryer_mode === 'Auto' && unitsData[selectedUnit.id].humidity > envStates[selectedUnit.id].humidity_threshold && (
                      <div className="env-alert-banner">
                        <span>⚠️</span>
                        <span><strong>Warning:</strong> High Humidity Detected. Dehumidifier Activated automatically ({unitsData[selectedUnit.id].humidity.toFixed(1)}% &gt; {envStates[selectedUnit.id].humidity_threshold.toFixed(1)}%)</span>
                      </div>
                    )}

                    <div className="env-grid">
                      {/* AC Device */}
                      <div className="env-device-card">
                        <div className="device-header">
                          <span className="device-name">Air Conditioner (AC)</span>
                          <span className={`device-status-dot ${envStates[selectedUnit.id].ac_status === 'ON' ? 'on' : 'off'}`}>
                            {envStates[selectedUnit.id].ac_status === 'ON' ? '🟢 ON' : '🔴 OFF'}
                          </span>
                        </div>
                        
                        <div className="device-mode-selector">
                          <button 
                            className={`mode-btn ${envStates[selectedUnit.id].ac_mode === 'Auto' ? 'active' : ''}`}
                            onClick={() => setEnvStates(prev => {
                              const next = { ...prev };
                              next[selectedUnit.id].ac_mode = 'Auto';
                              return next;
                            })}
                          >Auto</button>
                          <button 
                            className={`mode-btn ${envStates[selectedUnit.id].ac_mode === 'Manual' ? 'active' : ''}`}
                            onClick={() => setEnvStates(prev => {
                              const next = { ...prev };
                              next[selectedUnit.id].ac_mode = 'Manual';
                              return next;
                            })}
                          >Manual</button>
                        </div>

                        {envStates[selectedUnit.id].ac_mode === 'Manual' && (
                          <div className="device-manual-switch">
                            <span>Power State</span>
                            <label className="switch">
                              <input 
                                type="checkbox"
                                checked={envStates[selectedUnit.id].ac_status === 'ON'}
                                onChange={(e) => setEnvStates(prev => {
                                  const next = { ...prev };
                                  next[selectedUnit.id].ac_status = e.target.checked ? 'ON' : 'OFF';
                                  return next;
                                })}
                              />
                              <span className="slider"></span>
                            </label>
                          </div>
                        )}

                        <div className="device-runtime">
                          ⏱️ Runtime: {formatRuntime(envStates[selectedUnit.id].ac_runtime)}
                        </div>
                      </div>

                      {/* Dehumidifier Device */}
                      <div className="env-device-card">
                        <div className="device-header">
                          <span className="device-name">Dehumidifier / Dryer</span>
                          <span className={`device-status-dot ${envStates[selectedUnit.id].dryer_status === 'ON' ? 'on' : 'off'}`}>
                            {envStates[selectedUnit.id].dryer_status === 'ON' ? '🟢 ON' : '🔴 OFF'}
                          </span>
                        </div>
                        
                        <div className="device-mode-selector">
                          <button 
                            className={`mode-btn ${envStates[selectedUnit.id].dryer_mode === 'Auto' ? 'active' : ''}`}
                            onClick={() => setEnvStates(prev => {
                              const next = { ...prev };
                              next[selectedUnit.id].dryer_mode = 'Auto';
                              return next;
                            })}
                          >Auto</button>
                          <button 
                            className={`mode-btn ${envStates[selectedUnit.id].dryer_mode === 'Manual' ? 'active' : ''}`}
                            onClick={() => setEnvStates(prev => {
                              const next = { ...prev };
                              next[selectedUnit.id].dryer_mode = 'Manual';
                              return next;
                            })}
                          >Manual</button>
                        </div>

                        {envStates[selectedUnit.id].dryer_mode === 'Manual' && (
                          <div className="device-manual-switch">
                            <span>Power State</span>
                            <label className="switch">
                              <input 
                                type="checkbox"
                                checked={envStates[selectedUnit.id].dryer_status === 'ON'}
                                onChange={(e) => setEnvStates(prev => {
                                  const next = { ...prev };
                                  next[selectedUnit.id].dryer_status = e.target.checked ? 'ON' : 'OFF';
                                  return next;
                                })}
                              />
                              <span className="slider"></span>
                            </label>
                          </div>
                        )}

                        <div className="device-runtime">
                          ⏱️ Runtime: {formatRuntime(envStates[selectedUnit.id].dryer_runtime)}
                        </div>
                      </div>
                    </div>

                    {/* Thresholds sliders */}
                    <div className="threshold-slider-group">
                      <div className="threshold-header">
                        <span>AC Temperature Trigger Threshold</span>
                        <span>{envStates[selectedUnit.id].temp_threshold.toFixed(1)}°C</span>
                      </div>
                      <input 
                        type="range" 
                        min="15" 
                        max="50" 
                        step="0.5"
                        className="slider-input"
                        value={envStates[selectedUnit.id].temp_threshold}
                        onChange={(e) => setEnvStates(prev => {
                          const next = { ...prev };
                          next[selectedUnit.id].temp_threshold = parseFloat(e.target.value);
                          return next;
                        })}
                      />
                    </div>

                    <div className="threshold-slider-group">
                      <div className="threshold-header">
                        <span>Dryer Humidity Trigger Threshold</span>
                        <span>{envStates[selectedUnit.id].humidity_threshold.toFixed(0)}%</span>
                      </div>
                      <input 
                        type="range" 
                        min="20" 
                        max="90" 
                        className="slider-input"
                        value={envStates[selectedUnit.id].humidity_threshold}
                        onChange={(e) => setEnvStates(prev => {
                          const next = { ...prev };
                          next[selectedUnit.id].humidity_threshold = parseInt(e.target.value);
                          return next;
                        })}
                      />
                    </div>

                    {/* Rules Commands Engine Flow indicator */}
                    <div className="rule-commands">
                      <div className="rule-cmd-line">
                        <span>⚡ Rule Logic:</span>
                        <span>Temp ({unitsData[selectedUnit.id].temperature.toFixed(1)}°C) &gt; Setpoint ({envStates[selectedUnit.id].temp_threshold.toFixed(1)}°C) ➔ AC CMD: </span>
                        <span className={`cmd-badge ${envStates[selectedUnit.id].ac_status === 'ON' ? 'on' : 'off'}`}>
                          {envStates[selectedUnit.id].ac_status === 'ON' ? 'TURN_ON' : 'TURN_OFF'}
                        </span>
                      </div>
                      <div className="rule-cmd-line">
                        <span>⚡ Rule Logic:</span>
                        <span>Humid ({unitsData[selectedUnit.id].humidity.toFixed(1)}%) &gt; Setpoint ({envStates[selectedUnit.id].humidity_threshold.toFixed(0)}%) ➔ Dryer CMD: </span>
                        <span className={`cmd-badge ${envStates[selectedUnit.id].dryer_status === 'ON' ? 'on' : 'off'}`}>
                          {envStates[selectedUnit.id].dryer_status === 'ON' ? 'TURN_ON' : 'TURN_OFF'}
                        </span>
                      </div>
                    </div>
                  </div>

                </div>

                {/* Live Trends Charts */}
                <div className="glass-panel charts-panel">
                  <h3>📈 Historical Trend Charts</h3>
                  <TrendCharts 
                    history={unitsHistory[selectedUnit.id] || []}
                    tempThreshold={envStates[selectedUnit.id].temp_threshold}
                    humidThreshold={envStates[selectedUnit.id].humidity_threshold}
                  />
                </div>

                {/* Device detailed parameters */}
                <div className="glass-panel panel-section">
                  <h3>🛰 Device Node Specifications</h3>
                  <div className="info-row">
                    <span className="info-label">Device Name / Node ID</span>
                    <span className="info-value">{unitsData[selectedUnit.id].device}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Last Transmission Timestamp</span>
                    <span className="info-value">{unitsData[selectedUnit.id].timestamp}</span>
                  </div>
                  <div className="info-row">
                    <span className="info-label">Environmental Alarm Trigger</span>
                    <span className="info-value" style={{color: unitsData[selectedUnit.id].status === 'SAFE' ? 'var(--safe)' : 'var(--danger)'}}>
                      {unitsData[selectedUnit.id].active_alert || "None"}
                    </span>
                  </div>
                </div>
              </>
            )}
          </main>
        </div>
      )}

      {/* Footer */}
      <footer className="footer">
        <div>REMAC Raw Material Storage Intelligence Platform © 2026</div>
        <div>Powered by React • Vite • Cloud KVDB • Scikit-learn Classifier</div>
      </footer>
    </div>
  );
}

// ============================================================
// SUB-COMPONENTS
// ============================================================

// 1. Telemetry Metric Card
function SensorCard({ title, value, max, unit, alertType, limitInfo }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  return (
    <div className="glass-panel sensor-card">
      <div className="sensor-card-top">
        <span className="sensor-card-title">{title}</span>
        <span className={`sensor-card-alert ${alertType}`}>{alertType}</span>
      </div>
      <div className="sensor-card-value">
        {value.toFixed(1)}
        <span className="sensor-card-unit">{unit}</span>
      </div>
      <div className="progress-track">
        <div className={`progress-fill ${alertType}`} style={{ width: `${pct}%` }}></div>
      </div>
      <div className="sensor-card-bottom">
        <span>0 {unit}</span>
        <span>{limitInfo}</span>
        <span>{max} {unit}</span>
      </div>
    </div>
  );
}

// Helper: Format run time inside environmental timers
function formatRuntime(totalSeconds) {
  const hrs = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  return `${hrs.toString().padStart(2, '0')}h:${mins.toString().padStart(2, '0')}m:${secs.toString().padStart(2, '0')}s`;
}

// 2. Trend charts rendered using light responsive inline SVGs
function TrendCharts({ history, tempThreshold, humidThreshold }) {
  const [activeTab, setActiveTab] = useState('temp');

  if (history.length < 2) {
    return (
      <div style={{color: 'var(--text-muted)', padding: '40px', textAlign: 'center'}}>
        Awaiting live telemetry timestamps to draw historical trends...
      </div>
    );
  }

  // Pick history array fields
  let chartTitle = "";
  let chartUnit = "";
  let dataPoints = [];
  let yMinLimit = 0;
  let yMaxLimit = 100;
  let thresholdVal = null;
  let chartType = "";

  if (activeTab === 'temp') {
    chartTitle = "Temperature Trend";
    chartUnit = "°C";
    dataPoints = history.map(h => h.Temperature);
    yMinLimit = 15;
    yMaxLimit = 50;
    thresholdVal = tempThreshold;
    chartType = "temp";
  } else if (activeTab === 'humid') {
    chartTitle = "Humidity Trend";
    chartUnit = "%";
    dataPoints = history.map(h => h.Humidity);
    yMinLimit = 0;
    yMaxLimit = 100;
    thresholdVal = humidThreshold;
    chartType = "humidity";
  } else if (activeTab === 'material_pct') {
    chartTitle = "Material Percentage Trend";
    chartUnit = "%";
    dataPoints = history.map(h => h.Material_Level);
    yMinLimit = 0;
    yMaxLimit = 100;
    chartType = "material_pct";
  } else if (activeTab === 'material_cm') {
    chartTitle = "Material Level Trend";
    chartUnit = "cm";
    dataPoints = history.map(h => 40.0 - h.Distance);
    yMinLimit = 0;
    yMaxLimit = 40;
    chartType = "material_cm";
  }

  // Draw chart dimensions
  const width = 800;
  const height = 250;
  const padLeft = 60;
  const padRight = 20;
  const padTop = 20;
  const padBottom = 40;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const n = dataPoints.length;
  const xMax = n - 1;

  // Calculate local minimum and maximum limits for auto scaling
  const minVal = Math.min(...dataPoints);
  const maxVal = Math.max(...dataPoints);
  const span = maxVal - minVal;
  
  const yMin = span === 0 ? minVal - 5.0 : minVal - 0.1 * span;
  const yMax = span === 0 ? maxVal + 5.0 : maxVal + 0.1 * span;

  // Pixel coordinates mappers
  const getX = (idx) => padLeft + (idx / xMax) * chartW;
  const getY = (val) => {
    const ySpan = yMax - yMin;
    if (ySpan === 0) return padTop + chartH / 2;
    return padTop + chartH - ((val - yMin) / ySpan) * chartH;
  };

  // Helper color thresholds
  const getColorForVal = (val) => {
    if (chartType === 'temp') {
      if (val <= tempThreshold) return "#77DD77";
      if (val <= tempThreshold + 5.0) return "#FFF2A3";
      return "#FF9F9F";
    }
    if (chartType === 'humidity') {
      if (val <= humidThreshold) return "#77DD77";
      if (val <= humidThreshold + 10.0) return "#FFF2A3";
      return "#FF9F9F";
    }
    if (chartType === 'material_pct') {
      if (val > 50.0) return "#77DD77";
      if (val > 20.0) return "#FFF2A3";
      return "#FF9F9F";
    }
    if (chartType === 'material_cm') {
      if (val > 10.0) return "#77DD77";
      if (val >= 5.0) return "#FFF2A3";
      return "#FF9F9F";
    }
    return "#77DD77";
  };

  // Y Grid marks
  const gridTicks = [];
  for (let k = 0; k < 5; k++) {
    const val = yMin + (k / 4.0) * (yMax - yMin);
    gridTicks.push(val);
  }

  // Format short timestamp
  const formatTime = (tStr) => {
    if (!tStr) return "";
    return tStr.includes(" ") ? tStr.split(" ")[1] : tStr;
  };

  return (
    <div>
      <div className="charts-tabs">
        <button className={`chart-tab-btn ${activeTab === 'temp' ? 'active' : ''}`} onClick={() => setActiveTab('temp')}>🌡 Temperature</button>
        <button className={`chart-tab-btn ${activeTab === 'humid' ? 'active' : ''}`} onClick={() => setActiveTab('humid')}>💧 Humidity</button>
        <button className={`chart-tab-btn ${activeTab === 'material_pct' ? 'active' : ''}`} onClick={() => setActiveTab('material_pct')}>📦 Material Percentage</button>
        <button className={`chart-tab-btn ${activeTab === 'material_cm' ? 'active' : ''}`} onClick={() => setActiveTab('material_cm')}>📐 Level (cm)</button>
      </div>

      <h4 style={{color: '#fff', marginBottom: '15px', fontSize: '14px'}}>{chartTitle} ({chartUnit})</h4>
      
      <div className="svg-chart-container">
        <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="auto" style={{overflow: 'visible'}}>
          {/* Y Axis Grid lines */}
          {gridTicks.map((val, idx) => {
            const yPx = getY(val);
            return (
              <g key={idx}>
                <line x1={padLeft} y1={yPx} x2={width - padRight} y2={yPx} stroke="#2e2e4a" strokeWidth="1" strokeDasharray="4,4" />
                <text x={padLeft - 10} y={yPx + 4} fill="var(--text-secondary)" fontSize="11" textAnchor="end">{val.toFixed(1)}</text>
              </g>
            );
          })}

          {/* Time axis stamps */}
          <text x={padLeft} y={height - 10} fill="var(--text-secondary)" fontSize="11" textAnchor="start">{formatTime(history[0].Timestamp)}</text>
          <text x={padLeft + chartW / 2} y={height - 10} fill="var(--text-secondary)" fontSize="11" textAnchor="middle">{formatTime(history[Math.floor(n/2)].Timestamp)}</text>
          <text x={width - padRight} y={height - 10} fill="var(--text-secondary)" fontSize="11" textAnchor="end">{formatTime(history[n-1].Timestamp)}</text>

          {/* Core axis lines */}
          <line x1={padLeft} y1={padTop} x2={padLeft} y2={height - padBottom} stroke="#3a3a5c" strokeWidth="1.5" />
          <line x1={padLeft} y1={height - padBottom} x2={width - padRight} y2={height - padBottom} stroke="#3a3a5c" strokeWidth="1.5" />

          {/* Trend lines */}
          {dataPoints.map((val, idx) => {
            if (idx === n - 1) return null;
            const x1 = getX(idx);
            const y1 = getY(val);
            const x2 = getX(idx + 1);
            const y2 = getY(dataPoints[idx + 1]);
            const avgVal = (val + dataPoints[idx + 1]) / 2.0;
            const color = getColorForVal(avgVal);
            return (
              <line key={idx} x1={x1} y1={y1} x2={x2} y2={y2} stroke={color} strokeWidth="3" strokeLinecap="round" style={{ transition: 'all 0.5s ease-in-out' }} />
            );
          })}

          {/* Trend dots */}
          {dataPoints.map((val, idx) => {
            const x = getX(idx);
            const y = getY(val);
            const color = getColorForVal(val);
            return (
              <circle key={idx} cx={x} cy={y} r="4.5" fill={color} stroke="#121226" strokeWidth="1.5" style={{ transition: 'all 0.5s ease-in-out' }} />
            );
          })}
        </svg>
      </div>
    </div>
  );
}
