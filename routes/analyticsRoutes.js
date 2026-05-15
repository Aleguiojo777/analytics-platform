const express = require('express');
const router = express.Router();
const { getTableAnalytics } = require('../controllers/analyticsController');
const auth = require('../config/authMiddleware');

router.post('/table', auth, getTableAnalytics);

module.exports = router;
