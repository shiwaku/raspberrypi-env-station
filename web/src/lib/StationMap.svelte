<script lang="ts">
	import {
		AttributionControl,
		Map as MapLibreMap,
		Marker,
		setWorkerUrl,
		type StyleSpecification
	} from 'maplibre-gl';
	// MapLibre 6 は Web Worker を別ファイルで読む。バンドル後も届くよう Vite に worker として出させる
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
	import { onMount } from 'svelte';
	import type { Basemap, Station } from './api.ts';
	import { BASEMAPS, GSI_ATTRIBUTION, tileUrl } from './basemaps.ts';

	let {
		station,
		basemaps,
		intervalS,
		scale = 1,
		padRight = 0
	}: {
		station: Station | null;
		basemaps: Basemap[];
		intervalS: number;
		scale?: number;
		/** 右側に重ねるパネルの幅。地点がパネルに隠れないよう、残りの範囲の中央に置く */
		padRight?: number;
	} = $props();

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
				paint: {
					'raster-opacity': i === 0 ? 1 : 0,
					'raster-opacity-transition': { duration: 2000 },
					// 地図は背景なので色を少し抑え、地点の印とパネルを目立たせる
					'raster-saturation': id === 'seamlessphoto' ? -0.2 : -0.4,
					'raster-contrast': -0.1
				}
			});
		});
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
			zoom: station ? 12 : 4.5,
			interactive: false, // 大型モニターに映すだけで、操作はしない
			attributionControl: false,
			// 画面全体を CSS で拡大するので、その分だけ細かく描いてぼやけないようにする
			pixelRatio: window.devicePixelRatio * scale
		}));
		map.setPadding({ top: 0, bottom: 0, left: 0, right: padRight });
		// 右側はパネルで隠れるので、出典は左下に出す
		map.addControl(new AttributionControl({ compact: false }), 'bottom-left');

		// 地点の印は DOM で描き、CSS で波紋を付ける（app.css の .station-marker）
		if (station) {
			const el = document.createElement('div');
			el.className = 'station-marker';
			new Marker({ element: el }).setLngLat(center()).addTo(map);
		}

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

<div class="absolute inset-0">
	<div bind:this={container} class="h-full w-full"></div>
	<div
		class="absolute top-3 left-3 flex items-center gap-3 rounded-full bg-white px-4 py-2 shadow-2"
	>
		<span class="size-2.5 rounded-full bg-key-900"></span>
		<span class="text-std-16B-170">{station?.name ?? '設置場所が未設定'}</span>
		<span class="h-4 w-px bg-solid-gray-200"></span>
		<span class="text-dns-14N-130 text-solid-gray-600">
			{BASEMAPS[basemaps[current] ?? 'pale'].label}
		</span>
	</div>
</div>
