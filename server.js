const express = require('express');
const path = require('path');
const app = express();
const port = process.env.PORT || 3000;

app.use(express.json());

// In-memory telemetry cache for the 10 storage units
const telemetryData = {};

// CORS Headers to allow local development testing
app.use((req, res, next) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, PUT, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') {
    return res.sendStatus(200);
  }
  next();
});

// GET: Fetch telemetry for a specific unit
app.get('/api/telemetry/:unitId', (req, res) => {
  const { unitId } = req.params;
  const data = telemetryData[unitId];
  if (!data) {
    return res.status(404).json({ error: 'No data received from hardware yet' });
  }
  res.json(data);
});

// PUT: NodeMCU uploads sensor reading
app.put('/api/telemetry/:unitId', (req, res) => {
  const { unitId } = req.params;
  telemetryData[unitId] = req.body;
  console.log(`[Telemetry Received] Unit ${unitId}:`, req.body);
  res.json({ success: true, unit: unitId });
});

// Serve the static files from the Vite build folder
app.use(express.static(path.join(__dirname, 'frontend', 'dist')));

// Fallback all other routes to React index.html for Single Page App routing
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'dist', 'index.html'));
});

app.listen(port, () => {
  console.log(`REMAC Fullstack server running on port ${port}`);
});
