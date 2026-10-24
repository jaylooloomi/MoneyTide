// 🧾 資金一致性證據: one ✓／✗ list per pair in K's 🔗 交集 (pure, node --test).
// Inputs: K's payload evidence (excess R matrix, 1-minute pair stats), pairFacts' numbers, and the
// /api/history/pairs entry (baselines, chips, N sightings, relations, themes). A check without data is
// shown as — and counted neither way.

import { escapeHtml } from './transform.js';

const r2 = (v) => (v === null || v === undefined ? '—' : v.toFixed(2));

/** [{key, ok: true|false|null, label, detail}] for one pair. */
export function evidenceItems(f, ext, ev) {
  const items = [];
  const add = (key, ok, label, detail) => items.push({ key, ok, label, detail });

  // 1. not just the index
  const ex = ev?.excess;
  add('excess', ex === null || ex === undefined ? null : ex >= 0.4,
    '扣掉大盤後還是很像',
    ex === null || ex === undefined ? '資料不足' : `扣大盤／櫃買後分時 R ${r2(ex)}（原 ${r2(f.ri)}）`);

  // 2. not chance: random pairs of the same day and 漲幅 range
  const bi = ext?.baseline_intraday;
  const bd = ext?.baseline_daily;
  const base = bi || bd;
  add('baseline', base ? base.pct >= 90 : null,
    '比隨機配對更像',
    base
      ? [bi ? `分時 R 高於 ${bi.pct}% 的同日隨機配對` : '', bd ? `日 R 高於 ${bd.pct}%` : ''].filter(Boolean).join('；')
      : '資料不足');

  // 3. volume in the same minute
  const mn = ev?.minute;
  const co = mn && mn.expected !== null ? mn : null;
  add('burst', co ? co.co >= 2 && co.co >= 2 * Math.max(co.expected, 0.5) : null,
    '同一分鐘一起爆量',
    co ? `同分鐘爆量 ${co.co} 次（隨機預期 ${co.expected.toFixed(1)} 次）` : '沒有 1 分 K（約 30 天前的日子沒有）');

  // 4. same minute, not one following the other
  const sync = mn && mn.r0 !== null && mn.r_off !== null ? mn : null;
  add('sync', sync ? sync.r0 >= 0.3 && sync.r0 - sync.r_off >= 0.1 : null,
    '同一分鐘同步（不是一前一後）',
    sync ? `1 分 K R ${r2(sync.r0)}，錯開 1～3 分最多 ${r2(sync.r_off)}` : '沒有 1 分 K');

  // 5. found again on other days
  const days = ext ? new Set((ext.finder || []).map((h) => h.date)).size : null;
  add('repeat', days === null ? null : days >= 2, '不只一天', days === null ? '載入中' : `近 5 天 N 找到同一群 ${days} 天`);

  // 6. the same money behind both
  const ch = ext?.chips;
  if (ch) {
    const trust = ch.trust_days ? ch.trust_both_buy + ch.trust_both_sell : null;
    const inst = ch.inst_a !== null && ch.inst_b !== null && ch.inst_a !== 0 && ch.inst_b !== 0 ? ch.inst_a === ch.inst_b : null;
    const ok = trust !== null && trust >= 3 ? true : inst;
    const parts = [];
    if (ch.trust_days) parts.push(`近 ${ch.trust_days} 天投信同買 ${ch.trust_both_buy} 天、同賣 ${ch.trust_both_sell} 天`);
    if (inst !== null) parts.push(`今天法人${inst ? '同方向' : '方向相反'}`);
    add('chips', ok, '籌碼同一邊', parts.join('；') || '當天法人還沒公布');
  } else add('chips', null, '籌碼同一邊', '載入中');

  // 7. a structural reason
  const rel = ext ? (ext.relations?.length || 0) + (ext.group ? 1 : 0) : null;
  add('relation', rel === null ? null : rel > 0 ? true : null, '有持股／集團關係', rel ? '見下方 🏢' : '沒有（或還沒抓到）');

  // 8. day after day
  const sd = ext?.same_dir;
  add('samedir', sd?.total ? sd.same / sd.total >= 0.75 : null, '天天同漲同跌', sd?.total ? `近 ${sd.total} 天 ${sd.same} 天同方向` : '資料不足');

  // 9. one story
  add('theme', ext ? (ext.themes?.length ? true : null) : null, '同一個題材', ext?.themes?.length ? `📰 ${ext.themes.slice(0, 3).join('、')}` : '沒有共同題材');
  return items;
}

/** The ✓／✗ list with its count: 「9 項裡 6 項支持（2 項資料不足）」. */
export function evidenceHtml(items) {
  const yes = items.filter((x) => x.ok === true).length;
  const no = items.filter((x) => x.ok === false).length;
  const none = items.length - yes - no;
  const mark = (ok) => (ok === true ? '<b class="up">✓</b>' : ok === false ? '<b class="down">✗</b>' : '<span class="muted">—</span>');
  const rows = items
    .map((x) => `<li class="${x.ok === null ? 'muted' : ''}">${mark(x.ok)} ${escapeHtml(x.label)} <small class="muted">${escapeHtml(x.detail)}</small></li>`)
    .join('');
  return `<div class="ev-box"><div class="ev-h">🧾 資金一致性證據 <b>${yes}</b>／${yes + no} 項支持${none ? ` <small class="muted">（${none} 項資料不足，不算）</small>` : ''}</div><ul class="ev-list">${rows}</ul></div>`;
}
