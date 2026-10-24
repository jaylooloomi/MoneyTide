import { test } from 'node:test';
import assert from 'node:assert/strict';
import { concHtml, goneReading, mergeGroups, motiveOf, reportText, trackHtml, trackRows, watchOf } from '../../static/js/report.js';
import { groupEvidenceItems } from '../../static/js/evidence.js';

const m = (code, name = code) => ({ code, name, change_pct: 5 });
// an N group with the given checks passing (the server's pair majorities)
const grp = (codes, ok = {}, extra = {}) => ({
  members: codes.map((c) => m(c)),
  evidence: Object.fromEntries(['excess', 'baseline', 'burst', 'sync', 'samedir'].map((k) => [k, { ok: ok[k] ?? null }])),
  ...extra,
});

test('mergeGroups: one entry per member set across 找法1/2, the better supported kept, by support', () => {
  const a = grp(['1', '2'], { excess: true });
  const b = grp(['2', '1'], { excess: true, baseline: true, burst: true }); // the same pair, found by 找法2
  const c = grp(['3', '4'], { excess: true, baseline: true });
  const list = mergeGroups({ groups: [a, c] }, { groups: [b] });
  assert.deepEqual(list.map((x) => [x.key, x.method, x.ev.yes]), [['1,2', 'new', 3], ['3,4', 'known', 2]]);
  assert.deepEqual(mergeGroups(null, null), []);
});

test('motiveOf: the readings come from the evidence, strongest first, at most two', () => {
  const g = grp(['1', '2'], {}, { branches: { ok: true, common: [{ name: '美商高盛', ranks: { 1: 2, 2: 2 } }] }, inst: { lots: 1200 }, daytrade: { hot: true } });
  const r = motiveOf(g, groupEvidenceItems(g));
  assert.deepEqual(r.map((x) => x.label), ['同分點布局', '隔日沖熱錢']);
  assert.match(r[0].text, /美商高盛 同時買超 2 檔/);
  const bare = grp(['1', '2']);
  assert.deepEqual(motiveOf(bare, groupEvidenceItems(bare)).map((x) => x.label), ['只有價格同步']);
  const basket = grp(['1', '2'], { burst: true });
  assert.deepEqual(motiveOf(basket, groupEvidenceItems(basket)).map((x) => x.label), ['一籃子下單']);
});

test('watchOf: what would confirm the reading tomorrow', () => {
  assert.deepEqual(watchOf(grp(['1', '2']), 0), ['是否再一起動']);
  const g = grp(['1', '2'], {}, { branches: { ok: true, common: [{ name: '凱基-台北', ranks: {} }] }, inst: { lots: 5 } });
  assert.deepEqual(watchOf(g, 2), ['是否連續第 3 天同步', '凱基-台北 是否續買', '法人是否續買']);
});

test('trackRows: streaks, new, back again, gone, and days not computed', () => {
  const day = (...groups) => mergeGroups({ groups }, null);
  const ab = (n) => grp(['A', 'B'], Object.fromEntries(['excess', 'baseline', 'burst', 'sync'].slice(0, n).map((k) => [k, true])));
  const cd = grp(['C', 'D'], { excess: true });
  const ef = grp(['E', 'F'], { excess: true });
  const gh = grp(['G', 'H'], { excess: true });
  // oldest → report day; day 2 not computed (null)
  const rows = trackRows([day(gh), null, day(ab(1), cd), day(ab(2), cd), day(ab(3), ef, gh)]);
  const by = Object.fromEntries(rows.map((r) => [r.names, r]));
  assert.equal(by['A、B'].status, '連 3 天・證據變強');
  assert.deepEqual(by['A、B'].cells, [null, undefined, 1, 2, 3]);
  assert.equal(by['A、B'].streak, 2);
  assert.equal(by['E、F'].status, '新出現');
  assert.equal(by['G、H'].status, '再度出現');
  assert.equal(by['C、D'].status, '消失（資金撤出？）');
  assert.deepEqual(rows.map((r) => r.names), ['A、B', 'E、F', 'G、H', 'C、D']); // today's first, then the gone
  const html = trackHtml(['2026-10-16', '2026-10-19', '2026-10-20', '2026-10-21', '2026-10-22'], rows);
  assert.match(html, /<td class="muted" title="那天還沒計算">…<\/td>/);
  assert.match(html, /<td class="l muted">消失（資金撤出？）<\/td>/);
});

test('reportText: the copy-paste version', () => {
  const g = grp(['1', '2'], { excess: true, baseline: true }, { themes: [{ term: 'PCB' }] });
  g.members = [m('1', '華通'), m('2', 'TPK-KY')];
  const list = mergeGroups({ groups: [g] }, null);
  const text = reportText('2026-10-22', [{ name: '大盤', change_pct: -1.81 }], list, trackRows([list]));
  assert.match(text, /^2026-10-22 盤後報告\n大盤 -1\.81%/);
  assert.match(text, /1\. 華通、TPK-KY（證據 3\/3）/);
  assert.match(text, /題材輪動：同題材：PCB/);
  assert.match(text, /明天觀察：是否再一起動/);
});

test('concHtml: each member with 分點 stored, signed; nothing without', () => {
  const g = { members: [{ code: '1', name: '甲' }, { code: '2', name: '乙' }], concentration: { 1: 12.3, 2: -4 } };
  assert.match(concHtml(g), /籌碼集中度<\/span> 甲 <span class="up">\+12\.3%<\/span>、乙 <span class="down">-4\.0%<\/span>/);
  assert.equal(concHtml({ members: [] }), '');
  assert.equal(concHtml({ members: [], concentration: null }), '');
});

test('goneReading: 爆量收黑 by most members reads as 出貨; otherwise they just stopped moving together', () => {
  const ms = [{ code: '1' }, { code: '2' }];
  assert.equal(goneReading(ms, { 1: { change_pct: -5, vol_ratio: 2.4 }, 2: { change_pct: -3, vol_ratio: 2.1 } }), '疑似出貨');
  assert.equal(goneReading(ms, { 1: { change_pct: -5, vol_ratio: 2.4 }, 2: { change_pct: 1, vol_ratio: 0.8 } }), '疑似出貨'); // half of them
  assert.equal(goneReading(ms, { 1: { change_pct: -2, vol_ratio: 1.1 }, 2: { change_pct: 1, vol_ratio: 0.8 } }), '不再同步');
  assert.equal(goneReading(ms, {}), null);
});
