// Lightweight adapter to parse body and provide Express-like response helpers
async function parseJsonBody(req) {
  if (!req || !req.method) return {};
  if (req.method === 'GET' || req.method === 'HEAD') return {};
  let body = '';
  for await (const chunk of req) body += chunk;
  if (!body) return {};
  try {
    return JSON.parse(body);
  } catch (e) {
    return {};
  }
}

function createRes(originalRes) {
  let _status = 200;
  const resObj = {
    status: (s) => { _status = s; return resObj; },
    json: (obj) => {
      try {
        originalRes.statusCode = _status;
        originalRes.setHeader('Content-Type', 'application/json');
        originalRes.end(JSON.stringify(obj));
      } catch (e) {
        originalRes.statusCode = 500;
        originalRes.end(JSON.stringify({ error: 'Response error' }));
      }
    }
  };
  return resObj;
}

module.exports = { parseJsonBody, createRes };
