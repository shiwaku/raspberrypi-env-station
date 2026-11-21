<script lang="ts">
	import type { Point } from './api.ts';

	// 直近の推移を描くだけの軽い SVG グラフ（Pi 4 で重いライブラリを使わない）
	let {
		points,
		hours = 24,
		color = '#38bdf8',
		unit = '',
		digits = 0,
		threshold
	}: {
		points: Point[];
		hours?: number;
		color?: string;
		unit?: string;
		digits?: number;
		threshold?: number;
	} = $props();

	// 右列のパネル（約 590×420）に合わせた座標。文字は 3〜5m 離れて読める大きさにする
	const W = 600;
	const H = 420;
	const PAD = { left: 90, right: 16, top: 20, bottom: 50 };

	let now = $derived(points.length ? Date.parse(points[points.length - 1]![0]) : Date.now());
	let t0 = $derived(now - hours * 3600_000);
	let values = $derived(points.map(([, v]) => v));
	let lo = $derived(Math.min(...values, threshold ?? Infinity));
	let hi = $derived(Math.max(...values, threshold ?? -Infinity));
	let span = $derived(hi - lo || 1);
	let yMin = $derived(lo - span * 0.1);
	let yMax = $derived(hi + span * 0.1);

	const x = (t: number) =>
		PAD.left + ((t - t0) / (now - t0)) * (W - PAD.left - PAD.right);
	const y = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin)) * (H - PAD.top - PAD.bottom);

	let path = $derived(
		points.map(([ts, v], i) => `${i ? 'L' : 'M'}${x(Date.parse(ts)).toFixed(1)},${y(v).toFixed(1)}`).join('')
	);

	// 6 時間ごとの目盛り（現地時刻）
	let ticks = $derived(
		Array.from({ length: Math.floor(hours / 6) + 1 }, (_, i) => now - i * 6 * 3600_000)
	);
	const hhmm = (t: number) =>
		new Date(t).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
</script>

<svg viewBox="0 0 {W} {H}" class="h-full w-full">
	{#if points.length}
		{#each [yMin + (yMax - yMin) * 0.1, yMax - (yMax - yMin) * 0.1] as v (v)}
			<line x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)} stroke="#334155" stroke-width="1" />
			<text x={PAD.left - 10} y={y(v) + 8} text-anchor="end" font-size="28" fill="#94a3b8">
				{v.toFixed(digits)}{unit}
			</text>
		{/each}
		{#if threshold !== undefined}
			<line
				x1={PAD.left}
				x2={W - PAD.right}
				y1={y(threshold)}
				y2={y(threshold)}
				stroke="#f59e0b"
				stroke-width="2"
				stroke-dasharray="8 6"
			/>
		{/if}
		<path d={path} fill="none" stroke={color} stroke-width="5" stroke-linejoin="round" />
		{#each ticks as t, i (t)}
			<text x={x(t)} y={H - 8} text-anchor={i === 0 ? 'end' : 'middle'} font-size="28" fill="#94a3b8">{hhmm(t)}</text>
		{/each}
	{:else}
		<text x={W / 2} y={H / 2} text-anchor="middle" font-size="36" fill="#64748b">データなし</text>
	{/if}
</svg>
