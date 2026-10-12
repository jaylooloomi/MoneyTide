// Pure functions: snapshot + UI state → filtered stocks, industry aggregates, ECharts option.
// No DOM and no global `echarts` here, so everything is testable with `node --test`.

export const COLOR_LIMITS = { today: 7, week: 15 };
export const LABEL_MIN_WIDTH = 44;
export const LABEL_MIN_HEIGHT = 26;
export const ROOT_ID = '全市場';

const NEUTRAL = [0x3d, 0x3d, 0x46];
const UP = [0xe0, 0x26, 0x2c]; // 台股：紅漲
const DOWN = [0x1f, 0xa2, 0x4a]; // 綠跌
export const NO_DATA_COLOR = '#2e2e2e';
export const INDUSTRY_BG = '#1b1d22';
export const ROOT_BG = '#0f1115';

const hex = (rgb) => '#' + rgb.map((c) => Math.round(c).toString(16).padStart(2, '0')).join('');

/** Linear red/grey/green scale clamped at ±limit. null/NaN → NO_DATA_COLOR. */
export function colorFor(pct, limit) {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return NO_DATA_COLOR;
  const t = Math.min(Math.abs(pct) / limit, 1);
  const end = pct >= 0 ? UP : DOWN;
  return hex(NEUTRAL.map((c, i) => c + (end[i] - c) * t));
}

export const pctField = (colorBy) => (colorBy === 'week' ? 'week_pct' : 'change_pct');
export const colorLimit = (colorBy) => (colorBy === 'week' ? COLOR_LIMITS.week : COLOR_LIMITS.today);

// ---- formatting ----------------------------------------------------------

export function fmtPct(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  const r = Math.round(v * 100) / 100;
  if (r === 0) return '0.00%';
  return (r > 0 ? '+' : '') + r.toFixed(2) + '%';
}

export function fmtNum(v, digits) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return v.toLocaleString('zh-TW', {
    minimumFractionDigits: digits ?? 0,
    maximumFractionDigits: digits ?? 2,
  });
}

export function fmtPrice(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  return v.toLocaleString('zh-TW', { maximumFractionDigits: 2 });
}

export function fmtChange(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  if (v === 0) return '0';
  return (v > 0 ? '▲' : '▼') + Math.abs(v).toLocaleString('zh-TW', { maximumFractionDigits: 2 });
}

/** 元 → "28.1 兆" / "352.1 億" / "8,500 萬". */
export function fmtCap(yuan) {
  if (yuan === null || yuan === undefined || !Number.isFinite(yuan) || yuan <= 0) return '—';
  if (yuan >= 1e12) return (yuan / 1e12).toFixed(2) + ' 兆';
  if (yuan >= 1e8) return fmtNum(yuan / 1e8, 1) + ' 億';
  return fmtNum(yuan / 1e4, 0) + ' 萬';
}

export function fmtTurnover(hundredMillion) {
  if (hundredMillion === null || hundredMillion === undefined || !Number.isFinite(hundredMillion)) return '—';
  return fmtNum(hundredMillion, 2) + ' 億';
}

// ---- filtering & aggregation --------------------------------------------

/**
 * filters: { market: 'all'|'上市'|'上櫃', includeEtf: bool, watchOnly: bool }
 * - kind 'other' (特別股/TDR/ETN/REIT) is hidden unless it is in the watchlist and watchOnly is on;
 * - ETFs need includeEtf, except watchlisted ETFs in watchOnly mode (an explicit user choice).
 */
export function filterStocks(stocks, filters, watchCodes) {
  const watch = new Set(watchCodes || []);
  return stocks.filter((s) => {
    if (filters.market !== 'all' && s.market !== filters.market) return false;
    if (filters.watchOnly) return watch.has(s.code);
    if (s.kind === 'other') return false;
    if (s.kind === 'etf' && !filters.includeEtf) return false;
    return true;
  });
}

/** Weight = market cap at previous close, so the industry % equals its aggregate cap change. */
function capWeight(s) {
  if (!s.market_cap || s.market_cap <= 0) return 0;
  const ref = s.price ?? s.prev_close;
  if (!ref) return 0;
  return (s.market_cap / ref) * (s.prev_close ?? ref);
}

