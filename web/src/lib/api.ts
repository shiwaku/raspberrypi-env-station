// env-dashboard（Python）の API。時刻は UTC の ISO 8601 文字列。

export type Basemap = 'pale' | 'std' | 'seamlessphoto';

export interface Station {
	name: string;
	latitude: number;
	longitude: number;
}

export interface DashboardConfig {
	station: Station | null;
	basemaps: Basemap[];
	basemap_interval_s: number;
}

export interface Latest {
	ts: string | null;
	co2_ppm: number | null;
	temperature_c: number | null;
	humidity_pct: number | null;
}

export type Metric = 'co2_ppm' | 'temperature_c' | 'humidity_pct';
export type Point = [ts: string, value: number];

async function getJson<T>(path: string): Promise<T> {
	const res = await fetch(path, { cache: 'no-store' });
	if (!res.ok) throw new Error(`${path}: ${res.status}`);
	return (await res.json()) as T;
}

export const fetchConfig = () => getJson<DashboardConfig>('/api/config');
export const fetchLatest = () => getJson<Latest>('/api/latest');
export const fetchSeries = (metric: Metric, hours = 24) =>
	getJson<{ metric: Metric; points: Point[] }>(`/api/series?metric=${metric}&hours=${hours}`).then(
		(body) => body.points
	);
