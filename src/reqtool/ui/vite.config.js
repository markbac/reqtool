import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const r = (p) => path.resolve(__dirname, 'node_modules', p);

export default defineConfig({
  plugins: [react()],

  resolve: {
    // Force all packages to use the same React copy.
    dedupe: ['react', 'react-dom'],
    alias: [
      { find: /^react$/, replacement: r('react/index.js') },
      { find: /^react\/jsx-runtime$/, replacement: r('react/jsx-runtime.js') },
      { find: /^react\/jsx-dev-runtime$/, replacement: r('react/jsx-dev-runtime.js') },
      { find: /^react-dom$/, replacement: r('react-dom/index.js') },
      { find: /^react-dom\/client$/, replacement: r('react-dom/client.js') },
    ],
  },

  optimizeDeps: {
    include: ['react', 'react-dom', 'react/jsx-runtime', '@uiw/react-codemirror'],
  },

  server: {
    proxy: {
      '/requirements':   'http://localhost:8765',
      '/principles':     'http://localhost:8765',
      '/tbds':           'http://localhost:8765',
      '/products':       'http://localhost:8765',
      '/modules':        'http://localhost:8765',
      '/enums':          'http://localhost:8765',
      '/validate':       'http://localhost:8765',
      '/hierarchy':      'http://localhost:8765',
      '/kanban':         'http://localhost:8765',
      '/help':           'http://localhost:8765',
      '/filter-presets': 'http://localhost:8765',
      '/git':            'http://localhost:8765',
      '/export':         'http://localhost:8765',
      '/ws':             { target: 'ws://localhost:8765', ws: true },
    },
  },

  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.jsx'],
    // Force all imports of react/* through the same resolved path.
    // This prevents @testing-library and the app source from each getting
    // their own React instance, which causes "Invalid hook call".
    alias: [
      { find: /^react$/, replacement: new URL('./node_modules/react/index.js', import.meta.url).pathname },
      { find: /^react\/jsx-runtime$/, replacement: new URL('./node_modules/react/jsx-runtime.js', import.meta.url).pathname },
      { find: /^react\/jsx-dev-runtime$/, replacement: new URL('./node_modules/react/jsx-dev-runtime.js', import.meta.url).pathname },
      { find: /^react-dom$/, replacement: new URL('./node_modules/react-dom/index.js', import.meta.url).pathname },
      { find: /^react-dom\/client$/, replacement: new URL('./node_modules/react-dom/client.js', import.meta.url).pathname },
    ],
    deps: {
      // Inline these packages into the Vitest transform so they share
      // the same module registry as the test files.
      inline: [
        'react',
        'react-dom',
        '@testing-library/react',
        '@testing-library/user-event',
        '@testing-library/dom',
      ],
    },
  },
});
