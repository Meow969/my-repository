const handler = require('../../api/search-support.js');
exports.handler = async (event) => {
  let statusCode = 200;
  const headers = {};
  const res = {
    setHeader: (key, value) => { headers[key] = value; },
    status: (code) => { statusCode = code; return { json: (body) => ({ statusCode, headers: { ...headers, 'content-type': 'application/json' }, body: JSON.stringify(body) }) }; }
  };
  const req = { url: event.rawUrl || `http://localhost${event.path}?${event.rawQuery || ''}`, query: event.queryStringParameters || {} };
  return handler(req, res);
};
