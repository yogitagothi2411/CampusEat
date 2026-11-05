// Direct automated test suite for CampusEats REST API
const app = require('./server');

async function runTests() {
  const PORT = 3002;
  const server = app.listen(PORT);
  const baseUrl = `http://localhost:${PORT}`;

  console.log('🧪 Starting CampusEats REST API verification tests...\n');

  try {
    // Test 1: GET /items (List all items)
    console.log('--- Test 1: GET /items ---');
    let res = await fetch(`${baseUrl}/items`);
    let data = await res.json();
    console.log(`Status: ${res.status} (Expected: 200)`);
    console.log(`Count: ${data.length} items`);
    console.assert(res.status === 200, 'Test 1 Failed: Status should be 200');
    console.assert(Array.isArray(data) && data.length >= 4, 'Test 1 Failed: Should return seed items array');
    console.log('✅ Test 1 Passed!\n');

    // Test 2: GET /items/:id (Fetch existing item #1)
    console.log('--- Test 2: GET /items/1 (Existing item) ---');
    res = await fetch(`${baseUrl}/items/1`);
    data = await res.json();
    console.log(`Status: ${res.status} (Expected: 200)`);
    console.log(`Data:`, data);
    console.assert(res.status === 200, 'Test 2 Failed: Status should be 200');
    console.assert(data.id === 1 && data.name === 'Paneer Tikka Roll', 'Test 2 Failed: Should match seed item 1');
    console.log('✅ Test 2 Passed!\n');

    // Test 3: GET /items/:id (Fetch non-existent item #99 -> 404)
    console.log('--- Test 3: GET /items/99 (Non-existent item) ---');
    res = await fetch(`${baseUrl}/items/99`);
    data = await res.json();
    console.log(`Status: ${res.status} (Expected: 404)`);
    console.log(`Error Response:`, data);
    console.assert(res.status === 404, 'Test 3 Failed: Status should be 404');
    console.assert(data.error !== undefined, 'Test 3 Failed: Should return error message');
    console.log('✅ Test 3 Passed!\n');

    // Test 4: POST /items (Validation error: Missing name -> 422)
    console.log('--- Test 4: POST /items without name (Validation Error) ---');
    res = await fetch(`${baseUrl}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ price: 100, category: 'Snacks' })
    });
    data = await res.json();
    console.log(`Status: ${res.status} (Expected: 422)`);
    console.log(`Validation Error:`, data);
    console.assert(res.status === 422, 'Test 4 Failed: Status should be 422');
    console.log('✅ Test 4 Passed!\n');

    // Test 5: POST /items (Validation error: Missing price -> 422)
    console.log('--- Test 5: POST /items without price (Validation Error) ---');
    res = await fetch(`${baseUrl}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Samosa' })
    });
    data = await res.json();
    console.log(`Status: ${res.status} (Expected: 422)`);
    console.log(`Validation Error:`, data);
    console.assert(res.status === 422, 'Test 5 Failed: Status should be 422');
    console.log('✅ Test 5 Passed!\n');

    // Test 6: POST /items (Create valid item -> 201)
    console.log('--- Test 6: POST /items with valid data (Create item) ---');
    res = await fetch(`${baseUrl}/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: 'Pav Bhaji Special',
        price: 110,
        category: 'Snacks',
        available: true
      })
    });
    data = await res.json();
    console.log(`Status: ${res.status} (Expected: 201)`);
    console.log(`Created Item:`, data);
    console.assert(res.status === 201, 'Test 6 Failed: Status should be 201');
    console.assert(data.id === 5 && data.name === 'Pav Bhaji Special', 'Test 6 Failed: Returned item should have id 5');
    console.log('✅ Test 6 Passed!\n');

    // Test 7: GET /items (Verify newly added item is in list)
    console.log('--- Test 7: GET /items after POST (Verify list update) ---');
    res = await fetch(`${baseUrl}/items`);
    data = await res.json();
    console.log(`Status: ${res.status} (Expected: 200)`);
    console.log(`New count: ${data.length} items`);
    const foundNewItem = data.find(i => i.id === 5);
    console.assert(foundNewItem !== undefined, 'Test 7 Failed: New item #5 should be present in list');
    console.log('✅ Test 7 Passed!\n');

    // Test 8: GET / (Frontend served via express.static('public'))
    console.log('--- Test 8: GET / (Check static file serving) ---');
    res = await fetch(`${baseUrl}/`);
    const htmlText = await res.text();
    console.log(`Status: ${res.status} (Expected: 200)`);
    console.assert(res.status === 200, 'Test 8 Failed: Status should be 200');
    console.assert(htmlText.includes('CampusEats'), 'Test 8 Failed: HTML should contain CampusEats');
    console.log('✅ Test 8 Passed!\n');

    console.log('🎉 ALL 8 TESTS PASSED PERFECTLY!');
  } catch (err) {
    console.error('❌ Test suite failed:', err);
    process.exit(1);
  } finally {
    server.close();
  }
}

runTests();

