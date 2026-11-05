/**
 * CampusEats Front-End Application Logic
 * CS543 Web Services · Assignment 8
 * Interfaces with REST API endpoints: GET /items, GET /items/:id, POST /items
 */

// DOM Elements
const itemsTbody = document.getElementById('items-tbody');
const itemCountBadge = document.getElementById('item-count-badge');
const createItemForm = document.getElementById('create-item-form');
const formFeedback = document.getElementById('form-feedback');
const fetchOneForm = document.getElementById('fetch-one-form');
const searchIdInput = document.getElementById('search-id');
const fetchResult = document.getElementById('fetch-result');
const refreshBtn = document.getElementById('refresh-btn');
const resetBtn = document.getElementById('reset-btn');

/**
 * 1. Fetch & Display all catalogue items (GET /items)
 */
async function loadItems() {
  try {
    itemsTbody.innerHTML = `
      <tr>
        <td colspan="6" class="loading-state">Fetching catalogue items from GET /items...</td>
      </tr>
    `;

    const res = await fetch('/items');
    
    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status}`);
    }

    const items = await res.json();
    renderItemsTable(items);
  } catch (err) {
    console.error('Error fetching items:', err);
    itemsTbody.innerHTML = `
      <tr>
        <td colspan="6" class="feedback-error" style="text-align: center; padding: 18px;">
          Failed to fetch items from <code>GET /items</code>. Ensure backend server is running. (${err.message})
        </td>
      </tr>
    `;
  }
}

/**
 * Render items array into HTML table rows
 */
function renderItemsTable(items) {
  itemCountBadge.textContent = `${items.length} ${items.length === 1 ? 'item' : 'items'}`;

  if (!items || items.length === 0) {
    itemsTbody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">No catalogue items found. Add one above!</td>
      </tr>
    `;
    return;
  }

  itemsTbody.innerHTML = items.map(item => `
    <tr id="item-row-${item.id}">
      <td><span class="id-badge">#${item.id}</span></td>
      <td><strong class="item-title">${escapeHtml(item.name)}</strong></td>
      <td><span class="category-tag">${escapeHtml(item.category || 'General')}</span></td>
      <td><span class="price-tag">₹${Number(item.price).toFixed(2)}</span></td>
      <td>
        <span class="status-tag ${item.available ? 'available' : 'unavailable'}">
          ${item.available ? '● Available' : '○ Out of Stock'}
        </span>
      </td>
      <td>
        <button 
          class="btn-table-action" 
          onclick="inspectItem(${item.id})"
          title="Test GET /items/${item.id}"
        >
          Inspect (GET /:id)
        </button>
      </td>
    </tr>
  `).join('');
}

/**
 * 2. Create new item (POST /items)
 */
createItemForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideFeedback();

  const name = document.getElementById('item-name').value.trim();
  const priceInput = document.getElementById('item-price').value;
  const category = document.getElementById('item-category').value;
  const available = document.getElementById('item-available').checked;

  const payload = {
    name,
    price: priceInput !== '' ? parseFloat(priceInput) : undefined,
    category,
    available
  };

  try {
    const res = await fetch('/items', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();

    if (res.status === 201) {
      // Success (201 Created)
      showFeedback(
        `✅ <strong>HTTP 201 Created</strong>: "${escapeHtml(data.name)}" added successfully with ID <code>#${data.id}</code>!`,
        'success'
      );
      createItemForm.reset();
      document.getElementById('item-available').checked = true;
      // Refresh list to show newly added item
      await loadItems();

      // Highlight the single item inspect box
      inspectItem(data.id);
    } else if (res.status === 422) {
      // Validation error (422 Unprocessable Entity)
      showFeedback(
        `⚠️ <strong>HTTP 422 Unprocessable Entity</strong>: ${escapeHtml(data.error || 'Validation error')}`,
        'error'
      );
    } else {
      showFeedback(
        `❌ <strong>HTTP ${res.status}</strong>: ${escapeHtml(data.error || 'Unexpected error occurred')}`,
        'error'
      );
    }
  } catch (err) {
    console.error('Error submitting POST /items:', err);
    showFeedback(`❌ Network Error: Could not connect to API server.`, 'error');
  }
});

/**
 * 3. Fetch single item by ID (GET /items/:id)
 */
fetchOneForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const id = searchIdInput.value.trim();
  if (id) {
    inspectItem(id);
  }
});

async function inspectItem(id) {
  searchIdInput.value = id;
  fetchResult.innerHTML = `<p class="placeholder-text">Calling <code>GET /items/${id}</code>...</p>`;

  try {
    const res = await fetch(`/items/${id}`);
    const data = await res.json();

    if (res.status === 200) {
      fetchResult.innerHTML = `
        <div class="result-card">
          <div class="result-header">
            <span class="status-badge s200">200 OK</span>
            <span class="id-badge">ID #${data.id}</span>
          </div>
          <div class="result-name">${escapeHtml(data.name)}</div>
          <div class="result-details">
            <span><strong>Price:</strong> ₹${Number(data.price).toFixed(2)}</span>
            <span><strong>Category:</strong> ${escapeHtml(data.category || 'General')}</span>
            <span><strong>Status:</strong> ${data.available ? '<span style="color:#15803d">Available</span>' : '<span style="color:#b91c1c">Out of stock</span>'}</span>
          </div>
        </div>
      `;
    } else if (res.status === 404) {
      fetchResult.innerHTML = `
        <div class="feedback-alert feedback-error" style="display:block; margin: 0;">
          ❌ <strong>HTTP 404 Not Found</strong>: ${escapeHtml(data.error || `Item #${id} not found`)}
        </div>
      `;
    } else {
      fetchResult.innerHTML = `
        <div class="feedback-alert feedback-error" style="display:block; margin: 0;">
          ⚠️ <strong>HTTP ${res.status}</strong>: ${escapeHtml(data.error || 'Error fetching item')}
        </div>
      `;
    }
  } catch (err) {
    fetchResult.innerHTML = `
      <div class="feedback-alert feedback-error" style="display:block; margin: 0;">
        ❌ Connection error: ${escapeHtml(err.message)}
      </div>
    `;
  }
}

/**
 * Helper alert display
 */
function showFeedback(htmlMessage, type = 'success') {
  formFeedback.className = `feedback-alert feedback-${type}`;
  formFeedback.innerHTML = htmlMessage;
  formFeedback.classList.remove('hidden');
}

function hideFeedback() {
  formFeedback.classList.add('hidden');
  formFeedback.innerHTML = '';
}

/**
 * Utilities
 */
function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Global inspectItem binding for inline HTML onclick
window.inspectItem = inspectItem;

// Button Event Listeners
refreshBtn.addEventListener('click', loadItems);

resetBtn.addEventListener('click', async () => {
  if (confirm('Reset items back to the original 4 seed records?')) {
    try {
      const res = await fetch('/items/reset', { method: 'POST' });
      if (res.ok) {
        showFeedback('⏮ In-memory array reset to original 4 seed items.', 'success');
        await loadItems();
        fetchResult.innerHTML = `<p class="placeholder-text">Enter an ID above or click any item in the table to test <code>GET /items/:id</code></p>`;
      }
    } catch (err) {
      alert('Failed to reset: ' + err.message);
    }
  }
});

// Initial load
loadItems();

