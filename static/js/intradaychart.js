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
      const at = c >= limit - 0.005;
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

/** A benchmark's race points ([[minute, close %, …]]) up to minute m, drawn at the same % of this
 *  stock's previous close: on the right-hand % axis the two lines read against each other directly. */
export function benchPath(points, prev, m) {
  return (points || []).filter((p) => p[0] <= m).map((p) => [p[0], priceAt(prev, p[1])]);
}

export function buildIntradayOption(data, m, benches = []) {
  const prev = data.prev_close;
  const bars = data.bars.filter((b) => b[0] <= m);
  const range = priceRange(data);
  const benchLines = benches.map((b) => ({ name: b.name, all: benchPath(b.points, prev, END), path: benchPath(b.points, prev, m) }));
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
        const b = bars.find((x) => x[0] === t);
        if (!b) return '';
        const idx = benchLines
          .map((x) => [x.name, x.path.filter((p) => p[0] <= t).at(-1)])
          .filter(([, p]) => p)
          .map(([name, p]) => `<br>${escapeHtml(name)} ${fmtPct(pctOf(p[1]))}`)
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

/** The chart panel inside `el`; load(code) fetches a member, sync(m) redraws up to minute m. */
export function mountIntraday(el, { date, onCard, benchmarks = [] }) {
  el.innerHTML = `<div class="ic-head"><b class="ic-title"></b><span class="muted ic-note"></span>
      <button type="button" class="icon wide ic-card">資訊卡</button></div>
    <div class="ic-body"><div class="ic-chart"></div><div class="ic-side"></div></div>`;
  const title = el.querySelector('.ic-title');
  const note = el.querySelector('.ic-note');
  const chartEl = el.querySelector('.ic-chart');
  const side = el.querySelector('.ic-side');
  const cache = new Map();
  const state = { code: null, data: null, m: END, chart: null, ticket: 0 };
  el.querySelector('.ic-card').addEventListener('click', () => state.code && onCard?.(state.code));

  function draw() {
    const d = state.data;
    if (!d) return;
    if (!d.bars.length) {
      side.innerHTML = '';
      chartEl.innerHTML = '<p class="hint" style="padding:8px">這一天沒有這檔的分時資料。</p>';
      state.chart?.dispose();
      state.chart = null;
      return;
    }
    if (!state.chart) {
      chartEl.innerHTML = '';
      state.chart = echarts.init(chartEl);
      new ResizeObserver(() => state.chart?.resize()).observe(chartEl);
    }
    state.chart.setOption(buildIntradayOption(d, state.m, benchmarks), { notMerge: true });
    side.innerHTML = infoHtml(d, statsAt(d, state.m), state.m);
  }

  async function load(code, name) {
    state.code = code;
    const t = ++state.ticket;
    title.textContent = `${name || code} ${code} · ${date}`;
    note.textContent = '載入中…';
    let d = cache.get(code);
    if (!d) {
      try {
        const r = await fetch(`/api/history/intraday?code=${encodeURIComponent(code)}&date=${encodeURIComponent(date)}`, { cache: 'no-store' });
        d = await r.json();
        if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
        cache.set(code, d);
      } catch (err) {
        if (t === state.ticket) note.textContent = `載入失敗：${err.message}`;
        return;
      }
    }
    if (t !== state.ticket) return;
    state.data = d;
    note.innerHTML = `${d.step_min === 5 ? '5 分 K' : '1 分 K'}${d.source === 'recorded' ? '（自錄，無成交量）' : ''}；紫線＝均價；● 日內最高點${benchmarks.length ? `；虛線＝${benchmarks.map((b, i) => `<span style="color:${BENCH_COLORS[i % BENCH_COLORS.length]}">${escapeHtml(b.name)}</span>`).join('／')}（同一 % 軸）` : ''}`;
    draw();
  }

  return {
    load,
    sync(m) {
      state.m = m;
      draw();
    },
  };
}
