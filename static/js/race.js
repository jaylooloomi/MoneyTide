// K · 日內最高點時間＋漲幅 (animated): the group's top members replayed minute by minute from 09:00 to
// 13:30 on a time axis. Each row draws its change-% path up to the playhead, a dot on the highest point
// so far (09:00–13:00 window, earliest wins), and the current change; rows re-rank by that change, and
// a stock locked limit-up stays ahead of every later limit-up (and of everyone not at the limit).
// Pure frame builders on top (node --test); the animated panel below.

import { mountIntraday } from './intradaychart.js';
import { colorFor, escapeHtml, fmtPct, limitTag } from './transform.js';

export const RACE_END = 270; // minutes after 09:00 → 13:30
export const PEAK_END = 240; // the intraday high is taken over 09:00–13:00
const ROW_H = 38;
const PAD = 3; // px above / below the path inside a row
export const RACE_SPEEDS = { slow: ['慢', 160], mid: ['中', 70], fast: ['快', 25] }; // ms per minute

/**
 * points {code: [[minute, close %, high %]]} → per code, for m = 0…RACE_END:
 * values[m] the last close % (null before the first trade), since[m] the minute that value was reached,
 * highs[m] the high % of minute m itself (null without data), and lockedAt[m] the minute the current
 * limit-up streak began (null when not at limit-up at m).
 */
export function raceFrames(points, codes, limits = {}) {
  const out = {};
  for (const c of codes) {
    const locked = isLimitUp(limits[c]);
    const at = new Map((points?.[c] || []).map(([m, v, h]) => [m, [v, h ?? v]]));
    const values = new Array(RACE_END + 1).fill(null);
    const since = new Array(RACE_END + 1).fill(null);
    const highs = new Array(RACE_END + 1).fill(null);
    const lockedAt = new Array(RACE_END + 1).fill(null);
    let v = null;
    let s = null;
    let lock = null;
    for (let m = 0; m <= RACE_END; m++) {
      const p = at.get(m);
      if (p) {
        highs[m] = p[1];
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
    out[c] = { values, since, highs, lockedAt };
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

/** The highest high up to minute m (never past 13:00) and the first minute it was reached; null before any trade. */
export function peakSoFar(frame, m) {
  let best = null;
  for (let i = 0; i <= Math.min(m, PEAK_END); i++) {
    const h = frame.highs[i];
    if (h !== null && (best === null || h > best.v)) best = { m: i, v: h };
  }
  return best;
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
  const [lo, hi] = raceDomain(frames);
  const inner = ROW_H - 2 * PAD;
  const y = (v) => PAD + ((hi - v) / (hi - lo)) * inner;
  const leader = codes[0];
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
      <small class="muted">${step}；● ＝到目前為止的最高點；先鎖漲停的排前面；點一列看右邊的走勢圖</small>
    </div>
    <div class="rt">
      <div class="rt-axis">${TICKS.map(([label, m]) => `<span style="left:${pctX(m)}%">${label}</span>`).join('')}</div>
      <div class="rt-board" style="height:${codes.length * ROW_H}px">
        <div class="rt-layer"><span class="rt-after" style="left:${pctX(PEAK_END)}%" title="13:00 之後不計入日內最高點"></span><span class="rt-head"></span></div>
        ${codes
          .map((c) => {
            const m = byCode.get(c);
            return `<div class="rt-row" data-code="${escapeHtml(c)}" title="${escapeHtml(c)} ${escapeHtml(m.name)}：點一下看右邊的走勢圖">
              <span class="rt-rank"></span><span class="rt-name">${c === leader ? '👑' : ''}${escapeHtml(m.name)}</span>
              <span class="rt-track">
                <svg viewBox="0 0 ${RACE_END} ${ROW_H}" preserveAspectRatio="none"><line class="rt-zero" x1="0" x2="${RACE_END}" y1="${y(0)}" y2="${y(0)}"/><polyline class="rt-path"/></svg>
                <span class="rt-dot"></span>
              </span>
              <span class="rt-now"></span><span class="rt-peak"></span></div>`;
          })
          .join('')}
      </div>
    </div></div><div class="race-side"></div></div>`;
  const chart = mountIntraday(box.querySelector('.race-side'), { date: d.date, onCard: onStock });
  const rows = new Map([...box.querySelectorAll('.rt-row')].map((el) => [el.dataset.code, el]));
  const clock = box.querySelector('.race-clock');
  const seek = box.querySelector('.race-seek');
  const head = box.querySelector('.rt-head');
  const playBtn = box.querySelector('[data-act="play"]');
  const state = { m: RACE_END, timer: null, picked: null };
  function pick(code) {
    state.picked = code;
    for (const [c, el] of rows) el.classList.toggle('on', c === code);
    chart.load(code, byCode.get(code)?.name).then(() => chart.sync(state.m));
  }

  function show(m) {
    state.m = m;
    clock.textContent = fmtClock(m);
    seek.value = String(m);
    head.style.left = `${pctX(m)}%`;
    chart.sync(m);
    raceOrder(codes, frames, m).forEach((c, i) => {
      const el = rows.get(c);
      const f = frames[c];
      const v = f.values[m];
      el.style.transform = `translateY(${i * ROW_H}px)`;
      el.querySelector('.rt-rank').textContent = v === null ? '' : String(i + 1);
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
      el.querySelector('.rt-peak').textContent = peak ? `高點 ${fmtClock(peak.m)} ${fmtPct(peak.v)}` : '';
    });
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
    const row = e.target.closest('.rt-row');
    if (row) pick(row.dataset.code);
  });
  seek.addEventListener('input', () => {
    stop();
    show(Number(seek.value));
  });
  pick(leader); // the leader's chart until another row is clicked
  show(RACE_END); // the finished day first: the same picture as the static timeline; ▶ replays from 09:00
  return stop;
}
