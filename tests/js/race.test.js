import { test } from 'node:test';
import assert from 'node:assert/strict';

import { riDaysHtml, sharedGroupsHtml, pairCardHtml, pairFacts, pairTableHtml, verdictOf, RACE_END, amplitudeSoFar, fmtClock, instTip, isLimitUp, leadOf, pathPoints, peakSoFar, raceDomain, raceFrames, raceOrder } from '../../static/js/race.js';

test('raceFrames forward-fills closes, remembers when a value was reached, keeps highs per minute', () => {
  const f = raceFrames({ A: [[0, 1, 2], [5, 10, 10], [6, 10, 10], [30, 9, 9.5]] }, ['A', 'B']);
  assert.equal(f.A.values.length, RACE_END + 1);
  assert.deepEqual([f.A.values[0], f.A.values[4], f.A.values[5], f.A.values[29], f.A.values[30]], [1, 1, 10, 10, 9]);
  assert.deepEqual([f.A.since[6], f.A.since[29], f.A.since[30]], [5, 5, 30]); // 10% since 09:05
  assert.deepEqual([f.A.highs[0], f.A.highs[1], f.A.highs[30]], [2, null, 9.5]);
  assert.equal(f.B.values[100], null); // no trade
});

test('raceOrder: higher change first; equal limit-up → the earlier one stays ahead; untraded last', () => {
  const f = raceFrames({ A: [[0, 2], [40, 10]], B: [[0, 5], [10, 10]], C: [[0, 3]], D: [] }, ['A', 'B', 'C', 'D']);
  assert.deepEqual(raceOrder(['A', 'B', 'C', 'D'], f, 0), ['B', 'C', 'A', 'D']);
  assert.deepEqual(raceOrder(['A', 'B', 'C', 'D'], f, 50), ['B', 'A', 'C', 'D']); // both 10%: B locked first
});

test('peakSoFar: highest high so far, earliest minute on ties, nothing after 13:00 counts', () => {
  const f = raceFrames({ A: [[0, 1, 1], [20, 3, 4], [50, 2, 4], [250, 6, 8]] }, ['A']).A;
  assert.equal(peakSoFar(f, 10).v, 1);
  assert.deepEqual(peakSoFar(f, 100), { m: 20, v: 4 }); // 4 again at 09:50: the first stays
  assert.deepEqual(peakSoFar(f, 270), { m: 20, v: 4 }); // the 13:10 spike is outside the window
  assert.equal(peakSoFar(raceFrames({}, ['X']).X, 270), null);
});

test('pathPoints draws the close path up to the playhead only', () => {
  const f = raceFrames({ A: [[2, 1], [4, -1]] }, ['A']).A;
  assert.equal(pathPoints(f, 3, (v) => 10 - v), '2,9.0 3,9.0');
});

test('raceDomain covers zero, closes and highs; clock labels', () => {
  assert.deepEqual(raceDomain(raceFrames({ A: [[0, -3, -2], [9, 7, 8]] }, ['A'])), [-3, 8]);
  assert.deepEqual(raceDomain(raceFrames({ A: [[0, 0.2]] }, ['A'])), [0, 1]);
  assert.equal(fmtClock(0), '09:00');
  assert.equal(fmtClock(270), '13:30');
});

test('raceOrder: the first stock locked limit-up stays first even when a later one shows a higher %', () => {
  // A locks at 09:30 (+9.94%); B reaches the limit at 12:00 with +10.00% (tick rounding)
  const f = raceFrames({ A: [[0, 3], [30, 9.94]], B: [[0, 5], [180, 10.0]], C: [[0, 8]] }, ['A', 'B', 'C']);
  assert.deepEqual(raceOrder(['A', 'B', 'C'], f, 20), ['C', 'B', 'A']);
  assert.deepEqual(raceOrder(['A', 'B', 'C'], f, 40), ['A', 'C', 'B']); // a limit-up beats +8%
  assert.deepEqual(raceOrder(['A', 'B', 'C'], f, 200), ['A', 'B', 'C']); // B is higher but locked later
  assert.deepEqual([f.A.lockedAt[29], f.A.lockedAt[30], f.A.lockedAt[270]], [null, 30, 30]);
});

