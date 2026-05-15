const { parseJsonBody, createRes } = require('../_shim');
const { connect } = require('../../controllers/dbController');

module.exports = async (req, res) => {
  req.body = await parseJsonBody(req);
  req.headers = req.headers || {};
  const shimRes = createRes(res);
  try {
    await connect(req, shimRes);
  } catch (err) {
    res.statusCode = 500;
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ error: err.message }));
  }
};
