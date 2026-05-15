const jwt = require('jsonwebtoken');

const SECRET = process.env.JWT_SECRET || 'fallback_secret_change_me';

module.exports = {
  sign: (payload) => jwt.sign(payload, SECRET, { expiresIn: '8h' }),
  verify: (token) => jwt.verify(token, SECRET)
};
