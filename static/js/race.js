// 漲幅賽跑 (in K): the group's top members replayed minute by minute from 09:00 to 13:30, ranked by
// their change at that minute. Equal changes (two stocks locked limit-up) keep the one that got there
// first in front. Pure frame builders on top (node --test); the animated panel below.

import { colorFor, escapeHtml, fmtPct, limitTag } from './transform.js';

export const RACE_END = 270; // minutes after 09:00 → 13:30
const ROW_H = 24;
export const RACE_SPEEDS = { slow: ['慢', 160], mid: ['中', 70], fast: ['快', 25] }; // ms per minute

/**
 * points {code: [[minute, pct]]} → per code, values[m] and since[m] for m = 0…RACE_END:
 * the last known change at minute m (null before the first trade) and the minute it took that value.
 */
export function raceFrames(points, codes) {
  const out = {};
  for (const c of codes) {
    const at = new Map((points?.[c] || []).map(([m, v]) => [m, v]));
    const values = new Array(RACE_END + 1).fill(null);
    const since = new Array(RACE_END + 1).fill(null);
    let v = null;
    let s = null;
    for (let m = 0; m <= RACE_END; m++) {
      if (at.has(m) && at.get(m) !== v) {
        v = at.get(m);
        s = m;
      }
      values[m] = v;
      since[m] = s;
    }
    out[c] = { values, since };
  }
  return out;
}

/** Codes in race order at minute m: change desc, then whoever reached that change first; no trade yet last. */
export function raceOrder(codes, frames, m) {
  return [...codes].sort((a, b) => {
    const va = frames[a].values[m];
    const vb = frames[b].values[m];
    if (va === null || vb === null) return (va === null) - (vb === null);
    if (Math.abs(va - vb) >= 0.005) return vb - va;
    return frames[a].since[m] - frames[b].since[m];
  });
}

export function fmtClock(m) {
  return `${String(9 + Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;
}

/** Shared x-axis: from the lowest to the highest change of the whole day (always including 0). */
export function raceDomain(frames) {
  let lo = 0;
  let hi = 0;
  for (const f of Object.values(frames)) {
    for (const v of f.values) {
      if (v === null) continue;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  if (hi - lo < 1) hi = lo + 1;
  return [lo, hi];
}

// ---- panel --------------------------------------------------------------------------------------

/** Mount the race into `box` for linkage data `d`; returns a stop() that halts the timer. */
export function mountRace(box, d, { onStock } = {}) {
  const codes = d.members.map((m) => m.code);
  const byCode = new Map(d.members.map((m) => [m.code, m]));
  const frames = raceFrames(d.race?.points, codes);
  if (!codes.some((c) => frames[c].values[RACE_END] !== null)) {
    box.innerHTML = '<p class="hint">這一天沒有分時資料，無法播放。</p>';
    return () => {};
  }
  const [lo, hi] = raceDomain(frames);
  const zero = (-lo / (hi - lo)) * 100;
  const leader = codes[0];
  const step = d.race?.step_min === 5 ? '5 分 K' : '1 分 K';
  let speed = 'mid';
  try {
    if (localStorage.getItem('openmarket.race.speed') in RACE_SPEEDS) speed = localStorage.getItem('openmarket.race.speed');
  } catch {
    /* default */
  }
  box.innerHTML = `<div class="race-ctl">
      <button type="button" class="icon" data-act="play" title="播放／暫停">▶</button>
      <button type="button" class="icon" data-act="restart" title="從 09:00 重新開始">⏮</button>
      <b class="race-clock">09:00</b>
      <input type="range" class="race-seek" min="0" max="${RACE_END}" value="0" aria-label="時間">
      <div class="seg race-speed">${Object.entries(RACE_SPEEDS)
        .map(([k, [label]]) => `<button type="button" data-speed="${k}"${k === speed ? ' class="on"' : ''}>${label}</button>`)
        .join('')}</div>
      <small class="muted">${step}；同漲幅（例如都漲停）先到的排前面</small>
    </div>
    <div class="race-board" style="height:${codes.length * ROW_H}px">${codes
      .map((c) => {
        const m = byCode.get(c);
        return `<div class="race-row" data-code="${escapeHtml(c)}" title="${escapeHtml(c)} ${escapeHtml(m.name)}">
          <span class="race-rank"></span><span class="race-name">${c === leader ? '👑' : ''}${escapeHtml(m.name)}</span>
          <span class="race-track"><span class="race-zero" style="left:${zero}%"></span><span class="race-bar"></span></span>
          <span class="race-pct"></span></div>`;
      })
      .join('')}</div>`;
  const rows = new Map([...box.querySelectorAll('.race-row')].map((el) => [el.dataset.code, el]));
  const clock = box.querySelector('.race-clock');
  const seek = box.querySelector('.race-seek');
  const playBtn = box.querySelector('[data-act="play"]');
  const state = { m: 0, timer: null };

  function show(m) {
    state.m = m;
    clock.textContent = fmtClock(m);
    seek.value = String(m);
    raceOrder(codes, frames, m).forEach((c, i) => {
      const el = rows.get(c);
      const v = frames[c].values[m];
      el.style.transform = `translateY(${i * ROW_H}px)`;
      el.querySelector('.race-rank').textContent = v === null ? '' : String(i + 1);
      const bar = el.querySelector('.race-bar');
      if (v === null) {
        bar.style.width = '0';
      } else {
        const x = ((v - lo) / (hi - lo)) * 100;
        bar.style.left = `${Math.min(x, zero)}%`;
        bar.style.width = `${Math.abs(x - zero)}%`;
        bar.style.background = colorFor(v, 7);
        bar.classList.toggle('limit', !!limitTag(v));
      }
      const tag = limitTag(v);
      el.querySelector('.race-pct').innerHTML = v === null ? '<span class="muted">未成交</span>' : `${fmtPct(v)}${tag ? ` <b class="race-tag">${tag}</b>` : ''}`;
    });
  }

  function stop() {
    clearInterval(state.timer);
    state.timer = null;
    playBtn.textContent = '▶';
  }
  function play() {
    if (state.m >= RACE_END) show(0);
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
    const row = e.target.closest('.race-row');
    if (row) onStock?.(row.dataset.code);
  });
  seek.addEventListener('input', () => {
    stop();
    show(Number(seek.value));
  });
  show(0);
  return stop;
}
