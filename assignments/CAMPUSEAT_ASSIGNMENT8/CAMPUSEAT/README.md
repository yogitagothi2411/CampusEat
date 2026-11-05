# CampusEats REST API Service (Menu / Catalogue)
**CS543 · Web Services · Assignment 8 of 12**  
*Instructor: Dr. Pramit Mazumdar (`pramit.mazumdar@iiitvadodara.ac.in`)*

---

## ⚡ Quick Start (How to Run)

### Start Both Frontend and Backend Simultaneously (Dev Mode):
```bash
npm run dev
```
Running this single command starts both services concurrently with live file watching (`--watch`):
- **Backend REST API**: Running on **[http://localhost:3000](http://localhost:3000)** (`/items`, `/items/:id`)
- **Frontend Web Client**: Running on **[http://localhost:5000](http://localhost:5000)** (and also served directly at **[http://localhost:3000](http://localhost:3000)**)

### Start via Standard Server (PDF Deliverable):
```bash
npm start
```
Runs `node server.js` which serves both the REST API and the frontend via `express.static('public')` on `http://localhost:3000`.

### Run Automated Verification Tests:
```bash
npm test
```

---

## 👥 Team Submission Details
- **Team Members & Roll Numbers:**
  - `Member 1 Name` — Roll No: `202X00001`
  - `Member 2 Name` — Roll No: `202X00002`
- **Google Drive Demonstration Video Link:**
  - `[Insert Google Drive Link Here]`
- **Screenshots:**
  - Before POST: `screenshots/screenshot-1-before-post.png`
  - After POST: `screenshots/screenshot-2-after-post.png`

---

## 📝 Answers to Assignment Questions

### 1. Which CampusEats service did you pick, and what are its routes (method + path)?
We selected the **Menu / Catalogue Service** of CampusEats. Each entity record represents a food/beverage item in the campus cafeteria catalogue with attributes `id` (integer), `name` (string), `price` (number), `category` (string), and `available` (boolean).

The REST API exposes the following routes:

| HTTP Method | Route Path | Purpose / Description | Expected Status Codes |
| :--- | :--- | :--- | :--- |
| **`GET`** | `/items` | List all menu/catalogue items from in-memory array | `200 OK` |
| **`GET`** | `/items/:id` | Fetch details of a single item by its ID | `200 OK` / `404 Not Found` |
| **`POST`** | `/items` | Create a new menu item and append it to catalogue | `201 Created` / `422 Unprocessable` |
| **`POST`** | `/items/reset` | *(Helper)* Resets catalogue to initial 4 seed records | `200 OK` |

---

### 2. Which status codes did you return, and for which outcomes (200 / 201 / 404 / 422)?
The service strictly adheres to standard RESTful HTTP semantics:

- **`200 OK`**:
  - Returned by `GET /items` when the catalogue list is successfully retrieved.
  - Returned by `GET /items/:id` when the requested item exists in the array and is successfully returned.
  - Returned by `POST /items/reset` after resetting data to the seed records.

- **`201 Created`**:
  - Returned by `POST /items` upon successful creation and insertion of a new item into the in-memory array. The response body contains the newly created record with its assigned `id`.

- **`404 Not Found`**:
  - Returned by `GET /items/:id` when no record matches the ID provided in `req.params.id` (e.g. searching for `/items/99`). The response body returns `{ "error": "Item with id 99 not found" }`.

- **`422 Unprocessable Entity`**:
  - Returned by `POST /items` when semantic client-side payload validation fails — specifically if the required `name` property is missing/empty, or if `price` is missing or negative. Returns `{ "error": "Validation failed: 'name' is required..." }`.

---

### 3. Where did you use `req.params` and where `req.body`? Why does POST need `express.json()`?

- **Usage of `req.params`**:
  - Used in **`GET /items/:id`** as `req.params.id`. It extracts route parameters encoded in the URL path. In Express, named segments prefixed with `:` (such as `/:id`) are captured into the `req.params` object.

- **Usage of `req.body`**:
  - Used in **`POST /items`** as `req.body`. It extracts the submitted JSON payload data containing `{ name, price, category, available }` sent by the client when creating a new record.

- **Why does POST need `express.json()`?**:
  - By default in Node.js and Express, incoming HTTP request payloads are received as raw binary data streams (`ReadableStream`), and Express leaves `req.body` as `undefined`.
  - The middleware `express.json()` intercepts incoming HTTP requests whose `Content-Type` header matches `application/json`. It buffers the stream chunks, parses the raw JSON string into a native JavaScript object, and attaches it to `req.body`.
  - **Without `express.json()`**, `req.body` would be `undefined`, and attempting to read or destructure fields like `const { name } = req.body;` would throw a fatal runtime TypeError (`Cannot destructure property 'name' of 'req.body' as it is undefined`), causing the POST request to crash or fail.

---

## 📁 Project Architecture & Folder Structure

```
CAMPUSEAT/
├── backend/                     # Dedicated Backend Folder
│   ├── data/
│   │   └── seedItems.js         # In-memory array & CRUD helper methods
│   ├── routes/
│   │   └── items.js             # Express Router defining REST endpoints
│   ├── server.js                # Backend server entry point
│   └── package.json             # Backend package config
├── frontend/                    # Dedicated Frontend Folder
│   ├── index.html               # Clean, responsive Web UI
│   ├── style.css                # Modern CSS design & color schemes
│   └── app.js                   # Client-side JavaScript with fetch() calls
├── public/                      # Static assets folder (served via express.static)
│   ├── index.html
│   ├── style.css
│   └── app.js
├── screenshots/                 # Submission Screenshots
│   ├── screenshot-1-before-post.png
│   └── screenshot-2-after-post.png
├── server.js                    # Root Express server (Assignment Deliverable)
├── package.json                 # Root dependencies & scripts (express)
├── test-api.js                  # Automated test verification suite
└── README.md                    # Project documentation & rubric answers
```

---

## 🧪 Testing the REST API

### Automated Test Suite:
Run the built-in test suite:
```bash
npm test
```
All 8 verification checks test:
1. `GET /items` (Status 200, array of 4 items)
2. `GET /items/1` (Status 200, retrieves existing item)
3. `GET /items/99` (Status 404, not found error handling)
4. `POST /items` without name (Status 422, validation error)
5. `POST /items` without price (Status 422, validation error)
6. `POST /items` with valid data (Status 201, creates item #5)
7. `GET /items` after POST (Status 200, verifies item count updated to 5)
8. `GET /` (Status 200, verifies static frontend serving)

### Manual cURL / PowerShell Testing:

**1. Fetch all items:**
```bash
curl -X GET http://localhost:3000/items
```

**2. Fetch single item (200 OK):**
```bash
curl -X GET http://localhost:3000/items/1
```

**3. Fetch non-existent item (404 Not Found):**
```bash
curl -X GET http://localhost:3000/items/999
```

**4. Create item validation failure (422 Unprocessable Entity):**
```bash
curl -X POST http://localhost:3000/items -H "Content-Type: application/json" -d "{ \"price\": 50 }"
```

**5. Create item successfully (201 Created):**
```bash
curl -X POST http://localhost:3000/items -H "Content-Type: application/json" -d "{ \"name\": \"Samosa Chaat\", \"price\": 70, \"category\": \"Snacks\", \"available\": true }"
```

