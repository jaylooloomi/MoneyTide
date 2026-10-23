// G panel: TAIEX + TPEx daily candles, MA5/20/60, turnover bars and "strong day" marks.
// Pure option builders on top (tested with node --test); the DOM/ECharts part is mountIndexPanel().

import { fmtPct } from './transform.js';

export const MA_DAYS = [5, 20, 60];
export const STRONG_DAY = { ratio: 10, limitUp: 90 }; // ≈ top 10% of days over 2025-10…2026-10
export const DEFAULT_VISIBLE = 60; // trading days shown initially
const UP = '#e0262c'; // 台股：紅漲
const DOWN = '#1fa24a'; // 綠跌
const MA_COLORS = ['#f2c94c', '#56ccf2', '#bb6bd9'];
const MARKETS = [
  { key: 'twse', label: '加權指數' },
  { key: 'tpex', label: '櫃買指數' },
];

/** Simple moving average of `values` (null where fewer than `n` valid values end at that day). */
export function movingAverage(values, n) {
  const out = [];
  let sum = 0;
  let count = 0;
  const win = [];
  for (const v of values) {
    win.push(v);
    if (v !== null && v !== undefined) {
      sum += v;
      count += 1;
    }
    if (win.length > n) {
      const old = win.shift();
      if (old !== null && old !== undefined) {
        sum -= old;
        count -= 1;
      }
    }
    out.push(win.length === n && count === n ? Math.round((sum / n) * 100) / 100 : null);
  }
  return out;
}

export function isStrongDay(d) {
  return (d.strong_ratio ?? -1) >= STRONG_DAY.ratio || (d.limit_up ?? -1) >= STRONG_DAY.limitUp;
}

const fmtYi = (yuan) => (yuan === null || yuan === undefined ? '—' : `${(yuan / 1e8).toLocaleString('zh-TW', { maximumFractionDigits: 0 })} 億`);
const fmtIdx = (v) => (v === null || v === undefined ? '—' : v.toLocaleString('zh-TW', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));

export function indexTooltip(d) {
  if (!d) return '';
  const lines = [`<b>${d.date}</b>${d.has_stocks ? '' : ' <span style="opacity:.7">（無個股資料）</span>'}`];
  for (const { key, label } of MARKETS) {
    const r = d[key];
    if (!r) {
      lines.push(`${label}　—`);
      continue;
    }
    const prev = r.close !== null && r.change !== null ? r.close - r.change : null;
    const pct = prev ? (r.change / prev) * 100 : null;
    lines.push(
      `${label}　${fmtIdx(r.close)}（${r.change === null ? '—' : (r.change > 0 ? '+' : '') + r.change.toFixed(2)}，${fmtPct(pct)}）<br>` +
        `<span style="opacity:.75">　開 ${fmtIdx(r.open)}　高 ${fmtIdx(r.high)}　低 ${fmtIdx(r.low)}　成交值 ${fmtYi(r.turnover_yuan)}</span>`,
    );
  }
  if (d.has_stocks) {
    lines.push(`≥5% 佔比 ${d.strong_ratio.toFixed(1)}%　漲停 ${d.limit_up} 家${isStrongDay(d) ? '　<b style="color:#ffd400">強勢日</b>' : ''}`);
  }
  return lines.join('<br>');
}

