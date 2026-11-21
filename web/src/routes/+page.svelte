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
	import { CO2_MESSAGE, co2Level } from '#lib/co2.ts';
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
	// 1920×1080 で組んだ画面を、ウィンドウに収まるよう拡大・縮小する
	let scale = $derived(Math.min(innerWidth / 1920, innerHeight / 1080));
	let error = $state<string | null>(null);

	let level = $derived(latest?.co2_ppm != null ? co2Level(latest.co2_ppm) : null);
	let stale = $derived(!latest?.ts || now - Date.parse(latest.ts) > STALE_MS);

	const LEVEL_CLASS = {
		good: 'text-emerald-400',
		warn: 'text-amber-400',
		bad: 'text-red-500'
	} as const;

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

<!-- 1920×1080 の大型モニターを 3〜5m 離れて見る前提の 1 画面 -->
<main
	class="grid h-[1080px] w-[1920px] origin-top-left grid-cols-[1fr_640px] grid-rows-[1fr_300px] gap-6 p-6"
	style:transform="scale({scale})"
>
	<section class="row-span-1 min-h-0">
		{#if config}
			<StationMap
				station={config.station}
				basemaps={config.basemaps}
				intervalS={config.basemap_interval_s}
			/>
		{/if}
	</section>

	<aside class="row-span-2 flex min-h-0 flex-col gap-6">
		<div class="text-right text-4xl font-bold tabular-nums">{clock}</div>

		<div class="rounded-xl bg-slate-900 p-6">
			<div class="text-2xl text-slate-400">CO2</div>
			<div class="flex items-baseline gap-4">
				<span class="text-9xl font-bold tabular-nums {level ? LEVEL_CLASS[level] : ''}">
					{fmt(latest?.co2_ppm, 0)}
				</span>
				<span class="text-4xl text-slate-400">ppm</span>
			</div>
			<div class="mt-2 text-3xl {level ? LEVEL_CLASS[level] : 'text-slate-500'}">
				{level ? CO2_MESSAGE[level] : '—'}
			</div>
			<div class="mt-4 text-4xl tabular-nums">
				{fmt(latest?.temperature_c, 1)} ℃ ・ {fmt(latest?.humidity_pct, 0)} %
			</div>
			{#if stale}
				<div class="mt-4 text-2xl text-amber-400">計測値が届いていません（env-station を確認）</div>
			{/if}
		</div>

		<div class="flex min-h-0 flex-1 flex-col rounded-xl bg-slate-900 p-6">
			<div class="text-2xl text-slate-400">CO2 の推移（直近 24 時間）</div>
			<div class="min-h-0 flex-1">
				<LineChart points={co2Series} unit="" threshold={1000} color="#38bdf8" />
			</div>
		</div>

		<div class="rounded-xl bg-slate-900 p-6 text-2xl text-slate-500">
			鉄道・飛行機（データの入手先を調査中）
		</div>
	</aside>

	<section class="rounded-xl bg-slate-900 p-6">
		<div class="text-2xl text-slate-400">警報・注意報・災危通報</div>
		<div class="mt-4 text-3xl text-slate-500">未実装（気象庁 XML・qzss_dcr とつなぐ）</div>
	</section>

	{#if error}
		<div class="fixed bottom-4 left-4 rounded bg-red-900/90 px-4 py-2 text-xl">{error}</div>
	{/if}
</main>
