// 關鍵字圖: the current grouping's group names laid out inside the outline of Taiwan, sized by
// turnover (or move) and coloured by the cap-weighted change; groups also hot in the news glow.
// Pure builders on top (node --test); the ECharts / DOM part below.

import { aggregateIndustries, escapeHtml, fmtPct, fmtTurnover } from './transform.js';

export const WORD_METRICS = { turnover: '字大小：成交值', move: '字大小：漲跌幅' };
const MAX_WORDS = 120;
const GLOW = '#ffb347';
const REDRAW_MS = 60_000; // a re-layout shuffles every word: live refreshes redraw at most this often

/** "半導體／IC設計／電源管理IC" → "電源管理IC", "半導體業" → "半導體"; the full name stays the key. */
export function shortLabel(name) {
  const last = String(name).split('／').pop();
  return last.length > 2 && last.endsWith('業') ? last.slice(0, -1) : last;
}

/**
 * Stocks already grouped (industry := group name) → words for the cloud, biggest first:
 * [{name: label, full, value, turnover_100m, change_pct, count, hot}]. A label shared by two
 * groups falls back to the full name so every word stays unique.
 */
export function groupWords(stocks, { metric = 'turnover', hot = new Set() } = {}) {
  const rows = aggregateIndustries(stocks.filter((s) => s.kind === 'stock' && s.industry)).filter((r) => r.turnover_100m > 0);
  const weight = (r) => (metric === 'move' ? Math.abs(r.change_pct ?? 0) : r.turnover_100m);
  rows.sort((a, b) => weight(b) - weight(a));
  const top = rows.slice(0, MAX_WORDS);
  const seen = new Map();
  for (const r of top) seen.set(shortLabel(r.name), (seen.get(shortLabel(r.name)) || 0) + 1);
  return top.map((r) => {
    const label = seen.get(shortLabel(r.name)) > 1 ? r.name : shortLabel(r.name);
    return {
      name: label,
      full: r.name,
      // sqrt keeps one or two giant groups from shrinking every other word to the minimum
      value: Math.sqrt(weight(r)),
      turnover_100m: r.turnover_100m,
      change_pct: r.change_pct,
      count: r.stock_count,
      hot: hot.has(r.name) || hot.has(label),
    };
  });
}

/** Grey for flat, deepening to red (up) / green (down) by ±4%. */
export function wordColor(pct) {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return '#9a9aa6';
  const t = Math.min(0.25 + Math.abs(pct) / 5, 1);
  const from = [0x9a, 0x9a, 0xa6];
  const to = pct >= 0 ? [0xff, 0x4d, 0x4f] : [0x2e, 0xcc, 0x71];
  return '#' + from.map((c, i) => Math.round(c + (to[i] - c) * t).toString(16).padStart(2, '0')).join('');
}

export function wordTooltip(w) {
  if (!w) return '';
  return `<b>${escapeHtml(w.full)}</b>（${w.count} 家）<br>成交值　${fmtTurnover(w.turnover_100m)}<br>市值加權漲幅　${fmtPct(w.change_pct)}${
    w.hot ? '<br><span style="color:' + GLOW + '">新聞熱門族群</span>' : ''
  }<br><span style="opacity:.7">點一下放大到這個族群</span>`;
}

/** Series box in px that keeps the island's aspect (the mask is stretched to the box). */
export function fitBox(width, height, aspect) {
  let h = height * 0.96;
  let w = h * aspect;
  if (w > width * 0.96) {
    w = width * 0.96;
    h = w / aspect;
  }
  return { width: Math.floor(w), height: Math.floor(h) };
}

