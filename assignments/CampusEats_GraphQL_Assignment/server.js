const path = require('path');
const express = require('express');
const { ApolloServer } = require('@apollo/server');
const { expressMiddleware } = require('@as-integrations/express5');
const { ApolloServerPluginDrainHttpServer } = require('@apollo/server/plugin/drainHttpServer');
const http = require('http');
const cors = require('cors');
const bodyParser = require('body-parser');
const fs = require('fs');
const pool = require('./db');

async function startServer() {
  const app = express();
  const httpServer = http.createServer(app);
  const typeDefs = fs.readFileSync(path.join(__dirname, 'schema.graphql'), 'utf8');

  const resolvers = {
    Query: {
      dishes: async () => {
        const [rows] = await pool.query(
          'SELECT id, name, price, available FROM dishes ORDER BY id'
        );
        return rows.map(row => ({ ...row, price: Number(row.price), available: Boolean(row.available) }));
      },
      dish: async (_, { id }) => {
        const [rows] = await pool.execute(
          'SELECT id, name, price, available FROM dishes WHERE id = ?',
          [id]
        );
        if (!rows.length) return null;
        const row = rows[0];
        return { ...row, price: Number(row.price), available: Boolean(row.available) };
      }
    },
    Mutation: {
      addDish: async (_, { input }) => {
        const [result] = await pool.execute(
          'INSERT INTO dishes (name, price, available) VALUES (?, ?, ?)',
          [input.name, input.price, true]
        );
        const [rows] = await pool.execute(
          'SELECT id, name, price, available FROM dishes WHERE id = ?',
          [result.insertId]
        );
        const row = rows[0];
        return { ...row, price: Number(row.price), available: Boolean(row.available) };
      }
    }
  };

  const server = new ApolloServer({
    typeDefs,
    resolvers,
    plugins: [ApolloServerPluginDrainHttpServer({ httpServer })]
  });
  await server.start();

  app.use('/graphql', cors(), bodyParser.json(), expressMiddleware(server));
  app.use(express.static(path.join(__dirname, 'public')));

  const port = process.env.PORT || 4000;
  await new Promise(resolve => httpServer.listen({ port }, resolve));
  console.log(`CampusEats running at http://localhost:${port}`);
  console.log(`GraphQL endpoint: http://localhost:${port}/graphql`);
}

startServer().catch(error => {
  console.error('Failed to start CampusEats:', error);
  process.exit(1);
});
