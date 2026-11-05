const path = require('path');
const express = require('express');
const cors = require('cors');
const itemsRouter = require('./routes/items');

const app = express();
const PORT = process.env.PORT || 3000;

// Enable CORS
app.use(cors());

// Middleware to parse JSON request bodies into req.body
app.use(express.json());

// Serve static frontend assets
app.use(express.static(path.join(__dirname, '../public')));
app.use(express.static(path.join(__dirname, '../frontend')));

// Mount REST API routes for items
app.use('/items', itemsRouter);

// Root fallback to index.html if needed
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, '../public/index.html'));
});

// Start listening if run directly
if (require.main === module) {
  app.listen(PORT, () => {
    console.log(`======================================================`);
    console.log(`🚀 CampusEats Service API running at: http://localhost:${PORT}`);
    console.log(`📦 Routes:`);
    console.log(`   - GET  /items       -> List all items (200)`);
    console.log(`   - GET  /items/:id   -> Fetch item by ID (200 / 404)`);
    console.log(`   - POST /items       -> Create new item (201 / 422)`);
    console.log(`======================================================`);
  });
}

module.exports = app;

