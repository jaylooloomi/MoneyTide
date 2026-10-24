// K · 日內最高點時間＋漲幅 (animated): the group's top members replayed minute by minute from 09:00 to
// 13:30 on a time axis. Each row draws its change-% path up to the playhead, a dot on the highest point
// so far (09:00–13:00 window, earliest wins), and the current change; rows re-rank by that change, and
// a stock locked limit-up stays ahead of every later limit-up (and of everyone not at the limit).
// Pure frame builders on top (node --test); the animated panel below.

import { PICK_COLORS, mountIntraday, nextPicks } from './intradaychart.js';
import { colorFor, escapeHtml, fmtPct, limitTag } from './transform.js';
import { k5CardHtml, k5Svg, k5Title } from './k5.js';
import { relationsHtml } from './relations.js';
import { evidenceHtml, evidenceItems } from './evidence.js';

export const RACE_END = 270; // minutes after 09:00 → 13:30
export const PEAK_END = 240; // the intraday high is taken over 09:00–13:00
const ROW_H = 38;
const PAD = 3; // px above / below the path inside a row
export const RACE_SPEEDS = { slow: ['慢', 160], mid: ['中', 70], fast: ['快', 25] }; // ms per minute

/**
 * points {code: [[minute, close %, high %, low %]]} → per code, for m = 0…RACE_END:
 * values[m] the last close % (null before the first trade), since[m] the minute that value was reached,
 * highs[m] / lows[m] the high / low % of minute m itself (null without data), and lockedAt[m] the minute the current
 * limit-up streak began (null when not at limit-up at m).
 */
export function raceFrames(points, codes, limits = {}) {
  const out = {};
  for (const c of codes) {
    const locked = isLimitUp(limits[c]);
    const at = new Map((points?.[c] || []).map(([m, v, h, lo]) => [m, [v, h ?? v, lo ?? v]]));
    const values = new Array(RACE_END + 1).fill(null);
    const since = new Array(RACE_END + 1).fill(null);
    const highs = new Array(RACE_END + 1).fill(null);
    const lows = new Array(RACE_END + 1).fill(null);
    const lockedAt = new Array(RACE_END + 1).fill(null);
    let v = null;
    let s = null;
    let lock = null;
    for (let m = 0; m <= RACE_END; m++) {
      const p = at.get(m);
      if (p) {
        highs[m] = p[1];
        lows[m] = p[2];
        if (p[0] !== v) {
          v = p[0];
          s = m;
        }
      }
      values[m] = v;
      since[m] = s;
      // limit-up streak: opening the limit loses it, locking again starts a new one
      lock = locked(v) ? (lock ?? m) : null;
      lockedAt[m] = lock;
    }
    out[c] = { values, since, highs, lows, lockedAt };
  }
  return out;
}

/**
 * At-limit-up test for one stock: its exact limit-up % (prev close × 1.1 down to the tick, from the
 * server) when known, else the app-wide ≥ 9.5% rule.
 */
export function isLimitUp(limitPct) {
  return (v) => v !== null && v !== undefined && (limitPct ? v >= limitPct - 0.005 : limitTag(v) === '漲停');
}

/**
 * Codes in race order at minute m. Stocks at limit-up come first, the earliest lock in front (a later
 * limit-up never passes it, even with a higher % from tick rounding); then change desc, ties to
 * whoever reached that change first; no trade yet last.
 */
export function raceOrder(codes, frames, m) {
  return [...codes].sort((a, b) => {
    const va = frames[a].values[m];
    const vb = frames[b].values[m];
    if (va === null || vb === null) return (va === null) - (vb === null);
    const la = frames[a].lockedAt[m];
    const lb = frames[b].lockedAt[m];
    if (la !== null || lb !== null) {
      if (la === null || lb === null) return (la === null) - (lb === null);
      if (la !== lb) return la - lb;
    }
    if (Math.abs(va - vb) >= 0.005) return vb - va;
    return frames[a].since[m] - frames[b].since[m];
  });
}

/**
 * 領漲: the stock first at the close, and the minute from which it held first place to the close
 * (with the lock-first rule: the earliest limit-up that stayed locked, else the day's top gainer).
 * null when nobody traded or the day's first place closed flat or down.
 */
export function leadOf(codes, frames) {
  const first = [];
  for (let m = 0; m <= RACE_END; m++) first.push(raceOrder(codes, frames, m)[0]);
  const code = first[RACE_END];
  const v = frames[code]?.values[RACE_END];
  if (v === null || v === undefined || v <= 0) return null;
  let from = RACE_END;
  while (from > 0 && first[from - 1] === code && frames[code].values[from - 1] !== null) from -= 1;
  return { code, from };
}

