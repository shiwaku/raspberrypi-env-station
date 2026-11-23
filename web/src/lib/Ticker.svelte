<script lang="ts">
	// 発車標のように右から左へ流れるお知らせ。なければ控えめに「ありません」と出す
	import type { Notice } from './notices.ts';

	let { notices }: { notices: Notice[] } = $props();

	const TONE = { white: 'text-led-white', amber: 'text-led-amber', red: 'text-led-red' };
	// 文字数に合わせて流れる速さをそろえる（1 文字あたり 0.35 秒、最短 20 秒）
	let seconds = $derived(
		Math.max(20, notices.reduce((n, x) => n + x.text.length + 4, 0) * 0.35)
	);
	let key = $derived(notices.map((n) => n.text).join('|'));
</script>

<div class="flex items-center gap-9 overflow-hidden bg-[#0a0a0a] px-9 py-4 text-[38px] tracking-[0.08em]">
	<span class="shrink-0 text-led-amber">お知らせ</span>
	<div class="min-w-0 flex-1 overflow-hidden whitespace-nowrap">
		{#if notices.length}
			{#key key}
				<span class="ticker-track" style:--ticker-s="{seconds}s">
					{#each notices as n, i (i)}
						<span class={TONE[n.tone]}>{n.text}</span>{#if i < notices.length - 1}<span
								class="text-led-dim">　／　</span
							>{/if}
					{/each}
				</span>
			{/key}
		{:else}
			<span class="text-led-dim">お知らせはありません</span>
		{/if}
	</div>
</div>
