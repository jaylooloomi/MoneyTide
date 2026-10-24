// ③ Money map: listed companies grouped by head-office county (縣市), coloured by turnover or by
// the cap-weighted change. Pure aggregation/option builders on top (node --test); DOM part below.

import { colorFor, escapeHtml, fmtPct, fmtTurnover, industryAverage } from './transform.js';

export const MAP_NAME = 'tw-counties';
export const OVERSEAS = '海外';
export const MAP_METRICS = { turnover: '顏色：成交值總和', change: '顏色：市值加權漲幅' };
const TOP_N = 3;

/**
 * stocks (live or history rows; duplicates from regrouping are fine) + {code: [county]} →
 * { rows: [{name, count, turnover_100m, change_pct, top}], overseas, unknown }.
 * Common stocks only; each code counted once.
 */
export function aggregateCounties(stocks, countyByCode) {
  const seen = new Set();
  const byCounty = new Map();
  let overseas = 0;
  let unknown = 0;
  for (const s of stocks) {
    if (s.kind !== 'stock' || seen.has(s.code)) continue;
    seen.add(s.code);
    const county = countyByCode?.[s.code]?.[0];
    if (!county) {
      unknown += 1;
      continue;
    }
    if (county === OVERSEAS) {
      overseas += 1;
      continue;
    }
    if (!byCounty.has(county)) byCounty.set(county, []);
    byCounty.get(county).push(s);
  }
  const rows = [...byCounty].map(([name, members]) => ({
    name,
    count: members.length,
    turnover_100m: members.reduce((a, s) => a + (s.turnover_100m || 0), 0),
    change_pct: industryAverage(members, 'change_pct'),
    top: [...members]
      .filter((s) => s.turnover_100m > 0)
      .sort((a, b) => b.turnover_100m - a.turnover_100m)
      .slice(0, TOP_N)
      .map((s) => ({ code: s.code, name: s.name, turnover_100m: s.turnover_100m, change_pct: s.change_pct })),
    members: members.map((s) => ({ code: s.code, name: s.name, industry: s.industry, turnover_100m: s.turnover_100m, change_pct: s.change_pct })),
  }));
  rows.sort((a, b) => b.turnover_100m - a.turnover_100m);
  return { rows, overseas, unknown };
}

export function countyTooltip(r) {
  if (!r) return '';
  const top = r.top
    .map((s) => `${escapeHtml(s.code)} ${escapeHtml(s.name)}　${fmtTurnover(s.turnover_100m)}　${fmtPct(s.change_pct)}`)
    .join('<br>');
  return (
    `<b>${escapeHtml(r.name)}</b>（${r.count} 家）<br>成交值　${fmtTurnover(r.turnover_100m)}<br>市值加權漲幅　${fmtPct(r.change_pct)}` +
    (top ? `<br><span style="opacity:.75">成交值前 ${r.top.length} 大</span><br>${top}` : '')
  );
}

/** Turnover share colour: log-ish ramp so 臺北市 does not wash out every other county. */
export function turnoverColor(value, max) {
  if (!(value > 0) || !(max > 0)) return '#2a2d35';
  const t = Math.sqrt(value / max);
  const from = [0x2a, 0x2d, 0x35];
  const to = [0xff, 0xb3, 0x00];
  return '#' + from.map((c, i) => Math.round(c + (to[i] - c) * t).toString(16).padStart(2, '0')).join('');
}

export function buildMapOption(rows, metric = 'turnover') {
  const max = Math.max(0, ...rows.map((r) => r.turnover_100m));
  const byName = new Map(rows.map((r) => [r.name, r]));
  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      backgroundColor: '#1d212a',
      borderColor: '#444a57',
      textStyle: { color: '#ddd', fontSize: 12 },
      formatter: (p) => countyTooltip(byName.get(p.name)) || `${escapeHtml(p.name)}（無上市櫃公司總部）`,
    },
    series: [
      {
        type: 'map',
        map: MAP_NAME,
        roam: true,
        // the outlying islands (Kinmen, Matsu) stretch the bounds: fit Taiwan and Penghu instead
        boundingCoords: [[119.35, 25.35], [122.05, 21.85]],
        labelLayout: { hideOverlap: true },
        label: {
          show: true,
          color: '#e6e6e6',
          fontSize: 10,
          formatter: (p) => {
            const r = byName.get(p.name);
            if (!r) return '';
            return metric === 'change' ? `${p.name}\n${fmtPct(r.change_pct)}` : `${p.name}\n${fmtTurnover(r.turnover_100m)}`;
          },
        },
        itemStyle: { borderColor: '#0f1115', borderWidth: 0.8, areaColor: '#2a2d35' },
        emphasis: { label: { color: '#fff' }, itemStyle: { areaColor: '#ffd400' } },
        select: { disabled: true },
        data: rows.map((r) => ({
          name: r.name,
          value: metric === 'change' ? r.change_pct : r.turnover_100m,
          itemStyle: { areaColor: metric === 'change' ? colorFor(r.change_pct, 3) : turnoverColor(r.turnover_100m, max) },
        })),
      },
    ],
  };
}

