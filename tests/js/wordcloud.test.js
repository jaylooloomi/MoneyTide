import { test } from 'node:test';
import assert from 'node:assert/strict';

import { buildWordOption, fitBox, groupWords, shortLabel, sideHtml, wordColor, wordTooltip } from '../../static/js/wordcloud.js';

const s = (code, industry, turnover_100m, change_pct, kind = 'stock') => ({
  code, name: `n${code}`, kind, industry, turnover_100m, change_pct, change: change_pct, market_cap: 100, prev_close: 10,
});

test('shortLabel keeps the finest level and drops a trailing 業', () => {
  assert.equal(shortLabel('半導體／IC設計／電源管理IC'), '電源管理IC');
  assert.equal(shortLabel('半導體業'), '半導體');
  assert.equal(shortLabel('工業'), '工業'); // too short to strip
});

test('groupWords: one word per group, biggest turnover first, sqrt-scaled, hot groups flagged', () => {
  const stocks = [s('1', '甲鏈／記憶體', 400, 2), s('2', '甲鏈／記憶體', 0, 4), s('3', 'ABF', 100, -1), s('E', 'ABF', 999, 0, 'etf'), s('4', '冷門', 0, 0)];
  const words = groupWords(stocks, { hot: new Set(['ABF']) });
  assert.deepEqual(words.map((w) => [w.name, w.full, w.value, w.count, w.hot]), [
    ['記憶體', '甲鏈／記憶體', 20, 2, false],
    ['ABF', 'ABF', 10, 1, true],
  ]); // ETFs and groups without turnover drop out
  assert.equal(words[0].change_pct, 3); // equal caps: (2 + 4) / 2
});

test('groupWords: a shared short label falls back to the full name; move metric sizes by |change|', () => {
  const stocks = [s('1', '甲／其他', 10, 1), s('2', '乙／其他', 20, -4)];
  assert.deepEqual(groupWords(stocks).map((w) => w.name), ['乙／其他', '甲／其他']);
  const byMove = groupWords(stocks, { metric: 'move' });
  assert.deepEqual(byMove.map((w) => [w.full, w.value]), [['乙／其他', 2], ['甲／其他', 1]]);
});

test('wordColor: grey when unknown, red up, green down', () => {
  assert.equal(wordColor(null), '#9a9aa6');
  assert.equal(wordColor(9), '#ff4d4f');
  assert.equal(wordColor(-9), '#2ecc71');
});

test('fitBox keeps the aspect inside the element', () => {
  assert.deepEqual(fitBox(1000, 500, 0.5), { width: 240, height: 480 });
  assert.deepEqual(fitBox(100, 1000, 0.5), { width: 96, height: 192 });
});

test('buildWordOption: hot words glow, the tooltip names the full group', () => {
  const words = [{ name: 'ABF', full: '載板／ABF', value: 3, turnover_100m: 9, change_pct: 1, count: 2, hot: true }];
  const series = buildWordOption(words, { width: 300, height: 600 }).series[0];
  assert.equal(series.type, 'wordCloud');
  assert.equal(series.width, 300);
  assert.equal(series.data[0].textStyle.textShadowBlur, 12);
  assert.match(wordTooltip(words[0]), /載板／ABF/);
  assert.match(wordTooltip(words[0]), /新聞熱門/);
});

test('sideHtml: group figures and members with their share of the group turnover', () => {
  const w = { name: '記憶體', full: '甲鏈／記憶體', value: 3, turnover_100m: 40, change_pct: 2.5, count: 2, up: 2, down: 0, hot: true };
  const members = [s('1', '甲鏈／記憶體', 30, 10), s('2', '甲鏈／記憶體', 10, 1)];
  const html = sideHtml(w, members, 80);
  assert.match(html, /甲鏈／記憶體/);
  assert.match(html, /占 50\.0%/); // 40 of all words' 80
  assert.match(html, /新聞熱門/);
  assert.match(html, /data-code="1"[\s\S]*75%[\s\S]*data-code="2"[\s\S]*25%/);
  assert.match(html, /漲停/);
  assert.match(sideHtml(null, [], 0), /點左邊的字/);
});
