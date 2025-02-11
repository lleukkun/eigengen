const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = {
  server: {
    baseDir: "dist",
    middleware: [
      createProxyMiddleware({
        target: 'http://localhost:8000',
        changeOrigin: true
      })
    ]
  }
};
