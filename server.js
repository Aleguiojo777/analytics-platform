require('dotenv').config();
const express = require('express');
const cors = require('cors');
const path = require('path');

const authRoutes = require('./routes/authRoutes');
const dbRoutes = require('./routes/dbRoutes');
const analyticsRoutes = require('./routes/analyticsRoutes');

const app = express();

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'frontend')));

// API Routes
app.use('/api/auth', authRoutes);
app.use('/api/db', dbRoutes);
app.use('/api/analytics', analyticsRoutes);

// Serve frontend for all non-API routes
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'frontend', 'index.html'));
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`\n🚀 Analytics Platform running at http://localhost:${PORT}`);
  console.log(`   Press Ctrl+C to stop\n`);
});
