const express = require('express');
const router = express.Router();
const { register, login, me } = require('../controllers/authController');
const auth = require('../config/authMiddleware');

router.post('/register', register);
router.post('/login', login);
router.get('/me', auth, me);

module.exports = router;
