<script lang="ts">
	import { Map as MapLibreMap, setWorkerUrl, type StyleSpecification } from 'maplibre-gl';
	// MapLibre 6 は Web Worker を別ファイルで読む。バンドル後も届くよう Vite に worker として出させる
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
	import { onMount } from 'svelte';
	import type { Basemap, Station } from './api.ts';
	import { BASEMAPS, GSI_ATTRIBUTION, tileUrl } from './basemaps.ts';

	let {
		station,
		basemaps,
		intervalS,
		scale = 1
	}: { station: Station | null; basemaps: Basemap[]; intervalS: number; scale?: number } = $props();

	let container: HTMLDivElement;
	let current = $state(0);

	// 設置場所が未設定のときは日本全体を映す
	const center = (): [number, number] =>
		station ? [station.longitude, station.latitude] : [137.0, 37.5];

	function buildStyle(): StyleSpecification {
		const sources: StyleSpecification['sources'] = {};
		const layers: StyleSpecification['layers'] = [];
		basemaps.forEach((id, i) => {
			sources[id] = {
				type: 'raster',
				tiles: [tileUrl(id)],
				tileSize: 256,
				minzoom: BASEMAPS[id].minzoom,
				maxzoom: 18,
				attribution: GSI_ATTRIBUTION
			};
			layers.push({
				id,
				type: 'raster',
				source: id,
				// 非表示の地図も透明のまま読み込んでおき、切り替えた瞬間に黒くならないようにする
				paint: { 'raster-opacity': i === 0 ? 1 : 0, 'raster-opacity-transition': { duration: 2000 } }
			});
		});
		if (station) {
			sources.station = {
				type: 'geojson',
				data: { type: 'Point', coordinates: center() }
			};
			layers.push({
				id: 'station',
				type: 'circle',
				source: 'station',
				paint: {
					'circle-radius': 9,
					'circle-color': '#0017c1', // DADS key-900
					'circle-stroke-width': 3,
					'circle-stroke-color': '#ffffff'
				}
			});
		}
		return { version: 8, sources, layers };
	}

	setWorkerUrl(workerUrl);

	let mapRef: MapLibreMap | undefined;
	$effect(() => {
		mapRef?.setPixelRatio(window.devicePixelRatio * scale);
	});

	onMount(() => {
		const map = (mapRef = new MapLibreMap({
			container,
			style: buildStyle(),
			center: center(),
			zoom: station ? 10 : 4.5,
			interactive: false, // 大型モニターに映すだけで、操作はしない
			attributionControl: { compact: false },
			// 画面全体を CSS で拡大するので、その分だけ細かく描いてぼやけないようにする
			pixelRatio: window.devicePixelRatio * scale
		}));

		// 背景地図が 2 つ以上なら、決めた間隔で順に切り替える
		const timer =
			basemaps.length > 1
				? setInterval(() => {
						const next = (current + 1) % basemaps.length;
						map.setPaintProperty(basemaps[current]!, 'raster-opacity', 0);
						map.setPaintProperty(basemaps[next]!, 'raster-opacity', 1);
						current = next;
					}, intervalS * 1000)
				: undefined;

		return () => {
			clearInterval(timer);
			map.remove();
		};
	});
</script>

<div class="relative h-full w-full overflow-hidden rounded-8 border border-solid-gray-200">
	<div bind:this={container} class="h-full w-full"></div>
	<div class="absolute top-2 left-2 rounded-6 bg-white/90 px-3 py-1 shadow-1">
		<span class="text-std-16B-170">{station?.name ?? '設置場所が未設定'}</span>
		<span class="ml-2 text-dns-14N-130 text-solid-gray-600">
			{BASEMAPS[basemaps[current] ?? 'pale'].label}
		</span>
	</div>
</div>
