// K · 5 日 K beside the timeline: the last 5 daily candles of a stock, as plain SVG (pure, node --test).
// Server: linkage payload `daily_k` {code: [{date, open, high, low, close, pct, lots, limit, vr, inst}]}.

import { escapeHtml, fmtPct } from './transform.js';

const UP = '#ff4d4f';
const DOWN = '#2ecc71';
const FLAT = '#aeb3bf';
const VR_HOT = 2; // 量比 at or above this is marked on the candle

/** 5 日累計漲幅 (first open-day's previous close → last close) and the current up / down streak. */
export function k5Summary(series) {
  if (!series?.length) return { cum: null, streak: 0 };
  const growth = series.reduce((g, x) => (x.pct === null || x.pct === undefined ? g : g * (1 + x.pct / 100)), 1);
  let streak = 0;
  for (let i = series.length - 1; i >= 0; i--) {
    const p = series[i].pct;
    if (!p) break;
    if (streak === 0) streak = p > 0 ? 1 : -1;
    else if ((p > 0) === streak > 0) streak += streak > 0 ? 1 : -1;
    else break;
  }
  return { cum: (growth - 1) * 100, streak };
}

/** The candles as an SVG string, w × h; `full` adds volume bars and labels (漲跌 %, 🔒, 量比, 法人). */
export function k5Svg(series, w, h, full = false) {
  const s = (series || []).filter((x) => x.high !== null && x.low !== null);
  if (!s.length) return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"></svg>`;
  const labelH = full ? 46 : 0; // under the candles: %, 法人 and the date, one line each
  const volH = full ? 26 : 0;
  const priceH = h - labelH - volH - (full ? 14 : 2);
  const top = full ? 12 : 1;
  const hi = Math.max(...s.map((x) => x.high));
  const lo = Math.min(...s.map((x) => x.low));
  const y = (p) => top + (hi === lo ? priceH / 2 : ((hi - p) / (hi - lo)) * priceH);
  const slot = w / s.length;
  const body = Math.max(2, slot * 0.5);
  const maxLots = Math.max(1, ...s.map((x) => x.lots || 0));
  const parts = [];
  s.forEach((x, i) => {
    const cx = slot * i + slot / 2;
    const open = x.open ?? x.close;
    const color = x.close > open ? UP : x.close < open ? DOWN : x.pct > 0 ? UP : x.pct < 0 ? DOWN : FLAT;
    const y1 = y(Math.max(open, x.close));
    const y2 = y(Math.min(open, x.close));
    parts.push(`<line x1="${cx}" x2="${cx}" y1="${y(x.high)}" y2="${y(x.low)}" stroke="${color}" stroke-width="1"/>`);
    // solid bodies, the Taiwan way: red 收 > 開, green 收 < 開 (no hollow candles)
    parts.push(`<rect x="${cx - body / 2}" y="${y1}" width="${body}" height="${Math.max(1, y2 - y1)}" fill="${color}" stroke="${color}" stroke-width="1"/>`);
    if (!full) return;
    const pc = x.pct > 0 ? UP : x.pct < 0 ? DOWN : FLAT;
    if (x.limit) parts.push(`<text x="${cx}" y="${y(x.high) - 2}" font-size="9" text-anchor="middle">🔒</text>`);
    const vy = top + priceH + 4;
    const vh = x.lots ? (x.lots / maxLots) * volH : 0;
    // volume: narrow grey bars under a divider, so they never read as a second row of candles (量比 ≥ 2 in orange)
    if (i === 0) {
      parts.push(`<line x1="0" x2="${w}" y1="${vy - 1}" y2="${vy - 1}" stroke="#2a2e37" stroke-width="1"/>`);
      parts.push(`<text x="1" y="${vy + 8}" font-size="8" fill="#6b7080">量</text>`);
    }
    const hot = x.vr !== null && x.vr !== undefined && x.vr >= VR_HOT;
    parts.push(`<rect x="${cx - body / 4}" y="${vy + volH - vh}" width="${body / 2}" height="${vh}" fill="${hot ? '#ffb300' : '#6b7080'}" opacity="${hot ? 0.85 : 0.6}"/>`);
    if (x.vr !== null && x.vr !== undefined && x.vr >= VR_HOT) {
      parts.push(`<text x="${cx}" y="${vy + volH - vh - 2}" font-size="9" fill="#ffb300" text-anchor="middle">×${x.vr.toFixed(1)}</text>`);
    }
    const ly = vy + volH + 12;
    parts.push(`<text x="${cx}" y="${ly}" font-size="10" fill="${pc}" text-anchor="middle">${x.pct === null || x.pct === undefined ? '—' : fmtPct(x.pct)}</text>`);
    if (x.inst !== null && x.inst !== undefined) {
      const ic = x.inst > 0 ? UP : x.inst < 0 ? DOWN : FLAT;
      const n = Math.abs(x.inst) >= 10000 ? `${(x.inst / 10000).toFixed(1)}萬` : x.inst.toLocaleString();
      parts.push(`<text x="${cx}" y="${ly + 13}" font-size="9" fill="${ic}" text-anchor="middle">${x.inst > 0 ? '+' : ''}${n}</text>`);
    }
    parts.push(`<text x="${cx}" y="${h - 1}" font-size="9" fill="#8a8f9c" text-anchor="middle">${escapeHtml(x.date.slice(5).replace('-', '/'))}</text>`);
  });
  return `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">${parts.join('')}</svg>`;
}

/** A row's tooltip for its mini 5 日 K: each day's close and %, plus the summary. */
export function k5Title(series) {
  if (!series?.length) return '';
  const { cum, streak } = k5Summary(series);
  const days = series.map((x) => `${x.date.slice(5)} ${x.close}（${x.pct === null ? '—' : fmtPct(x.pct)}）${x.limit ? '🔒' : ''}`).join('\n');
  return `近 ${series.length} 日 ${cum === null ? '' : fmtPct(cum)}${streak ? `　${streak > 0 ? '連漲' : '連跌'} ${Math.abs(streak)} 天` : ''}\n${days}`;
}

/** One picked stock's card in the middle column: name, 5 日累計 / 連漲, the full candles. */
export function k5CardHtml(name, code, color, series) {
  const { cum, streak } = k5Summary(series);
  const head = `<div class="k5-h"><b style="color:${color}">${escapeHtml(name)}</b> <small class="muted">${escapeHtml(code)}</small>
    ${cum === null ? '' : `<span class="${cum > 0 ? 'up' : cum < 0 ? 'down' : ''}">5 日 ${fmtPct(cum)}</span>`}
    ${streak ? `<span class="${streak > 0 ? 'up' : 'down'}">${streak > 0 ? '連漲' : '連跌'} ${Math.abs(streak)} 天</span>` : ''}</div>`;
  return `<div class="k5-card">${head}${series?.length ? k5Svg(series, 260, 170, true) : '<p class="hint">沒有日 K 資料</p>'}</div>`;
}
