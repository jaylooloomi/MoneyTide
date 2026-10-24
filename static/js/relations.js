// 🏢 Company relations (轉投資 / 法人董監 / 集團) in words, shared by K's 交集, N's cards and the stock card.
// Server: edges {src, dst, src_name, dst_name, pct, method, seats: [職稱…]}; groups {leader_name, size, members}.

import { escapeHtml } from './transform.js';

const pct = (v) => (v === null || v === undefined ? '' : ` ${Number(v).toFixed(2).replace(/\.?0+$/, '')}%`);

/** 「董事 ×2、監察人」 */
function seatsText(seats) {
  const n = new Map();
  for (const s of seats || []) n.set(s, (n.get(s) || 0) + 1);
  return [...n].map(([s, k]) => `${escapeHtml(s)}${k > 1 ? ` ×${k}` : ''}`).join('、');
}

/** One holder → held pair as a sentence: 「菱光 持有 東友 29.69%（權益法），派任 董事 ×2」 /
 *  「環泥 是 菱光 的董事（持股 8.59%）」. */
export function relText(e) {
  const src = `<b>${escapeHtml(e.src_name || e.src)}</b>`;
  const dst = `<b>${escapeHtml(e.dst_name || e.dst)}</b>`;
  const seats = seatsText(e.seats);
  if (!e.method && seats) return `${src} 是 ${dst} 的${seats}${e.pct ? `（持股${pct(e.pct)}）` : ''}`;
  return `${src} 持有 ${dst}${pct(e.pct)}${e.method ? `（${escapeHtml(e.method)}）` : ''}${seats ? `，派任 ${seats}` : ''}`;
}

/** A group as words: 「東元 集團（8 家）」 with the members in the title. */
export function groupText(g) {
  if (!g) return '';
  const names = (g.members || []).map((m) => m.name).join('、');
  return `<span title="${escapeHtml(`同集團（持股 ≥ 20% 權益法或派任董監串起來）：${names}`)}">以 <b>${escapeHtml(g.leader_name)}</b> 為首的集團（${g.size} 家）</span>`;
}

/** The 🏢 line of an N card / 交集 row: every relation among the stocks, then their shared group. */
export function relationsHtml(edges, group) {
  const parts = (edges || []).map(relText);
  if (group) parts.push(groupText(group));
  return parts.join('；');
}
