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
	import {
		CO2_BADGE_CLASS,
		CO2_DOT_CLASS,
		CO2_LIMIT,
		CO2_MESSAGE,
		CO2_TEXT_CLASS,
		co2Level
	} from '#lib/co2.ts';
	import LineChart from '#lib/LineChart.svelte';
	import StationMap from '#lib/StationMap.svelte';

	const LATEST_INTERVAL_MS = 30_000;
	const SERIES_INTERVAL_MS = 5 * 60_000;
	const STALE_MS = 5 * 60_000; // これより古い値しか無ければ「届いていない」と出す
	const PANEL_W = 300; // 右のパネルの幅（960×540 の画面上）
	const GAP = 12;

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

	const fmt = (v: number | null | undefined, digits: number) =>
		v == null ? '—' : v.toLocaleString('ja-JP', { maximumFractionDigits: digits, minimumFractionDigits: digits });
	const timeOf = (t: number) =>
		new Date(t).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
	let date = $derived(
		new Date(now).toLocaleDateString('ja-JP', { month: 'long', day: 'numeric', weekday: 'short' })
	);
</script>

<svelte:window bind:innerWidth bind:innerHeight />

<main
	class="relative h-[540px] w-[960px] origin-top-left overflow-hidden bg-solid-gray-100"
	style:transform="scale({scale})"
>
	{#if config}
		<StationMap
			station={config.station}
			basemaps={config.basemaps}
			intervalS={config.basemap_interval_s}
			{scale}
			padRight={PANEL_W + GAP * 2}
		/>
	{/if}

	<aside
		class="absolute flex flex-col gap-4 rounded-16 bg-white p-5 shadow-4"
		style:top="{GAP}px"
		style:right="{GAP}px"
		style:bottom="{GAP}px"
		style:width="{PANEL_W}px"
	>
		<header class="flex items-baseline justify-between">
			<span class="text-dns-16N-130 text-solid-gray-600">{date}</span>
			<time class="text-std-32B-150 tabular-nums">{timeOf(now)}</time>
		</header>

		<section>
			<h2 class="text-dns-16B-130 text-solid-gray-600">CO₂ 濃度</h2>
			<p class="mt-1 flex items-baseline gap-2">
				<span class="text-dsp-64B-140 tabular-nums {level ? CO2_TEXT_CLASS[level] : ''}">
					{fmt(latest?.co2_ppm, 0)}
				</span>
				<span class="text-std-20N-150 text-solid-gray-600">ppm</span>
			</p>
			{#if level}
				<p
					class="inline-flex items-center gap-2 rounded-full px-3 py-1 text-dns-16B-130 {CO2_BADGE_CLASS[
						level
					]}"
				>
					<span class="size-2 rounded-full {CO2_DOT_CLASS[level]}"></span>
					{CO2_MESSAGE[level]}
				</p>
			{/if}
		</section>

		<section class="grid grid-cols-2 gap-2">
			{#each [{ label: '室温', value: fmt(latest?.temperature_c, 1), unit: '℃' }, { label: '湿度', value: fmt(latest?.humidity_pct, 0), unit: '%' }] as tile (tile.label)}
				<div class="rounded-12 bg-solid-gray-50 px-4 py-2">
					<h2 class="text-dns-14N-130 text-solid-gray-600">{tile.label}</h2>
					<p class="flex items-baseline gap-1">
						<span class="text-std-28B-150 tabular-nums">{tile.value}</span>
						<span class="text-dns-16N-130 text-solid-gray-600">{tile.unit}</span>
					</p>
				</div>
			{/each}
		</section>

		<section class="flex min-h-0 flex-1 flex-col gap-1">
			<div class="flex items-center justify-between">
				<h2 class="text-dns-14B-130 text-solid-gray-600">過去 24 時間（ppm）</h2>
				<span class="flex items-center gap-1 text-dns-14N-130 text-solid-gray-600">
					<svg width="16" height="2" class="block" aria-hidden="true">
						<line x1="0" x2="16" y1="1" y2="1" stroke="var(--color-warning-orange-1)" stroke-width="2" stroke-dasharray="4 3" />
					</svg>
					基準 {CO2_LIMIT.toLocaleString('ja-JP')}
				</span>
			</div>
			<div class="min-h-0 flex-1">
				<LineChart points={co2Series} threshold={CO2_LIMIT} />
			</div>
		</section>

		<footer class="text-dns-14N-130 text-solid-gray-536">
			{#if stale}
				<span class="font-bold text-warning-orange-2">計測値が届いていません</span>
			{:else if latest?.ts}
				{timeOf(Date.parse(latest.ts))} 計測
			{/if}
		</footer>
	</aside>

	{#if error}
		<div
			class="absolute bottom-10 left-3 rounded-8 bg-error-2 px-3 py-2 text-dns-14N-130 text-white shadow-2"
		>
			{error}
		</div>
	{/if}
</main>
