// CO2 濃度の目安。建築物衛生法の基準は 1,000ppm 以下。
export type Co2Level = 'good' | 'warn' | 'bad';

export const CO2_LIMIT = 1000;

export function co2Level(ppm: number): Co2Level {
	if (ppm < CO2_LIMIT) return 'good';
	if (ppm < 1500) return 'warn';
	return 'bad';
}

export const CO2_MESSAGE: Record<Co2Level, string> = {
	good: '良好',
	warn: '換気してください',
	bad: 'すぐに換気してください'
};

// DADS の意味を持つ色。文字は白い背景でコントラストが足りる濃いほう（-2）を使う
export const CO2_TEXT_CLASS: Record<Co2Level, string> = {
	good: 'text-success-2',
	warn: 'text-warning-orange-2',
	bad: 'text-error-2'
};

// 状態を示すバッジ（薄い背景 + 濃い文字 + 色の点）
export const CO2_BADGE_CLASS: Record<Co2Level, string> = {
	good: 'bg-green-50 text-success-2',
	warn: 'bg-orange-50 text-warning-orange-2',
	bad: 'bg-red-50 text-error-2'
};

export const CO2_DOT_CLASS: Record<Co2Level, string> = {
	good: 'bg-success-1',
	warn: 'bg-warning-orange-1',
	bad: 'bg-error-1'
};
