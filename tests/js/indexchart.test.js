import { test } from 'node:test';
import assert from 'node:assert/strict';

import { STRONG_DAY, buildIndexOption, indexTooltip, isStrongDay, movingAverage, windowShowing } from '../../static/js/indexchart.js';

test('movingAverage needs a full window of valid values', () => {
  assert.deepEqual(movingAverage([1, 2, 3, 4], 2), [null, 1.5, 2.5, 3.5]);
  assert.deepEqual(movingAverage([1, null, 3, 4, 5], 2), [null, null, null, 3.5, 4.5]);
  assert.deepEqual(movingAverage([1, 2], 5), [null, null]);
});

test('isStrongDay uses either threshold, inclusive', () => {
  assert.equal(isStrongDay({ strong_ratio: STRONG_DAY.ratio, limit_up: 0 }), true);
  assert.equal(isStrongDay({ strong_ratio: 9.99, limit_up: STRONG_DAY.limitUp }), true);
  assert.equal(isStrongDay({ strong_ratio: 9.99, limit_up: STRONG_DAY.limitUp - 1 }), false);
  assert.equal(isStrongDay({ strong_ratio: null, limit_up: null }), false);
});

const bar = (o, c) => ({ open: o, high: Math.max(o, c) + 1, low: Math.min(o, c) - 1, close: c, change: c - o, turnover_yuan: 1e11 });
const days = [
  { date: '2026-09-01', twse: bar(100, 110), tpex: bar(10, 9), strong_ratio: 12, limit_up: 40, has_stocks: true },
  { date: '2026-09-02', twse: bar(110, 105), tpex: null, strong_ratio: 3, limit_up: 10, has_stocks: true },
  { date: '2026-09-03', twse: null, tpex: bar(9, 9.5), strong_ratio: null, limit_up: null, has_stocks: false },
];

test('buildIndexOption: candles, gaps, volume colours, strong marks, selected line', () => {
  const opt = buildIndexOption(days, '2026-09-02', 2);
  const s = Object.fromEntries(opt.series.map((x) => [x.id, x]));
  assert.deepEqual(s.twseK.data, [[100, 110, 99, 111], [110, 105, 104, 111], '-']);
  assert.deepEqual(s.tpexK.data[1], '-');
  assert.equal(s.twseVol.data[0].itemStyle.color, '#e0262c');
  assert.equal(s.twseVol.data[1].itemStyle.color, '#1fa24a');
  assert.deepEqual(s.strong.data.map((p) => p[0]), [0]);
  assert.deepEqual(s.twseK.markLine.data, [{ xAxis: '2026-09-02' }]);
  assert.equal(s.twseMA5.data.every((v) => v === '-'), true);
  assert.equal(opt.dataZoom[0].startValue, 1);
  assert.equal(opt.dataZoom[0].endValue, 2);
  assert.equal(opt.xAxis.length, 4);
});

test('indexTooltip shows both markets and the strong-day tag', () => {
  const html = indexTooltip(days[0]);
  assert.match(html, /加權指數/);
  assert.match(html, /櫃買指數/);
  assert.match(html, /強勢日/);
  assert.match(indexTooltip(days[2]), /無個股資料/);
});

test('windowShowing keeps the width and clamps to the data', () => {
  assert.deepEqual(windowShowing(5, 0, 9, 100), [0, 9]);
  assert.deepEqual(windowShowing(50, 0, 9, 100), [46, 55]);
  assert.deepEqual(windowShowing(99, 0, 9, 100), [90, 99]);
  assert.deepEqual(windowShowing(0, 90, 99, 100), [0, 9]);
});
