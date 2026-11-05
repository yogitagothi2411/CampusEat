/**
 * CampusEats Dedicated Frontend Development Server
 * Serves frontend static files on port 5000
 * Proxies API requests (/items) to backend at port 3000
 */

const path = require('path');
const express = require('express');

const app = express();
const FRONTEND_PORT = process.env.FRONTEND_PORT || 5000;
const BACKEND_PORT = process.env.PORT || 3000;

app.use(express.json());

// Proxy API requests to backend REST API service
app.all('/items*', async (req, res) => {
  const backendUrl = `http://localhost:${BACKEND_PORT}${req.originalUrl}`;
  try {
    const fetchOptions = {
      method: req.method,
      headers: {
        'Content-Type': 'application/json'
      }
    };

    if (['POST', 'PUT', 'PATCH'].includes(req.method)) {
      fetchOptions.body = JSON.stringify(req.body);
    }

    const apiRes = await fetch(backendUrl, fetchOptions);
    const data = await apiRes.text();

    res.status(apiRes.status)
       .header('Content-Type', apiRes.headers.get('content-type') || 'application/json')
       .send(data);
  } catch (err) {
    res.status(502).json({
      error: `Could not connect to Backend at http://localhost:${BACKEND_PORT}. Make sure backend is running. (${err.message})`
    });
  }
});

// Serve frontend static assets (index.html, style.css, app.js)
app.use(express.static(path.join(__dirname)));

// Root fallback to index.html
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Start listening if run directly
if (require.main === module) {
  app.listen(FRONTEND_PORT, () => {
    console.log(`================================================================`);
    console.log(`🌐 CampusEats Frontend Server running at http://localhost:${FRONTEND_PORT}`);
    console.log(`🔗 Proxying /items requests to Backend API at http://localhost:${BACKEND_PORT}`);
    console.log(`================================================================`);
  });
}

module.exports = app;

