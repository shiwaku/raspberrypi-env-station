<script lang="ts">
	import type { Point } from './api.ts';

	// 直近の推移を描くだけの軽い SVG グラフ（Pi 4 で重いライブラリを使わない）。
	// 色と文字は DADS のトークン（CSS 変数・文字スタイル）を使う
	let {
		points,
		hours = 24,
		threshold
	}: {
		points: Point[];
		hours?: number;
		/** 基準値。超えた範囲の背景に薄い色を付け、点線を引く */
		threshold?: number;
	} = $props();

	const uid = $props.id();
	let width = $state(260);
	let height = $state(140);
	const PAD = { left: 48, right: 8, top: 8, bottom: 22 };
	const HOUR = 3600_000;

	let now = $derived(points.length ? Date.parse(points[points.length - 1]![0]) : Date.now());
	let t0 = $derived(now - hours * HOUR);
	let values = $derived(points.map(([, v]) => v));

	// 目盛りは 1・2・2.5・5 × 10^n の区切りのよい値で 3〜4 本にする
	function niceStep(range: number, count: number): number {
		const raw = range / count;
		const mag = 10 ** Math.floor(Math.log10(raw));
		const step = [1, 2, 2.5, 5, 10].find((s) => s * mag >= raw) ?? 10;
		return step * mag;
	}
	let lo = $derived(Math.min(...values, threshold ?? Infinity));
	let hi = $derived(Math.max(...values, threshold ?? -Infinity));
	let step = $derived(niceStep(hi - lo || 1, 3));
	let yMin = $derived(Math.floor(lo / step) * step);
	let yMax = $derived(Math.ceil(hi / step) * step);
	let yTicks = $derived(
		Array.from({ length: Math.round((yMax - yMin) / step) + 1 }, (_, i) => yMin + i * step)
	);

	const x = (t: number) => PAD.left + ((t - t0) / (now - t0)) * (width - PAD.left - PAD.right);
	const y = (v: number) =>
		PAD.top + (1 - (v - yMin) / (yMax - yMin)) * (height - PAD.top - PAD.bottom);

	let coords = $derived(points.map(([ts, v]) => [x(Date.parse(ts)), y(v)] as const));
	let line = $derived(
		coords.map(([cx, cy], i) => `${i ? 'L' : 'M'}${cx.toFixed(1)},${cy.toFixed(1)}`).join('')
	);
	let area = $derived(
		coords.length
			? `${line}L${coords[coords.length - 1]![0].toFixed(1)},${y(yMin)}L${coords[0]![0].toFixed(1)},${y(yMin)}Z`
			: ''
	);
	let last = $derived(coords[coords.length - 1]);

	// 横軸は現地時刻の 0・6・12・18 時。端に近すぎる目盛りは文字が欠けるので出さない
	let xTicks = $derived.by(() => {
		const first = new Date(t0);
		first.setMinutes(0, 0, 0);
		if (first.getTime() < t0) first.setHours(first.getHours() + 1);
		while (first.getHours() % 6) first.setHours(first.getHours() + 1);
		const out: number[] = [];
		for (let t = first.getTime(); t <= now; t += 6 * HOUR) {
			const px = x(t);
			if (px > PAD.left + 14 && px < width - PAD.right - 14) out.push(t);
		}
		return out;
	});
	const hourLabel = (t: number) => `${new Date(t).getHours()}時`;
	const num = (v: number) => v.toLocaleString('ja-JP');
</script>

<div class="h-full w-full" bind:clientWidth={width} bind:clientHeight={height}>
	<svg {width} {height} class="block">
		{#if points.length}
			<defs>
				<linearGradient id="{uid}-fill" x1="0" x2="0" y1="0" y2="1">
					<stop offset="0" stop-color="var(--color-key-900)" stop-opacity="0.18" />
					<stop offset="1" stop-color="var(--color-key-900)" stop-opacity="0" />
				</linearGradient>
			</defs>
			{#if threshold !== undefined && threshold < yMax}
				<rect
					x={PAD.left}
					y={y(yMax)}
					width={width - PAD.left - PAD.right}
					height={y(threshold) - y(yMax)}
					fill="var(--color-orange-50)"
				/>
			{/if}
			{#each yTicks as v (v)}
				<line
					x1={PAD.left}
					x2={width - PAD.right}
					y1={y(v)}
					y2={y(v)}
					stroke="var(--color-solid-gray-100)"
				/>
				<text
					x={PAD.left - 8}
					y={y(v) + 4}
					text-anchor="end"
					class="text-dns-14N-130 tabular-nums"
					fill="var(--color-solid-gray-600)">{num(v)}</text
				>
			{/each}
			{#if threshold !== undefined}
				<line
					x1={PAD.left}
					x2={width - PAD.right}
					y1={y(threshold)}
					y2={y(threshold)}
					stroke="var(--color-warning-orange-1)"
					stroke-width="1.5"
					stroke-dasharray="4 3"
				/>
			{/if}
			<path d={area} fill="url(#{uid}-fill)" />
			<path
				d={line}
				fill="none"
				stroke="var(--color-key-900)"
				stroke-width="2"
				stroke-linejoin="round"
				stroke-linecap="round"
			/>
			{#if last}
				<circle
					cx={last[0]}
					cy={last[1]}
					r="4"
					fill="var(--color-key-900)"
					stroke="var(--color-white)"
					stroke-width="2"
				/>
			{/if}
			{#each xTicks as t (t)}
				<text
					x={x(t)}
					y={height - 4}
					text-anchor="middle"
					class="text-dns-14N-130 tabular-nums"
					fill="var(--color-solid-gray-600)">{hourLabel(t)}</text
				>
			{/each}
		{:else}
			<text
				x={width / 2}
				y={height / 2}
				text-anchor="middle"
				class="text-std-16N-170"
				fill="var(--color-solid-gray-536)">データなし</text
			>
		{/if}
	</svg>
</div>
