<script lang="ts">
	import type { Flight, Train } from './api.ts';
	import { dataTime, flightRow, trainRow, upcoming, type Tone } from './transit.ts';

	// 表示板の「運行状況」のページ。飛行機は路線ごとにこれから出る便、右に地下鉄の運行情報
	let {
		flights,
		trains,
		routes,
		airports,
		sources,
		contact,
		error
	}: {
		flights: Flight[];
		trains: Train[];
		routes: [string, string][];
		airports: Record<string, string>;
		sources: string[];
		contact: string;
		error: string | null;
	} = $props();

	const ROWS = 5;
	const TONE: Record<Tone, string> = {
		green: 'text-led-green',
		amber: 'text-led-amber',
		red: 'text-led-red',
		dim: 'text-led-dim',
		white: 'text-led-white'
	};
	const name = (code: string) => airports[code] ?? code;
	const time = (iso: string | null) =>
		iso ? new Date(iso).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' }) : '—';

	let tables = $derived(
		routes.map(([from, to]) => ({
			key: `${from}-${to}`,
			title: `${name(from)} → ${name(to)}`,
			rows: upcoming(flights, from, to, ROWS).map(flightRow)
		}))
	);
	let trainRows = $derived(trains.map(trainRow));
	let updated = $derived(time(dataTime(flights, trains)));

	const FGRID = 'grid grid-cols-[170px_120px_120px_100px_1fr] items-center';
</script>

<div class="flex min-h-0 flex-1 flex-col">
	<div
		class="grid min-h-0 flex-1"
		style:grid-template-columns="repeat({tables.length}, 1fr) {trains.length ? '500px' : ''}"
	>
		{#each tables as table (table.key)}
			<div class="flex min-h-0 flex-col overflow-hidden border-r-[3px] border-rule px-7 pt-2">
				<div class="text-[34px] leading-[1.3] tracking-[0.12em]">{table.title}</div>
				<div class="{FGRID} mt-1 bg-[#1b1b1b] px-2 py-1 text-[22px] tracking-[0.16em] text-[#c8c8c2]">
					<span>便名</span><span>定刻</span><span>変更</span><span>ゲート</span><span>状況</span>
				</div>
				{#each table.rows as row (row.number + row.scheduled)}
					<div class="{FGRID} h-12 shrink-0 border-b-2 border-rule px-2 text-[32px] tabular-nums">
						<span>{row.number}</span>
						<span>{row.scheduled}</span>
						<span class="text-led-amber">{row.changed ?? ''}</span>
						<span class="text-led-dim">{row.gate}</span>
						<span class="truncate {TONE[row.tone]}">{row.status}</span>
					</div>
				{:else}
					<div class="px-2 pt-4 text-[30px] text-led-dim">これから出る便はありません</div>
				{/each}
			</div>
		{/each}
		{#if trains.length}
			<div class="flex min-h-0 flex-col overflow-hidden px-7 pt-2">
				<div class="text-[34px] leading-[1.3] tracking-[0.12em]">東京の地下鉄</div>
				<div class="mt-1 flex justify-between bg-[#1b1b1b] px-2 py-1 text-[22px] tracking-[0.16em] text-[#c8c8c2]">
					<span>路線</span><span>運行</span>
				</div>
				{#each trainRows as row (row.name)}
					<div class="flex h-12 shrink-0 items-center justify-between border-b-2 border-rule px-2 text-[32px]">
						<span class="truncate">{row.name}</span>
						<span class="shrink-0 pl-4 {TONE[row.tone]}">{row.status}</span>
					</div>
				{/each}
			</div>
		{/if}
	</div>
	<!-- ODPT の規約で出す：出典・データの時刻・正確性を保証しないこと・問い合わせ先 -->
	<div class="shrink-0 truncate border-t-2 border-rule px-9 py-1 font-sans text-[18px] text-led-dim">
		{#if error && !flights.length && !trains.length}
			<span class="text-led-amber">運行状況を取得できません。</span>
		{/if}
		データ：公共交通オープンデータセンター（{sources.join('・')}）　{updated} 時点　正確性・完全性は保証されません{contact
			? `　お問い合わせ：${contact}`
			: ''}
	</div>
</div>
