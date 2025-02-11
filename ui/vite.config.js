import { defineConfig } from 'vite';

export default defineConfig({
    server: {
        // Proxy API calls
        proxy: {
            '/api': {
                target: 'http://localhost:8000',
                changeOrigin: true,
                // rewrite: (path) => path.replace(/^\/api/, ''), // if needed
            },
        },
    },
});