/** Inline 領漲 icon: a red disc with a rising arrow. */
export const LEAD_ICON =
  '<svg class="lead-icon" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="7.5" fill="#e0282e"/><path d="M3.6 10.6 6.6 7.4 8.6 9.2 11.6 5.6" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M9.2 5.2h2.8v2.8" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';

/** The highest high up to minute m (never past 13:00) and the first minute it was reached; null before any trade. */
export function peakSoFar(frame, m) {
  let best = null;
  for (let i = 0; i <= Math.min(m, PEAK_END); i++) {
    const h = frame.highs[i];
    if (h !== null && (best === null || h > best.v)) best = { m: i, v: h };
  }
  return best;
}

/** 振幅 so far: highest high − lowest low up to minute m, in % of the previous close (null before a trade). */
export function amplitudeSoFar(frame, m) {
  let hi = null;
  let lo = null;
  for (let i = 0; i <= m; i++) {
    const h = frame.highs[i];
    const l = frame.lows?.[i];
    if (h !== null && (hi === null || h > hi)) hi = h;
    if (l !== null && l !== undefined && (lo === null || l < lo)) lo = l;
  }
  return hi === null || lo === null ? null : hi - lo;
}

// ---- 🔗 交集: what two picked stocks have in common ------------------------------------------------

/** K's verdict wording for a correlation (daily 0.7 / 0.3, intraday 0.5 / 0.2). */
export function verdictOf(r, high, low) {
  if (r === null || r === undefined) return '資料不足';
  return r > high ? '群體圍攻' : r < low ? '單兵作戰' : '中度連動';
}

/** One pair's figures from K's data at minute m: daily / intraday R, who peaked and locked first, the
 *  change gap and 法人. a / b are codes; d is the linkage payload, frames its raceFrames. */
export function pairFacts(d, frames, a, b, m) {
  const idx = new Map(d.members.map((x, i) => [x.code, i]));
  const i = idx.get(a);
  const j = idx.get(b);
  const cell = (mx) => (mx && i !== undefined && j !== undefined ? mx[i]?.[j] ?? null : null);
  const at = (c) => {
    const f = frames[c];
    const lock = f?.lockedAt[m] ?? null;
    return { now: f?.values[m] ?? null, peak: f ? peakSoFar(f, m) : null, lock };
  };
  const A = at(a);
  const B = at(b);
  const first = (x, y) => (x === null && y === null ? null : y === null || (x !== null && x < y) ? a : x === y ? '' : b);
  const pa = A.peak?.m ?? null;
  const pb = B.peak?.m ?? null;
  // the whole 09:00–13:00 window, whatever the playhead (N's 高點差 uses this one)
  const da = frames[a] ? peakSoFar(frames[a], RACE_END)?.m ?? null : null;
  const db = frames[b] ? peakSoFar(frames[b], RACE_END)?.m ?? null : null;
  const member = (c) => d.members[idx.get(c)] || {};
  return {
    a, b,
    r20: cell(d.daily?.matrix20), r60: cell(d.daily?.matrix60), ri: cell(d.intraday?.matrix),
    // each session's R, the shown day first (今日, 昨日, 前日)
    riDays: [...(d.intraday?.by_session || [])].reverse().map((s) => ({ date: s.date, r: cell(s.matrix) })),
    peakA: pa, peakB: pb, peakGap: pa !== null && pb !== null ? Math.abs(pa - pb) : null, firstPeak: first(pa, pb),
    dayPeakA: da, dayPeakB: db, dayPeakGap: da !== null && db !== null ? Math.abs(da - db) : null,
    lockA: A.lock, lockB: B.lock, firstLock: first(A.lock, B.lock),
    nowA: A.now, nowB: B.now, diff: A.now !== null && B.now !== null ? A.now - B.now : null,
    instA: member(a).inst_net ?? null, instB: member(b).inst_net ?? null,
    // 資金一致性 from the payload: R after the index, and the 1-minute pair stats (either key order)
    ev: { excess: cell(d.evidence?.excess), minute: d.evidence?.minute?.[`${a},${b}`] ?? d.evidence?.minute?.[`${b},${a}`] ?? null },
  };
}

const rTag = (r, high, low) => {
  const v = verdictOf(r, high, low);
  const cls = v === '群體圍攻' ? 'up' : v === '單兵作戰' ? 'muted' : '';
  return `<b class="${cls}">${r === null ? '—' : r.toFixed(2)}</b> <small class="${cls}">${v}</small>`;
};
const lots = (net) => (net === null ? '—' : `${net > 0 ? '+' : net < 0 ? '−' : ''}${Math.abs(Math.round(net / 1000)).toLocaleString()} 張`);