/** ECharts option: grids 0/2 = candles (TAIEX/TPEx), 1/3 = turnover bars; one shared dataZoom. */
export function buildIndexOption(days, selected, visible = DEFAULT_VISIBLE) {
  const dates = days.map((d) => d.date);
  const grids = [
    { top: 28, height: '27%' },
    { top: '35%', height: '9%' },
    { top: '52%', height: '27%' },
    { top: '81%', height: '9%' },
  ].map((g) => ({ left: 64, right: 18, ...g }));
  const xAxis = grids.map((_, i) => ({
    type: 'category',
    gridIndex: i,
    data: dates,
    boundaryGap: true,
    axisLine: { lineStyle: { color: '#444a57' } },
    axisLabel: { show: i === 1 || i === 3, color: '#999' },
    axisTick: { show: false },
    axisPointer: { label: { show: i === 3 } },
  }));
  const yAxis = grids.map((_, i) => ({
    type: 'value',
    gridIndex: i,
    scale: i % 2 === 0,
    splitNumber: i % 2 === 0 ? 4 : 2,
    axisLabel: { color: '#999', formatter: i % 2 === 0 ? undefined : (v) => `${Math.round(v / 1e8)}億` },
    splitLine: { lineStyle: { color: '#262a33' } },
  }));
  const series = [];
  const mark = selected ? { symbol: 'none', silent: true, label: { show: false }, lineStyle: { color: '#ffd400', type: 'solid', width: 1 }, data: [{ xAxis: selected }] } : undefined;
  MARKETS.forEach(({ key, label }, m) => {
    const k = m * 2;
    const rows = days.map((d) => d[key]);
    series.push({
      id: `${key}K`,
      name: label,
      type: 'candlestick',
      xAxisIndex: k,
      yAxisIndex: k,
      data: rows.map((r) => (r && r.open !== null && r.close !== null ? [r.open, r.close, r.low, r.high] : '-')),
      itemStyle: { color: UP, color0: DOWN, borderColor: UP, borderColor0: DOWN },
      markLine: mark,
    });
    const closes = rows.map((r) => (r ? r.close : null));
    MA_DAYS.forEach((n, j) => {
      series.push({
        id: `${key}MA${n}`,
        name: `MA${n}`,
        type: 'line',
        xAxisIndex: k,
        yAxisIndex: k,
        data: movingAverage(closes, n).map((v) => (v === null ? '-' : v)),
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 1, color: MA_COLORS[j] },
        itemStyle: { color: MA_COLORS[j] },
        silent: true,
      });
    });
    series.push({
      id: `${key}Vol`,
      name: `${label}成交值`,
      type: 'bar',
      xAxisIndex: k + 1,
      yAxisIndex: k + 1,
      data: rows.map((r) =>
        r && r.turnover_yuan !== null
          ? { value: r.turnover_yuan, itemStyle: { color: r.close !== null && r.open !== null && r.close < r.open ? DOWN : UP } }
          : '-',
      ),
      markLine: mark,
    });
  });
  series.push({
    id: 'strong',
    name: '強勢日',
    type: 'scatter',
    xAxisIndex: 0,
    yAxisIndex: 0,
    symbol: 'triangle',
    symbolSize: 9,
    symbolRotate: 180,
    itemStyle: { color: '#ffd400' },
    data: days
      .map((d, i) => (isStrongDay(d) && d.twse?.high ? [i, Math.round(d.twse.high * 1.012 * 100) / 100] : null))
      .filter(Boolean),
    tooltip: { show: false },
  });
  const end = dates.length - 1;
  return {
    animation: false,
    backgroundColor: 'transparent',
    legend: { top: 2, left: 64, textStyle: { color: '#bbb' }, data: ['MA5', 'MA20', 'MA60', '強勢日'], itemWidth: 14 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross', link: [{ xAxisIndex: 'all' }] },
      backgroundColor: '#1d212a',
      borderColor: '#444a57',
      textStyle: { color: '#ddd', fontSize: 12 },
      formatter: (params) => indexTooltip(days[params?.[0]?.dataIndex]),
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    grid: grids,
    xAxis,
    yAxis,
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2, 3], startValue: Math.max(0, end - visible + 1), endValue: end },
      { type: 'slider', xAxisIndex: [0, 1, 2, 3], bottom: 4, height: 16, startValue: Math.max(0, end - visible + 1), endValue: end, textStyle: { color: '#999' } },
    ],
    series,
  };
}

/** The window [start, end] (indices) to show so that `idx` is visible, keeping the width. */
export function windowShowing(idx, start, end, length) {
  if (idx >= start && idx <= end) return [start, end];
  const width = end - start;
  let s = idx - Math.floor(width / 2);
  s = Math.max(0, Math.min(s, length - 1 - width));
  return [s, s + width];
}

