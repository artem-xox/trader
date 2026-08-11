import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vite';

// The agent app in dev — `make app`. In production there is no proxy at all:
// FastAPI serves this build itself, so the SPA and the API share an origin and
// every request below is a same-origin relative path either way.
const DEV_API = 'http://127.0.0.1:8000';

// The document CSP in index.html is written for what we ship. `vite dev` serves
// CSS as JS that injects a <style> tag, which `style-src 'self'` blocks, and
// polls for restarts from a blob: worker. Relax exactly those two in dev; the
// built document stays strict. (Same trick as farkle's web app.)
const devCsp = (): Plugin => ({
  name: 'trader-dev-csp',
  apply: 'serve',
  transformIndexHtml: (html) =>
    html.replace("style-src 'self'", "style-src 'self' 'unsafe-inline'; worker-src 'self' blob:"),
});

export default defineConfig({
  plugins: [react(), devCsp()],
  server: {
    proxy: {
      // `/agent` is proxied too: it is the endpoint the Telegram worker uses,
      // and being able to hit it from the browser is useful when comparing the
      // two clients against the same run.
      '/api': { target: DEV_API, changeOrigin: true },
      '/agent': { target: DEV_API, changeOrigin: true },
    },
  },
});
