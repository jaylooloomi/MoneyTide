// K · the picked member's session beside the animation: price + 均價 on a price / % axis, volume below,
// and an info column. Everything is drawn up to the playhead minute, so it plays along with the race.
// Server: /api/history/intraday (bars [[minute, open, high, low, close, volume shares | null]]).
// Pure builders on top (node --test); the ECharts / DOM part below.

import { escapeHtml, fmtPct, fmtTurnover } from './transform.js';

const END = 270; // 13:30
const PEAK_END = 240; // the intraday high window ends at 13:00
const UP = '#ff4d4f';
const DOWN = '#2ecc71';
const fmtClock = (m) => `${String(9 + Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

/** Price at a % change from the previous close. */
const priceAt = (prev, pct) => prev * (1 + pct / 100);

/** The session up to minute m: open / high / low / last, volume, 均價, the intraday high and the limit-up lock. */
export function statsAt(data, m) {
  const bars = (data?.bars || []).filter((b) => b[0] <= m);
  const prev = data?.prev_close;
  if (!bars.length || !prev) return null;
  let hi = -Infinity;
  let lo = Infinity;
  let vol = 0;
  let value = 0;
  let volKnown = true;
  let peak = null;
  for (const [t, , h, l, c, v] of bars) {
    hi = Math.max(hi, h);
    lo = Math.min(lo, l);
    if (v === null || v === undefined) volKnown = false;
    else {
      vol += v;
      value += v * c;
    }
    if (t <= PEAK_END && (peak === null || h > peak.price)) peak = { m: t, price: h };
  }
  const last = bars[bars.length - 1][4];
  // limit-up lock on the closes: the first lock, whether it still holds, and how often it was opened
  const limit = data.limit_up_pct != null ? priceAt(prev, data.limit_up_pct) : null;
  let firstLock = null;
  let opens = 0;
  let locked = false;
  if (limit) {
    for (const [t, , , , c] of bars) {
      const at = c >= limit * (1 - 2e-4); // the price rebuilt from the rounded % can sit just above the real one (487.5 → 536.006)
      if (at && firstLock === null) firstLock = t;
      if (locked && !at) opens += 1;
      locked = at;
    }
  }
  return {
    open: bars[0][1],
    high: hi,
    low: lo,
    last,
    change: last - prev,
    pct: (last / prev - 1) * 100,
    amplitude: ((hi - lo) / prev) * 100,
    volume: volKnown ? vol : null,
    turnover: volKnown ? value : null,
    vwap: volKnown && vol > 0 ? value / vol : null,
    peak,
    firstLock,
    locked,
    opens,
  };
}

/** 均價 path: cumulative Σ(close × volume) / Σvolume per bar, up to minute m (null without volume). */
export function vwapPath(bars, m) {
  let v = 0;
  let pv = 0;
  const out = [];
  for (const [t, , , , c, vol] of bars) {
    if (t > m) break;
    if (vol === null || vol === undefined) return [];
    v += vol;
    pv += vol * c;
    if (v > 0) out.push([t, pv / v]);
  }
  return out;
}

/** Price-axis range over the whole day (so it never jumps while playing), widened to a nearby limit. */
export function priceRange(data) {
  const prev = data.prev_close;
  let hi = prev;
  let lo = prev;
  for (const b of data.bars) {
    hi = Math.max(hi, b[2]);
    lo = Math.min(lo, b[3]);
  }
  const up = data.limit_up_pct != null ? priceAt(prev, data.limit_up_pct) : null;
  const down = data.limit_down_pct != null ? priceAt(prev, data.limit_down_pct) : null;
  // show a limit line when the day came within 1% of it
  const showUp = up !== null && hi >= priceAt(prev, data.limit_up_pct - 1);
  const showDown = down !== null && lo <= priceAt(prev, data.limit_down_pct + 1);
  if (showUp) hi = Math.max(hi, up);
  if (showDown) lo = Math.min(lo, down);
  const pad = Math.max((hi - lo) * 0.06, prev * 0.002);
  return { min: lo - pad, max: hi + pad, up: showUp ? up : null, down: showDown ? down : null };
}

export const BENCH_COLORS = ['#7fb3ff', '#f0a35e']; // 大盤, 櫃買

export const BENCH_ALIGNS = { open: '開盤對齊', prev: '昨收' }; // how 大盤／櫃買 are drawn beside a stock

/** A benchmark's race points ([[minute, close %, …]]) → [[minute, % since its 09:00 point, day %]]: at the
 *  open both indexes read 0, so they start together whatever their overnight gap. */
export function sinceOpen(points) {
  const base = points?.[0]?.[1];
  if (base === undefined || base === null) return [];
  return points.map((p) => [p[0], ((1 + p[1] / 100) / (1 + base / 100) - 1) * 100, p[1]]);
}

/** A benchmark's race points up to minute m as [minute, price] beside this stock. align 'prev': the same %
 *  of the stock's previous close (the right-hand % axis reads both); 'open': its move since the open,
 *  from the stock's first price, so the stock and both indexes start at one point. */
export function benchPath(points, prev, m, align = 'prev', start = null) {
  if (align === 'open' && start) return sinceOpen(points).filter((p) => p[0] <= m).map((p) => [p[0], start * (1 + p[1] / 100)]);
  return (points || []).filter((p) => p[0] <= m).map((p) => [p[0], priceAt(prev, p[1])]);
}

export function buildIntradayOption(data, m, benches = [], align = 'prev') {
  const prev = data.prev_close;
  const bars = data.bars.filter((b) => b[0] <= m);
  const range = priceRange(data);
  const start = data.bars[0]?.[4] ?? null; // the stock line's first point (its first bar's close): the three lines start there
  const benchLines = benches.map((b) => ({
    name: b.name,
    all: benchPath(b.points, prev, END, align, start),
    path: benchPath(b.points, prev, m, align, start),
    open: sinceOpen(b.points),
    day: b.points || [],
  }));
  for (const b of benchLines) {
    for (const [, price] of b.all) {
      range.min = Math.min(range.min, price);
      range.max = Math.max(range.max, price);
    }
  }
  const s = statsAt(data, m);
  const color = s && s.last < prev ? DOWN : UP;
  const lines = [{ yAxis: prev, lineStyle: { color: '#8a8f9c', type: 'dashed' }, label: { show: false } }];
  if (range.up !== null) lines.push({ yAxis: range.up, lineStyle: { color: '#ffd400', type: 'dotted' }, label: { formatter: '漲停', color: '#ffd400', fontSize: 10 } });
  if (range.down !== null) lines.push({ yAxis: range.down, lineStyle: { color: '#3de0ff', type: 'dotted' }, label: { formatter: '跌停', color: '#3de0ff', fontSize: 10 } });
  const head = { xAxis: m, lineStyle: { color: '#ffd400', type: 'solid', width: 1.5 }, label: { show: false } };
  const xAxis = (gridIndex, labels) => ({
    type: 'value',
    gridIndex,
    min: 0,
    max: END,
    interval: 30,
    axisLabel: { show: labels, color: '#8a8f9c', fontSize: 10, formatter: (v) => (v % 60 === 0 || v === END ? fmtClock(v) : '') },
    axisLine: { lineStyle: { color: '#3a3e48' } },
    axisTick: { show: false },
    splitLine: { show: true, lineStyle: { color: '#23262e' } },
  });
  const pctOf = (p) => (p / prev - 1) * 100;
  return {
    animation: false,
    grid: [
      { left: 52, right: 52, top: 10, height: '62%' },
      { left: 52, right: 52, top: '76%', bottom: 22 },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1d212a',
      borderColor: '#444a57',
      textStyle: { color: '#ddd', fontSize: 12 },
      axisPointer: { type: 'line', link: [{ xAxisIndex: 'all' }] },
      formatter: (ps) => {
        const t = ps[0]?.value?.[0];
        const b = [...bars].reverse().find((x) => x[0] <= t);
        if (!b) return '';
        const idx = benchLines
          .map((x) => [x.name, x.open.filter((p) => p[0] <= t).at(-1)])
          .filter(([, p]) => p)
          .map(([name, p]) => `<br>${escapeHtml(name)} 開盤以來 ${fmtPct(p[1])}（當日 ${fmtPct(p[2])}）`)
          .join('');
        return `${fmtClock(t)}<br>價 ${b[4]}（${fmtPct(pctOf(b[4]))}）<br>高 ${b[2]}　低 ${b[3]}${b[5] != null ? `<br>量 ${Math.round(b[5] / 1000).toLocaleString()} 張` : ''}${idx}`;
      },
    },
    xAxis: [xAxis(0, false), xAxis(1, true)],
    yAxis: [
      { type: 'value', gridIndex: 0, min: range.min, max: range.max, scale: true, axisLabel: { color: '#aeb3bf', fontSize: 10, formatter: (v) => v.toFixed(prev < 50 ? 2 : 1) }, splitLine: { lineStyle: { color: '#23262e' } } },
      {
        type: 'value',
        gridIndex: 0,
        position: 'right',
        min: range.min,
        max: range.max,
        axisLabel: { fontSize: 10, formatter: (v) => fmtPct(pctOf(v)), color: '#aeb3bf' },
        splitLine: { show: false },
      },
      { type: 'value', gridIndex: 1, axisLabel: { color: '#8a8f9c', fontSize: 9, formatter: (v) => (v >= 1e6 ? `${Math.round(v / 1e6)}k` : Math.round(v / 1000)) }, splitLine: { show: false } },
    ],
    series: [
      {
        name: '價',
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: bars.map((b) => [b[0], b[4]]),
        showSymbol: false,
        lineStyle: { color, width: 1.6 },
        markLine: { symbol: 'none', silent: true, data: [...lines, head] },
        markPoint: s?.peak
          ? { symbol: 'circle', symbolSize: 9, itemStyle: { color: UP, borderColor: '#fff' }, label: { show: false }, data: [{ coord: [s.peak.m, s.peak.price] }] }
          : undefined,
      },
      { name: '均價', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: vwapPath(data.bars, m), showSymbol: false, lineStyle: { color: '#c39bd3', width: 1.2 } },
      ...benchLines.map((b, i) => ({
        name: b.name,
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: b.path,
        showSymbol: false,
        silent: true,
        z: 1,
        lineStyle: { color: BENCH_COLORS[i % BENCH_COLORS.length], width: 1, type: 'dashed', opacity: 0.8 },
      })),
      {
        name: '量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 2,
        barWidth: data.step_min === 5 ? 4 : 1.2,
        data: bars.map((b, i) => ({ value: [b[0], b[5] ?? 0], itemStyle: { color: b[4] >= (i ? bars[i - 1][4] : prev) ? UP : DOWN } })),
        markLine: { symbol: 'none', silent: true, data: [head] },
      },
    ],
  };
}

// the picked stocks in order (the K rows' outlines match); more than this many cycle the colours
export const PICK_COLORS = ['#ffd400', '#3de0ff', '#ff6bd6', '#7dff8a', '#ff9f43', '#b18cff', '#ffffff', '#4dabf7', '#ff6b6b', '#c0eb75'];
export const MAX_PICKS = 10;
const pickColor = (i) => PICK_COLORS[i % PICK_COLORS.length];
const COMPARE_BENCH_COLORS = ['#9aa0aa', '#c39bd3']; // 大盤／櫃買 in a comparison: away from the two stocks' yellow / cyan

/** Several stocks on one % axis (each against its own previous close), volume below, 大盤／櫃買 dashed;
 *  everything up to minute m, the axis range from the whole day so it does not jump while playing. */
export function buildCompareOption(items, m, benches = [], align = 'prev') {
  // 'open': the indexes from 0 at 09:00 (their move since the open), so the two start together
  const benchPts = benches.map((b) => (align === 'open' ? sinceOpen(b.points) : (b.points || []).map((p) => [p[0], p[1], p[1]])));
  const pctOf = (d, p) => (p / d.prev_close - 1) * 100;
  let lo = 0;
  let hi = 0;
  for (const { data } of items) {
    for (const b of data.bars) {
      lo = Math.min(lo, pctOf(data, b[3]));
      hi = Math.max(hi, pctOf(data, b[2]));
    }
  }
  for (const pts of benchPts) for (const p of pts) (lo = Math.min(lo, p[1])), (hi = Math.max(hi, p[1]));
  const pad = Math.max((hi - lo) * 0.06, 0.3);
  const head = { xAxis: m, lineStyle: { color: '#ffd400', type: 'solid', width: 1.5 }, label: { show: false } };
  const xAxis = (gridIndex, labels) => ({
    type: 'value',
    gridIndex,
    min: 0,
    max: END,
    interval: 30,
    axisLabel: { show: labels, color: '#8a8f9c', fontSize: 10, formatter: (v) => (v % 60 === 0 || v === END ? fmtClock(v) : '') },
    axisLine: { lineStyle: { color: '#3a3e48' } },
    axisTick: { show: false },
    splitLine: { show: true, lineStyle: { color: '#23262e' } },
  });
  const step = Math.max(...items.map((x) => x.data.step_min || 1));
  const lines = items.map(({ data, name }, i) => {
    const s = statsAt(data, m);
    return {
      name,
      type: 'line',
      xAxisIndex: 0,
      yAxisIndex: 0,
      data: data.bars.filter((b) => b[0] <= m).map((b) => [b[0], pctOf(data, b[4])]),
      showSymbol: false,
      lineStyle: { color: pickColor(i), width: items.length > 4 ? 1.3 : 1.6 },
      itemStyle: { color: pickColor(i) },
      markLine: i === 0 ? { symbol: 'none', silent: true, data: [{ yAxis: 0, lineStyle: { color: '#8a8f9c', type: 'dashed' }, label: { show: false } }, head] } : undefined,
      markPoint: s?.peak
        ? { symbol: 'circle', symbolSize: 8, itemStyle: { color: pickColor(i), borderColor: '#fff' }, label: { show: false }, data: [{ coord: [s.peak.m, pctOf(data, s.peak.price)] }] }
        : undefined,
    };
  });
  const slot = (step === 5 ? 4 : 0.9) / items.length; // each stock's share of one bar's width
  const volumes = items.map(({ data, name }, i) => ({
    name: `${name} 量`,
    type: 'bar',
    xAxisIndex: 1,
    yAxisIndex: 1,
    barWidth: Math.max(0.5, slot * 0.9),
    // side by side: each stock's bars sit a little to the right of the previous one's
    data: data.bars.filter((b) => b[0] <= m).map((b) => [b[0] + i * slot, b[5] ?? 0]),
    itemStyle: { color: pickColor(i), opacity: 0.75 },
    markLine: i === 0 ? { symbol: 'none', silent: true, data: [head] } : undefined,
  }));
  const benchLines = benches.map((b, i) => ({
    name: b.name,
    type: 'line',
    xAxisIndex: 0,
    yAxisIndex: 0,
    data: benchPts[i].filter((p) => p[0] <= m).map((p) => [p[0], p[1]]),
    showSymbol: false,
    silent: true,
    z: 1,
    lineStyle: { color: COMPARE_BENCH_COLORS[i % COMPARE_BENCH_COLORS.length], width: 1, type: 'dashed', opacity: 0.8 },
  }));
  return {
    animation: false,
    grid: [
      { left: 52, right: 12, top: 10, height: '62%' },
      { left: 52, right: 12, top: '76%', bottom: 22 },
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#1d212a',
      borderColor: '#444a57',
      textStyle: { color: '#ddd', fontSize: 12 },
      axisPointer: { type: 'line', link: [{ xAxisIndex: 'all' }] },
      formatter: (ps) => {
        const t = ps[0]?.value?.[0];
        if (t == null) return '';
        const at = Math.floor(t);
        const stocks = items
          .map(({ data, name }, i) => {
            const b = [...data.bars].reverse().find((x) => x[0] <= at);
            return b ? `<span style="color:${pickColor(i)}">●</span> ${escapeHtml(name)} ${b[4]}（${fmtPct(pctOf(data, b[4]))}）` : '';
          })
          .filter(Boolean);
        const idx = benches
          .map((b) => [b.name, sinceOpen(b.points).filter((p) => p[0] <= at).at(-1)])
          .filter(([, p]) => p)
          .map(([name, p]) => `${escapeHtml(name)} 開盤以來 ${fmtPct(p[1])}（當日 ${fmtPct(p[2])}）`);
        return [fmtClock(at), ...stocks, ...idx].join('<br>');
      },
    },
    xAxis: [xAxis(0, false), xAxis(1, true)],
    yAxis: [
      { type: 'value', gridIndex: 0, min: lo - pad, max: hi + pad, axisLabel: { color: '#aeb3bf', fontSize: 10, formatter: (v) => fmtPct(v) }, splitLine: { lineStyle: { color: '#23262e' } } },
      { type: 'value', gridIndex: 1, axisLabel: { color: '#8a8f9c', fontSize: 9, formatter: (v) => (v >= 1e6 ? `${Math.round(v / 1e6)}k` : Math.round(v / 1000)) }, splitLine: { show: false } },
    ],
    series: [...lines, ...benchLines, ...volumes],
  };
}

/** The info table for several stocks: the same figures side by side, as of the playhead minute. */
export function compareInfoHtml(items, m) {
  const stats = items.map(({ data }) => statsAt(data, m));
  const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
  const p = (d, v) => (v == null ? '—' : v.toFixed(d.prev_close < 50 ? 2 : 1));
  const cell = (i, f) => {
    const s = stats[i];
    return s ? f(items[i].data, s) : '—';
  };
  const row = (k, f) => `<tr><td class="muted">${k}</td>${items.map((_, i) => `<td>${cell(i, f)}</td>`).join('')}</tr>`;
  const lockOf = (d, s) => (d.limit_up_pct == null || s.firstLock === null ? '—' : `<span class="${s.locked ? 'up' : ''}">${fmtClock(s.firstLock)}${s.locked ? '' : '（開）'}</span>`);
  return `<table class="ic-info cmp">
    <tr><td></td>${items.map(({ name }, i) => `<td><b style="color:${pickColor(i)}">${escapeHtml(name)}</b></td>`).join('')}</tr>
    ${row(m >= END ? '收盤' : '現價', (d, s) => `<span class="${cls(s.change)}">${p(d, s.last)}</span>`)}
    ${row('漲幅', (d, s) => `<span class="${cls(s.change)}">${fmtPct(s.pct)}</span>`)}
    ${row('最高', (d, s) => p(d, s.high))}
    ${row('最低', (d, s) => p(d, s.low))}
    ${row('振幅', (d, s) => `${s.amplitude.toFixed(2)}%`)}
    ${row('成交量', (d, s) => (s.volume == null ? '—' : `${Math.round(s.volume / 1000).toLocaleString()}`))}
    ${row('成交值', (d, s) => (s.turnover == null ? '—' : fmtTurnover(s.turnover / 1e8)))}
    ${row('最高點', (d, s) => (s.peak ? `${fmtClock(s.peak.m)}<br>${fmtPct((s.peak.price / d.prev_close - 1) * 100)}` : '—'))}
    ${row('鎖漲停', lockOf)}
  </table>`;
}

/** The K rows picked for the chart: a plain click shows just that stock, Ctrl/⌘/Shift adds one more
 *  (up to MAX_PICKS; past that the oldest goes), clicking a picked stock with the modifier drops it. */
export function nextPicks(picked, code, additive) {
  if (!additive) return [code];
  if (picked.includes(code)) return picked.length > 1 ? picked.filter((c) => c !== code) : picked;
  return [...picked, code].slice(-MAX_PICKS);
}

/** The info column: figures as of the playhead minute. */
export function infoHtml(data, s, m) {
  if (!s) return '<p class="hint">尚未成交</p>';
  const cls = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
  const p = (v) => (v == null ? '—' : v.toFixed(data.prev_close < 50 ? 2 : 1));
  const row = (k, v, c = '') => `<tr><td class="muted">${k}</td><td class="${c}">${v}</td></tr>`;
  const lock =
    data.limit_up_pct == null
      ? ''
      : s.firstLock === null
        ? row('鎖漲停', '—')
        : row('鎖漲停', `${fmtClock(s.firstLock)}${s.locked ? '' : '（已打開）'}`, s.locked ? 'up' : '') + row('開板', `${s.opens} 次`);
  return `<table class="ic-info">
    ${row(m >= END ? '收盤' : '現價', p(s.last), cls(s.change))}
    ${row('漲跌', `${s.change > 0 ? '+' : ''}${p(s.change)}`, cls(s.change))}
    ${row('漲幅', fmtPct(s.pct), cls(s.change))}
    ${row('開盤', p(s.open), cls(s.open - data.prev_close))}
    ${row('最高', p(s.high), cls(s.high - data.prev_close))}
    ${row('最低', p(s.low), cls(s.low - data.prev_close))}
    ${row('昨收', p(data.prev_close))}
    ${row('振幅', `${s.amplitude.toFixed(2)}%`)}
    ${row('均價', p(s.vwap))}
    ${row('成交量', s.volume == null ? '—' : `${Math.round(s.volume / 1000).toLocaleString()} 張`)}
    ${row('成交值', s.turnover == null ? '—' : fmtTurnover(s.turnover / 1e8))}
    ${row('最高點', s.peak ? `${fmtClock(s.peak.m)} ${fmtPct((s.peak.price / data.prev_close - 1) * 100)}` : '—')}
    ${lock}
  </table>`;
}

// ---- DOM / ECharts ---------------------------------------------------------------------

const LAYOUT_KEY = 'openmarket.intraday.compare';
const ALIGN_KEY = 'openmarket.intraday.benchAlign';
export const COMPARE_LAYOUTS = { overlay: '疊圖', stack: '上下' };

/** The chart panel inside `el`: show([{code, name}]) draws one stock, or several (疊圖 on one % axis /
 *  上下 one full chart each, switchable); sync(m) redraws up to minute m. load(code, name) = one stock. */
export function mountIntraday(el, { date, onCard, onDate, benchmarks = [] }) {
  // viewDate: the day drawn (a 5 日 K candle can pick another); 大盤／櫃買 exist for `date` only
  let viewDate = date;
  const benches = () => (viewDate === date ? benchmarks : []);
  el.innerHTML = `<div class="ic-head"><span class="ic-title"></span><span class="muted ic-note"></span>
      <div class="seg ic-align"${benchmarks.length ? '' : ' hidden'} title="大盤／櫃買虛線：開盤對齊＝從開盤一起出發（比開盤後的強弱）；昨收＝各自相對昨收的漲跌">${Object.entries(BENCH_ALIGNS).map(([k, label]) => `<button type="button" data-align="${k}">${label}</button>`).join('')}</div>
      <div class="seg ic-layout" hidden>${Object.entries(COMPARE_LAYOUTS).map(([k, label]) => `<button type="button" data-layout="${k}">${label}</button>`).join('')}</div>
      <button type="button" class="icon wide ic-card">資訊卡</button></div>
    <div class="ic-bodies"></div>`;
  const title = el.querySelector('.ic-title');
  const note = el.querySelector('.ic-note');
  const bodies = el.querySelector('.ic-bodies');
  const layoutSeg = el.querySelector('.ic-layout');
  const alignSeg = el.querySelector('.ic-align');
  let align = 'open';
  try {
    if (localStorage.getItem(ALIGN_KEY) in BENCH_ALIGNS) align = localStorage.getItem(ALIGN_KEY);
  } catch {
    /* default */
  }
  const markAlign = () => {
    for (const b of alignSeg.querySelectorAll('[data-align]')) b.classList.toggle('on', b.dataset.align === align);
  };
  markAlign();
  alignSeg.addEventListener('click', (e) => {
    const b = e.target.closest('[data-align]');
    if (!b) return;
    align = b.dataset.align;
    try {
      localStorage.setItem(ALIGN_KEY, align);
    } catch {
      /* ignore */
    }
    markAlign();
    draw();
  });
  const cache = new Map();
  let layout = 'overlay';
  try {
    if (localStorage.getItem(LAYOUT_KEY) in COMPARE_LAYOUTS) layout = localStorage.getItem(LAYOUT_KEY);
  } catch {
    /* default */
  }
  // items: [{code, name, data}]; slots: the chart areas on screen, rebuilt when their shape changes
  const state = { items: [], m: END, ticket: 0, slots: [], shape: '' };
  el.querySelector('.ic-card').addEventListener('click', () => state.items[0] && onCard?.(state.items[0].code));
  title.addEventListener('click', (e) => {
    if (e.target.closest('[data-act="back-day"]')) return setDate(date).then(() => onDate?.(date));
    const b = e.target.closest('[data-card]');
    if (b) onCard?.(b.dataset.card);
  });
  layoutSeg.addEventListener('click', (e) => {
    const b = e.target.closest('[data-layout]');
    if (!b) return;
    layout = b.dataset.layout;
    try {
      localStorage.setItem(LAYOUT_KEY, layout);
    } catch {
      /* ignore */
    }
    show(state.items).then(() => draw()); // cached: redraws with the note for the new layout
  });

  function slotsFor(n) {
    const many = n >= 2;
    const shape = `${n}|${many ? layout : ''}`;
    if (shape === state.shape) return state.slots;
    for (const s of state.slots) s.chart?.dispose();
    const count = many && layout === 'stack' ? n : 1;
    // 疊圖: two stocks keep the info column beside the chart; more go into a full-width table below
    const side = !many || layout === 'stack' ? 'ic-side' : n === 2 ? 'ic-side wide' : 'ic-side below';
    bodies.innerHTML = Array.from(
      { length: count },
      (_, i) => `${count > 1 ? `<div class="ic-sub" style="color:${pickColor(i)}"></div>` : ''}<div class="ic-body${side.includes('below') ? ' col' : ''}"><div class="ic-chart${count > 1 ? ' half' : ''}"></div><div class="${side}"></div></div>`,
    ).join('');
    const subs = [...bodies.querySelectorAll('.ic-sub')];
    state.slots = [...bodies.querySelectorAll('.ic-body')].map((b, i) => ({ chartEl: b.querySelector('.ic-chart'), side: b.querySelector('.ic-side'), sub: subs[i] || null, chart: null }));
    state.shape = shape;
    return state.slots;
  }

  function paintSlot(slot, option, sideHtml) {
    if (!slot.chart) {
      slot.chartEl.innerHTML = '';
      slot.chart = echarts.init(slot.chartEl);
      new ResizeObserver(() => slot.chart?.resize()).observe(slot.chartEl);
    }
    slot.chart.setOption(option, { notMerge: true });
    slot.side.innerHTML = sideHtml;
  }

  function empty(slot, name) {
    slot.chart?.dispose();
    slot.chart = null;
    slot.side.innerHTML = '';
    slot.chartEl.innerHTML = `<p class="hint" style="padding:8px">這一天沒有${escapeHtml(name || '這檔')}的分時資料。</p>`;
  }

  function draw() {
    const m = viewDate === date ? state.m : END; // another day (a 5 日 K candle): the whole session
    const items = state.items.filter((x) => x.data);
    if (!items.length || items.length < state.items.length) return;
    layoutSeg.hidden = items.length < 2;
    for (const [i, b] of [...title.querySelectorAll('[data-card]')].entries()) b.style.color = items.length > 1 ? pickColor(i) : '';
    for (const b of layoutSeg.querySelectorAll('[data-layout]')) b.classList.toggle('on', b.dataset.layout === layout);
    const slots = slotsFor(items.length);
    if (items.length >= 2 && layout === 'overlay') {
      const withBars = items.filter((x) => x.data.bars.length);
      if (!withBars.length) return empty(slots[0]);
      paintSlot(slots[0], buildCompareOption(withBars, m, benches(), align), compareInfoHtml(withBars, m));
      return;
    }
    items.forEach((x, i) => {
      if (slots[i].sub) slots[i].sub.textContent = `${x.name || x.code} ${x.code}`; // 上下: which chart is which
      if (!x.data.bars.length) return empty(slots[i], x.name);
      paintSlot(slots[i], buildIntradayOption(x.data, m, benches(), align), infoHtml(x.data, statsAt(x.data, m), m));
    });
  }

  function heading(items) {
    const many = items.length > 1;
    title.innerHTML = items
      .map((x, i) => `<b class="ic-name" data-card="${escapeHtml(x.code)}" title="點名稱開資訊卡"${many ? ` style="color:${pickColor(i)}"` : ''}>${escapeHtml(x.name || x.code)}${many && items.length > 3 ? '' : ` ${escapeHtml(x.code)}`}</b>`)
      .join(items.length === 2 ? ' <span class="muted">vs</span> ' : '<span class="muted">、</span>') +
      (viewDate === date
        ? ` <span class="muted">· ${escapeHtml(date)}</span>`
        : ` <b class="ic-other-day">· ${escapeHtml(viewDate)}</b> <button type="button" class="icon wide" data-act="back-day">⤺ 回到 ${escapeHtml(date.slice(5).replace('-', '/'))}</button>`);
  }

  const keyOf = (code) => `${code}@${viewDate}`;
  async function fetchDay(code) {
    const key = keyOf(code);
    if (cache.has(key)) return cache.get(key);
    const r = await fetch(`/api/history/intraday?code=${encodeURIComponent(code)}&date=${encodeURIComponent(viewDate)}`, { cache: 'no-store' });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    cache.set(key, d);
    return d;
  }

  /** Draw the shown stocks on another day (a 5 日 K candle); `date` again goes back. */
  function setDate(d) {
    viewDate = d || date;
    return show(state.items.map(({ code, name }) => ({ code, name })));
  }

  async function show(list) {
    const t = ++state.ticket;
    state.items = list.map(({ code, name }) => ({ code, name, data: cache.get(keyOf(code)) || null }));
    heading(state.items);
    note.textContent = '載入中…';
    try {
      const datas = await Promise.all(state.items.map((x) => fetchDay(x.code)));
      if (t !== state.ticket) return;
      state.items.forEach((x, i) => (x.data = datas[i]));
    } catch (err) {
      if (t === state.ticket) note.textContent = `載入失敗：${err.message}`;
      return;
    }
    const d = state.items[0].data;
    const step = `${state.items.some((x) => x.data.step_min === 5) ? '5 分 K' : '1 分 K'}${state.items.some((x) => x.data.source === 'recorded') ? '（自錄，無成交量）' : ''}`;
    const benchIn = (colors) =>
      viewDate !== date
        ? '；大盤／櫃買虛線只有 ' + escapeHtml(date.slice(5)) + ' 那天的資料'
        : benchmarks.length ? `；虛線＝${benchmarks.map((b, i) => `<span style="color:${colors[i % colors.length]}">${escapeHtml(b.name)}</span>`).join('／')}` : '';
    const bench = benchIn(state.items.length >= 2 && layout === 'overlay' ? COMPARE_BENCH_COLORS : BENCH_COLORS);
    note.innerHTML =
      state.items.length >= 2 && layout === 'overlay'
        ? `${step}；${state.items.length} 檔都換算成相對各自昨收的 %，可直接比強弱；● 各自的日內最高點${bench}；Ctrl／⌘＋點 K 的列可再加或取消（最多 ${MAX_PICKS} 檔）`
        : state.items.length >= 2
          ? `${step}；上下各一張完整的走勢（價格軸、漲停線、紫線＝均價）${bench}；Ctrl／⌘＋點 K 的列可再加或取消（最多 ${MAX_PICKS} 檔）`
        : `${d.step_min === 5 ? '5 分 K' : '1 分 K'}${d.source === 'recorded' ? '（自錄，無成交量）' : ''}；紫線＝均價；● 日內最高點${bench}${benches().length ? '（同一 % 軸）' : ''}；Ctrl／⌘＋點另一列可加入比較`;
    draw();
  }

  return {
    show,
    setDate,
    load: (code, name) => show([{ code, name }]),
    sync(m) {
      state.m = m;
      draw();
    },
  };
}
