import { test } from 'node:test';
import assert from 'node:assert/strict';

import { matrixHtml, summaryHtml } from '../../static/js/linkage.js';

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
