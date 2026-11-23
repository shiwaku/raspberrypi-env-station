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
		CO2_STATUS,
		co2Level,
		HUMIDITY_RANGE,
		inRange,
		LEVEL_TEXT,
		TEMP_RANGE
	} from '#lib/co2.ts';
	import DotChart from '#lib/DotChart.svelte';
	import { buildNotices } from '#lib/notices.ts';
	import OfficeMap from '#lib/OfficeMap.svelte';
	import Ticker from '#lib/Ticker.svelte';

	const LATEST_INTERVAL_MS = 30_000;
	const SERIES_INTERVAL_MS = 5 * 60_000;
	const STALE_MS = 5 * 60_000; // これより古い値しか無ければ「受信なし」と出す
	// 画面は 1920×1080 で組み、ウィンドウに合わせて拡大・縮小する
	const W = 1920;
	const H = 1080;

	let config = $state<DashboardConfig | null>(null);
	let latest = $state<Latest | null>(null);
	let co2Series = $state<Point[]>([]);
	let now = $state(Date.now());
	let innerWidth = $state(W);
	let innerHeight = $state(H);
	let scale = $derived(Math.min(innerWidth / W, innerHeight / H));
	let error = $state<string | null>(null);

	let stale = $derived(!latest?.ts || now - Date.parse(latest.ts) > STALE_MS);
	let co2 = $derived(stale ? null : (latest?.co2_ppm ?? null));
	let temp = $derived(stale ? null : (latest?.temperature_c ?? null));
	let humidity = $derived(stale ? null : (latest?.humidity_pct ?? null));
	let notices = $derived(buildNotices(latest, stale, error));

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

	const fmt = (v: number | null, digits: number) =>
		v == null ? '—' : v.toFixed(digits);
	let time = $derived(
		new Date(now).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' })
	);
	let date = $derived.by(() => {
		const d = new Date(now);
		const wd = d.toLocaleDateString('ja-JP', { weekday: 'short' });
		return `${d.getMonth() + 1}月${d.getDate()}日(${wd})`;
	});

	// 行ごとの表示（値・単位・状態・色）
	let rows = $derived([
		{
			key: 'CO₂',
			value: co2 == null ? '—' : String(Math.round(co2)),
			unit: 'ppm',
			status: co2 == null ? '受信なし' : CO2_STATUS[co2Level(co2)],
			valueClass: co2 == null ? 'text-led-dim' : LEVEL_TEXT[co2Level(co2)],
			statusClass: co2 == null ? 'text-led-dim' : LEVEL_TEXT[co2Level(co2)],
			big: true
		},
		{
			key: '室温',
			value: fmt(temp, 1),
			unit: '℃',
			status: temp == null ? '—' : inRange(temp, TEMP_RANGE) ? '基準内' : '基準外',
			valueClass: temp == null ? 'text-led-dim' : 'text-led-white',
			statusClass:
				temp == null ? 'text-led-dim' : inRange(temp, TEMP_RANGE) ? 'text-led-green' : 'text-led-amber',
			big: false
		},
		{
			key: '湿度',
			value: fmt(humidity, 0),
			unit: '%',
			status: humidity == null ? '—' : inRange(humidity, HUMIDITY_RANGE) ? '基準内' : '基準外',
			valueClass: humidity == null ? 'text-led-dim' : 'text-led-white',
			statusClass:
				humidity == null
					? 'text-led-dim'
					: inRange(humidity, HUMIDITY_RANGE)
						? 'text-led-green'
						: 'text-led-amber',
			big: false
		}
	]);

	const GRID = 'grid grid-cols-[170px_1fr_110px_330px] items-center px-9';
</script>

<svelte:window bind:innerWidth bind:innerHeight />

<main
	class="relative origin-top-left overflow-hidden bg-black"
	style:width="{W}px"
	style:height="{H}px"
	style:transform="scale({scale})"
>
	<!-- 上半分：拠点の地図（2 つまで横に並べる） -->
	<section class="absolute inset-x-0 top-0 grid h-[500px] gap-1.5 bg-black"
		style:grid-template-columns="repeat({Math.max(config?.offices.length ?? 1, 1)}, 1fr)">
		{#each config?.offices ?? [] as office (office.name)}
			<OfficeMap {office} {scale} />
		{/each}
	</section>

	<!-- 下半分：発車標風の表示板 -->
	<section
		class="led-grain absolute inset-x-0 bottom-0 flex h-[580px] flex-col border-t-[6px] border-[#1d1d1d] bg-ink"
	>
		<header class="flex items-center justify-between border-b-[3px] border-rule bg-plate px-9 py-3.5">
			<h1 class="m-0 text-[40px] font-normal tracking-[0.12em]">
				{config?.station?.name ?? ''}{config?.station?.name ? '　' : ''}室内環境<small
					class="ml-[18px] text-[24px] tracking-[0.1em] text-led-dim">INDOOR</small
				>
			</h1>
			<div class="flex items-baseline gap-[22px]">
				<span class="text-[32px] text-led-dim">{date}</span>
				<time class="text-[64px] leading-none tracking-[0.04em] text-led-amber">{time}</time>
			</div>
		</header>

		<div class="grid min-h-0 flex-1 grid-cols-[1fr_820px]">
			<div class="flex flex-col border-r-[3px] border-rule">
				<div class="{GRID} bg-[#1b1b1b] py-2.5 text-[24px] tracking-[0.2em] text-[#c8c8c2]">
					<span>項目</span><span class="text-right">現在</span><span></span><span class="pl-9"
						>状態</span
					>
				</div>
				{#each rows as row, i (row.key)}
					<div
						class="{GRID} {row.big ? 'h-[140px]' : 'h-20'} {i < rows.length - 1
							? 'border-b-[3px] border-rule'
							: ''}"
					>
						<span class="{row.big ? 'text-[48px]' : 'text-[36px]'} tracking-[0.16em]">{row.key}</span>
						<span
							class="text-right leading-none tabular-nums {row.big
								? 'text-[124px]'
								: 'text-[60px]'} {row.valueClass}">{row.value}</span
						>
						<span
							class="self-end pl-3.5 text-led-dim {row.big
								? 'pb-[22px] text-[40px]'
								: 'pb-2.5 text-[30px]'}">{row.unit}</span
						>
						<span
							class="pl-9 tracking-[0.14em] {row.big ? 'text-[56px]' : 'text-[46px]'} {row.statusClass}"
							>{row.status}</span
						>
					</div>
				{/each}
			</div>

			<div class="flex flex-col px-9 pt-[22px] pb-[18px]">
				<div class="mb-3 flex justify-between text-[26px] tracking-[0.14em] text-[#c8c8c2]">
					<span>CO₂　過去24時間</span>
					<span
						><span class="text-led-green">■</span>〜1000 <span class="text-led-amber">■</span
						>1000〜 <span class="text-led-red">■</span>1500〜</span
					>
				</div>
				<div class="min-h-0 flex-1">
					<DotChart points={co2Series} />
				</div>
			</div>
		</div>

		<Ticker {notices} />
	</section>
</main>
