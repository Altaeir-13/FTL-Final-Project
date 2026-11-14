import http from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root = path.join(path.dirname(fileURLToPath(import.meta.url)), 'dist');
const port = Number(process.env.PORT || 4173);
const prefix = '/FTL-Final-Project/';
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript', '.css':'text/css', '.json':'application/json', '.geojson':'application/geo+json', '.csv':'text/csv; charset=utf-8', '.svg':'image/svg+xml', '.png':'image/png' };
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    let name = decodeURIComponent(url.pathname);
    if (name.startsWith(prefix)) name = name.slice(prefix.length);
    const target = path.resolve(root, '.' + (name.startsWith('/') ? name : '/' + name));
    if (target !== root && !target.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
    const file = (await stat(target)).isDirectory() ? path.join(target, 'index.html') : target;
    res.writeHead(200, { 'Content-Type':types[path.extname(file)] || 'application/octet-stream', 'Cache-Control':'no-cache' });
    res.end(await readFile(file));
  } catch { res.writeHead(404, {'Content-Type':'text/plain'}).end('Arquivo não encontrado'); }
});
server.listen(port, '127.0.0.1', () => console.log(`AquaClima: http://127.0.0.1:${port}${prefix}`));
