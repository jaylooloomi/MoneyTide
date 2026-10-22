import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  NO_DATA_COLOR,
  aggregateIndustries,
  buildTreemapData,
  buildTreemapOption,
  colorFor,
  filterStocks,
  fmtCap,
  fmtChange,
  fmtPct,
  industryAverage,
  labelLayout,
  leafLabelFormatter,
  sortRows,
  tooltipFormatter,
  upperLabelFormatter,
  watchRows,
} from '../../static/js/transform.js';

const stock = (code, over = {}) => ({
  code,
  name: code,
  price: 100,
  change: 1,
  change_pct: 1,
  week_pct: 2,
  amplitude_pct: 3,
  open: 99,
  high: 101,
  low: 98,
  prev_close: 100,
  volume_lots: 10,
  turnover_100m: 1,
  industry: '半導體業',
  market: '上市',
  kind: 'stock',
  market_cap: 1000,
  ...over,
});

test('colorFor: neutral, clamped ends, null', () => {
  assert.equal(colorFor(0, 7), '#3d3d46');
  assert.equal(colorFor(7, 7), '#e0262c');
  assert.equal(colorFor(14, 7), '#e0262c');
  assert.equal(colorFor(-7, 7), '#1fa24a');
  assert.equal(colorFor(-20, 7), '#1fa24a');
  assert.equal(colorFor(null, 7), NO_DATA_COLOR);
  assert.equal(colorFor(NaN, 7), NO_DATA_COLOR);
  assert.notEqual(colorFor(3.5, 7), colorFor(7, 7));
});

test('formatters', () => {
  assert.equal(fmtPct(1.234), '+1.23%');
  assert.equal(fmtPct(-0.5), '-0.50%');
  assert.equal(fmtPct(0), '0.00%');
  assert.equal(fmtPct(-0.001), '0.00%');
  assert.equal(fmtPct(0.004), '0.00%');
  assert.equal(fmtPct(null), '—');
  assert.equal(fmtChange(210), '▲210');
  assert.equal(fmtChange(-35.5), '▼35.5');
  assert.equal(fmtCap(28.1e12), '28.10 兆');
  assert.equal(fmtCap(352.1e8), '352.1 億');
  assert.equal(fmtCap(null), '—');
});

test('filterStocks: market, ETF, other, watchOnly', () => {
  const stocks = [
    stock('2330'),
    stock('5274', { market: '上櫃' }),
    stock('0050', { kind: 'etf', industry: 'ETF' }),
    stock('2881A', { kind: 'other' }),
  ];
  const codes = (list) => list.map((s) => s.code);
  assert.deepEqual(codes(filterStocks(stocks, { market: 'all', includeEtf: false, watchOnly: false }, [])), ['2330', '5274']);
  assert.deepEqual(codes(filterStocks(stocks, { market: 'all', includeEtf: true, watchOnly: false }, [])), ['2330', '5274', '0050']);
  assert.deepEqual(codes(filterStocks(stocks, { market: '上櫃', includeEtf: true, watchOnly: false }, [])), ['5274']);
  assert.deepEqual(
    codes(filterStocks(stocks, { market: 'all', includeEtf: false, watchOnly: true }, ['0050', '2881A', '2330'])),
    ['2330', '0050', '2881A'],
  );
  assert.deepEqual(codes(filterStocks(stocks, { market: 'all', includeEtf: false, watchOnly: true }, [])), []);
});

test('industryAverage: cap-weighted over members with cap, equal weight only when none has cap', () => {
  const a = stock('A', { change_pct: 2, market_cap: 300 });
  const b = stock('B', { change_pct: -1, market_cap: 100 });
  assert.equal(industryAverage([a, b], 'change_pct'), (2 * 300 - 1 * 100) / 400);
  // a member without cap is ignored while others have caps
  const c = stock('C', { change_pct: 50, market_cap: null });
  assert.equal(industryAverage([a, b, c], 'change_pct'), (2 * 300 - 1 * 100) / 400);
  // nobody has cap → equal weight
  const d = stock('D', { change_pct: 1, market_cap: null });
  assert.equal(industryAverage([c, d], 'change_pct'), 25.5);
  // nulls excluded; nothing left → null
  assert.equal(industryAverage([stock('E', { change_pct: null })], 'change_pct'), null);
});

