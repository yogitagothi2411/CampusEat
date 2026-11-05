const express = require('express');
const router = express.Router();
const { getItems, getItemById, addItem, resetItems } = require('../data/seedItems');

/**
 * 1. GET /items
 * Returns the list of all menu/catalogue items.
 * Status: 200 OK
 */
router.get('/', (req, res) => {
  const items = getItems();
  return res.status(200).json(items);
});

/**
 * 2. GET /items/:id
 * Fetches a single item by id from req.params.id.
 * Status: 200 OK (if found), 404 Not Found (if absent)
 */
router.get('/:id', (req, res) => {
  const id = parseInt(req.params.id, 10);

  if (isNaN(id)) {
    return res.status(400).json({ error: 'Item ID must be a valid number' });
  }

  const item = getItemById(id);

  if (!item) {
    return res.status(404).json({ error: `Item with id ${req.params.id} not found` });
  }

  return res.status(200).json(item);
});

/**
 * 3. POST /items
 * Creates a new menu item.
 * Reads JSON payload from req.body (parsed via express.json()).
 * Validates required fields: reply 422 if 'name' or valid 'price' is missing.
 * Status: 201 Created (success), 422 Unprocessable Entity (validation error)
 */
router.post('/', (req, res) => {
  const { name, price, category, available } = req.body;

  // Validation: 'name' is required and must not be empty
  if (!name || typeof name !== 'string' || name.trim() === '') {
    return res.status(422).json({
      error: "Validation failed: 'name' is required and cannot be empty"
    });
  }

  // Validation: 'price' is required, must be a non-negative number
  if (
    price === undefined ||
    price === null ||
    price === '' ||
    isNaN(Number(price)) ||
    Number(price) < 0
  ) {
    return res.status(422).json({
      error: "Validation failed: 'price' must be a valid non-negative number"
    });
  }

  const newItem = addItem({ name, price, category, available });
  return res.status(201).json(newItem);
});

/**
 * Optional helper route: POST /items/reset
 * Resets the in-memory array back to initial seed records for demo testing.
 */
router.post('/reset', (req, res) => {
  const resetList = resetItems();
  return res.status(200).json({
    message: 'Data successfully reset to initial seed records',
    items: resetList
  });
});

module.exports = router;

