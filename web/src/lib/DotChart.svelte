<script lang="ts">
	import type { Point } from './api.ts';
	import { co2Level, CO2_LIMIT, LEVEL_FILL } from './co2.ts';

	// 発車標の LED の点で描く、CO2 の棒グラフ。1 列 = 30 分の平均（24 時間で 48 列）
	let { points, hours = 24 }: { points: Point[]; hours?: number } = $props();

	let COLS = $derived(hours * 2);
	const ROWS = 14;
	const MAX = 2000; // 縦軸の上限（ppm）。超えた値は上端で止める
	const LABEL_H = 34;
	const HOUR = 3600_000;

	let width = $state(750);
	let height = $state(240);
	let now = $derived(points.length ? Date.parse(points[points.length - 1]![0]) : Date.now());
	let t0 = $derived(now - hours * HOUR);

	// 列ごとの平均。値がない列は null（すべて消灯）
	let columns = $derived.by(() => {
		const sums = Array.from({ length: COLS }, () => ({ sum: 0, n: 0 }));
		for (const [ts, v] of points) {
			const i = Math.floor(((Date.parse(ts) - t0) / (hours * HOUR)) * COLS);
			const col = sums[Math.min(Math.max(i, 0), COLS - 1)]!;
			col.sum += v;
			col.n += 1;
		}
		return sums.map(({ sum, n }) => (n ? sum / n : null));
	});

	let cw = $derived(width / COLS);
	let ch = $derived((height - LABEL_H) / ROWS);
	let r = $derived(Math.min(cw, ch) * 0.36);
	let yLimit = $derived((ROWS - (CO2_LIMIT / MAX) * ROWS) * ch);

	// 横軸は 6 時間ごとの時刻（現地時刻）。右端は「今」
	let ticks = $derived(
		[0, 6, 12, 18].map((k) => ({
			x: (k / 24) * width,
			label: `${new Date(now - (24 - k) * HOUR).getHours()}時`
		}))
	);
</script>

<div class="h-full w-full" bind:clientWidth={width} bind:clientHeight={height}>
	<svg {width} {height} class="block">
		{#each columns as v, i (i)}
			{@const lit = v == null ? 0 : Math.round((Math.min(v, MAX) / MAX) * ROWS)}
			{#each { length: ROWS }, j (j)}
				<circle
					cx={i * cw + cw / 2}
					cy={(ROWS - j - 0.5) * ch}
					{r}
					fill={j < lit && v != null ? LEVEL_FILL[co2Level(v)] : 'var(--color-off)'}
				/>
			{/each}
		{/each}
		<line
			x1="0"
			x2={width}
			y1={yLimit}
			y2={yLimit}
			stroke="#fff"
			stroke-opacity="0.35"
			stroke-width="2"
			stroke-dasharray="2 6"
		/>
		{#each ticks as t (t.x)}
			<text x={t.x} y={height - 4} font-size="24" fill="var(--color-led-dim)">{t.label}</text>
		{/each}
		<text x={width} y={height - 4} font-size="24" fill="var(--color-led-amber)" text-anchor="end"
			>今</text
		>
	</svg>
</div>
