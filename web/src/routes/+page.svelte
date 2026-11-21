<script lang="ts">
	import { onMount } from 'svelte';
	import {
		fetchConfig,
		fetchLatest,
		fetchSeries,
		type DashboardConfig,
		type Latest,
		type Point
	} from '#lib/api.ts';
	import { CO2_MESSAGE, CO2_TEXT_CLASS, co2Level } from '#lib/co2.ts';
	import LineChart from '#lib/LineChart.svelte';
	import StationMap from '#lib/StationMap.svelte';

	const LATEST_INTERVAL_MS = 30_000;
	const SERIES_INTERVAL_MS = 5 * 60_000;
	const STALE_MS = 5 * 60_000; // これより古い値しか無ければ「届いていない」と出す

	let config = $state<DashboardConfig | null>(null);
	let latest = $state<Latest | null>(null);
	let co2Series = $state<Point[]>([]);
	let now = $state(Date.now());
	let innerWidth = $state(1920);
	let innerHeight = $state(1080);
	// 画面は 960×540 で組み、ウィンドウに合わせて拡大する（1920×1080 なら 2 倍）。
	// DADS の文字スタイルをそのまま使い、2 倍にして 3〜5m 離れても読める大きさにする
	let scale = $derived(Math.min(innerWidth / 960, innerHeight / 540));
	let error = $state<string | null>(null);

	let level = $derived(latest?.co2_ppm != null ? co2Level(latest.co2_ppm) : null);
	let stale = $derived(!latest?.ts || now - Date.parse(latest.ts) > STALE_MS);

	async function refreshLatest() {
		try {
			latest = await fetchLatest();
			error = null;
		} catch (e) {
			error = String(e);
		}
	}

	async function refreshSeries() {
		try {
			co2Series = await fetchSeries('co2_ppm', 24);
		} catch (e) {
			error = String(e);
		}
	}

	onMount(() => {
		fetchConfig()
			.then((c) => (config = c))
			.catch((e) => (error = String(e)));
		refreshLatest();
		refreshSeries();
		const timers = [
			setInterval(refreshLatest, LATEST_INTERVAL_MS),
			setInterval(refreshSeries, SERIES_INTERVAL_MS),
			setInterval(() => (now = Date.now()), 1000)
		];
		return () => timers.forEach(clearInterval);
	});

	const fmt = (v: number | null | undefined, digits: number) => (v == null ? '—' : v.toFixed(digits));
	let clock = $derived(
		new Date(now).toLocaleString('ja-JP', {
			month: 'numeric',
			day: 'numeric',
			weekday: 'short',
			hour: '2-digit',
			minute: '2-digit'
		})
	);
</script>

<svelte:window bind:innerWidth bind:innerHeight />

<main
	class="grid h-[540px] w-[960px] origin-top-left grid-cols-[1fr_320px] grid-rows-[1fr_112px] gap-3 p-3"
	style:transform="scale({scale})"
>
	<section class="min-h-0">
		{#if config}
			<StationMap
				station={config.station}
				basemaps={config.basemaps}
				intervalS={config.basemap_interval_s}
				{scale}
			/>
		{/if}
	</section>

	<aside class="row-span-2 flex min-h-0 flex-col gap-3">
		<div class="text-right text-std-20B-150 tabular-nums">{clock}</div>

		<div class="rounded-8 border border-solid-gray-200 bg-white px-4 py-3">
			<h2 class="text-dns-14B-130 text-solid-gray-600">CO2</h2>
			<div class="flex items-baseline gap-2">
				<span class="text-dsp-64B-140 tabular-nums {level ? CO2_TEXT_CLASS[level] : ''}">
					{fmt(latest?.co2_ppm, 0)}
				</span>
				<span class="text-std-20N-150 text-solid-gray-600">ppm</span>
			</div>
			<p class="text-std-18B-160 {level ? CO2_TEXT_CLASS[level] : 'text-solid-gray-536'}">
				{level ? CO2_MESSAGE[level] : '—'}
			</p>
			<p class="text-std-20N-150 tabular-nums">
				{fmt(latest?.temperature_c, 1)} ℃ ・ {fmt(latest?.humidity_pct, 0)} %
			</p>
			{#if stale}
				<p class="mt-1 text-dns-14B-130 text-warning-orange-2">
					計測値が届いていません
				</p>
			{/if}
		</div>

		<div class="flex min-h-0 flex-1 flex-col rounded-8 border border-solid-gray-200 bg-white px-4 py-3">
			<h2 class="text-dns-14B-130 text-solid-gray-600">CO2 の推移（直近 24 時間）</h2>
			<div class="min-h-0 flex-1">
				<LineChart points={co2Series} threshold={1000} />
			</div>
		</div>

		<div class="rounded-8 border border-solid-gray-200 bg-white px-4 py-3">
			<h2 class="text-dns-14B-130 text-solid-gray-600">鉄道・飛行機</h2>
			<p class="text-dns-14N-130 text-solid-gray-536">データの入手先を調査中</p>
		</div>
	</aside>

	<section class="rounded-8 border border-solid-gray-200 bg-white px-4 py-3">
		<h2 class="text-dns-14B-130 text-solid-gray-600">警報・注意報・災危通報</h2>
		<p class="mt-1 text-std-16N-170 text-solid-gray-536">未実装（気象庁 XML・qzss_dcr とつなぐ）</p>
	</section>

	{#if error}
		<div class="fixed bottom-2 left-2 rounded-4 bg-error-2 px-2 py-1 text-dns-14N-130 text-white">
			{error}
		</div>
	{/if}
</main>