/** Ranking table beside the map, sorted by the chosen metric. */
export function countyListHtml(rows, metric = 'turnover') {
  const sorted = [...rows].sort((a, b) =>
    metric === 'change' ? (b.change_pct ?? -Infinity) - (a.change_pct ?? -Infinity) : b.turnover_100m - a.turnover_100m,
  );
  const total = rows.reduce((a, r) => a + r.turnover_100m, 0);
  const body = sorted
    .map(
      (r) => `<tr data-county="${escapeHtml(r.name)}" title="${escapeHtml(r.top.map((t) => `${t.code} ${t.name}`).join('、'))}">
        <td class="l">${escapeHtml(r.name)}</td><td class="muted">${r.count}</td>
        <td>${fmtTurnover(r.turnover_100m)}</td><td class="muted">${total > 0 ? ((r.turnover_100m / total) * 100).toFixed(1) + '%' : '—'}</td>
        <td class="c" style="background:${colorFor(r.change_pct, 3)}">${fmtPct(r.change_pct)}</td></tr>`,
    )
    .join('');
  return `<table class="grid"><thead><tr><th class="l">縣市</th><th>家數</th><th>成交值</th><th>占比</th><th>漲跌</th></tr></thead><tbody>${body}</tbody></table>`;
}

export const COMPANY_SORTS = { turnover_100m: '成交值', change_pct: '漲跌', code: '代號' };

/** One county's companies (the right-hand list drilled down): back button, then every company,
 *  sorted by `sort` (成交值 / 漲跌 high first, 代號 ascending); a row opens that stock's card. */
export function countyCompaniesHtml(row, sort = 'turnover_100m') {
  if (!row) return '';
  const key = sort in COMPANY_SORTS ? sort : 'turnover_100m';
  const list = [...(row.members || [])].sort((a, b) =>
    key === 'code' ? a.code.localeCompare(b.code) : (b[key] ?? -Infinity) - (a[key] ?? -Infinity),
  );
  const th = (k, label, cls = '') =>
    `<th class="${cls}${k === key ? ' sorted' : ''}" data-sort="${k}" style="cursor:pointer" title="依${label}排序">${label}${k === key ? ' ▾' : ''}</th>`;
  const body = list
    .map(
      (s) => `<tr data-code="${escapeHtml(s.code)}" style="cursor:pointer" title="${escapeHtml(s.industry || '')}　點一下看資訊卡">
        <td class="l">${escapeHtml(s.code)}</td><td class="l">${escapeHtml(s.name)}</td>
        <td class="c" style="background:${colorFor(s.change_pct, 7)}">${fmtPct(s.change_pct)}</td><td>${fmtTurnover(s.turnover_100m)}</td></tr>`,
    )
    .join('');
  return `<div class="cm-drill-h"><button type="button" class="icon wide" data-act="back">← 回縣市</button>
      <b>${escapeHtml(row.name)}</b> <span class="muted">${row.count} 家 · ${fmtTurnover(row.turnover_100m)} · ${fmtPct(row.change_pct)}</span></div>
    <table class="grid"><thead><tr>${th('code', '代號', 'l')}<th class="l">名稱</th>${th('change_pct', '漲跌')}${th('turnover_100m', '成交值')}</tr></thead><tbody>${body}</tbody></table>`;
}

// ---- DOM / ECharts ---------------------------------------------------------------------

let geoPromise = null;
let mappingPromise = null;

function loadGeo() {
  geoPromise ??= fetch('/geo/tw-counties.geo.json')
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
    .then((geo) => echarts.registerMap(MAP_NAME, geo))
    .catch((err) => {
      geoPromise = null; // retry on the next render
      throw err;
    });
  return geoPromise;
}

function loadMapping() {
  mappingPromise ??= fetch('/api/groupings/county', { cache: 'no-store' })
    .then(async (r) => (r.ok ? (await r.json()).mapping : Promise.reject(new Error(r.status === 404 ? '公司地址資料尚未載入完成' : `HTTP ${r.status}`))))
    .catch((err) => {
      mappingPromise = null;
      throw err;
    });
  return mappingPromise;
}

