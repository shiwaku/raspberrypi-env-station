// CO2 濃度の目安。建築物衛生法の基準は 1,000ppm 以下。
export type Co2Level = 'good' | 'warn' | 'bad';

export function co2Level(ppm: number): Co2Level {
	if (ppm < 1000) return 'good';
	if (ppm < 1500) return 'warn';
	return 'bad';
}

export const CO2_MESSAGE: Record<Co2Level, string> = {
	good: '良好',
	warn: '換気してください',
	bad: 'すぐに換気してください'
};
