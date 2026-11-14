import { build } from 'esbuild';
import { mkdir, rm, writeFile } from 'node:fs/promises';

await rm('dist', { recursive: true, force: true });
await mkdir('dist', { recursive: true });
await build({
  entryPoints: ['entry.tsx'],
  bundle: true,
  minify: true,
  outfile: 'dist/app.js',
  define: { 'process.env.NODE_ENV': '"production"' },
  jsx: 'automatic',
  alias: {
    react: './node_modules/react',
    'react-dom': './node_modules/react-dom',
  },
  metafile: true,
});
await writeFile('dist/index.html', `<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="color-scheme" content="dark"><title>Афиша Башкортостана</title><script src="https://telegram.org/js/telegram-web-app.js"></script><link rel="stylesheet" href="/app.css"></head><body><div id="root"></div><script defer src="/app.js"></script></body></html>`);
