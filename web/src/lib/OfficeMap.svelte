<script lang="ts">
	import { AttributionControl, Map as MapLibreMap, Marker, setWorkerUrl } from 'maplibre-gl';
	// MapLibre 6 は Web Worker を別ファイルで読む。バンドル後も届くよう Vite に worker として出させる
	import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
	import { onMount } from 'svelte';
	import type { Office, OfficeWeather } from './api.ts';
	import { shortPeriod, warningText } from './weather.ts';

	let {
		office,
		scale = 1,
		weather = null
	}: {
		office: Office;
		scale?: number;
		/** 気象の帯。null なら帯を出さない（気象の設定がない拠点・まだ取れていないとき） */
		weather?: OfficeWeather | null;
	} = $props();

	const STRIP_H = 100; // 気象の帯の高さ
	let warn = $derived(warningText(weather));
	const TONE = {
		green: 'text-led-green',
		amber: 'text-led-amber',
		red: 'text-led-red',
		dim: 'text-led-dim'
	};
	const hhmm = (iso: string | null | undefined) =>
		iso ? new Date(iso).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' }) : '';

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

	// 気象の帯が出ているときは、拠点の印が帯に隠れないよう地図の中心を上にずらす
	$effect(() => {
		mapRef?.setPadding({ top: 0, left: 0, right: 0, bottom: weather ? STRIP_H : 0 });
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

	{#if weather}
		<!-- 気象の帯：天気・最高／最低・降水確率・警報注意報（気象庁防災情報 XML） -->
		<div
			class="absolute inset-x-0 bottom-0 grid grid-cols-[240px_200px_180px_1fr] border-t-[3px] border-[#222] bg-ink/92"
			style:height="{STRIP_H}px"
		>
			<div class="flex min-w-0 flex-col gap-0.5 overflow-hidden border-r-2 border-[#1d1d1d] px-4 py-2">
				<span class="text-[20px] tracking-[0.1em] text-led-dim">天気{weather.weather ? `・${weather.weather.label}` : ''}</span>
				<span class="truncate text-[36px] leading-tight">{weather.weather?.text ?? '—'}</span>
			</div>
			<div class="flex flex-col gap-0.5 border-r-2 border-[#1d1d1d] px-4 py-2">
				<span class="truncate text-[20px] tracking-[0.1em] text-led-dim">最高／最低</span>
				<span class="text-[36px] leading-tight tabular-nums whitespace-nowrap"
					>{weather.high?.value ?? '—'}<small class="text-[22px] text-led-dim">℃</small>
					<span class="text-led-dim">/</span>
					{weather.low?.value ?? '—'}<small class="text-[22px] text-led-dim">℃</small></span
				>
			</div>
			<div class="flex flex-col gap-0.5 border-r-2 border-[#1d1d1d] px-4 py-2">
				<span class="truncate text-[20px] tracking-[0.1em] text-led-dim">降水確率</span>
				<span class="text-[36px] leading-tight whitespace-nowrap tabular-nums"
					>{weather.pop?.value ?? '—'}<small class="text-[22px] text-led-dim">%</small>{#if weather.pop}<small
							class="ml-1.5 text-[18px] text-led-dim">{shortPeriod(weather.pop.label)}</small
						>{/if}</span
				>
			</div>
			<div class="flex min-w-0 flex-col gap-0.5 overflow-hidden px-4 py-2">
				<span class="flex justify-between text-[20px] tracking-[0.1em] text-led-dim">
					<span>警報・注意報</span>
					<span class="font-sans text-[16px] tracking-normal">気象庁 {hhmm(weather.forecast_time)}発表</span>
				</span>
				<span class="truncate text-[36px] leading-tight {TONE[warn.tone]}">{warn.text}</span>
			</div>
		</div>
	{/if}
</div>
