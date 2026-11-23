// 地図の下の気象の帯と、お知らせに流す警報の判定。データは気象庁防災情報 XML
import type { OfficeWeather } from './api.ts';
import type { Notice } from './notices.ts';

/** 全角数字を半角にする（気象庁の「１２時から１８時まで」など） */
const half = (s: string) => s.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));

/** 「１２時から１８時まで」→「12〜18時」。それ以外の名前（今日日中など）はそのまま */
export function shortPeriod(label: string): string {
	const m = half(label).match(/^(\d+)時から(\d+)時まで$/);
	return m ? `${Number(m[1])}〜${Number(m[2])}時` : label;
}

export type WarningTone = 'green' | 'amber' | 'red' | 'dim';

/** 警報・注意報の表示。特別警報と警報は赤、注意報だけなら橙、何もなければ「発表なし」 */
export function warningText(w: OfficeWeather | null): { text: string; tone: WarningTone } {
	if (!w?.warnings) return { text: '—', tone: 'dim' };
	if (!w.warnings.length) return { text: '発表なし', tone: 'green' };
	const severe = w.warnings.some((x) => x.level !== 'advisory');
	// 重いものから並べる
	const order = { emergency: 0, warning: 1, advisory: 2 };
	const names = [...w.warnings].sort((a, b) => order[a.level] - order[b.level]).map((x) => x.name);
	return { text: names.join('・'), tone: severe ? 'red' : 'amber' };
}

/** お知らせに流すのは警報と特別警報だけ（注意報は帯に出ている） */
export function weatherNotices(offices: Record<string, OfficeWeather | null>): Notice[] {
	const out: Notice[] = [];
	for (const [office, w] of Object.entries(offices)) {
		for (const x of w?.warnings ?? []) {
			if (x.level !== 'advisory')
				out.push({ text: `${office}　${x.name}が発表されています`, tone: 'red' });
		}
	}
	return out;
}
