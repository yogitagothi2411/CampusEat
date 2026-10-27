# CampusEats GraphQL — Assignment 7

## Team details
-Team 23 – Yogita Gothi (20251651107), 
           Janvi Goud (20251651047), 
           Shreya Verma (20251651086), 
           Sonali Choudhary (20251651088)
- GitHub repository: [(https://github.com/yogitagothi2411/CampusEat)]


## 1. Which CampusEats service did you pick?
We picked the **Menu/Dishes service**. It lists campus food dishes with their ID, name, price, and availability, and lets a client add a new dish.

## 2. Name one field a client can skip and one it cannot. Why do we use `!`?
A client can skip `available` in a query if it does not need to display availability. It cannot omit `name` from the `AddDishInput`, because `name: String!` marks it as required. In GraphQL, `!` means a field/input is non-null and must not be null; for an input field it must be supplied.

## 3. Map it to SQL: which part became WHERE, and which resolver ran INSERT?
For the by-ID query, the GraphQL argument `id` is used in SQL as `WHERE id = ?` in the `dish` resolver. The `addDish` mutation resolver runs `INSERT INTO dishes (name, price, available) VALUES (?, ?, ?)`.

## Requirements
- Node.js 18+ recommended
- MySQL server

## Run the project
1. Create the database and seed rows by running `schema.sql` in MySQL.
2. In this project folder, run `npm install`.
3. Set `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` environment variables if your MySQL configuration differs from the defaults.
4. Run `npm start`.
5. Open `http://localhost:4000` in a browser. The GraphQL endpoint is `http://localhost:4000/graphql`.
6. Add a dish using the form and take before/after screenshots for submission.

## Example GraphQL query
```graphql
query {
  dishes {
    id
    name
    price
    available
  }
}
```

## Example GraphQL mutation
```graphql
mutation {
  addDish(input: { name: "Paneer Roll", price: 90 }) {
    id
    name
    price
  }
}
```

## Files
- `schema.graphql`: GraphQL object, query, mutation, and input schema
- `db.js`: MySQL connection pool using `mysql2`
- `server.js`: Apollo Server and SQL resolvers
- `schema.sql`: table and seed data
- `public/index.html`: HTML/CSS page that reads and adds dishes