export function buildWordOption(words, box) {
  return {
    backgroundColor: 'transparent',
    tooltip: {
      backgroundColor: '#1d212a',
      borderColor: '#444a57',
      textStyle: { color: '#ddd', fontSize: 12 },
      formatter: (p) => wordTooltip(p.data),
    },
    series: [
      {
        type: 'wordCloud',
        left: 'center',
        top: 'center',
        width: box.width,
        height: box.height,
        sizeRange: [12, Math.max(28, Math.round(box.height / 9))],
        rotationRange: [0, 0],
        gridSize: 3,
        drawOutOfBound: false,
        layoutAnimation: false,
        textStyle: { fontWeight: 'bold', fontFamily: 'Microsoft JhengHei, PingFang TC, sans-serif' },
        emphasis: { textStyle: { textShadowColor: '#fff8', textShadowBlur: 8 } },
        data: words.map((w) => ({
          ...w,
          textStyle: { color: w.hot ? GLOW : wordColor(w.change_pct), textShadowColor: w.hot ? '#ff7a00' : 'transparent', textShadowBlur: w.hot ? 12 : 0 },
        })),
      },
    ],
  };
}

// ---- DOM / ECharts ---------------------------------------------------------------------

const PLUGIN_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/echarts-wordcloud/2.1.0/echarts-wordcloud.min.js';
const PLUGIN_SRI = 'sha512-1G9nOyHfWSx/z86MwODfigLvd2pT3dK40hNX9OfEKGtlSRFnOd+u2WFWLkAS0xDusSck/34g6E3vrbFhZL/g8g==';
// main island + Penghu (Kinmen / Matsu would stretch the outline)
const BOUNDS = { lon0: 119.3, lon1: 122.1, lat0: 21.85, lat1: 25.35 };
const MASK_H = 700;

let pluginPromise = null;
let maskPromise = null;

function loadPlugin() {
  pluginPromise ??= new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = PLUGIN_SRC;
    el.integrity = PLUGIN_SRI;
    el.crossOrigin = 'anonymous';
    el.referrerPolicy = 'no-referrer';
    el.onload = resolve;
    el.onerror = () => {
      pluginPromise = null;
      el.remove();
      reject(new Error('字雲元件載入失敗'));
    };
    document.head.appendChild(el);
  });
  return pluginPromise;
}

/** Black island on white, drawn from the county GeoJSON; resolves to {canvas, aspect}. */
function loadMask() {
  maskPromise ??= fetch('/geo/tw-counties.geo.json')
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
    .then((geo) => {
      const { lon0, lon1, lat0, lat1 } = BOUNDS;
      // equirectangular with cos(lat) so the island is not squashed
      const kx = Math.cos((((lat0 + lat1) / 2) * Math.PI) / 180);
      const aspect = ((lon1 - lon0) * kx) / (lat1 - lat0);
      const H = MASK_H;
      const W = Math.round(H * aspect);
      const c = document.createElement('canvas');
      c.width = W;
      c.height = H;
      const g = c.getContext('2d');
      g.fillStyle = '#fff';
      g.fillRect(0, 0, W, H);
      g.fillStyle = '#000';
      const sx = (x) => ((x - lon0) / (lon1 - lon0)) * W;
      const sy = (y) => ((lat1 - y) / (lat1 - lat0)) * H;
      for (const f of geo.features) {
        const polys = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
        for (const p of polys) {
          const ring = p[0];
          if (ring[0][0] < lon0 || ring[0][0] > lon1 || ring[0][1] > lat1) continue;
          g.beginPath();
          ring.forEach(([x, y], k) => (k ? g.lineTo(sx(x), sy(y)) : g.moveTo(sx(x), sy(y))));
          g.fill();
        }
      }
      return { canvas: c, aspect };
    })
    .catch((err) => {
      maskPromise = null;
      throw err;
    });
  return maskPromise;
}