test('industryAverage weights by previous-close cap', () => {
  // price 110 vs prev 100: weight = cap/price*prev
  const a = stock('A', { change_pct: 10, price: 110, prev_close: 100, market_cap: 1100 });
  const b = stock('B', { change_pct: 0, price: 100, prev_close: 100, market_cap: 1000 });
  assert.equal(industryAverage([a, b], 'change_pct'), 5);
});

test('aggregateIndustries: counts, turnover share', () => {
  const rows = aggregateIndustries([
    stock('A', { change: 1, turnover_100m: 3 }),
    stock('B', { change: -1, turnover_100m: 1 }),
    stock('C', { change: 0, turnover_100m: 0, industry: '航運業' }),
    stock('D', { change: null, turnover_100m: null, industry: '航運業' }),
  ]);
  const semi = rows.find((r) => r.name === '半導體業');
  const ship = rows.find((r) => r.name === '航運業');
  assert.deepEqual([semi.up_count, semi.down_count, semi.flat_count, semi.stock_count], [1, 1, 0, 2]);
  assert.equal(semi.turnover_share, 100);
  assert.equal(ship.flat_count, 2);
  assert.equal(ship.turnover_share, 0);
});

test('sortRows: direction, nulls last, breadth', () => {
  const rows = [
    { name: 'a', change_pct: 1, up_count: 1, down_count: 5 },
    { name: 'b', change_pct: null, up_count: 9, down_count: 0 },
    { name: 'c', change_pct: 3, up_count: 2, down_count: 2 },
  ];
  assert.deepEqual(sortRows(rows, 'change_pct', 'desc').map((r) => r.name), ['c', 'a', 'b']);
  assert.deepEqual(sortRows(rows, 'change_pct', 'asc').map((r) => r.name), ['a', 'c', 'b']);
  assert.deepEqual(sortRows(rows, 'breadth', 'desc').map((r) => r.name), ['b', 'c', 'a']);
});

test('watchRows keeps order and marks missing codes', () => {
  const rows = watchRows([stock('2330'), stock('2454')], ['2454', '9999', '2330']);
  assert.deepEqual(rows.map((r) => r.code), ['2454', '9999', '2330']);
  assert.equal(rows[1].missing, true);
});

test('buildTreemapData: sizes, hidden counts, colors, fresh objects', () => {
  const stocks = [
    stock('A', { market_cap: 500, change_pct: 7 }),
    stock('B', { market_cap: null, change_pct: -1 }),
    stock('E', { kind: 'etf', industry: 'ETF', market_cap: null, turnover_100m: 5 }),
    stock('S', { industry: '航運業', market_cap: 50, week_pct: -15, turnover_100m: 0 }),
  ];
  const cap = buildTreemapData(stocks, { sizeBy: 'cap', colorBy: 'today' });
  assert.equal(cap.hiddenNoSize, 1);
  assert.equal(cap.hiddenEtf, 1);
  const semi = cap.data.find((d) => d.id === 'ind:半導體業');
  assert.equal(semi.children.length, 1);
  assert.equal(semi.children[0].id, 'stk:A');
  assert.equal(semi.children[0].value, 500);
  assert.equal(semi.children[0].itemStyle.color, '#e0262c');
  assert.equal(semi.industry.stock_count, 2); // aggregates include hidden members

  const turnover = buildTreemapData(stocks, { sizeBy: 'turnover', colorBy: 'week' });
  assert.equal(turnover.hiddenNoSize, 1); // S has 0 turnover
  assert.equal(turnover.hiddenEtf, 0);
  assert.ok(turnover.data.find((d) => d.id === 'ind:ETF'));
  const again = buildTreemapData(stocks, { sizeBy: 'turnover', colorBy: 'week' });
  assert.notEqual(again.data[0], turnover.data[0]);
  assert.notEqual(again.data[0].children[0].stock, stocks[0]);
});

