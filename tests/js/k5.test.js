import { test } from 'node:test';
import assert from 'node:assert/strict';

import { k5CardHtml, k5Summary, k5Svg, k5Title } from '../../static/js/k5.js';

const S = [
  { date: '2026-08-01', open: 100, high: 103, low: 99, close: 102, pct: 2, lots: 1000, limit: false, vr: 1.1, inst: -20 },
  { date: '2026-08-02', open: 102, high: 102, low: 98, close: 99, pct: -2.94, lots: 800, limit: false, vr: 0.8, inst: null },
  { date: '2026-08-03', open: 99, high: 105, low: 99, close: 104, pct: 5.05, lots: 3000, limit: false, vr: 3.4, inst: 1500 },
  { date: '2026-08-04', open: 104, high: 114.4, low: 104, close: 114.4, pct: 10, lots: 5000, limit: true, vr: 2.5, inst: 23456 },
];

test('k5Summary: 5 日累計 compounds the daily %, streak counts the latest same-sign days', () => {
  const { cum, streak } = k5Summary(S);
  assert.ok(Math.abs(cum - ((1.02 * 0.9706 * 1.0505 * 1.1 - 1) * 100)) < 0.01);
  assert.equal(streak, 2);
  assert.equal(k5Summary([...S, { ...S[0], date: '2026-08-05', pct: -1 }]).streak, -1);
  assert.deepEqual(k5Summary([]), { cum: null, streak: 0 });
});

test('k5Svg / k5CardHtml / k5Title: candles, 🔒, 量比, 法人, dates', () => {
  const mini = k5Svg(S, 64, 30);
  assert.equal((mini.match(/<rect/g) || []).length, 4); // a body per day, no volume in the mini one
  assert.doesNotMatch(mini, /🔒/);
  const full = k5Svg(S, 260, 170, true);
  assert.match(full, /🔒/);
  assert.doesNotMatch(full, /fill="none"/); // solid candles only
  assert.match(full, />量</); // the volume strip is labelled
  assert.match(full, /×3\.4/);
  assert.doesNotMatch(full, /×1\.1/); // only 量比 ≥ 2 is marked
  assert.match(full, /\+2\.3萬/); // 23,456 張 of 法人
  assert.match(full, /08\/04/);
  const card = k5CardHtml('甲', '1234', '#ffd400', S);
  assert.match(card, /<b style="color:#ffd400">甲<\/b>/);
  assert.match(card, /連漲 2 天/);
  assert.match(card, /5 日 \+/);
  assert.match(k5CardHtml('乙', '9', '#fff', []), /沒有日 K 資料/);
  assert.match(k5Title(S), /連漲 2 天/);
  assert.match(k5Title(S), /08-04 114\.4（\+10\.00%）🔒/);
});
