import { test } from 'node:test';
import assert from 'node:assert/strict';

import { RACE_END, fmtClock, isLimitUp, pathPoints, peakSoFar, raceDomain, raceFrames, raceOrder } from '../../static/js/race.js';

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
