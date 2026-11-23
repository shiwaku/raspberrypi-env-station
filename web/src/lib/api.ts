// env-dashboard（Python）の API。時刻は UTC の ISO 8601 文字列。

export interface Station {
	name: string;
	latitude: number;
	longitude: number;
}

/** 画面の上半分に並べる拠点（札幌・東京など） */
export interface Office {
	name: string;
	label: string;
	latitude: number;
	longitude: number;
	zoom: number;
}

export interface DashboardConfig {
	station: Station | null;
	offices: Office[];
}

export interface Latest {
	ts: string | null;
	co2_ppm: number | null;
	temperature_c: number | null;
	humidity_pct: number | null;
}

/** 飛行機の出発便（ODPT の FlightInformationDeparture を整えたもの） */
export interface Flight {
	number: string;
	airline: string;
	from: string; // 空港コード（CTS など）
	to: string;
	scheduled: string | null; // 現地時刻 HH:MM
	estimated: string | null;
	actual: string | null;
	gate: string | null;
	status: string | null; // Cancelled・Departed など。定刻なら null
	status_ja: string | null;
	summary: string | null; // 出発遅れ など
	text: string | null;
	date: string | null; // dc:date
}

/** 地下鉄の運行情報。平常時は status が null */
export interface Train {
	railway: string;
	name: string;
	operator: string;
	status: string | null;
	text: string | null;
	cause: string | null;
	date: string | null;
}

export type Transit =
	| { enabled: false }
	| {
			enabled: true;
			flights: Flight[];
			trains: Train[];
			fetched_at: string | null;
			error: string | null;
			sources: string[];
			contact: string;
			airports: Record<string, string>;
			routes: [string, string][];
	  };

export type Metric = 'co2_ppm' | 'temperature_c' | 'humidity_pct';
export type Point = [ts: string, value: number];

async function getJson<T>(path: string): Promise<T> {
	const res = await fetch(path, { cache: 'no-store' });
	if (!res.ok) throw new Error(`${path}: ${res.status}`);
	return (await res.json()) as T;
}

export const fetchConfig = () => getJson<DashboardConfig>('/api/config');
export const fetchLatest = () => getJson<Latest>('/api/latest');
export const fetchTransit = () => getJson<Transit>('/api/transit');
export const fetchSeries = (metric: Metric, hours = 24) =>
	getJson<{ metric: Metric; points: Point[] }>(`/api/series?metric=${metric}&hours=${hours}`).then(
		(body) => body.points
	);
