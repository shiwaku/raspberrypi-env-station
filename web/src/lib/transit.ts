// 運行状況（飛行機・地下鉄）を表示板に出すための判定。データは ODPT（公共交通オープンデータセンター）
import type { Flight, Train } from './api.ts';
import type { Notice } from './notices.ts';

export type Tone = 'green' | 'amber' | 'red' | 'dim' | 'white';

/** 出発済み（表示板からは消す） */
const GONE = new Set(['Departed', 'InAir', 'LeftGate', 'Arrived', 'Landed']);
/** 手続きが進んでいるだけで、問題のない状況 */
const PROGRESS = new Set(['CheckIn', 'CheckInClose', 'Boarding', 'BoardingComplete', 'FinalCall']);

export interface FlightRow {
	number: string;
	scheduled: string;
	changed: string | null; // 変更時刻（定刻と違うときだけ）
	gate: string;
	status: string;
	tone: Tone;
}

export function flightRow(f: Flight): FlightRow {
	const changed = f.estimated && f.estimated !== f.scheduled ? f.estimated : null;
	let status = '定刻';
	let tone: Tone = 'green';
	if (f.status === 'Cancelled') {
		status = '欠航';
		tone = 'red';
	} else if (changed) {
		status = '遅延';
		tone = 'amber';
	} else if (f.summary) {
		status = f.summary; // 出発遅れ など
		tone = 'amber';
	} else if (f.status && f.status !== 'EstimatedDeparture') {
		status = f.status_ja ?? f.status;
		tone = PROGRESS.has(f.status) ? 'green' : 'amber'; // 天候不良・機材繰り など
	}
	return {
		number: f.number,
		scheduled: f.scheduled ?? '—',
		changed,
		gate: f.gate ?? '—',
		status,
		tone
	};
}

/** その路線のこれから出る便を、定刻の早い順に count 便 */
export function upcoming(flights: Flight[], from: string, to: string, count: number): Flight[] {
	return flights
		.filter((f) => f.from === from && f.to === to && !(f.status && GONE.has(f.status)))
		.sort((a, b) => (a.scheduled ?? '').localeCompare(b.scheduled ?? ''))
		.slice(0, count);
}

export interface TrainRow {
	name: string;
	status: string;
	tone: Tone;
}

/** 平常時は status が空。「見合わせ」「運休」は赤、それ以外（遅延など）は橙 */
export function trainRow(t: Train): TrainRow {
	if (!t.status) return { name: t.name, status: '平常', tone: 'green' };
	const red = /見合わせ|運休|運転中止/.test(t.status);
	return { name: t.name, status: t.status, tone: red ? 'red' : 'amber' };
}

/** お知らせに流す運行情報（欠航・地下鉄の乱れ） */
export function transitNotices(
	flights: Flight[],
	trains: Train[],
	airports: Record<string, string>,
	routes: [string, string][]
): Notice[] {
	const out: Notice[] = [];
	const name = (code: string) => airports[code] ?? code;
	for (const [from, to] of routes) {
		for (const f of upcoming(flights, from, to, 20)) {
			if (f.status === 'Cancelled')
				out.push({ text: `${f.number} ${name(from)}${f.scheduled ?? ''}発 ${name(to)}行き 欠航`, tone: 'red' });
		}
	}
	for (const t of trains) {
		if (t.status) {
			const row = trainRow(t);
			out.push({ text: `${t.name} ${t.status}：${t.text ?? ''}`, tone: row.tone === 'red' ? 'red' : 'amber' });
		}
	}
	return out;
}

/** データの時刻（dc:date の新しいもの）。ODPT の規約で画面に出す */
export function dataTime(flights: Flight[], trains: Train[]): string | null {
	const dates = [...flights, ...trains].map((x) => x.date).filter((d): d is string => !!d);
	return dates.length ? dates.sort().at(-1)! : null;
}
