import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import searchHandler from '../api/search-support.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const port = Number(process.env.PORT || 8787);
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.md': 'text/markdown; charset=utf-8' };

function sendJson(res, code, body) {
  res.writeHead(code, { 'content-type': 'application/json; charset=utf-8', 'access-control-allow-origin': '*' });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://localhost:${port}`);
  if (url.pathname === '/api/search-support') {
    const mockReq = { url: url.toString(), query: Object.fromEntries(url.searchParams.entries()) };
    const mockRes = {
      setHeader: (key, value) => res.setHeader(key, value),
      status: (code) => ({ json: (body) => sendJson(res, code, body) })
    };
    return searchHandler(mockReq, mockRes);
  }
  let filePath = path.normalize(path.join(root, url.pathname === '/' ? 'index.html' : url.pathname));
  if (!filePath.startsWith(root)) return sendJson(res, 403, { error: 'Forbidden' });
  try {
    const data = await fs.readFile(filePath);
    res.writeHead(200, { 'content-type': types[path.extname(filePath)] || 'application/octet-stream' });
    res.end(data);
  } catch {
    sendJson(res, 404, { error: 'Not found' });
  }
});
server.listen(port, () => console.log(`AI Shopping Radar running at http://localhost:${port}`));
