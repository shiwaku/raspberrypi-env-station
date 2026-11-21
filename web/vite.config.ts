import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		// 画面は 1 枚で、データは Python の env-dashboard から API で取るので静的ファイルにする
		sveltekit({ adapter: adapter({ fallback: 'index.html' }) })
	],
	// MapLibre の worker は ES モジュールなので、そのまま ES 形式で出す
	worker: { format: 'es' },
	build: { chunkSizeWarningLimit: 1500 }, // MapLibre だけで 1MB 近くある
	server: {
		// pnpm dev のときは API を env-dashboard（127.0.0.1:8080）へ流す
		proxy: { '/api': 'http://127.0.0.1:8080' }
	}
});
