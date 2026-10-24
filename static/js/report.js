// 分頁3 · 盤後報告: the day's N groups read as a story (A1) and how each one fared over the last days (A3).
// Built from N's stored results under the default 條件 (找法1 + 找法2, precomputed after the close), so
// opening it starts no search for past days. Pure functions first (node --test), the panel last.

import { escapeHtml, fmtPct } from './transform.js';
import { evidenceCount, groupEvidenceItems, isStrong } from './evidence.js';

export const TRACK_DAYS = 5; // the 跨天追蹤 columns: the report day and the 4 trading days before it
const SHOW_MAX = 8; // groups written out in full; the rest under 其餘

const keyOf = (g) => g.members.map((m) => m.code).sort().join(',');
const namesOf = (g) => g.members.map((m) => m.name).join('、');

/** Both methods' groups of one day, one entry per member set (the one with more support kept), by support. */
export function mergeGroups(known, fresh) {
  const by = new Map();
  for (const [res, method] of [[known, 'known'], [fresh, 'new']]) {
    for (const g of res?.groups || []) {
      const ev = evidenceCount(groupEvidenceItems(g));
      const k = keyOf(g);
      const old = by.get(k);
      if (!old || ev.yes > old.ev.yes) by.set(k, { g, method, ev, key: k, strong: isStrong(ev) });
    }
  }
  return [...by.values()].sort((a, b) => b.ev.yes - a.ev.yes || b.ev.known - a.ev.known || b.g.members.length - a.g.members.length);
}

/**
 * 動機判讀: what the money looks like, from the evidence a group has — at most two readings, the
 * strongest first. [{label, text}]
 */
export function motiveOf(g, items) {
  const ok = (k) => items.find((x) => x.key === k)?.ok === true;
  const out = [];
  const br = g.branches?.common?.[0];
  if (ok('branch') && br) out.push({ label: '同分點布局', text: `${br.name} 同時買超 ${Object.keys(br.ranks).length} 檔，像同一批資金布局` });
  if (ok('relation')) out.push({ label: '集團／持股', text: g.rel_group ? `同屬以 ${g.rel_group.leader_name} 為首的集團` : '成員之間有轉投資或董監關係' });
  if (g.daytrade?.hot) out.push({ label: '隔日沖熱錢', text: '當沖比偏高，短線資金多，明天容易倒貨' });
  if (ok('chips') || g.inst?.lots > 0) out.push({ label: '法人同步', text: g.inst?.lots > 0 ? `法人合計買超 ${g.inst.lots.toLocaleString()} 張` : '投信／法人同方向' });
  if (ok('theme')) out.push({ label: '題材輪動', text: `同題材：${g.themes.map((t) => t.term).slice(0, 3).join('、')}` });
  if (!out.length && (ok('burst') || ok('sync'))) out.push({ label: '一籃子下單', text: '同一分鐘同時爆量／同步，像程式或一籃子單' });
  if (!out.length) out.push({ label: '只有價格同步', text: '缺少資金面的證據，可能是巧合或同一則消息' });
  return out.slice(0, 2);
}

/** 明天觀察: what would confirm (or undo) the reading tomorrow. */
export function watchOf(g, streak) {
  const out = [];
  if (streak >= 1) out.push(`是否連續第 ${streak + 1} 天同步`);
  const br = g.branches?.ok && g.branches.common?.[0];
  if (br) out.push(`${br.name} 是否續買`);
  if (g.inst?.lots > 0) out.push('法人是否續買');
  if (g.daytrade?.hot) out.push('開盤是否開高走低（隔日沖出貨）');
  return out.length ? out : ['是否再一起動'];
}

/**
 * 跨天追蹤: days oldest → newest (the last is the report day), each a merged list (null = not computed).
 * → rows [{key, names, cells: [yes|null|undefined per day], status, streak, members}] — the report day's
 * groups first (as merged), then the ones that were there yesterday and are gone today.
 */
export function trackRows(days) {
  const n = days.length;
  const at = days.map((list) => (list ? new Map(list.map((x) => [x.key, x])) : null));
  const today = days[n - 1] || [];
  const keys = [...today.map((x) => x.key)];
  for (const x of days[n - 2] || []) if (!keys.includes(x.key)) keys.push(x.key);
  return keys.map((k) => {
    const cells = at.map((m) => (m === null ? undefined : m.get(k)?.ev.yes ?? null)); // undefined: that day not computed
    const ref = at.map((m) => m?.get(k)).filter(Boolean).at(-1);
    let streak = 0;
    for (let i = n - 1; i >= 0 && cells[i] !== null && cells[i] !== undefined; i--) streak++;
    const before = cells.slice(0, -1).some((c) => c !== null && c !== undefined);
    const now = cells[n - 1];
    const prev = cells[n - 2];
    let status;
    if (now === null || now === undefined) status = prev !== null && prev !== undefined ? '消失（資金撤出？）' : '—';
    else if (streak >= 2) status = now > prev ? `連 ${streak} 天・證據變強` : `連 ${streak} 天`;
    else status = before ? '再度出現' : '新出現';
    return { key: k, names: namesOf(ref.g), members: ref.g.members, cells, status, streak: Math.max(0, streak - 1) };
  });
}

