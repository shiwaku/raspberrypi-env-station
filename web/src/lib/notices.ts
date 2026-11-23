import type { Latest } from './api.ts';
import { CO2_LIMIT, co2Level, HUMIDITY_RANGE, inRange, TEMP_RANGE } from './co2.ts';

/** 一番下に流すお知らせ */
export interface Notice {
	text: string;
	tone: 'white' | 'amber' | 'red';
}

const n = (v: number) => v.toLocaleString('ja-JP');

/** 計測値からお知らせを作る。値が古いときは、古い値での注意は出さずに「届いていない」だけ出す */
export function buildNotices(latest: Latest | null, stale: boolean, error: string | null): Notice[] {
	const out: Notice[] = [];
	if (error) out.push({ text: 'ダッシュボードのサーバーに接続できません', tone: 'red' });
	if (stale) {
		out.push({ text: '室内環境の計測値が 5 分以上届いていません', tone: 'amber' });
		return out;
	}
	if (latest?.co2_ppm != null) {
		const level = co2Level(latest.co2_ppm);
		if (level === 'bad')
			out.push({
				text: `CO₂ が ${n(latest.co2_ppm)}ppm です。すぐに窓を開けて換気してください`,
				tone: 'red'
			});
		else if (level === 'warn')
			out.push({
				text: `CO₂ が基準の ${n(CO2_LIMIT)}ppm を超えています。窓を開けて換気してください`,
				tone: 'amber'
			});
	}
	if (latest?.temperature_c != null && !inRange(latest.temperature_c, TEMP_RANGE)) {
		const [lo, hi] = TEMP_RANGE;
		out.push({ text: `室温が基準（${lo}〜${hi}℃）の外です`, tone: 'amber' });
	}
	if (latest?.humidity_pct != null && !inRange(latest.humidity_pct, HUMIDITY_RANGE)) {
		const [lo, hi] = HUMIDITY_RANGE;
		out.push({ text: `湿度が基準（${lo}〜${hi}%）の外です`, tone: 'amber' });
	}
	return out;
}
