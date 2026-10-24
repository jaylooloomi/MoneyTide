import { test } from 'node:test';
import assert from 'node:assert/strict';

import { evidenceCount, evidenceHtml, evidenceItems, groupEvidenceHtml, groupEvidenceItems, isStrong } from '../../static/js/evidence.js';

const EXT = {
  same_dir: { same: 16, total: 20 },
  groups: [],
  finder: [{ date: '2026-10-22', method: 'known' }, { date: '2026-10-21', method: 'known' }],
  themes: ['PCB'],
  relations: [{ src_name: 'A', dst_name: 'B', pct: 30, method: '權益法', seats: [] }],
  group: null,
  baseline_intraday: { pct: 96, n: 300, median: 0.1 },
  baseline_daily: { pct: 80, n: 300, median: 0.2 },
  chips: { trust_days: 10, trust_both_buy: 4, trust_both_sell: 0, inst_a: 1, inst_b: -1, margin_a: 1, margin_b: 1 },
};

test('evidenceItems: each check as ✓／✗／— from the numbers', () => {
  const f = { ri: 0.62 };
  const ev = { excess: 0.55, minute: { co: 4, expected: 0.8, r0: 0.45, r_off: 0.2, bursts_a: 10, bursts_b: 12 } };
  const items = evidenceItems(f, EXT, ev);
  const by = Object.fromEntries(items.map((x) => [x.key, x.ok]));
  assert.deepEqual(by, { excess: true, baseline: true, burst: true, sync: true, repeat: true, chips: true, relation: true, samedir: true, theme: true });
  assert.match(items.find((x) => x.key === 'excess').detail, /扣大盤／櫃買後分時 R 0\.55（原 0\.62）/);
  assert.match(items.find((x) => x.key === 'baseline').detail, /高於 96% 的同日隨機配對；日 R 高於 80%/);
  // weak numbers say ✗; missing data says —
  const weak = evidenceItems({ ri: 0.3 }, { ...EXT, finder: [], baseline_intraday: { pct: 40 }, chips: { trust_days: 10, trust_both_buy: 0, trust_both_sell: 1, inst_a: 1, inst_b: -1 } }, { excess: 0.1, minute: { co: 1, expected: 1.5, r0: 0.3, r_off: 0.35 } });
  const w = Object.fromEntries(weak.map((x) => [x.key, x.ok]));
  assert.deepEqual([w.excess, w.baseline, w.burst, w.sync, w.repeat, w.chips], [false, false, false, false, false, false]);
  const none = Object.fromEntries(evidenceItems({ ri: null }, null, { excess: null, minute: null }).map((x) => [x.key, x.ok]));
  assert.ok(Object.values(none).every((v) => v === null));
});

test('evidenceHtml: counts only the checks that had data', () => {
  const html = evidenceHtml([
    { key: 'a', ok: true, label: '甲', detail: 'x' },
    { key: 'b', ok: false, label: '乙', detail: 'y' },
    { key: 'c', ok: null, label: '丙', detail: '資料不足' },
  ]);
  assert.match(html, /🧾 資金一致性證據 <b>1<\/b>／2 項支持 <small class="muted">（1 項資料不足，不算）/);
  assert.match(html, /<b class="up">✓<\/b> 甲/);
  assert.match(html, /<b class="down">✗<\/b> 乙/);
  assert.match(html, /<li class="muted"><span class="muted">—<\/span> 丙/);
});

test('groupEvidenceItems / groupEvidenceHtml / isStrong: an N group\'s checks', () => {
  const g = {
    evidence: {
      excess: { ok: true, r: 0.55 }, baseline: { ok: true, pct: 96 }, burst: { ok: false, co: 1, expected: 2 },
      sync: { ok: null, r0: null, r_off: null }, samedir: { ok: true, share: 0.8 },
    },
    seen_days: ['2026-10-21'], checked_days: 4, evidence_chips: { ok: true, pairs: 1 },
    relations: [], rel_group: null, themes: [{ term: 'PCB', count: 2 }],
  };
  const items = groupEvidenceItems(g);
  const c = evidenceCount(items);
  assert.deepEqual(c, { yes: 6, known: 7 });
  assert.equal(isStrong(c), true);
  assert.equal(isStrong({ yes: 4, known: 4 }), false);
  const html = groupEvidenceHtml(g);
  assert.match(html, /class="fd-ev strong"/);
  assert.match(html, /🧾 證據 <b>6<\/b>\/7/);
  assert.match(html, /<span class="down">✗同爆量<\/span>/);
  assert.match(html, /扣大盤／櫃買後分時 R 0\.55/);
  assert.equal(groupEvidenceHtml({}), ''); // an old result without evidence: no line
});
