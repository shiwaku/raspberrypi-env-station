<script lang="ts">
	import type { Point } from './api.ts';

	// 直近の推移を描くだけの軽い SVG グラフ（Pi 4 で重いライブラリを使わない）。
	// 色と文字は DADS のトークン（CSS 変数・文字スタイル）を使う
	let {
		points,
		hours = 24,
		unit = '',
		digits = 0,
		threshold
	}: {
		points: Point[];
		hours?: number;
		unit?: string;
		digits?: number;
		threshold?: number;
	} = $props();

	let width = $state(280);
	let height = $state(200);
	const PAD = { left: 44, right: 8, top: 10, bottom: 24 };

	let now = $derived(points.length ? Date.parse(points[points.length - 1]![0]) : Date.now());
	let t0 = $derived(now - hours * 3600_000);
	let values = $derived(points.map(([, v]) => v));
	let lo = $derived(Math.min(...values, threshold ?? Infinity));
	let hi = $derived(Math.max(...values, threshold ?? -Infinity));
	let span = $derived(hi - lo || 1);
	let yMin = $derived(lo - span * 0.1);
	let yMax = $derived(hi + span * 0.1);

	const x = (t: number) => PAD.left + ((t - t0) / (now - t0)) * (width - PAD.left - PAD.right);
	const y = (v: number) =>
		PAD.top + (1 - (v - yMin) / (yMax - yMin)) * (height - PAD.top - PAD.bottom);

	let path = $derived(
		points
			.map(([ts, v], i) => `${i ? 'L' : 'M'}${x(Date.parse(ts)).toFixed(1)},${y(v).toFixed(1)}`)
			.join('')
	);

	// 6 時間ごとの目盛り（現地時刻）
	let ticks = $derived(
		Array.from({ length: Math.floor(hours / 6) + 1 }, (_, i) => now - i * 6 * 3600_000)
	);
	const hhmm = (t: number) =>
		new Date(t).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
</script>

<div class="h-full w-full" bind:clientWidth={width} bind:clientHeight={height}>
	<svg {width} {height} class="block">
		{#if points.length}
			{#each [yMin + (yMax - yMin) * 0.1, yMax - (yMax - yMin) * 0.1] as v (v)}
				<line
					x1={PAD.left}
					x2={width - PAD.right}
					y1={y(v)}
					y2={y(v)}
					stroke="var(--color-solid-gray-200)"
				/>
				<text
					x={PAD.left - 6}
					y={y(v) + 5}
					text-anchor="end"
					class="text-dns-14N-130"
					fill="var(--color-solid-gray-600)"
				>
					{v.toFixed(digits)}{unit}
				</text>
			{/each}
			{#if threshold !== undefined}
				<line
					x1={PAD.left}
					x2={width - PAD.right}
					y1={y(threshold)}
					y2={y(threshold)}
					stroke="var(--color-warning-orange-1)"
					stroke-width="1.5"
					stroke-dasharray="5 4"
				/>
			{/if}
			<path
				d={path}
				fill="none"
				stroke="var(--color-key-900)"
				stroke-width="2"
				stroke-linejoin="round"
			/>
			{#each ticks as t, i (t)}
				<text
					x={x(t)}
					y={height - 6}
					text-anchor={i === 0 ? 'end' : 'middle'}
					class="text-dns-14N-130"
					fill="var(--color-solid-gray-600)">{hhmm(t)}</text
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
