import type { Basemap } from './api.ts';

// 国土地理院の地理院タイル（https://maps.gsi.go.jp/development/ichiran.html）
export const GSI_ATTRIBUTION =
	'<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank">地理院タイル</a>';

export const BASEMAPS: Record<Basemap, { label: string; ext: 'png' | 'jpg'; minzoom: number }> = {
	pale: { label: '淡色地図', ext: 'png', minzoom: 2 },
	std: { label: '標準地図', ext: 'png', minzoom: 0 },
	seamlessphoto: { label: 'シームレス空中写真', ext: 'jpg', minzoom: 2 }
};

export const tileUrl = (id: Basemap) =>
	`https://cyberjapandata.gsi.go.jp/xyz/${id}/{z}/{x}/{y}.${BASEMAPS[id].ext}`;
