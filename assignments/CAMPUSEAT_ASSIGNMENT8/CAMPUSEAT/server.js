/**
 * CS543 · WEB SERVICES · ASSIGNMENT 8 OF 12
 * Project: CampusEats REST API Service (Menu / Catalogue)
 * Deliverable: server.js
 * 
 * Goal: Expose CampusEats Menu/Catalogue service as a REST API with Node & Express:
 *       list (GET /items), fetch-one (GET /items/:id), create (POST /items),
 *       demonstrated with a simple HTML/CSS page served from express.static('public').
 */

const path = require('path');
const express = require('express');
const cors = require('cors');
const itemsRouter = require('./backend/routes/items');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware: Enable CORS for cross-origin requests
app.use(cors());

// 1. Handlers & Body Parser:
// express.json() is required to parse incoming requests with JSON bodies (req.body)
app.use(express.json());

// 4. Front-end static file serving:
// Serves static files from 'public' directory as required by assignment specification
app.use(express.static(path.join(__dirname, 'public')));

// Also serve 'frontend' directory for modular frontend organization
app.use(express.static(path.join(__dirname, 'frontend')));

// 1. Routes Definition:
// Mounts REST API routes for CampusEats items entity:
//   - GET  /items       (list all items with 200 OK)
//   - GET  /items/:id   (fetch one item with 200 OK or 404 Not Found)
//   - POST /items       (create new item with 201 Created or 422 Unprocessable Entity)
app.use('/items', itemsRouter);

// Start the server if executed directly
if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`================================================================`);
    console.log(`🍔 CampusEats REST API Service running at http://localhost:${PORT}`);
    console.log(`📂 Web UI served from /public & /frontend`);
    console.log(`🔗 REST API Routes:`);
    console.log(`   - GET  /items       (200 OK) -> List all catalogue items`);
    console.log(`   - GET  /items/:id   (200 OK / 404 Not Found) -> Fetch single item`);
    console.log(`   - POST /items       (201 Created / 422 Unprocessable) -> Create item`);
    console.log(`================================================================`);
  });
}

module.exports = app;
