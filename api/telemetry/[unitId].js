export default async function handler(req, res) {
  // Allow CORS (required for local development and direct HTTP uploads)
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  const { unitId } = req.query;

  // Use our active, verified JSONBlob as the cloud key-value store under the hood
  const jsonBlobUrl = 'https://jsonblob.com/api/jsonBlob/019f4ab1-f7e9-7797-aad7-e56a4a77fc86';

  if (req.method === 'GET') {
    try {
      const response = await fetch(jsonBlobUrl);
      if (response.ok) {
        const data = await response.json();
        return res.status(200).json(data);
      }
      return res.status(response.status).json({ error: 'Failed to fetch telemetry from cloud database' });
    } catch (e) {
      return res.status(500).json({ error: e.message });
    }
  }

  if (req.method === 'PUT' || req.method === 'POST') {
    try {
      const payload = req.body;
      const response = await fetch(jsonBlobUrl, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (response.ok) {
        return res.status(200).json({ success: true });
      }
      return res.status(response.status).json({ error: 'Failed to save telemetry to cloud database' });
    } catch (e) {
      return res.status(500).json({ error: e.message });
    }
  }

  return res.status(405).json({ error: 'Method not allowed' });
}