/** The report as plain text (複製成文字: for notes or a chat). */
export function reportText(date, index, list, rows) {
  const lines = [`${date} 盤後報告`];
  if (index.length) lines.push(index.map((b) => `${b.name} ${fmtPct(b.change_pct)}`).join('　'));
  lines.push(`找到 ${list.length} 組，證據強 ${list.filter((x) => x.strong).length} 組，連續出現 ${rows.filter((r) => r.streak >= 1 && r.cells.at(-1) != null).length} 組`);
  list.slice(0, SHOW_MAX).forEach((x, i) => {
    const items = groupEvidenceItems(x.g);
    const row = rows.find((r) => r.key === x.key);
    lines.push('', `${i + 1}. ${namesOf(x.g)}（證據 ${x.ev.yes}/${x.ev.known}${x.strong ? '・證據強' : ''}）`);
    for (const m of motiveOf(x.g, items)) lines.push(`   ${m.label}：${m.text}`);
    lines.push(`   ✓ ${items.filter((t) => t.ok === true).map((t) => t.short).join('、') || '—'}　✗ ${items.filter((t) => t.ok === false).map((t) => t.short).join('、') || '—'}`);
    lines.push(`   明天觀察：${watchOf(x.g, row?.streak || 0).join('；')}`);
  });
  const gone = rows.filter((r) => r.status.startsWith('消失'));
  if (gone.length) lines.push('', `消失：${gone.map((r) => r.names).join('／')}`);
  return lines.join('\n');
}

// ---- HTML ---------------------------------------------------------------------------------------

function groupHtml(x, i, row) {
  const items = groupEvidenceItems(x.g);
  const chips = items
    .filter((t) => t.ok !== null)
    .map((t) => `<span class="${t.ok ? 'up' : 'down'}" title="${escapeHtml(t.detail)}">${t.ok ? '✓' : '✗'}${escapeHtml(t.short)}</span>`)
    .join(' ');
  const members = x.g.members
    .map((m) => `<button type="button" class="rp-stock" data-code="${escapeHtml(m.code)}" title="${escapeHtml(m.code)}：開資訊卡">${escapeHtml(m.name)} <small class="${m.change_pct > 0 ? 'up' : m.change_pct < 0 ? 'down' : ''}">${fmtPct(m.change_pct)}</small></button>`)
    .join('');
  const motive = motiveOf(x.g, items).map((m) => `<b>${escapeHtml(m.label)}</b>：${escapeHtml(m.text)}`).join('；');
  return `<div class="rp-group">
    <div class="rp-gh"><span class="rp-n">${i + 1}</span>${members}<span class="rp-ev${x.strong ? ' strong' : ''}" title="資金一致性證據：有資料的項目中 ✓ 的數量">${x.strong ? '證據強 ' : '證據 '}${x.ev.yes}/${x.ev.known}</span>
      <span class="muted rp-src">${x.method === 'new' ? '找法2' : '找法1'}</span></div>
    <div class="rp-line"><span class="muted">動機判讀</span> ${motive}</div>
    <div class="rp-line rp-chips">${chips || '<span class="muted">沒有證據資料</span>'}</div>
    <div class="rp-line"><span class="muted">明天觀察</span> ${escapeHtml(watchOf(x.g, row?.streak || 0).join('；'))}</div>
  </div>`;
}

export function trackHtml(dates, rows) {
  if (!rows.length) return '<p class="hint">這幾天沒有找到群組。</p>';
  const cell = (c) => (c === undefined ? '<td class="muted" title="那天還沒計算">…</td>' : c === null ? '<td class="muted">—</td>' : `<td class="up">✓ ${c}</td>`);
  const cls = (s) => (s.startsWith('消失') ? 'down' : s.includes('變強') || s.startsWith('連') ? 'up' : '');
  return `<table class="grid rp-track"><thead><tr><th class="l">群組</th>${dates.map((d) => `<th>${escapeHtml(d.slice(5))}</th>`).join('')}<th class="l">今天狀態</th></tr></thead><tbody>${rows
    .map((r) => `<tr><td class="l">${escapeHtml(r.names)}</td>${r.cells.map(cell).join('')}<td class="l ${cls(r.status)}">${escapeHtml(r.status)}</td></tr>`)
    .join('')}</tbody></table>`;
}

// ---- panel --------------------------------------------------------------------------------------

