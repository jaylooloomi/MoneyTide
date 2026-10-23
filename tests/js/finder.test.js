import { test } from 'node:test';
import assert from 'node:assert/strict';

import { PRESETS, cardHtml, digestText, shownFilter, finderMarkIndex, finderMarkTitle, csvExport, defaultGroupName, filterHtml, funnelText, presetOf, filterOptions, matchesFilter, progressView, queryOf, statsText } from '../../static/js/finder.js';

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
  assert.equal(new URLSearchParams(queryOf('new', { ...p, new_min_volume_lots: 500 })).get('new_min_volume_lots'), '500');
  assert.equal(new URLSearchParams(queryOf('known', { ...p, new_min_volume_lots: 500 })).get('new_min_volume_lots'), null);
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
  assert.match(html, /法人 \+32\.0 萬張/); // inst_net is shares: 3.2 億股 = 32 萬張
  assert.match(html, /甲、乙同步大漲/);
  assert.match(cardHtml({ ...G, inst_net: -4.5e6 }, 2), /法人 −4,500 張/);
  const inst = cardHtml({ ...G, inst: { lots: 12345, amount_100m: -3.456, buyers: 1, sellers: 2 } }, 2);
  assert.match(inst, /法人 <b class="up">\+1\.2 萬張<\/b>（≈ −3\.5 億）.*買超 1／賣超 2 檔/);
  const per = cardHtml({ ...G, members: G.members.map((m, k) => ({ ...m, inst_net: k ? -2_345_678 : 1_000_400 })) }, 2);
  assert.match(per, /title="[^"]*法人 \+1,000 張/);
  assert.match(per, /title="[^"]*法人 −2,346 張/);
  assert.doesNotMatch(cardHtml(G, 2), /title="[^"]*法人/); // no per-member 法人: nothing in the tooltip
  assert.match(cardHtml({ ...G, inst: { lots: -800, amount_100m: -0.5, buyers: 0, sellers: 2 } }, 2), /法人 <b class="down">−800 張<\/b>/);
  const money = cardHtml({ ...G, turnover_100m: 40, turnover_share: 1.234, avg_pct: 7 }, 4);
  assert.match(money, /成交值 <b>40\.00 億<\/b>（占全市場 <b>1\.23%<\/b>）/);
  assert.match(money, /平均漲幅 <b class="up">\+7\.00%<\/b>/);
  assert.doesNotMatch(html, /fd-money/); // older stored results without the fields
  assert.match(cardHtml({ ...G, seen_days: ['2026-10-20', '2026-10-21'], checked_days: 4 }, 5), /🔁 近 5 天第 3 次/);
  assert.match(cardHtml({ ...G, seen_days: [], checked_days: 4 }, 6), /🆕 首次/);
  assert.doesNotMatch(cardHtml({ ...G, seen_days: [], checked_days: 0 }, 7), /fd-seen/); // nothing to compare with
  const th = cardHtml({ ...G, themes: [{ term: '被動元件', count: 2 }, { term: 'AI', count: 1 }], members: [{ ...G.members[0], themes: ['被動元件', 'AI'] }, G.members[1]] }, 8);
  assert.match(th, /📰 題材：被動元件（2）、AI（1）/);
  assert.match(th, /title="1 甲[^"]*📰 被動元件、AI/);
  assert.doesNotMatch(html, /fd-themes/);
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

test('filter chips: 找法1 by source grouping (a group can count twice), 找法2 by kind', () => {
  const known = {
    method: 'known',
    groupings: ['官方產業', '自訂族群', '細產業'],
    groups: [
      { kind: '已知族群', sources: [{ label: '官方產業' }, { label: '自訂族群' }] },
      { kind: '已知族群', sources: [{ label: '細產業' }] },
      { kind: '已知族群', sources: [{ label: '官方產業' }] },
    ],
  };
  assert.deepEqual(filterOptions(known).map((o) => [o.key, o.n]), [['all', 3], ['官方產業', 2], ['自訂族群', 1], ['細產業', 1]]);
  assert.equal(known.groups.filter((g) => matchesFilter(g, '細產業', 'known')).length, 1);
  assert.equal(known.groups.filter((g) => matchesFilter(g, 'all', 'known')).length, 3);
  const fresh = { method: 'new', groups: [{ kind: '跨族群新組合' }, { kind: '已知族群' }, { kind: '跨族群新組合' }] };
  assert.deepEqual(filterOptions(fresh).map((o) => [o.label, o.n]), [['全部', 3], ['已知族群', 1], ['延伸', 0], ['跨族群新組合', 2]]);
  const html = filterHtml(fresh, '跨族群新組合');
  assert.match(html, /data-filter="跨族群新組合" class="on"/);
  assert.match(html, /data-filter="已知族群的延伸" disabled/);
});

