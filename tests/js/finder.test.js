import { test } from 'node:test';
import assert from 'node:assert/strict';

import { cardHtml, progressView, queryOf, statsText } from '../../static/js/finder.js';

test('queryOf sends only the fields of the chosen method; blank 起漲差 means not required', () => {
  const p = { daily_r: 0.75, daily_window: 20, new_daily_r: 0.85, pool_top: 30, intraday_r: 0.5, peak_gap: 8, start_gap: '', require_burst: true, groupings: ['custom', 'news'], pool_sources: ['gain'] };
  const known = new URLSearchParams(queryOf('known', p));
  assert.equal(known.get('method'), 'known');
  assert.equal(known.get('daily_r'), '0.75');
  assert.equal(known.get('new_daily_r'), null);
  assert.equal(known.get('start_gap'), '');
  assert.equal(known.get('require_burst'), 'true');
  assert.equal(known.get('groupings'), 'custom,news');
  const fresh = new URLSearchParams(queryOf('new', p));
  assert.equal(fresh.get('new_daily_r'), '0.85');
  assert.equal(fresh.get('daily_r'), null);
  assert.equal(fresh.get('pool_sources'), 'gain');
});

const G = {
  kind: '已知族群的延伸',
  members: [
    { code: '1', name: '甲', change_pct: 9.9, peak: '09:30', locked_at: '09:30', turnover_rate: 12.3 },
    { code: '2', name: '乙', change_pct: 5, peak: '09:34' },
  ],
  sources: [],
  pool: { 1: ['漲幅', '週轉率'] },
  matches: [{ label: '自訂族群', group: '被動', overlap: 0.5, outside: ['2'] }],
  daily_r: 0.86, intraday_r: 0.61, peak_spread: 4, start_spread: 2, together_bursts: ['09:25'], inst_net: 3.2e8,
  news: ['甲、乙同步大漲'],
};

test('cardHtml: kind, closest grouping, members (outside one marked), facts and headline', () => {
  const html = cardHtml(G, 0);
  assert.match(html, /已知族群的延伸/);
  assert.match(html, /最接近 自訂族群：被動（50%）/);
  assert.match(html, /fd-chip out[^>]*>乙/);
  assert.match(html, /🔒/);
  assert.match(html, /日 R <b>0\.86<\/b>/);
  assert.match(html, /高點差 <b>4<\/b> 分/);
  assert.match(html, /同時爆量 09:25/);
  assert.match(html, /法人 \+3\.2 億/);
  assert.match(html, /甲、乙同步大漲/);
  assert.match(cardHtml({ ...G, inst_net: -4.5e6 }, 2), /法人 −450 萬/);
  assert.match(cardHtml({ ...G, sources: [{ label: '概念股', group: 'AI' }] }, 1), /概念股：AI/);
});

test('statsText summarises the run', () => {
  const t = statsText({ method: 'new', stats: { pool: 113, candidates: 28, fetched: 74, groups: 4, seconds: { total: 2.5 } }, cached: false, missing_groupings: ['chain'] });
  assert.match(t, /候選池 113 檔/);
  assert.match(t, /找到 4 群/);
  assert.match(t, /2\.5 秒/);
  assert.match(t, /尚未載入：細產業/);
});

test('progressView: stages map onto one bar', () => {
  assert.equal(progressView(null).pct, 3);
  assert.match(progressView({ running: true, stage: 'daily', seconds: 1 }).text, /日相關/);
  const mid = progressView({ running: true, stage: 'fetch', done: 50, total: 100, seconds: 4.2 });
  assert.equal(mid.pct, 15 + 38);
  assert.match(mid.text, /抓分 K 50／100 檔　4 秒/);
  assert.equal(progressView({ running: true, stage: 'intraday' }).pct, 95);
});
