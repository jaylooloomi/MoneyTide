import { test } from 'node:test';
import assert from 'node:assert/strict';

import { aiStatusText, moverCardHtml, reasonsHtml } from '../../static/js/ainews.js';

const row = (over = {}) => ({ code: '2330', name: '台積電', industry: '半導體業', change_pct: 5, turnover_100m: 100, reason: null, links: [], ...over });

test('mover card states: not analysed, reason with links, error', () => {
  assert.match(moverCardHtml(row()), /尚未分析/);
  const html = moverCardHtml(row({ reason: '利多', cached: true, links: [{ title: 'T', source: 'S', url: 'https://x/1' }] }));
  assert.match(html, /利多/);
  assert.match(html, /href="https:\/\/x\/1" target="_blank" rel="noopener noreferrer"/);
  assert.match(html, /已快取/);
  assert.match(moverCardHtml(row({ error: 'AI 服務暫時無法使用' })), /⚠ AI 服務暫時無法使用/);
});

test('mover card escapes text and refuses non-http links', () => {
  const html = moverCardHtml(row({ name: '<img>', reason: '<script>', links: [{ title: 'x', url: 'javascript:alert(1)' }] }));
  assert.ok(!html.includes('<script>') && !html.includes('<img>'));
  assert.match(html, /href="#"/);
});

test('reasons layout and status text', () => {
  const html = reasonsHtml({ gainers: [row()], losers: [] });
  assert.match(html, /漲幅前 3 名/);
  assert.match(html, /沒有符合條件的股票/);
  assert.match(aiStatusText({ configured: false }), /OPENMARKET_AI_KEY/);
  assert.match(aiStatusText({ configured: true, model: 'm', host: 'h' }), /m（h）/);
});