test('raceOrder: opening the limit loses the place; re-locking counts from the new lock', () => {
  const f = raceFrames({ A: [[0, 9.9], [60, 8], [150, 9.9]], B: [[0, 2], [100, 9.95]] }, ['A', 'B']);
  assert.deepEqual(raceOrder(['A', 'B'], f, 50), ['A', 'B']);
  assert.deepEqual(raceOrder(['A', 'B'], f, 120), ['B', 'A']); // A opened at 10:00, B locked at 10:40
  assert.deepEqual(raceOrder(['A', 'B'], f, 200), ['B', 'A']); // A re-locked at 11:30, after B
  assert.equal(f.A.lockedAt[200], 150);
});

test('isLimitUp uses the exact limit-up % per stock, else the 9.5% rule', () => {
  const at = isLimitUp(9.95);
  assert.equal(at(9.7), false); // +9.70% is not limit-up when the limit is +9.95%
  assert.equal(at(9.95), true);
  assert.equal(isLimitUp(null)(9.6), true);
  const f = raceFrames({ A: [[0, 9.7], [10, 9.95]] }, ['A'], { A: 9.95 });
  assert.deepEqual([f.A.lockedAt[5], f.A.lockedAt[10]], [null, 10]);
});

test('leadOf: first at the close, from the minute it held first place to the close', () => {
  // B locks at 09:40 and stays; A was ahead before that
  const f = raceFrames({ A: [[0, 5], [60, 4]], B: [[0, 1], [40, 9.95]], C: [[0, 2]] }, ['A', 'B', 'C'], { B: 9.95 });
  assert.deepEqual(leadOf(['A', 'B', 'C'], f), { code: 'B', from: 40 });
  // a first place that closed down is no 領漲
  assert.equal(leadOf(['A'], raceFrames({ A: [[0, -1]] }, ['A'])), null);
});

test('amplitudeSoFar: highest high − lowest low up to the playhead', () => {
  const f = raceFrames({ A: [[0, 1, 2, -1], [30, 5, 6, 4], [60, -2, 0, -3]] }, ['A']).A;
  assert.equal(amplitudeSoFar(f, 10), 3); // 2 − (−1)
  assert.equal(amplitudeSoFar(f, 40), 7); // 6 − (−1)
  assert.equal(amplitudeSoFar(f, 270), 9); // 6 − (−3)
  assert.equal(amplitudeSoFar(raceFrames({}, ['X']).X, 270), null);
});

test('instTip: 三大法人 net shares as 張 for a K row tooltip', () => {
  assert.equal(instTip(1_234_400), '　法人 +1,234 張');
  assert.equal(instTip(-56_700), '　法人 −57 張');
  assert.equal(instTip(0), '　法人 0 張');
  assert.equal(instTip(null), '');
  assert.equal(instTip(undefined), '');
});

