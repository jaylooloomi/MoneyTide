import { test } from 'node:test';
import assert from 'node:assert/strict';

import { OVERSEAS, aggregateCounties, buildMapOption, countyTooltip, turnoverColor } from '../../static/js/countymap.js';

const s = (code, turnover_100m, change_pct, kind = 'stock', industry = 'X') => ({
  code, name: `n${code}`, kind, industry, turnover_100m, change_pct, change: change_pct, market_cap: 100, prev_close: 10,
});

test('aggregateCounties: common stocks once each, overseas and unknown counted apart', () => {
  const stocks = [s('1', 10, 1), s('1', 10, 1, 'stock', 'Y'), s('2', 30, -1), s('3', 5, 2), s('4', 1, 0), s('5', 2, 0), s('E', 99, 0, 'etf')];
  const map = { 1: ['臺北市'], 2: ['臺北市'], 3: ['新竹市'], 4: [OVERSEAS], E: ['臺北市'] };
  const { rows, overseas, unknown } = aggregateCounties(stocks, map);
  assert.equal(overseas, 1);
  assert.equal(unknown, 1); // code 5 has no county
  assert.deepEqual(rows.map((r) => [r.name, r.count, r.turnover_100m]), [['臺北市', 2, 40], ['新竹市', 1, 5]]);
  assert.deepEqual(rows[0].top.map((t) => t.code), ['2', '1']);
  assert.equal(rows[0].change_pct, 0); // equal caps: (+1 − 1) / 2
});

test('buildMapOption colours by turnover or change and labels accordingly', () => {
  const rows = [{ name: '臺北市', count: 2, turnover_100m: 400, change_pct: 1.5, top: [] }, { name: '新竹市', count: 1, turnover_100m: 100, change_pct: -2, top: [] }];
  const byTurnover = buildMapOption(rows, 'turnover').series[0];
  assert.equal(byTurnover.map, 'tw-counties');
  assert.equal(byTurnover.data[0].itemStyle.areaColor, turnoverColor(400, 400));
  assert.notEqual(byTurnover.data[1].itemStyle.areaColor, byTurnover.data[0].itemStyle.areaColor);
  assert.match(byTurnover.label.formatter({ name: '臺北市' }), /億/);
  const byChange = buildMapOption(rows, 'change').series[0];
  assert.equal(byChange.data[1].value, -2);
  assert.match(byChange.label.formatter({ name: '新竹市' }), /-2\.00%/);
  assert.equal(byChange.label.formatter({ name: '澎湖縣' }), '');
});

test('turnoverColor and tooltip', () => {
  assert.equal(turnoverColor(0, 100), '#2a2d35');
  assert.equal(turnoverColor(100, 100), '#ffb300');
  const html = countyTooltip({ name: '臺北市', count: 2, turnover_100m: 40, change_pct: 0.5, top: [{ code: '2', name: '<b>', turnover_100m: 30, change_pct: -1 }] });
  assert.match(html, /臺北市/);
  assert.match(html, /&lt;b&gt;/); // names are escaped
});

test('countyListHtml sorts by the chosen metric and shows shares', async () => {
  const { countyListHtml } = await import('../../static/js/countymap.js');
  const rows = [
    { name: '臺北市', count: 2, turnover_100m: 300, change_pct: -1, top: [] },
    { name: '新竹市', count: 1, turnover_100m: 100, change_pct: 2, top: [] },
  ];
  const order = (html) => [...html.matchAll(/data-county="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(order(countyListHtml(rows, 'turnover')), ['臺北市', '新竹市']);
  assert.deepEqual(order(countyListHtml(rows, 'change')), ['新竹市', '臺北市']);
  assert.match(countyListHtml(rows), /75\.0%/);
});
