const express = require('express');
const router = express.Router();
const { getTableAnalytics, getExecutiveSummary } = require('../controllers/analyticsController');

router.post('/table', getTableAnalytics);
router.post('/executive-summary', getExecutiveSummary);

module.exports = router;
