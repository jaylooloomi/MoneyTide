import { test } from 'node:test';
import assert from 'node:assert/strict';

import { clusterOrder, instSummaryHtml, loners, matrixBlock, matrixHtml, summaryHtml, topPairs } from '../../static/js/linkage.js';

test('matrix: diagonal dash, values, escaping', () => {
  const html = matrixHtml(['A', '<b>'], [[1, 0.82], [0.82, 1]]);
  assert.match(html, /0\.82/);
  assert.equal((html.match(/<td class="muted">—<\/td>/g) || []).length, 2);
  assert.ok(!html.includes('<b>') && html.includes('&lt;b&gt;'));
  assert.match(matrixHtml([], []), /資料不足/);
});

test('summary shows verdicts and sources', () => {
  const html = summaryHtml({
    daily: { r20: 0.81, r60: 0.6 }, intraday: { r: 0.3, sessions: [{ date: '2026-10-22', source: 'recorded' }, { date: '2026-10-21', source: 'yahoo' }] },
    peak_std_min: 8, leader_lag_min: 2.5, verdict: { daily: '群體圍攻', intraday: '中度連動', timing: '高度同步' },
  });
  assert.match(html, /0\.81/);
  assert.match(html, /群體圍攻/);
  assert.match(html, /10-22 自錄、10-21 Yahoo/);
  assert.match(html, /\+3 分/);
});

test('instSummaryHtml: 法人 of the shown members, labelled as such, nothing before 法人 is out', () => {
  const html = instSummaryHtml([{ inst_net: 2_010_223 }, { inst_net: 1_208_317 }, { inst_net: -1000 }, { inst_net: null }]);
  assert.match(html, /法人（前 4 大成員）<\/span> <b class="up">\+3,218 張<\/b> <small class="muted">買超 2／賣超 1<\/small>/);
  assert.match(html, /不是整個族群/);
  assert.equal(instSummaryHtml([{ inst_net: null }]), '');
  assert.equal(instSummaryHtml(undefined), '');
  assert.match(summaryHtml({ daily: {}, intraday: { sessions: [] }, verdict: {}, leader_lag_min: null, peak_std_min: null, members: [{ inst_net: -5000 }] }), /−5 張/);
});

// two blocks that move together (A,C) and (B,D), and E on its own
const M5 = [
  [1, 0.1, 0.9, 0.2, 0.0],
  [0.1, 1, 0.2, 0.8, 0.1],
  [0.9, 0.2, 1, 0.1, -0.1],
  [0.2, 0.8, 0.1, 1, 0.0],
  [0.0, 0.1, -0.1, 0.0, 1],
];
const N5 = ['A', 'B', 'C', 'D', 'E'];

test('clusterOrder puts members that move together next to each other', () => {
  const o = clusterOrder(M5).map((i) => N5[i]);
  const at = (x) => o.indexOf(x);
  assert.equal(Math.abs(at('A') - at('C')), 1);
  assert.equal(Math.abs(at('B') - at('D')), 1);
  assert.equal(o.length, 5);
});

test('topPairs / loners give the conclusions', () => {
  assert.deepEqual(topPairs(N5, M5, 2).map((p) => [p.a, p.b, p.r]), [['A', 'C', 0.9], ['B', 'D', 0.8]]);
  assert.equal(loners(N5, M5, 1)[0].name, 'E');
});

test('matrixBlock: numbers up to 12 members, a heat grid with conclusions above that', () => {
  assert.match(matrixBlock(N5, M5), /link-matrix/);
  const n = 13;
  const big = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => (i === j ? 1 : 0.5)));
  const html = matrixBlock(Array.from({ length: n }, (_, i) => `S${i}`), big);
  assert.match(html, /link-heat/);
  assert.match(html, /連動最強的 10 對/);
  assert.match(html, /最獨立的 5 檔/);
});
