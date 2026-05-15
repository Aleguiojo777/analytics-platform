const express = require('express');
const router = express.Router();
const { connect } = require('../controllers/dbController');
const auth = require('../config/authMiddleware');

router.post('/connect', auth, connect);

module.exports = router;
