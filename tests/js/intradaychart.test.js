import { test } from 'node:test';
import assert from 'node:assert/strict';

import { benchPath, buildCompareOption, compareInfoHtml, nextPicks, buildIntradayOption, infoHtml, priceRange, statsAt, vwapPath } from '../../static/js/intradaychart.js';

// prev close 100, limit-up +10% (110): locks at 09:02, opens at 09:03, locks again at 09:04
const data = {
  prev_close: 100,
  limit_up_pct: 10,
  limit_down_pct: -10,
  step_min: 1,
  bars: [
    [0, 101, 102, 100, 101, 1000],
    [1, 101, 105, 101, 104, 3000],
    [2, 104, 110, 104, 110, 2000],
    [3, 110, 110, 108, 108, 1000],
    [4, 108, 110, 108, 110, 3000],
    [250, 110, 112, 110, 110, 1000], // after 13:00: not the intraday high
  ],
};

test('statsAt: figures up to the playhead, intraday high within 09:00–13:00, lock and opens', () => {
  const s = statsAt(data, 1);
  assert.deepEqual([s.open, s.high, s.low, s.last, s.volume], [101, 105, 100, 104, 4000]);
  assert.equal(s.vwap, (101 * 1000 + 104 * 3000) / 4000);
  assert.equal(s.firstLock, null);
  const e = statsAt(data, 270);
  assert.deepEqual(e.peak, { m: 2, price: 110 }); // first 110; the 13:10 spike to 112 is outside the window
  assert.equal(e.firstLock, 2);
  assert.equal(e.opens, 1);
  assert.equal(e.locked, true);
  assert.equal(statsAt(data, -1), null);
});

test('volume unknown (self-recorded polls): no 均價 or volume, the rest still works', () => {
  const d = { ...data, bars: data.bars.map((b) => [...b.slice(0, 5), null]) };
  const s = statsAt(d, 270);
  assert.equal(s.volume, null);
  assert.equal(s.vwap, null);
  assert.deepEqual(vwapPath(d.bars, 270), []);
  assert.match(infoHtml(d, s, 270), /成交量<\/td><td class="">—/);
});

test('priceRange widens to a limit only when the day came near it', () => {
  const r = priceRange(data);
  assert.ok(Math.abs(r.up - 110) < 1e-9); // the limit-up line is shown
  assert.equal(r.down, null); // the low (100) was far from 90
  assert.ok(r.min < 100 && r.max > 112);
});

test('buildIntradayOption draws up to the playhead with the playhead line in both grids', () => {
  const o = buildIntradayOption(data, 2);
  assert.equal(o.series[0].data.length, 3);
  assert.equal(o.series[2].data.length, 3);
  assert.ok(o.series[0].markLine.data.some((l) => l.xAxis === 2));
  assert.ok(o.series[2].markLine.data.some((l) => l.xAxis === 2));
  assert.equal(o.series[1].data.length, 3); // 均價
  assert.match(infoHtml(data, statsAt(data, 270), 270), /收盤[\s\S]*鎖漲停[\s\S]*09:02[\s\S]*開板[\s\S]*1 次/);
});

test('benchPath / buildIntradayOption: 大盤／櫃買 drawn at the same % of this stock, up to the playhead', () => {
  const pts = [[0, 2, 2, 2], [2, -1, -1, -1], [270, -14, -14, -14]];
  assert.deepEqual(benchPath(pts, 100, 2), [[0, 102], [2, 99]]);
  assert.deepEqual(benchPath(null, 100, 2), []);
  const opt = buildIntradayOption(data, 3, [{ name: '大盤（加權）', points: pts }]);
  const s = opt.series.find((x) => x.name === '大盤（加權）');
  assert.deepEqual(s.data, [[0, 102], [2, 99]]);
  assert.ok(opt.yAxis[0].min <= 86); // the whole index line fits, not just what has been played
  assert.equal(buildIntradayOption(data, 3).series.length, 3); // no benchmarks: unchanged
});

test('statsAt: the lock is caught when the rounded % rebuilds a price just above the limit', () => {
  // prev 487.5 → limit-up 536 (9.95%: 487.5 × 1.0995 = 536.006)
  const d = { prev_close: 487.5, limit_up_pct: 9.95, bars: [[0, 520, 525, 519, 524, 1], [1, 524, 536, 524, 536, 1], [2, 536, 536, 536, 536, 1]] };
  const s = statsAt(d, 270);
  assert.equal(s.firstLock, 1);
  assert.equal(s.locked, true);
});

test('nextPicks: a plain click shows one, Ctrl/⌘/Shift adds a second, a third replaces the older', () => {
  assert.deepEqual(nextPicks(['A'], 'B', false), ['B']);
  assert.deepEqual(nextPicks(['A'], 'B', true), ['A', 'B']);
  assert.deepEqual(nextPicks(['A', 'B'], 'C', true), ['B', 'C']);
  assert.deepEqual(nextPicks(['A', 'B'], 'A', true), ['B']); // modifier on a picked one drops it
  assert.deepEqual(nextPicks(['A'], 'A', true), ['A']); // never empty
  assert.deepEqual(nextPicks([], 'A', true), ['A']);
});

test('buildCompareOption / compareInfoHtml: two stocks on one % axis, figures side by side', () => {
  const other = { prev_close: 50, limit_up_pct: 10, step_min: 1, bars: [[0, 50, 51, 49.5, 51, 500], [1, 51, 52, 51, 52, 800], [3, 52, 52, 51, 51.5, 100]] };
  const items = [{ code: 'A', name: '甲', data }, { code: 'B', name: '乙', data: other }];
  const opt = buildCompareOption(items, 3, [{ name: '大盤', points: [[0, -0.5], [3, -1]] }]);
  const a = opt.series.find((x) => x.name === '甲');
  const b = opt.series.find((x) => x.name === '乙');
  assert.deepEqual(a.data.map((p) => p[0]), [0, 1, 2, 3]); // up to the playhead
  assert.ok(Math.abs(a.data[2][1] - 10) < 1e-9); // 110 against prev 100
  assert.ok(Math.abs(b.data[1][1] - 4) < 1e-9); // 52 against prev 50
  assert.notEqual(a.lineStyle.color, b.lineStyle.color);
  assert.ok(opt.yAxis[0].max >= 12 && opt.yAxis[0].min <= -1); // the whole day (甲 reaches 112 after 13:00) and the index
  assert.deepEqual(opt.series.find((x) => x.name === '大盤').data, [[0, -0.5], [3, -1]]);
  assert.equal(opt.series.filter((x) => x.type === 'bar').length, 2);
  const html = compareInfoHtml(items, 270);
  assert.match(html, /甲<\/b><\/td><td><b style="color:[^"]+">乙/);
  assert.match(html, /漲幅<\/td><td><span class="up">\+10\.00%<\/span><\/td><td><span class="up">\+3\.00%/);
  assert.match(html, /鎖漲停<\/td><td><span class="up">09:02<\/span><\/td><td>—/); // 甲 locked from 09:02 and still locked; 乙 never
});