test('formatters branch on node type and never throw on parents', () => {
  const tree = buildTreemapData([stock('2330', { name: '台積電', change_pct: 1.5 })], { sizeBy: 'cap', colorBy: 'today' });
  const ind = tree.data[0];
  const leaf = ind.children[0];
  assert.equal(leafLabelFormatter({ data: leaf }), '台積電\n+1.50%');
  assert.equal(leafLabelFormatter({ data: ind }), '');
  assert.equal(upperLabelFormatter({ data: ind, name: ind.name }), '半導體業 +1.50%');
  assert.equal(upperLabelFormatter({ data: {}, name: '全市場' }), '全市場');
  assert.match(tooltipFormatter({ data: leaf }), /2330 台積電/);
  assert.match(tooltipFormatter({ data: ind }), /半導體業/);
  assert.equal(tooltipFormatter({ data: undefined }), '');
});

test('tooltip escapes HTML in names', () => {
  const tree = buildTreemapData([stock('1', { name: '<b>x</b>' })], { sizeBy: 'cap', colorBy: 'today' });
  assert.doesNotMatch(tooltipFormatter({ data: tree.data[0].children[0] }), /<b>x<\/b>/);
});

test('labelLayout hides labels in small cells only', () => {
  assert.deepEqual(labelLayout({ rect: { width: 43, height: 100 } }), { fontSize: 0 });
  assert.deepEqual(labelLayout({ rect: { width: 100, height: 25 } }), { fontSize: 0 });
  assert.deepEqual(labelLayout({ rect: { width: 44, height: 26 } }), {});
});

test('buildTreemapOption: fixed series config', () => {
  const opt = buildTreemapOption({ data: [] });
  const s = opt.series[0];
  assert.equal(s.type, 'treemap');
  assert.equal(s.id, 'map');
  assert.equal(s.name, '全市場');
  assert.equal(s.nodeClick, false);
  assert.equal(s.breadcrumb.show, false);
  assert.equal(s.levels.length, 3);
  assert.equal(s.animation, false);
  const emph = s.levels[1].emphasis;
  assert.notEqual(emph.upperLabel.color, emph.itemStyle.borderColor);
});

test('breadth share and colour', async () => {
  const { breadthShare, breadthColor, colorFor } = await import('../../static/js/transform.js');
  assert.equal(breadthShare(3, 1), 75);
  assert.equal(breadthShare(0, 0), null);
  assert.equal(breadthColor(5, 0), colorFor(50, 50)); // all up → full red
  assert.equal(breadthColor(0, 5), colorFor(-50, 50)); // all down → full green
  assert.equal(breadthColor(4, 4), colorFor(0, 50)); // even → grey
  assert.equal(breadthColor(0, 0), '#2e2e2e');
});

test('treemap ids stay unique when a stock is in several groups', async () => {
  const { buildTreemapData } = await import('../../static/js/transform.js');
  const s = { code: '3017', name: '奇鋐', price: 1, change: 1, change_pct: 1, week_pct: 1, prev_close: 1, turnover_100m: 1, kind: 'stock', market_cap: 10 };
  const tree = buildTreemapData([{ ...s, industry: '散熱' }, { ...s, industry: 'AI' }], { sizeBy: 'cap', colorBy: 'today' });
  const ids = tree.data.flatMap((g) => g.children.map((c) => c.id));
  assert.equal(new Set(ids).size, 2);
  assert.ok(ids.includes('stk:3017'));
});

test('equal size: every stock one tile, none hidden', async () => {
  const { buildTreemapData } = await import('../../static/js/transform.js');
  const base = { price: 1, change: 1, change_pct: 1, week_pct: 1, prev_close: 1, kind: 'stock', industry: 'X' };
  const stocks = [
    { ...base, code: 'A', name: 'A', market_cap: 1e12, turnover_100m: 100 },
    { ...base, code: 'B', name: 'B', market_cap: null, turnover_100m: 0 },
    { ...base, code: 'E', name: 'E', kind: 'etf', industry: 'ETF', market_cap: null, turnover_100m: null },
  ];
  const tree = buildTreemapData(stocks, { sizeBy: 'equal', colorBy: 'today' });
  assert.equal(tree.hiddenNoSize, 0);
  assert.equal(tree.hiddenEtf, 0);
  assert.deepEqual(tree.data.flatMap((g) => g.children.map((c) => c.value)), [1, 1, 1]);
});