test('pairFacts / pairCardHtml / pairTableHtml: 交集 of two picked stocks at the playhead', () => {
  const d = {
    members: [{ code: 'A', name: '甲', inst_net: 2_000_000 }, { code: 'B', name: '乙', inst_net: -500_000 }, { code: 'C', name: '丙', inst_net: null }],
    daily: { matrix20: [[1, 0.82, 0.1], [0.82, 1, 0.2], [0.1, 0.2, 1]], matrix60: [[1, 0.65, 0], [0.65, 1, 0], [0, 0, 1]] },
    intraday: {
      matrix: [[1, 0.71, 0.1], [0.71, 1, 0.3], [0.1, 0.3, 1]],
      by_session: [
        { date: '2026-10-20', matrix: [[1, null, 0], [null, 1, 0], [0, 0, 1]] },
        { date: '2026-10-21', matrix: [[1, 0.58, 0], [0.58, 1, 0], [0, 0, 1]] },
        { date: '2026-10-22', matrix: [[1, 0.72, 0], [0.72, 1, 0], [0, 0, 1]] },
      ],
    },
  };
  const frames = raceFrames({ A: [[0, 1, 1], [50, 9.9, 9.9], [55, 10, 10]], B: [[0, 2, 2], [45, 8, 8.6], [60, 8.6, 8.6]], C: [[0, -1, -1]] }, ['A', 'B', 'C'], { A: 10, B: 10, C: 10 });
  const f = pairFacts(d, frames, 'A', 'B', 270);
  assert.deepEqual([f.r20, f.r60, f.ri], [0.82, 0.65, 0.71]);
  assert.deepEqual(f.riDays, [{ date: '2026-10-22', r: 0.72 }, { date: '2026-10-21', r: 0.58 }, { date: '2026-10-20', r: null }]); // newest first
  assert.deepEqual([f.peakA, f.peakB, f.peakGap, f.firstPeak], [55, 45, 10, 'B']);
  assert.deepEqual([f.lockA, f.lockB, f.firstLock], [55, null, 'A']);
  assert.ok(Math.abs(f.diff - 1.4) < 1e-9);
  const early = pairFacts(d, frames, 'A', 'B', 50); // the playhead before A's lock and peak
  assert.equal(early.lockA, null);
  assert.equal(early.peakA, 50);
  const name = (c) => ({ A: '甲', B: '乙', C: '丙' })[c];
  const color = () => '#fff';
  const html = pairCardHtml(f, { same_dir: { same: 16, total: 20 }, groups: [{ label: '自訂族群', group: '記憶體' }], finder: [{ date: '2026-10-22', method: 'known' }], themes: ['PCB'] }, name, color);
  assert.match(html, /R20 <b class="up">0\.82<\/b> <small class="up">群體圍攻<\/small>/);
  assert.match(html, /乙<\/b> 09:45 先到，<b[^>]*>甲<\/b> 晚 <b>10<\/b> 分 <small class="up">高度同步/);
  assert.match(html, /甲<\/b> 09:55 鎖；<b[^>]*>乙<\/b> 未鎖/);
  assert.match(html, /\+2,000 張／<b[^>]*>乙<\/b> −500 張（方向相反）/);
  assert.match(html, /<b>16<\/b>／20 天 <small class="up">80%/);
  assert.match(html, /自訂族群：記憶體/);
  assert.match(html, /近 5 天 <b>1<\/b> 天：10-22 🔁/);
  assert.match(html, /📰 PCB/);
  assert.match(pairCardHtml(f, null, name, color), /載入中/);
  assert.equal(verdictOf(0.25, 0.7, 0.3), '單兵作戰');
  // three picked: a row per pair, highest R20 first, one expanded
  const list = [['A', 'B'], ['A', 'C'], ['B', 'C']].map(([a, b]) => ({ key: `${a},${b}`, f: pairFacts(d, frames, a, b, 270) }));
  const t = pairTableHtml(list, () => null, name, color, 'B,C');
  assert.deepEqual([...t.matchAll(/data-pair="([^"]+)"/g)].map((m) => m[1]), ['A,B', 'B,C', 'A,C']);
  assert.match(t, /class="rt-pair-open"/);
});

test('sharedGroupsHtml: each kind once, at most three names, the rest counted', () => {
  const gs = [{ label: '官方產業', group: '半導體業' }, ...['a', 'b', 'c', 'd', 'e'].map((x) => ({ label: '細產業', group: x }))];
  assert.equal(sharedGroupsHtml(gs), '官方產業：半導體業；細產業：a、b、c <small class="muted">等 5 個</small>');
  assert.equal(sharedGroupsHtml([{ label: '自訂族群', group: '<x>' }]), '自訂族群：&lt;x&gt;');
});

test('riDaysHtml: 今日／昨日／前日 intraday R, — when a session had too few points', () => {
  const html = riDaysHtml([{ date: '2026-10-22', r: 0.72 }, { date: '2026-10-21', r: 0.15 }, { date: '2026-10-20', r: null }]);
  assert.match(html, /今日 <b class="up" title="2026-10-22">0\.72<\/b>　昨日 <b class="muted"[^>]*>0\.15<\/b>　前日 <b class="muted"[^>]*>—<\/b>/);
  assert.equal(riDaysHtml([]), '');
  assert.equal(riDaysHtml(undefined), '');
});
