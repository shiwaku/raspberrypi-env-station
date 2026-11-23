<script lang="ts">
	import { AttributionControl, Map as MapLibreMap, Marker, setWorkerUrl } from 'maplibre-gl';
	// MapLibre 6 は Web Worker を別ファイルで読む。バンドル後も届くよう Vite に worker として出させる
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
	import { onMount } from 'svelte';
	import type { Office } from './api.ts';

	let { office, scale = 1 }: { office: Office; scale?: number } = $props();

	// 国土地理院の地理院タイル（淡色地図）。https://maps.gsi.go.jp/development/ichiran.html
	const GSI_ATTRIBUTION =
		'<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>';
	const TILES = 'https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png';

	setWorkerUrl(workerUrl);

	let container: HTMLDivElement;
	let mapRef: MapLibreMap | undefined;

	$effect(() => {
		mapRef?.setPixelRatio(window.devicePixelRatio * scale);
	});

	onMount(() => {
		const center: [number, number] = [office.longitude, office.latitude];
		const map = (mapRef = new MapLibreMap({
			container,
			center,
			zoom: office.zoom,
			interactive: false, // 大型モニターに映すだけで、操作はしない
			attributionControl: false,
			// 画面全体を CSS で拡大するので、その分だけ細かく描いてぼやけないようにする
			pixelRatio: window.devicePixelRatio * scale,
			style: {
				version: 8,
				sources: {
					pale: {
						type: 'raster',
						tiles: [TILES],
						tileSize: 256,
						minzoom: 2,
						maxzoom: 18,
						attribution: GSI_ATTRIBUTION
					}
				},
				layers: [
					{ id: 'bg', type: 'background', paint: { 'background-color': '#000' } },
					{
						id: 'pale',
						type: 'raster',
						source: 'pale',
						// 淡色地図の明るさを反転し（最小 > 最大）、色相を戻して暗い地図にする
						paint: {
							'raster-brightness-min': 0.74,
							'raster-brightness-max': 0,
							'raster-hue-rotate': 180,
							'raster-saturation': -0.6,
							'raster-contrast': 0.15
						}
					}
				]
			}
		}));
		map.addControl(new AttributionControl({ compact: false }), 'top-right');

		const el = document.createElement('div');
		el.className = 'office-marker';
		new Marker({ element: el }).setLngLat(center).addTo(map);

		return () => map.remove();
	});
</script>

<div class="relative h-full w-full overflow-hidden bg-black">
	<div bind:this={container} class="h-full w-full"></div>
	<div
		class="absolute top-[22px] left-6 flex items-baseline gap-[18px] border-2 border-[#222] bg-ink/90 px-[22px] py-2.5"
	>
		<b class="text-[44px] font-normal tracking-[0.12em]">{office.name}</b>
		{#if office.label}
			<span class="text-[26px] tracking-[0.1em] text-led-dim">{office.label}</span>
		{/if}
	</div>
</div>