/**
 * Average of `field` over members with a non-null value: cap-weighted over the members that have
 * a market cap; equal-weighted only when no member has one. null when nothing qualifies.
 */
export function industryAverage(members, field) {
  const valued = members.filter((s) => s[field] !== null && s[field] !== undefined && Number.isFinite(s[field]));
  if (!valued.length) return null;
  const weighted = valued.map((s) => [s[field], capWeight(s)]).filter(([, w]) => w > 0);
  if (weighted.length) {
    const total = weighted.reduce((a, [, w]) => a + w, 0);
    return weighted.reduce((a, [v, w]) => a + v * w, 0) / total;
  }
  return valued.reduce((a, s) => a + s[field], 0) / valued.length;
}

export function aggregateIndustries(stocks) {
  const groups = new Map();
  for (const s of stocks) {
    if (!groups.has(s.industry)) groups.set(s.industry, []);
    groups.get(s.industry).push(s);
  }
  const totalTurnover = stocks.reduce((a, s) => a + (s.turnover_100m || 0), 0);
  const rows = [];
  for (const [name, members] of groups) {
    const up = members.filter((s) => s.change > 0).length;
    const down = members.filter((s) => s.change < 0).length;
    const turnover = members.reduce((a, s) => a + (s.turnover_100m || 0), 0);
    const amps = members.map((s) => s.amplitude_pct).filter((v) => v !== null && v !== undefined);
    rows.push({
      name,
      change_pct: industryAverage(members, 'change_pct'),
      week_pct: industryAverage(members, 'week_pct'),
      amplitude_pct: amps.length ? amps.reduce((a, v) => a + v, 0) / amps.length : null,
      turnover_100m: turnover,
      turnover_share: totalTurnover > 0 ? (turnover / totalTurnover) * 100 : null,
      up_count: up,
      down_count: down,
      flat_count: members.length - up - down,
      stock_count: members.length,
    });
  }
  return rows;
}

export const SORT_KEYS = {
  name: (r) => r.name,
  change_pct: (r) => r.change_pct,
  week_pct: (r) => r.week_pct,
  amplitude_pct: (r) => r.amplitude_pct,
  turnover_share: (r) => r.turnover_share,
  breadth: (r) => r.up_count - r.down_count,
  // watchlist columns
  code: (r) => r.code,
  price: (r) => r.price,
  turnover_100m: (r) => r.turnover_100m,
};

/** Stable sort; null values always last regardless of direction. */
export function sortRows(rows, key, dir) {
  const get = SORT_KEYS[key] || ((r) => r[key]);
  const sign = dir === 'asc' ? 1 : -1;
  return rows
    .map((r, i) => [r, i])
    .sort(([a, ia], [b, ib]) => {
      const va = get(a);
      const vb = get(b);
      const na = va === null || va === undefined;
      const nb = vb === null || vb === undefined;
      if (na || nb) return na === nb ? ia - ib : na ? 1 : -1;
      const c = typeof va === 'string' ? va.localeCompare(vb, 'zh-Hant') : va - vb;
      return c !== 0 ? c * sign : ia - ib;
    })
    .map(([r]) => r);
}

/** Watchlist rows in insertion order; codes missing from the snapshot get a placeholder row. */
export function watchRows(stocks, codes) {
  const byCode = new Map(stocks.map((s) => [s.code, s]));
  return (codes || []).map((code) => byCode.get(code) || { code, name: '—', missing: true });
}

// ---- treemap ----------------------------------------------------------------

const sizeOf = (s, sizeBy) => (sizeBy === 'turnover' ? s.turnover_100m : s.market_cap);

/**
 * view: { sizeBy: 'cap'|'turnover', colorBy: 'today'|'week' }
 * Returns fresh objects on every call (ECharts mutates its input data).
 */
