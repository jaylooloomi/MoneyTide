import { test } from 'node:test';
import assert from 'node:assert/strict';

import { methodText, themesTableHtml, trendHtml } from '../../static/js/newsthemes.js';

const theme = (over = {}) => ({
  name: '低軌衛星', aliases: [], score: 5, prev_score: 2, avg_pct: 3.2, strong_ratio: 40,
  members: [{ code: '6285', name: '啟碁', change_pct: 9.9 }, { code: '3491', name: '昇達科', change_pct: null }],
  titles: [{ title: '低軌衛星族群升空', source: '經濟日報', url: 'https://x/1' }], ...over,
});

test('trend arrows', () => {
  assert.match(trendHtml(5, 2), /▲3/);
  assert.match(trendHtml(1, 4), /▼3/);
  assert.match(trendHtml(3, 0), /新/);
  assert.match(trendHtml(2, 2), /–/);
});

test('themes table: rows, chips, links, escaping', () => {
  const html = themesTableHtml({ themes: [theme(), theme({ name: '<b>x</b>', titles: [{ title: 't', url: 'javascript:alert(1)' }] })] });
  assert.match(html, /data-theme="低軌衛星"/);
  assert.match(html, /data-code="6285"/);
  assert.match(html, /5 則/);
  assert.match(html, /href="https:\/\/x\/1" target="_blank" rel="noopener noreferrer"/);
  assert.ok(!html.includes('<b>x</b>') && html.includes('href="#"'));
  assert.match(themesTableHtml({ themes: [] }), /還沒有新聞族群資料/);
});

test('method text', () => {
  assert.match(methodText({ news_date: '2026-10-22', method: 'ai' }, { running: false }), /AI 整理/);
  assert.match(methodText({ method: 'keyword' }, { running: true, done: 3, total: 60 }), /回補中 3\/60/);
});
