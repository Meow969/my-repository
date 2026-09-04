const vercelHandler = require('../../api/search-note.js');

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: JSON.stringify({ error: 'Method not allowed' }) };
  }
  const req = { method: 'POST', body: event.body || '{}' };
  let statusCode = 200;
  let payload = null;
  const res = {
    status(code) { statusCode = code; return this; },
    json(data) { payload = data; return this; }
  };
  await vercelHandler(req, res);
  return {
    statusCode,
    headers: { 'content-type': 'application/json; charset=utf-8' },
    body: JSON.stringify(payload || {})
  };
};
