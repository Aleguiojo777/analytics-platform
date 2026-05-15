const express = require('express');
const router = express.Router();
const { getTableAnalytics } = require('../controllers/analyticsController');

router.post('/table', getTableAnalytics);

module.exports = router;
