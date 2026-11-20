const http = require('http');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

config.server.enhanceMiddleware = (metro) => (req, res, next) => {
  if (!req.url.startsWith('/api/')) return metro(req, res, next);
  const backend = http.request(
    { host: '127.0.0.1', port: 8000, path: req.url.slice('/api'.length), method: req.method, headers: req.headers },
    (reply) => {
      res.writeHead(reply.statusCode, reply.headers);
      reply.pipe(res);
    }
  );
  backend.on('error', () => {
    res.writeHead(502, { 'Content-Type': 'text/plain' });
    res.end('Finexa backend is not running on port 8000.');
  });
  req.pipe(backend);
};

module.exports = config;