const DAY_NAMES = ['今日', '昨日', '前日'];

/** 「今日 0.72（10/22）／昨日 0.58／前日 —」: the intraday R of each of the latest sessions, newest first. */
export function riDaysHtml(days) {
  if (!days?.length) return '';
  const one = (x, i) => {
    const cls = x.r === null ? 'muted' : x.r > 0.5 ? 'up' : x.r < 0.2 ? 'muted' : '';
    return `${DAY_NAMES[i] || x.date.slice(5)} <b class="${cls}" title="${escapeHtml(x.date)}">${x.r === null ? '—' : x.r.toFixed(2)}</b>`;
  };
  return `<br><span class="rt-ri-days">${days.map(one).join('　')}</span>`;
}

/** Shared groups by kind, each label once and at most `max` names per kind (the rest counted). */
export function sharedGroupsHtml(groups, max = 3) {
  const by = new Map();
  for (const g of groups) by.set(g.label, [...(by.get(g.label) || []), g.group]);
  return [...by]
    .map(([label, names]) => `${escapeHtml(label)}：${names.slice(0, max).map((n) => escapeHtml(n)).join('、')}${names.length > max ? ` <small class="muted">等 ${names.length} 個</small>` : ''}`)
    .join('；');
}

/** The full 交集 card of one pair: `name(code)` and `color(code)` label the two; `ext` is the server's
 *  /api/history/pairs entry (null while loading). */
export function pairCardHtml(f, ext, name, color) {
  const n = (c) => `<b style="color:${color(c)}">${escapeHtml(name(c))}</b>`;
  const peak =
    f.peakA === null || f.peakB === null
      ? '—'
      : f.firstPeak === ''
        ? `同時 ${fmtClock(f.peakA)} 到最高點`
        : `${n(f.firstPeak)} ${fmtClock(Math.min(f.peakA, f.peakB))} 先到，${n(f.firstPeak === f.a ? f.b : f.a)} 晚 <b>${f.peakGap}</b> 分 <small class="${f.peakGap <= 10 ? 'up' : f.peakGap >= 60 ? 'muted' : ''}">${f.peakGap <= 10 ? '高度同步' : f.peakGap >= 60 ? '時間錯落' : ''}</small>`;
  const lockOne = (c, at) => (at === null ? `${n(c)} 未鎖` : `${n(c)} ${fmtClock(at)} 鎖`);
  const lock = f.lockA === null && f.lockB === null ? '兩檔都沒鎖漲停' : `${lockOne(f.a, f.lockA)}；${lockOne(f.b, f.lockB)}`;
  const strong =
    f.diff === null ? '—' : `${n(f.a)} ${fmtPct(f.nowA)} vs ${n(f.b)} ${fmtPct(f.nowB)}（${n(f.diff >= 0 ? f.a : f.b)} 強 ${Math.abs(f.diff).toFixed(2)}%）`;
  const instSame = f.instA !== null && f.instB !== null && f.instA * f.instB > 0;
  const inst =
    f.instA === null && f.instB === null
      ? '當天法人還沒公布'
      : `${n(f.a)} ${lots(f.instA)}／${n(f.b)} ${lots(f.instB)}${f.instA !== null && f.instB !== null ? (instSame ? '（同方向）' : '（方向相反）') : ''}`;
  const row = (k, v, tip = '') => `<tr${tip ? ` title="${escapeHtml(tip)}"` : ''}><td class="muted">${k}</td><td>${v}</td></tr>`;
  let more = '<tr><td colspan="2" class="hint">同漲同跌、共同族群、N 紀錄、共同題材載入中…</td></tr>';
  if (ext) {
    const sd = ext.same_dir;
    const pct = sd.total ? Math.round((sd.same / sd.total) * 100) : null;
    more =
      row('同漲同跌', sd.total ? `<b>${sd.same}</b>／${sd.total} 天 <small class="${pct >= 75 ? 'up' : pct <= 50 ? 'muted' : ''}">${pct}%</small>` : '—', '近 20 個交易日兩檔同一天都漲或都跌的天數') +
      row('共同族群', ext.groups.length ? sharedGroupsHtml(ext.groups) : '<span class="muted">沒有</span>', ext.groups.map((g) => `${g.label}：${g.group}`).join('\n')) +
      row('N 找過', ext.finder.length ? `近 5 天 <b>${new Set(ext.finder.map((h) => h.date)).size}</b> 天：${ext.finder.map((h) => `${h.date.slice(5)}${h.method === 'new' ? '（找法2）' : ''}`).join('、')} 🔁` : '<span class="muted">近 5 天沒有</span>', '近 5 個交易日 N 存下的結果裡，這兩檔被找成同一群') +
      row('共同題材', ext.themes.length ? ext.themes.map((t) => `📰 ${escapeHtml(t)}`).join('、') : '<span class="muted">沒有</span>', '近 3 個新聞日，兩檔都被同一個題材的新聞點名') +
      row('🏢 持股關係', ext.relations?.length || ext.group ? relationsHtml(ext.relations, ext.group) : '<span class="muted">沒有（或還沒抓到這兩檔的轉投資／董監資料）</span>', '轉投資、法人董監（MoneyDJ／公開資訊觀測站），以及由持股 ≥ 20%（權益法）或派任董監串起來的集團');
  }
  return `${evidenceHtml(evidenceItems(f, ext, f.ev))}<table class="rt-pair">
    ${row('日相關', `R20 ${rTag(f.r20, 0.7, 0.3)}　R60 ${rTag(f.r60, 0.7, 0.3)}`, '近 20／60 個交易日日漲跌幅的相關係數')}
    ${row('分時相關', `R ${rTag(f.ri, 0.5, 0.2)} <small class="muted">近 3 日合計</small>${riDaysHtml(f.riDays)}`, '5 分 K 報酬的相關係數；鎖漲停的平線不計，單日少於 15 個點時顯示 —')}
    ${row('最高點', `${peak}${f.dayPeakGap === null ? '' : `<br><small class="muted">全天（09:00–13:00，N 用的）：</small>${n(f.a)} ${fmtClock(f.dayPeakA)}／${n(f.b)} ${fmtClock(f.dayPeakB)}，差 <b class="${f.dayPeakGap <= 10 ? 'up' : ''}">${f.dayPeakGap}</b> 分`}`, '第一行：到播放頭為止的最高點；第二行：整天（13:00 之前）的最高點，N 的「高點差」篩選用的是這個')}
    ${row('鎖漲停', lock)}
    ${row('當下強弱', strong)}
    ${row('法人', inst)}
    ${more}
  </table>`;
}