/** Theme names + aliases from J's news groups, for the glow; refreshed every 10 minutes. */
const hotCache = new Map();
async function hotGroups(date) {
  const key = date || 'live';
  const hit = hotCache.get(key);
  if (hit && Date.now() - hit.at < 600_000) return hit.set;
  try {
    const r = await fetch(`/api/news-themes${date ? `?date=${encodeURIComponent(date)}` : ''}`, { cache: 'no-store' });
    const themes = r.ok ? (await r.json()).themes || [] : [];
    const set = new Set(themes.flatMap((t) => [t.name, ...(t.aliases || [])]));
    hotCache.set(key, { at: Date.now(), set });
    return set;
  } catch {
    return hit?.set || new Set();
  }
}

/**
 * A word cloud inside `el` with a size-metric <select> placed into `controls` and a note element.
 * render(stocks, {caption, date, force}) redraws (stocks grouped: industry := group name);
 * onGroup(fullName) runs when a word is clicked.
 */
export function mountWordCloud(el, { controls, note, prefKey, onGroup }) {
  const state = { chart: null, stocks: [], caption: '', date: null, metric: 'turnover', sig: '', at: 0, ticket: 0, timer: null, force: false };
  try {
    const saved = localStorage.getItem(prefKey);
    if (saved in WORD_METRICS) state.metric = saved;
  } catch {
    /* default */
  }
  const sel = document.createElement('select');
  sel.className = 'field';
  sel.innerHTML = Object.entries(WORD_METRICS).map(([k, label]) => `<option value="${k}">${label}</option>`).join('');
  sel.value = state.metric;
  sel.addEventListener('change', () => {
    state.metric = sel.value;
    try {
      localStorage.setItem(prefKey, state.metric);
    } catch {
      /* ignore */
    }
    draw(true);
  });
  controls.appendChild(sel);

  // the layout runs in the background: overlapping runs paint over each other, so coalesce calls
  function draw(force = false) {
    state.force ||= force;
    clearTimeout(state.timer);
    state.timer = setTimeout(() => {
      const f = state.force;
      state.force = false;
      layout(f);
    }, 120);
  }

  async function layout(force) {
    if (el.offsetParent === null) return; // hidden: redraw when shown
    const t = ++state.ticket;
    let mask;
    try {
      await loadPlugin();
      mask = await loadMask();
    } catch (err) {
      note.textContent = `關鍵字圖載入失敗：${err.message}`;
      return;
    }
    const hot = await hotGroups(state.date);
    if (t !== state.ticket) return;
    const words = groupWords(state.stocks, { metric: state.metric, hot });
    const sig = `${state.metric}|${words.map((w) => w.full).join(',')}`;
    // the same groups again (a live refresh): keep the layout still unless a minute has passed
    if (!force && sig === state.sig && Date.now() - state.at < REDRAW_MS) return;
    if (!state.chart) {
      state.chart = echarts.init(el);
      state.chart.on('click', (p) => p.data?.full && onGroup?.(p.data.full));
      let last = '';
      new ResizeObserver(() => {
        const size = `${el.clientWidth}x${el.clientHeight}`;
        if (size === last) return;
        last = size;
        state.chart.resize();
        draw(true);
      }).observe(el);
    }
    state.sig = sig;
    state.at = Date.now();
    const box = fitBox(el.clientWidth, el.clientHeight, mask.aspect);
    const option = buildWordOption(words, box);
    option.series[0].maskImage = mask.canvas;
    state.chart.clear();
    state.chart.setOption(option, { notMerge: true });
    const hotCount = words.filter((w) => w.hot).length;
    note.textContent = [
      state.caption,
      `${words.length} 個族群`,
      '紅漲綠跌',
      hotCount ? `橘色發光＝新聞熱門族群（${hotCount}）` : '',
      '放不下的小族群不顯示',
    ]
      .filter(Boolean)
      .join('　·　');
  }

  return {
    render(stocks, { caption = '', date = null, force = false } = {}) {
      const changed = date !== state.date;
      state.stocks = stocks;
      state.caption = caption;
      state.date = date;
      draw(force || changed);
    },
    show() {
      draw(true);
    },
  };
}