/**
 * A county map inside `el` with a metric <select> placed into `controls` and a note element.
 * render(stocks, caption) redraws; metric choice is kept in localStorage under `prefKey`.
 */
export function mountCountyMap(el, { controls, note, prefKey, onStock }) {
  // county: the county drilled into on the right (null = the county ranking); kept across redraws
  const state = { chart: null, stocks: [], caption: '', metric: 'turnover', retry: null, county: null, sort: 'turnover_100m', rows: [] };
  try {
    const saved = localStorage.getItem(prefKey);
    if (saved in MAP_METRICS) state.metric = saved;
  } catch {
    /* default */
  }
  const sel = document.createElement('select');
  sel.className = 'field';
  sel.innerHTML = Object.entries(MAP_METRICS).map(([k, label]) => `<option value="${k}">${label}</option>`).join('');
  sel.value = state.metric;
  sel.addEventListener('change', () => {
    state.metric = sel.value;
    try {
      localStorage.setItem(prefKey, state.metric);
    } catch {
      /* ignore */
    }
    draw();
  });
  controls.appendChild(sel);

  async function draw() {
    clearTimeout(state.retry);
    let mapping;
    try {
      await loadGeo();
      mapping = await loadMapping();
    } catch (err) {
      note.textContent = `地圖資料載入中：${err.message}（30 秒後重試）`;
      state.retry = setTimeout(draw, 30_000);
      return;
    }
    if (!state.chart) {
      // map on the left, a ranking list on the right (small northern counties overlap on the map)
      el.style.display = 'flex';
      el.innerHTML = '<div class="cm-map" style="flex:1;min-width:0"></div><div class="cm-list table-wrap" style="width:300px;overflow:auto"></div>';
      state.chart = echarts.init(el.querySelector('.cm-map'));
      new ResizeObserver(() => state.chart.resize()).observe(el.querySelector('.cm-map'));
      el.querySelector('.cm-list').addEventListener('mouseover', (e) => {
        const tr = e.target.closest('tr[data-county]');
        if (tr) state.chart.dispatchAction({ type: 'highlight', name: tr.dataset.county });
      });
      el.querySelector('.cm-list').addEventListener('mouseout', (e) => {
        const tr = e.target.closest('tr[data-county]');
        if (tr && tr.dataset.county !== state.county) state.chart.dispatchAction({ type: 'downplay', name: tr.dataset.county });
      });
      // 點縣市（地圖或右側清單）→ 右側換成那個縣市的公司；← 回縣市 回到排行
      state.chart.on('click', (p) => p.name && drill(p.name));
      el.querySelector('.cm-list').addEventListener('click', (e) => {
        if (e.target.closest('[data-act="back"]')) return drill(null);
        const th = e.target.closest('th[data-sort]');
        if (th) {
          state.sort = th.dataset.sort;
          return showList();
        }
        const company = e.target.closest('tr[data-code]');
        if (company) return onStock?.(company.dataset.code);
        const county = e.target.closest('tr[data-county]');
        if (county) drill(county.dataset.county);
      });
    }
    const { rows, overseas, unknown } = aggregateCounties(state.stocks, mapping);
    state.rows = rows;
    state.chart.setOption(buildMapOption(rows, state.metric), { notMerge: true });
    showList();
    const parts = [state.caption, `${rows.reduce((a, r) => a + r.count, 0)} 家依公司總部縣市`];
    if (overseas) parts.push(`總部在海外 ${overseas} 家未顯示`);
    if (unknown) parts.push(`地址無法判斷 ${unknown} 家未顯示`);
    note.textContent = parts.filter(Boolean).join('　·　');
  }

  function drill(name) {
    if (name && !state.rows.some((r) => r.name === name)) return; // a county without listed head offices
    if (state.county) state.chart?.dispatchAction({ type: 'downplay', name: state.county });
    state.county = name || null;
    showList(true);
  }

  function showList(top = false) {
    const list = el.querySelector('.cm-list');
    if (!list) return;
    const row = state.county && state.rows.find((r) => r.name === state.county);
    if (state.county && !row) state.county = null; // gone on this day: back to the ranking
    const keep = list.scrollTop; // a live poll redraws: do not jump back to the top
    list.innerHTML = row ? countyCompaniesHtml(row, state.sort) : countyListHtml(state.rows, state.metric);
    list.scrollTop = top ? 0 : keep;
    if (row) state.chart?.dispatchAction({ type: 'highlight', name: row.name });
  }

  return {
    render(stocks, caption = '') {
      state.stocks = stocks;
      state.caption = caption;
      if (el.offsetParent !== null) draw(); // hidden maps redraw when shown
    },
    show() {
      draw();
    },
  };
}