/** 分頁3: refresh(date, days) with the trading days list (newest first) to find the 4 days before. */
export function mountReportPanel(container, { onStock }) {
  const sec = document.createElement('section');
  sec.className = 'panel hReport';
  sec.innerHTML = `<div class="panel-h"><b>盤後報告</b><span class="muted" id="rpNote">N 的預設條件（找法1＋找法2），每天收盤後算好</span>
      <button type="button" class="icon wide" id="rpCopy" style="margin-left:auto" title="把報告複製成純文字">複製成文字</button></div>
    <div class="rp-body"><p class="hint">選一天看報告。</p></div>`;
  container.append(sec);
  const body = sec.querySelector('.rp-body');
  const state = { ticket: 0, text: '' };

  async function result(date, method, storedOnly) {
    const q = new URLSearchParams({ date, method });
    if (storedOnly) q.set('stored_only', '1');
    const r = await fetch(`/api/history/finder?${q}`, { cache: 'no-store' });
    const j = r.ok ? await r.json() : null;
    return j && (j.stored === false ? null : j);
  }

  async function refresh(date, days) {
    if (!date) return;
    const t = ++state.ticket;
    body.innerHTML = '<p class="hint">整理中…</p>';
    const i = days.indexOf(date);
    const dates = days.slice(i, i + TRACK_DAYS).reverse(); // oldest → the report day
    const one = async (d, stored) => {
      const [known, fresh] = await Promise.all([result(d, 'known', stored), result(d, 'new', stored)]);
      return known || fresh ? mergeGroups(known, fresh) : null;
    };
    let index;
    let per;
    try {
      // the report day may compute; the days before only if stored (the rest is worked out below)
      [index, ...per] = await Promise.all([
        fetch(`/api/history/index-race?date=${encodeURIComponent(date)}`).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        ...dates.map((d) => one(d, d !== date)),
      ]);
    } catch (err) {
      if (t === state.ticket) body.innerHTML = `<p class="hint">${escapeHtml(err.message)}</p>`;
      return;
    }
    if (t !== state.ticket) return;
    const bench = (index?.benchmarks || []).map((b) => ({ name: b.name.replace(/（.*）/, ''), change_pct: b.change_pct }));
    draw(date, dates, per, bench, '');
    // the days before that N never computed (only the latest 5 are, after the close): one at a time, the
    // nearest first, the table filled in as each one lands; a new date stops it
    const missing = dates.map((d, k) => [d, k]).filter(([d, k]) => d !== date && per[k] === null).reverse();
    for (const [n, [d, k]] of missing.entries()) {
      draw(date, dates, per, bench, `往前計算 ${d.slice(5)}（${n + 1}/${missing.length}，舊日子一天約 1～2 分鐘）…`);
      try {
        per[k] = (await one(d, false)) || [];
      } catch {
        per[k] = [];
      }
      if (t !== state.ticket) return;
    }
    if (missing.length) draw(date, dates, per, bench, '');
  }

  function draw(date, dates, per, bench, progress) {
    const list = per.at(-1) || [];
    const rows = trackRows(per);
    state.text = reportText(date, bench, list, rows);
    const strong = list.filter((x) => x.strong).length;
    const going = rows.filter((r) => r.streak >= 1 && r.cells.at(-1) != null).length;
    const metric = (label, value) => `<div class="rp-metric"><small>${label}</small><b>${value}</b></div>`;
    // 摘要 across the top; the day's groups (A1) on the left, 跨天追蹤 (A3) on the right
    body.innerHTML = `<div class="rp-metrics">${metric('找到群組', list.length)}${metric('證據強', strong)}${metric('連續出現', going)}${metric('大盤／櫃買', bench.map((b) => `<span class="${b.change_pct > 0 ? 'up' : 'down'}">${fmtPct(b.change_pct)}</span>`).join(' / ') || '—')}</div>
      <div class="rp-cols"><div class="rp-left">
        <h3 class="rp-h">${escapeHtml(date)} 找到的群組</h3>
        ${list.length ? list.slice(0, SHOW_MAX).map((x, k) => groupHtml(x, k, rows.find((r) => r.key === x.key))).join('') : '<p class="hint">這一天沒有找到群組（或 N 還沒算完，稍後再開）。</p>'}
        ${list.length > SHOW_MAX ? `<p class="muted">其餘 ${list.length - SHOW_MAX} 組在分頁2 的 N 看得到。</p>` : ''}
      </div><div class="rp-right">
        <h3 class="rp-h">跨天追蹤 <small class="muted">格子＝那天的證據 ✓ 數；— 那天沒有這組；… 還沒計算</small></h3>
        ${progress ? `<p class="hint rp-progress">${escapeHtml(progress)}</p>` : ''}
        ${trackHtml(dates, rows)}
      </div></div>`;
  }

  body.addEventListener('click', (e) => {
    const b = e.target.closest('.rp-stock');
    if (b) onStock?.(b.dataset.code);
  });
  sec.querySelector('#rpCopy').addEventListener('click', async (e) => {
    try {
      await navigator.clipboard.writeText(state.text);
      e.target.textContent = '已複製';
    } catch {
      e.target.textContent = '複製失敗';
    }
    setTimeout(() => (e.target.textContent = '複製成文字'), 1500);
  });
  return { refresh };
}
