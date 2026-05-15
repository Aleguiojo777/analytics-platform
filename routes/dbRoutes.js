const express = require('express');
const router = express.Router();
const { connect } = require('../controllers/dbController');

router.post('/connect', connect);

module.exports = router;