/** Three or more picked: one row per pair, the most correlated (R20) first; `open` = the expanded pair key. */
export function pairTableHtml(list, extOf, name, color, open) {
  const sorted = [...list].sort((x, y) => (y.f.r20 ?? -2) - (x.f.r20 ?? -2));
  const fmt = (r) => (r === null ? '—' : r.toFixed(2));
  const body = sorted
    .map(({ key, f }) => {
      const ext = extOf(key);
      const sd = ext?.same_dir;
      const cells = [
        `<b style="color:${color(f.a)}">${escapeHtml(name(f.a))}</b> × <b style="color:${color(f.b)}">${escapeHtml(name(f.b))}</b>`,
        `<span class="${f.r20 > 0.7 ? 'up' : f.r20 < 0.3 ? 'muted' : ''}">${fmt(f.r20)}</span>`,
        fmt(f.r60),
        `<span class="${f.ri > 0.5 ? 'up' : f.ri < 0.2 ? 'muted' : ''}">${fmt(f.ri)}</span>`,
        sd ? (sd.total ? `${sd.same}/${sd.total}` : '—') : '…',
        f.peakGap === null ? '—' : `${f.peakGap} 分`,
        ext ? (ext.groups.length ? escapeHtml(ext.groups.map((g) => g.group).join('、')) : '—') : '…',
        ext ? (ext.finder.length ? `🔁 ${new Set(ext.finder.map((h) => h.date)).size}` : '—') : '…',
        (() => {
          const items = evidenceItems(f, ext, f.ev);
          const yes = items.filter((x) => x.ok === true).length;
          const known = items.filter((x) => x.ok !== null).length;
          return ext ? `<b class="${yes >= Math.max(1, known * 0.6) ? 'up' : ''}">${yes}</b>/${known}` : '…';
        })(),
      ];
      const detail = key === open ? `<tr class="rt-pair-open"><td colspan="${cells.length}">${pairCardHtml(f, ext, name, color)}</td></tr>` : '';
      return `<tr data-pair="${escapeHtml(key)}" class="${key === open ? 'on' : ''}" style="cursor:pointer" title="點一下看這組的完整交集">${cells.map((c, k) => `<td${k === 0 || k === 6 ? ' class="l"' : ''}>${c}</td>`).join('')}</tr>${detail}`;
    })
    .join('');
  return `<table class="grid rt-pairs-t"><thead><tr><th class="l">組合</th><th title="近 20 日日相關">R20</th><th>R60</th><th title="近 3 日 5 分 K">分時 R</th><th title="近 20 日同漲同跌天數">同漲跌</th><th title="日內最高點時間差（到播放頭）">高點差</th><th class="l">共同族群</th><th title="近 5 天 N 找到同一群的天數">N</th><th title="資金一致性證據：支持的項數／有資料的項數">證據</th></tr></thead><tbody>${body}</tbody></table>`;
}