export function buildTreemapData(stocks, view) {
  const field = pctField(view.colorBy);
  const limit = colorLimit(view.colorBy);
  const industries = new Map(aggregateIndustries(stocks).map((r) => [r.name, r]));
  const groups = new Map();
  let hiddenNoSize = 0;
  let hiddenEtf = 0;
  for (const s of stocks) {
    const size = sizeOf(s, view.sizeBy);
    if (!(size > 0)) {
      if (view.sizeBy === 'cap' && s.kind === 'etf') hiddenEtf += 1;
      else hiddenNoSize += 1;
      continue;
    }
    if (!groups.has(s.industry)) groups.set(s.industry, []);
    groups.get(s.industry).push({
      id: 'stk:' + s.code,
      name: s.name,
      value: size,
      code: s.code,
      pct: s[field],
      stock: { ...s },
      itemStyle: { color: colorFor(s[field], limit) },
    });
  }
  const data = [];
  for (const [name, children] of groups) {
    data.push({
      id: 'ind:' + name,
      name,
      industry: { ...industries.get(name) },
      pct: industries.get(name)?.[field] ?? null,
      children,
      itemStyle: { color: INDUSTRY_BG },
    });
  }
  return { data, hiddenNoSize, hiddenEtf };
}

function leafTooltip(s) {
  const rows = [
    ['價格', fmtPrice(s.price)],
    ['漲跌', `${fmtChange(s.change)}（${fmtPct(s.change_pct)}）`],
    ['本週', fmtPct(s.week_pct)],
    ['成交值', fmtTurnover(s.turnover_100m)],
    ['市值', fmtCap(s.market_cap)],
  ];
  return (
    `<b>${escapeHtml(s.code)} ${escapeHtml(s.name)}</b> <span style="opacity:.7">${escapeHtml(s.industry)}</span><br>` +
    rows.map(([k, v]) => `${k}　${v}`).join('<br>')
  );
}

function industryTooltip(r) {
  return (
    `<b>${escapeHtml(r.name)}</b>（${r.stock_count} 檔）<br>` +
    `今日　${fmtPct(r.change_pct)}<br>本週　${fmtPct(r.week_pct)}<br>` +
    `漲 ${r.up_count} / 跌 ${r.down_count} / 平 ${r.flat_count}`
  );
}

export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

/** Formatters run for root, industry and stock nodes: always branch on the node type. */
export function tooltipFormatter(params) {
  const d = params.data || {};
  if (d.stock) return leafTooltip(d.stock);
  if (d.industry) return industryTooltip(d.industry);
  return '';
}

export function leafLabelFormatter(params) {
  const d = params.data || {};
  return d.stock ? `${d.name}\n${fmtPct(d.pct)}` : '';
}

export function upperLabelFormatter(params) {
  const d = params.data || {};
  return d.industry ? `${d.name} ${fmtPct(d.pct)}` : params.name;
}

export function labelLayout(params) {
  const r = params.rect;
  return r && (r.width < LABEL_MIN_WIDTH || r.height < LABEL_MIN_HEIGHT) ? { fontSize: 0 } : {};
}

export function buildTreemapOption(treeData) {
  return {
    animation: false,
    tooltip: { confine: true, formatter: tooltipFormatter, backgroundColor: '#1d212a', borderColor: '#444a57', textStyle: { color: '#ddd', fontSize: 12 } },
    series: [
      {
        type: 'treemap',
        id: 'map',
        name: ROOT_ID,
        roam: false,
        nodeClick: false,
        leafDepth: null,
        visibleMin: 10,
        breadcrumb: { show: false },
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        label: { show: true, formatter: leafLabelFormatter, color: '#fff', fontSize: 12, lineHeight: 15, overflow: 'truncate' },
        labelLayout,
        upperLabel: { show: true, height: 20, formatter: upperLabelFormatter, color: '#eee', fontSize: 12, overflow: 'truncate' },
        emphasis: { upperLabel: { show: true } },
        levels: [
          { itemStyle: { color: ROOT_BG, borderColor: ROOT_BG, borderWidth: 0, gapWidth: 2 }, upperLabel: { show: false } },
          {
            itemStyle: { color: INDUSTRY_BG, borderColor: INDUSTRY_BG, borderWidth: 2, gapWidth: 1 },
            upperLabel: { show: true },
            emphasis: { itemStyle: { borderColor: '#ffd400' }, upperLabel: { color: '#ffd400' } },
          },
          { itemStyle: { borderWidth: 0 } },
        ],
        data: treeData.data,
      },
    ],
  };
}
