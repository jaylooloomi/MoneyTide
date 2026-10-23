import { test } from 'node:test';
import assert from 'node:assert/strict';

import { RACE_END, fmtClock, raceDomain, raceFrames, raceOrder } from '../../static/js/race.js';

test('raceFrames forward-fills each minute and remembers when the value was reached', () => {
  const f = raceFrames({ A: [[0, 1], [5, 10], [6, 10], [30, 9]] }, ['A', 'B']);
  assert.equal(f.A.values.length, RACE_END + 1);
  assert.deepEqual([f.A.values[0], f.A.values[4], f.A.values[5], f.A.values[29], f.A.values[30]], [1, 1, 10, 10, 9]);
  assert.deepEqual([f.A.since[6], f.A.since[29], f.A.since[30]], [5, 5, 30]); // 10% since 09:05
  assert.equal(f.B.values[100], null); // no trade
});

test('raceOrder: higher change first; equal limit-up → the earlier one stays ahead; untraded last', () => {
  const f = raceFrames({ A: [[0, 2], [40, 10]], B: [[0, 5], [10, 10]], C: [[0, 3]], D: [] }, ['A', 'B', 'C', 'D']);
  assert.deepEqual(raceOrder(['A', 'B', 'C', 'D'], f, 0), ['B', 'C', 'A', 'D']);
  assert.deepEqual(raceOrder(['A', 'B', 'C', 'D'], f, 20), ['B', 'C', 'A', 'D']);
  assert.deepEqual(raceOrder(['A', 'B', 'C', 'D'], f, 50), ['B', 'A', 'C', 'D']); // both 10%: B locked first
});

test('raceDomain covers zero and the day range; clock labels', () => {
  const f = raceFrames({ A: [[0, -3], [9, 7]] }, ['A']);
  assert.deepEqual(raceDomain(f), [-3, 7]);
  assert.deepEqual(raceDomain(raceFrames({ A: [[0, 0.2]] }, ['A'])), [0, 1]);
  assert.equal(fmtClock(0), '09:00');
  assert.equal(fmtClock(270), '13:30');
});