/** 「　法人 +1,234 張」 for a row's tooltip from 三大法人 net shares; '' when the day has none yet. */
export function instTip(net) {
  if (net == null) return '';
  const lots = Math.round(net / 1000);
  return `　法人 ${lots > 0 ? '+' : lots < 0 ? '−' : ''}${Math.abs(lots).toLocaleString()} 張`;
}

export function fmtClock(m) {
  return `${String(9 + Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

/** Shared y-range: the day's lowest close to highest high over all members (always including 0). */
export function raceDomain(frames) {
  let lo = 0;
  let hi = 0;
  for (const f of Object.values(frames)) {
    for (let m = 0; m <= RACE_END; m++) {
      for (const v of [f.values[m], f.highs[m]]) {
        if (v === null) continue;
        if (v < lo) lo = v;
        if (v > hi) hi = v;
      }
    }
  }
  if (hi - lo < 1) hi = lo + 1;
  return [lo, hi];
}

/** SVG polyline points (x = minute, y = px from the row top) of the close path up to minute m. */
export function pathPoints(frame, m, y) {
  const out = [];
  for (let i = 0; i <= m; i++) if (frame.values[i] !== null) out.push(`${i},${y(frame.values[i]).toFixed(1)}`);
  return out.join(' ');
}

// ---- panel --------------------------------------------------------------------------------------

const TICKS = [['09:00', 0], ['10:00', 60], ['11:00', 120], ['12:00', 180], ['13:00', 240], ['13:30', 270]];

/** Mount the animated timeline into `box` for linkage data `d`; returns a stop() that halts the timer. */
export function mountRace(box, d, { onStock } = {}) {
  const codes = d.members.map((m) => m.code);
  const byCode = new Map(d.members.map((m) => [m.code, m]));
  const limits = Object.fromEntries(d.members.map((m) => [m.code, m.limit_up_pct]));
  const frames = raceFrames(d.race?.points, codes, limits);
  if (!codes.some((c) => frames[c].values[RACE_END] !== null)) {
    box.innerHTML = '<p class="hint">這一天沒有分時資料。</p>';
    return () => {};
  }
  // 大盤 / 櫃買 pinned on top for comparison: no rank, not part of the race
  const benches = (d.benchmarks || []).filter((b) => b.points?.length);
  const benchFrames = raceFrames(Object.fromEntries(benches.map((b) => [b.code, b.points])), benches.map((b) => b.code));
  const top = benches.length * ROW_H;
  const [lo, hi] = raceDomain({ ...frames, ...benchFrames });
  const inner = ROW_H - 2 * PAD;
  const y = (v) => PAD + ((hi - v) / (hi - lo)) * inner;
  const leader = codes[0]; // 👑 龍頭: the largest market cap
  const lead = leadOf(codes, frames); // the day's 領漲 (legend); the icon itself follows first place
  const step = d.race?.step_min === 5 ? '5 分 K：超過 30 天沒有 1 分資料' : '1 分 K';
  let speed = 'mid';
  try {
    if (localStorage.getItem('openmarket.race.speed') in RACE_SPEEDS) speed = localStorage.getItem('openmarket.race.speed');
  } catch {
    /* default */
  }
  const pctX = (m) => (m / RACE_END) * 100;
  box.innerHTML = `<div class="race-wrap"><div class="race-main"><div class="race-ctl">
      <button type="button" class="icon" data-act="play" title="從 09:00 播放／暫停">▶</button>
      <button type="button" class="icon" data-act="restart" title="從 09:00 重新開始">⏮</button>
      <b class="race-clock">13:30</b>
      <input type="range" class="race-seek" min="0" max="${RACE_END}" value="${RACE_END}" aria-label="時間">
      <div class="seg race-speed">${Object.entries(RACE_SPEEDS)
        .map(([k, [label]]) => `<button type="button" data-speed="${k}"${k === speed ? ' class="on"' : ''}>${label}</button>`)
        .join('')}</div>
      <small class="muted">${step}；● ＝到目前為止的最高點；👑 龍頭＝市值最大；${LEAD_ICON} 領漲＝當下排第一${lead ? `（收盤領漲：${escapeHtml(byCode.get(lead.code)?.name || lead.code)}，${fmtClock(lead.from)} 起一路領先）` : ''}；先鎖漲停的排前面；點一列看右邊的走勢圖，Ctrl／⌘＋點可再加好幾檔一起比較</small>
    </div>
    <div class="rt">
      <div class="rt-axis">${TICKS.map(([label, m]) => `<span style="left:${pctX(m)}%"${label === '13:00' ? ' class="t1300"' : ''}>${label}</span>`).join('')}</div>
      <div class="rt-board" style="height:${codes.length * ROW_H + top}px">
        <div class="rt-layer"><span class="rt-after" style="left:${pctX(PEAK_END)}%" title="13:00 之後不計入日內最高點"></span><span class="rt-head" title="拖動黃線選時間"><span class="rt-knob"></span></span></div>
        ${benches
          .map(
            (b, i) => `<div class="rt-row bench" data-bench="${escapeHtml(b.code)}" style="transform:translateY(${i * ROW_H}px)" title="${escapeHtml(b.name)}：比較用，不參與排名">
              <span class="rt-rank"></span><span class="rt-name">${escapeHtml(b.name)}</span>
              <span class="rt-track">
                <svg viewBox="0 0 ${RACE_END} ${ROW_H}" preserveAspectRatio="none"><line class="rt-zero" x1="0" x2="${RACE_END}" y1="${y(0)}" y2="${y(0)}"/><polyline class="rt-path"/></svg>
                <span class="rt-dot"></span>
              </span>
              <span class="rt-stat"><span class="rt-now"></span><span class="rt-sub"><span class="rt-amp"></span><span class="rt-peak"></span></span></span>
              <span class="rt-k5" title="${escapeHtml(k5Title(d.benchmark_k?.[b.code]))}">${k5Svg(d.benchmark_k?.[b.code], 64, 30)}</span></div>`,
          )
          .join('')}
        ${codes
          .map((c) => {
            const m = byCode.get(c);
            const extra = m.turnover_rate != null ? `　週轉率 ${m.turnover_rate.toFixed(1)}%　振幅 ${m.amplitude_pct?.toFixed(1) ?? '—'}%` : '';
            const inst = instTip(m.inst_net);
            return `<div class="rt-row" data-code="${escapeHtml(c)}" title="${escapeHtml(c)} ${escapeHtml(m.name)}${extra}${inst}：點一下看右邊的走勢圖，Ctrl／⌘＋點加入比較">
              <span class="rt-rank"></span><span class="rt-name">${c === leader ? '<span title="龍頭：族群市值最大">👑</span>' : ''}${escapeHtml(m.name)}<span class="rt-lead" title="領漲：這一分鐘排第一（有漲停時是最早鎖住的）" hidden>${LEAD_ICON}</span></span>
              <span class="rt-track">
                <svg viewBox="0 0 ${RACE_END} ${ROW_H}" preserveAspectRatio="none"><line class="rt-zero" x1="0" x2="${RACE_END}" y1="${y(0)}" y2="${y(0)}"/><polyline class="rt-path"/></svg>
                <span class="rt-dot"></span>
              </span>
              <span class="rt-stat"><span class="rt-now"></span><span class="rt-sub"><span class="rt-amp" title="振幅＝（到目前為止的最高 − 最低）÷ 昨收"></span><span class="rt-peak"></span></span></span>
              <span class="rt-k5" title="${escapeHtml(k5Title(d.daily_k?.[c]))}">${k5Svg(d.daily_k?.[c], 64, 30)}</span></div>`;
          })
          .join('')}
      </div>
    </div><div class="rt-pairs" hidden></div></div><div class="race-mid"></div><div class="race-side"></div></div>`;
  // a narrow track has no room for both 13:00 and 13:30: keep the dashed 13:00 line, drop its label
  const axis = box.querySelector('.rt-axis');
  const fitAxis = () => axis.classList.toggle('tight', axis.clientWidth < 450);
  new ResizeObserver(fitAxis).observe(axis);
  fitAxis();
  const chart = mountIntraday(box.querySelector('.race-side'), {
    date: d.date,
    onCard: onStock,
    benchmarks: benches,
    onDate: (day) => {
      k5Day = day; // 「回到」 in the chart's title
      drawK5();
    },
  });
  let k5Day = d.date; // the day the intraday chart shows (a 5 日 K candle can pick another)
  const rows = new Map([...box.querySelectorAll('.rt-row[data-code]')].map((el) => [el.dataset.code, el]));
  const benchRows = [...box.querySelectorAll('.rt-row.bench')].map((el) => [el, benchFrames[el.dataset.bench]]);
  const clock = box.querySelector('.race-clock');
  const seek = box.querySelector('.race-seek');
  const head = box.querySelector('.rt-head');
  const playBtn = box.querySelector('[data-act="play"]');
  const state = { m: RACE_END, timer: null, picked: [], pairOpen: null };
  // 🔗 交集 of the picked stocks: K's own figures now, the server's extras (同漲同跌, groups, N, themes) when they arrive
  const pairBox = box.querySelector('.rt-pairs');
  const pairExt = new Map(); // "a,b" (picked order) → the server's pair entry
  const pairAsked = new Set();
  const nameOf = (c) => byCode.get(c)?.name || c;
  const colorOf = (c) => PICK_COLORS[state.picked.indexOf(c) % PICK_COLORS.length];
  function pairKeys() {
    const out = [];
    for (let i = 0; i < state.picked.length; i++) for (let j = i + 1; j < state.picked.length; j++) out.push([state.picked[i], state.picked[j]]);
    return out;
  }
  function askPairs() {
    const key = state.picked.join(',');
    if (state.picked.length < 2 || pairAsked.has(key)) return;
    pairAsked.add(key);
    fetch(`/api/history/pairs?date=${encodeURIComponent(d.date)}&codes=${encodeURIComponent(key)}`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : null))
      .then((res) => {
        for (const p of res?.pairs || []) {
          pairExt.set(`${p.a},${p.b}`, p);
          pairExt.set(`${p.b},${p.a}`, p);
        }
        drawPairs();
      })
      .catch(() => {});
  }
  function drawPairs() {
    pairBox.hidden = state.picked.length < 2;
    if (pairBox.hidden) return;
    const list = pairKeys().map(([a, b]) => ({ key: `${a},${b}`, f: pairFacts(d, frames, a, b, state.m) }));
    const head = `<div class="rt-pairs-h">🔗 交集 <small class="muted">${list.length === 1 ? '兩檔之間的關係（跟著播放頭）' : `${list.length} 組，日相關高的在上；點一列看完整內容`}</small></div>`;
    pairBox.innerHTML =
      head +
      (list.length === 1
        ? pairCardHtml(list[0].f, pairExt.get(list[0].key) || null, nameOf, colorOf)
        : pairTableHtml(list, (k) => pairExt.get(k) || null, nameOf, colorOf, state.pairOpen));
  }
  // 5 日 K of the picked stocks, between the timeline and the intraday chart
  const midBox = box.querySelector('.race-mid');
  midBox.title = '選中股票的最近 5 個交易日＋之後 2 天：K 線、漲跌、🔒 漲停、量（橘＝量比 ≥ 2）、法人張數；點一根 K 看那天的分時走勢';
  function drawK5() {
    const many = state.picked.length > 1;
    midBox.innerHTML = `<div class="k5-title">5 日 K</div>${state.picked
      .map((c) => k5CardHtml(byCode.get(c)?.name || c, c, many ? colorOf(c) : '#e6e6e6', d.daily_k?.[c] || [], k5Day))
      .join('')}`;
  }
  // a candle → that day's intraday for every picked stock (the timeline stays on its own day)
  midBox.addEventListener('click', (e) => {
    const g = e.target.closest('[data-k5date]');
    if (!g) return;
    k5Day = g.dataset.k5date;
    drawK5();
    chart.setDate(k5Day).then(() => chart.sync(state.m));
  });
  pairBox.addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-pair]');
    if (!tr) return;
    state.pairOpen = state.pairOpen === tr.dataset.pair ? null : tr.dataset.pair;
    drawPairs();
  });
  // a plain click shows one stock; Ctrl / ⌘ / Shift + click adds more to compare (up to MAX_PICKS)
  function pick(code, additive = false) {
    state.picked = nextPicks(state.picked, code, additive);
    for (const [c, el] of rows) {
      const i = state.picked.indexOf(c);
      el.classList.toggle('on', i >= 0);
      el.style.outlineColor = i >= 0 && state.picked.length > 1 ? `${PICK_COLORS[i % PICK_COLORS.length]}aa` : '';
    }
    chart.show(state.picked.map((c) => ({ code: c, name: byCode.get(c)?.name }))).then(() => chart.sync(state.m));
    drawK5();
    askPairs();
    drawPairs();
  }

  function show(m) {
    state.m = m;
    clock.textContent = fmtClock(m);
    seek.value = String(m);
    head.style.left = `${pctX(m)}%`;
    chart.sync(m);
    if (state.picked.length > 1) drawPairs(); // 最高點／鎖漲停／強弱 follow the playhead
    for (const [el, f] of benchRows) paint(el, f, m);
    raceOrder(codes, frames, m).forEach((c, i) => {
      const el = rows.get(c);
      const v = frames[c].values[m];
      el.style.transform = `translateY(${top + i * ROW_H}px)`;
      el.querySelector('.rt-rank').textContent = v === null ? '' : String(i + 1);
      el.querySelector('.rt-lead').hidden = !(i === 0 && v > 0); // 領漲: first place right now, while up
      paint(el, frames[c], m);
    });
  }

  // one row's path, intraday-high dot and figures at minute m (stocks and the two indexes alike)
  function paint(el, f, m) {
    {
      const v = f.values[m];
      const path = el.querySelector('.rt-path');
      path.setAttribute('points', pathPoints(f, m, y));
      path.style.stroke = v === null ? 'transparent' : colorFor(v > 0 ? 10 : v < 0 ? -10 : 0, 10);
      const peak = peakSoFar(f, m);
      const dot = el.querySelector('.rt-dot');
      dot.hidden = !peak;
      if (peak) {
        dot.style.left = `${pctX(peak.m)}%`;
        dot.style.top = `${y(peak.v)}px`;
        dot.style.background = colorFor(peak.v, 7);
      }
      const tag = f.lockedAt[m] !== null ? '漲停' : limitTag(v) === '跌停' ? '跌停' : '';
      el.querySelector('.rt-now').innerHTML =
        v === null ? '<span class="muted">未成交</span>' : `<b class="${v > 0 ? 'up' : v < 0 ? 'down' : ''}">${fmtPct(v)}</b>${tag ? ` <b class="race-tag">${tag}</b>` : ''}`;
      const pk = el.querySelector('.rt-peak');
      pk.textContent = peak ? `高 ${fmtClock(peak.m)}` : '';
      pk.title = peak ? `日內最高點（到目前為止，13:00 之前）${fmtClock(peak.m)} ${fmtPct(peak.v)}` : '';
      const amp = amplitudeSoFar(f, m);
      el.querySelector('.rt-amp').textContent = amp === null ? '' : `振幅 ${amp.toFixed(1)}%`;
    }
  }

  function stop() {
    clearInterval(state.timer);
    state.timer = null;
    playBtn.textContent = '▶';
  }
  function play() {
    if (state.m >= RACE_END) show(0); // a fresh run always starts from 09:00
    clearInterval(state.timer);
    playBtn.textContent = '⏸';
    state.timer = setInterval(() => {
      if (!box.isConnected) return stop(); // the panel was redrawn
      if (state.m >= RACE_END) return stop();
      show(state.m + 1);
    }, RACE_SPEEDS[speed][1]);
  }

  box.addEventListener('click', (e) => {
    const act = e.target.closest('[data-act]')?.dataset.act;
    if (act === 'play') return state.timer ? stop() : play();
    if (act === 'restart') {
      show(0);
      return play();
    }
    const sp = e.target.closest('[data-speed]');
    if (sp) {
      speed = sp.dataset.speed;
      for (const b of box.querySelectorAll('[data-speed]')) b.classList.toggle('on', b === sp);
      try {
        localStorage.setItem('openmarket.race.speed', speed);
      } catch {
        /* ignore */
      }
      if (state.timer) play();
      return;
    }
    const row = e.target.closest('.rt-row[data-code]'); // the index rows are for comparison only
    if (row) pick(row.dataset.code, e.ctrlKey || e.metaKey || e.shiftKey);
  });
  seek.addEventListener('input', () => {
    stop();
    show(Number(seek.value));
  });
  // the yellow playhead is a handle too: dragging it moves the time like the slider above
  const layer = box.querySelector('.rt-layer');
  const minuteAt = (x) => {
    const r = layer.getBoundingClientRect();
    return Math.round(Math.min(1, Math.max(0, (x - r.left) / r.width)) * RACE_END);
  };
  head.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    stop();
    head.setPointerCapture(e.pointerId);
    head.classList.add('drag');
  });
  head.addEventListener('pointermove', (e) => {
    if (!head.hasPointerCapture(e.pointerId)) return;
    const m = minuteAt(e.clientX);
    if (m !== state.m) show(m);
  });
  const release = (e) => {
    if (head.hasPointerCapture(e.pointerId)) head.releasePointerCapture(e.pointerId);
    head.classList.remove('drag');
  };
  head.addEventListener('pointerup', release);
  head.addEventListener('pointercancel', release);
  pick(leader); // the leader's chart until another row is clicked
  show(RACE_END); // the finished day first: the same picture as the static timeline; ▶ replays from 09:00
  return stop;
}
