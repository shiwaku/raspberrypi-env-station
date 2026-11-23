// 室内環境の判定。建築物衛生法の建築物環境衛生管理基準による
// （CO2 1,000ppm 以下、温度 18℃以上 28℃以下、相対湿度 40% 以上 70% 以下）。

export type Level = 'good' | 'warn' | 'bad';

export const CO2_LIMIT = 1000;
const CO2_URGENT = 1500;
export const TEMP_RANGE: [number, number] = [18, 28];
export const HUMIDITY_RANGE: [number, number] = [40, 70];

export function co2Level(ppm: number): Level {
	if (ppm < CO2_LIMIT) return 'good';
	if (ppm < CO2_URGENT) return 'warn';
	return 'bad';
}

/** 発車標の「遅延」のような短い言葉 */
export const CO2_STATUS: Record<Level, string> = {
	good: '良好',
	warn: '要換気',
	bad: '至急換気'
};

export const inRange = (v: number, [lo, hi]: [number, number]) => v >= lo && v <= hi;

/** LED の色（Tailwind のクラス） */
export const LEVEL_TEXT: Record<Level, string> = {
	good: 'text-led-green',
	warn: 'text-led-amber',
	bad: 'text-led-red'
};

/** LED の点の色（SVG の fill） */
export const LEVEL_FILL: Record<Level, string> = {
	good: 'var(--color-led-green)',
	warn: 'var(--color-led-amber)',
	bad: 'var(--color-led-red)'
};