test('defaultGroupName: date + members, legal characters, 30 characters at most', () => {
  assert.equal(defaultGroupName({ members: [{ name: '國巨*' }, { name: '華新科' }] }, '2026-10-22'), 'N1022 國巨+華新科');
  const long = defaultGroupName({ members: Array.from({ length: 8 }, (_, i) => ({ name: `公司名稱${i}號'` })) }, '2026-10-22');
  assert.equal(long.length, 30);
  assert.ok(long.endsWith('…'));
  assert.ok(!/['"\\/,<>]/.test(long));
  assert.match(cardHtml({ ...G }, 3), /data-save="3"/);
});

test('csvExport: one row per member of the cards on screen, with the group figures and thresholds', () => {
  const d = {
    method: 'known', date: '2026-10-22',
    params: { min_amplitude: 3, min_volume_lots: 300, daily_r: 0.8, daily_window: 20, intraday_r: 0.5, peak_gap: 8 },
    groups: [
      { ...G, kind: '已知族群', sources: [{ label: '細產業', group: '被動元件／電容器' }], turnover_100m: 40, turnover_share: 1.2, avg_pct: 7 },
      { ...G, kind: '已知族群', sources: [{ label: '官方產業', group: '半導體業' }] },
    ],
  };
  const [name, header, rows] = csvExport(d);
  assert.equal(name, '資金連動搜尋_找法1_2026-10-22.csv');
  assert.equal(rows.length, 4); // 2 groups × 2 members
  assert.equal(header.length, rows[0].length);
  assert.deepEqual(rows[0].slice(0, 7), ['2026-10-22', '找法1 · 已知分類', 1, '已知族群', '細產業:被動元件／電容器', '1', '甲']);
  assert.match(rows[0][rows[0].length - 1], /振幅>3% 成交量≥300張 日R≥0\.8\(20日\) 分時R≥0\.5 高點差≤8分/);
  const only = csvExport(d, '官方產業');
  assert.equal(only[2].length, 2);
  assert.equal(only[2][0][2], 2); // keeps the card number it has on screen
  assert.match(only[0], /_官方產業\.csv$/);
  assert.equal(csvExport({ ...d, groups: [] }), null);
});

test('funnelText: what removed the pairs, most first, then how many passed', () => {
  const d = { stats: { groups: 2, funnel: { pairs: 40, no_bars: 3, passed: 5, rejected: { 分時相關不足: 20, 高點時間差太大: 12 } } } };
  assert.equal(funnelText(d), '漏斗：進入分時比對 40 對 → 刷掉：分時相關不足 20、高點時間差太大 12、沒有分 K 3 → 三關都過 5 對 → 2 群');
  assert.equal(funnelText({ stats: {} }), ''); // older stored results
});

test('presets only set the linkage thresholds; the current values map back to one or to 自訂', () => {
  const mine = { min_amplitude: 4, min_volume_lots: 500, daily_r: 0.8, new_daily_r: 0.8, intraday_r: 0.5, peak_gap: 8 };
  assert.equal(presetOf(mine), 'standard');
  const loose = { ...mine, ...PRESETS.loose.values };
  assert.equal(presetOf(loose), 'loose');
  assert.equal(loose.min_amplitude, 4); // untouched
  assert.equal(loose.min_volume_lots, 500);
  assert.equal(presetOf({ ...mine, intraday_r: 0.45 }), null); // a hand edit = 自訂
  assert.equal(presetOf({ ...mine, intraday_r: '0.5' }), 'standard'); // form values may be strings
});

test('finderMarkIndex / finderMarkTitle: B marks the groups N found, by source grouping and name', () => {
  const res = { groups: [
    { members: [{ name: '甲' }, { name: '乙' }], daily_r: 0.86, intraday_r: 0.61, peak_spread: 3, sources: [{ label: '官方產業', group: '半導體業' }, { label: '自訂族群', group: 'IC' }] },
    { members: [{ name: '丙' }, { name: '丁' }], daily_r: 0.9, intraday_r: null, peak_spread: 0, sources: [{ label: '官方產業', group: '半導體業' }] },
  ] };
  const idx = finderMarkIndex(res);
  assert.equal(idx.get('官方產業|半導體業').length, 2);
  assert.equal(idx.get('自訂族群|IC').length, 1);
  assert.equal(idx.get('細產業|半導體業'), undefined);
  const title = finderMarkTitle(idx.get('官方產業|半導體業'));
  assert.match(title, /甲、乙（日R 0\.86、分時R 0\.61、高點差 3 分）/);
  assert.match(title, /丙、丁（日R 0\.90、分時R —/);
  assert.equal(finderMarkIndex(null).size, 0);
});

test('digestText: counts per method from stored results, 🔁 for repeats, nothing when none is stored', () => {
  const known = { groups: [{ seen_days: ['2026-10-19'] }, { seen_days: [] }, {}] };
  const fresh = { groups: [{ seen_days: [] }] };
  assert.equal(digestText(known, fresh), '💡 資金連動：找法1 3 群（🔁 1）／找法2 1 群');
  assert.equal(digestText(known, { stored: false, groups: [] }), '💡 資金連動：找法1 3 群（🔁 1）');
  assert.equal(digestText({ groups: [] }, null), '💡 資金連動：找法1 0 群');
  assert.equal(digestText({ stored: false, groups: [] }, null), '');
});

test('shownFilter: a saved chip the day has no cards for falls back to 全部 (so the CSV matches the screen)', () => {
  const d = { method: 'new', groups: [{ kind: '已知族群' }] };
  assert.equal(shownFilter(d, '已知族群'), '已知族群');
  assert.equal(shownFilter(d, '跨族群新組合'), 'all');
  assert.equal(shownFilter(d, undefined), 'all');
  assert.equal(csvExport({ ...d, date: '2026-10-22', params: {}, groups: [{ kind: '已知族群', members: [{ code: '1', name: 'a' }] }] }, shownFilter(d, '跨族群新組合'))[2].length, 1);
});