// ---- DOM / ECharts ---------------------------------------------------------------------

/**
 * Mount the G panel into `container` (after F). `onPick(date)` switches the whole history view.
 * Returns { load(), mark(date) }.
 */
export function mountIndexPanel(container, onPick) {
  const sec = document.createElement('section');
  sec.id = 'hIndexPanel';
  sec.className = 'panel';
  sec.style.gridColumn = '1 / -1';
  sec.innerHTML = `<div class="panel-h"><b>G · 大盤＋櫃買</b>
      <span class="muted">日 K、MA5／20／60、成交值；▼＝強勢日（≥5% 佔比 ≥ ${STRONG_DAY.ratio}% 或漲停 ≥ ${STRONG_DAY.limitUp} 家）；點任一天切換上方所有面板</span>
      <span class="muted" id="hIndexNote" style="margin-left:auto"></span></div>
    <div id="hIndexChart" style="height:560px"></div>`;
  container.appendChild(sec);
  const el = sec.querySelector('#hIndexChart');
  const note = sec.querySelector('#hIndexNote');
  const state = { days: [], selected: null, chart: null, timer: null, loaded: false };

  function ensureChart() {
    if (state.chart) return state.chart;
    state.chart = echarts.init(el);
    new ResizeObserver(() => state.chart.resize()).observe(el);
    // click anywhere inside a grid (not only on a candle) picks that day
    state.chart.getZr().on('click', (e) => {
      const pt = [e.offsetX, e.offsetY];
      for (let g = 0; g < 4; g += 1) {
        if (!state.chart.containPixel({ gridIndex: g }, pt)) continue;
        const [i] = state.chart.convertFromPixel({ gridIndex: g }, pt); // category axis → day index
        const d = state.days[Math.round(i)];
        if (!d) return;
        if (!d.has_stocks) {
          note.textContent = `${d.date} 沒有個股資料，無法切換`;
          return;
        }
        note.textContent = '';
        onPick(d.date);
        return;
      }
    });
    return state.chart;
  }

  async function load() {
    clearTimeout(state.timer);
    let data;
    try {
      const resp = await fetch('/api/history/market-index?days=500', { cache: 'no-store' });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      data = await resp.json();
    } catch (err) {
      note.innerHTML = `大盤資料載入失敗（${err.message}） <button type="button" class="field" id="hIndexRetry">重試</button>`;
      note.querySelector('#hIndexRetry').addEventListener('click', load);
      return;
    }
    state.days = data.days;
    const hasIndex = data.days.some((d) => d.twse || d.tpex);
    const b = data.backfill || {};
    if (!hasIndex || b.running) {
      note.textContent = `大盤資料回補中（${b.months_done ?? 0}／${b.months_total ?? 0} 個市場月份）`;
      state.timer = setTimeout(load, 30_000);
    } else {
      note.textContent = b.error ? `部分月份抓取失敗，稍後重試：${b.error}` : '';
    }
    if (!hasIndex) return;
    state.loaded = true;
    ensureChart().setOption(buildIndexOption(state.days, state.selected), { notMerge: true });
  }

  function mark(date) {
    state.selected = date;
    if (!state.loaded) return;
    const chart = ensureChart();
    const line = { symbol: 'none', silent: true, label: { show: false }, lineStyle: { color: '#ffd400', type: 'solid', width: 1 }, data: [{ xAxis: date }] };
    chart.setOption({ series: ['twseK', 'twseVol', 'tpexK', 'tpexVol'].map((id) => ({ id, markLine: line })) });
    const idx = state.days.findIndex((d) => d.date === date);
    const dz = chart.getOption().dataZoom?.[0];
    if (idx < 0 || !dz) return;
    const [s, e] = windowShowing(idx, dz.startValue, dz.endValue, state.days.length);
    if (s !== dz.startValue) chart.dispatchAction({ type: 'dataZoom', startValue: s, endValue: e });
  }

  return { load, mark };
}
