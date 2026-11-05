/**
 * CampusEats - Menu / Catalogue In-Memory Data Store
 * Source of truth for Assignment 8 (CS543 Web Services)
 */

const initialSeedItems = [
  {
    id: 1,
    name: "Paneer Tikka Roll",
    price: 120,
    category: "Snacks",
    available: true
  },
  {
    id: 2,
    name: "Veg Cheese Burger",
    price: 90,
    category: "Fast Food",
    available: true
  },
  {
    id: 3,
    name: "Masala Chai",
    price: 20,
    category: "Beverages",
    available: true
  },
  {
    id: 4,
    name: "Cold Coffee",
    price: 50,
    category: "Beverages",
    available: false
  }
];

// In-memory array (source of truth)
let items = JSON.parse(JSON.stringify(initialSeedItems));
let nextId = 5;

// Helper getters and mutators
const getItems = () => items;

const getItemById = (id) => items.find((item) => item.id === Number(id));

const addItem = (itemData) => {
  const newItem = {
    id: nextId++,
    name: itemData.name.trim(),
    price: Number(itemData.price),
    category: itemData.category && itemData.category.trim() !== "" ? itemData.category.trim() : "General",
    available: itemData.available !== undefined ? Boolean(itemData.available) : true
  };
  items.push(newItem);
  return newItem;
};

const resetItems = () => {
  items = JSON.parse(JSON.stringify(initialSeedItems));
  nextId = 5;
  return items;
};

module.exports = {
  items,
  getItems,
  getItemById,
  addItem,
  resetItems
};

