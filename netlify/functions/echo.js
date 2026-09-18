const handler = require('../../api/echo.js');

exports.handler = async (event) => {
  let statusCode = 200;
  const headers = {};
  const res = {
    setHeader: (key, value) => { headers[key] = value; },
    status: (code) => {
      statusCode = code;
      return {
        json: (body) => ({ statusCode, headers: { ...headers, 'content-type': 'application/json; charset=utf-8' }, body: JSON.stringify(body) })
      };
    }
  };
  const req = { method: event.httpMethod, body: event.body || '{}' };
  return handler(req, res);
};
