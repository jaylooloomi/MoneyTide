import { test } from 'node:test';
import assert from 'node:assert/strict';

import { buildIntradayOption, infoHtml, priceRange, statsAt, vwapPath } from '../../static/js/intradaychart.js';

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
