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

test('bursts strip: chips link to matching themes', async () => {
  const { burstsHtml, themesTableHtml } = await import('../../static/js/newsthemes.js');
  const html = burstsHtml([{ term: 'CPO', recent: 9, base_mean: 0.5, z: 4.2 }, { term: 'HBM', recent: 4, base_mean: 0, z: 3 }], [{ name: '矽光子', aliases: ['CPO'] }]);
  assert.match(html, /data-theme="矽光子"/);
  assert.match(html, /HBM<small> 4 次・Z 3.0/);
  assert.equal(burstsHtml([], []), '');
  assert.match(themesTableHtml({ themes: [{ name: 'x', aliases: [], score: 3, prev_score: 1, members: [], titles: [], avg_pct: null, strong_ratio: null, burst: true }] }), /竄升/);
});
