// History view: A (day heatmap), B (group ranking), C (rotation matrix), D (movers).
import {
  ROOT_ID,
  breadthColor,
  buildTreemapData,
  buildTreemapOption,
  colorFor,
  escapeHtml,
  fmtCap,
  fmtChange,
  fmtNum,
  fmtPct,
  fmtPrice,
  fmtTurnover,
  sortRows,
} from './transform.js';
import { getGroups, loadGroups, onGroupsChange, openGroupPanel, setStockNames } from './groups.js';

const PREFS_KEY = 'openmarket.history.v1';
const $ = (sel) => document.querySelector(sel);

const st = {
  days: [], // ok dates, newest first
  date: null,
  threshold: 5,
  sizeBy: 'cap',
  rotDays: 20,
  rotMetric: 'strong_ratio',
  moverMode: 'day',
  moverValue: { day: 5, range: 15, streak: 3 },
  from: null,
  groupSort: { key: 'strong_ratio', dir: 'desc' },
  grouping: 'industry', // industry | custom | concept
  zoom: null,
  // data
  stocks: [],
  groups: [],
  backfill: null,
};

let chart = null;
let started = false;
let daysTimer = null;

function loadPrefs() {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
    for (const k of ['threshold', 'sizeBy', 'rotDays', 'rotMetric', 'moverMode', 'groupSort', 'grouping']) if (p[k] !== undefined) st[k] = p[k];
    if (p.moverValue) Object.assign(st.moverValue, p.moverValue);
  } catch {
    /* defaults */
  }
}

function savePrefs() {
  try {
    const { threshold, sizeBy, rotDays, rotMetric, moverMode, moverValue, groupSort, grouping } = st;
    localStorage.setItem(PREFS_KEY, JSON.stringify({ threshold, sizeBy, rotDays, rotMetric, moverMode, moverValue, groupSort, grouping }));
  } catch {
    /* ignore */
  }
}

async function getJson(url) {
  const resp = await fetch(url, { cache: 'no-store' });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// ---- days & status ----------------------------------------------------------

async function loadDays() {
  try {
    const data = await getJson('/api/history/days');
    const before = st.days.length;
    st.days = data.days.filter((d) => d.status === 'ok').map((d) => d.date);
    st.backfill = data.backfill;
    if (before && st.days.length !== before) loadRotation();
  } catch (err) {
    st.backfill = { error: err.message };
  }
  renderStatus();
  if (!st.date && st.days.length) await selectDate(st.days[0]);
  else if (!st.days.length) showEmpty();
  // keep polling while the backfill is running (new days appear)
  clearTimeout(daysTimer);
  if (!st.days.length || st.backfill?.running) daysTimer = setTimeout(loadDays, 15000);
}

function renderStatus() {
  const b = st.backfill || {};
  const el = $('#hStatus');
  let cls = 'ok';
  let text = `${st.days.length} 個交易日`;
  if (b.running) {
    cls = 'loading';
    text = `回補中 ${b.done}/${b.total}（已有 ${st.days.length} 天）`;
  } else if (!st.days.length) {
    cls = 'loading';
    text = '等待第一次回補（需先載入產業分類）…';
  }
  if (b.error) {
    if (cls === 'ok') cls = 'stale';
    el.title = `最近錯誤：${b.error}`;
  } else el.title = '';
  el.className = `status ${cls}`;
  $('#hStatusText').textContent = text;
  if (st.days.length) {
    $('#hDate').min = st.days[st.days.length - 1];
    $('#hDate').max = st.days[0];
  }
}

function showEmpty() {
  $('#hEmpty').hidden = false;
  $('#hEmpty').textContent = '尚無歷史資料。首次啟動會在背景回補近一年（約 25 分鐘），完成的日子會陸續出現。';
}

/** Snap to the nearest trading day on or before `date`. */
function snap(date) {
  return st.days.find((d) => d <= date) || st.days[st.days.length - 1];
}

async function selectDate(date) {
  if (!st.days.length) return;
  st.date = snap(date);
  $('#hDate').value = st.date;
  const i = st.days.indexOf(st.date);
  $('#hPrev').disabled = i >= st.days.length - 1;
  $('#hNext').disabled = i <= 0;
  if (!st.from || st.from >= st.date) st.from = st.days[Math.min(i + 4, st.days.length - 1)];
  $('#hFrom').value = st.from;
  $('#hBDate').textContent = st.date;
  await Promise.all([loadDay(), loadGroups_(), loadMovers()]);
  renderRotationSelection();
}

// ---- A: day heatmap ---------------------------------------------------------

async function loadDay() {
  try {
    const data = await getJson(`/api/history/day/${st.date}?grouping=${st.grouping}`);
    st.stocks = data.stocks.filter((s) => s.kind === 'stock');
    if (st.grouping === 'industry') setStockNames(st.stocks);
  } catch {
    st.stocks = [];
  }
  renderChart();
}

function renderChart() {
  if (!chart) return;
  const tree = buildTreemapData(st.stocks, { sizeBy: st.sizeBy, colorBy: 'today' });
  chart.setOption(buildTreemapOption(tree), { notMerge: true });
  $('#hEmpty').hidden = tree.data.length > 0;
  if (!tree.data.length) {
    $('#hEmpty').textContent = customEmpty()
      ? '還沒有自訂族群（或族群內沒有股票）。按上方「管理族群」建立。'
      : '這一天沒有資料。';
  }
  if (st.zoom && tree.data.some((d) => d.name === st.zoom)) {
    chart.dispatchAction({ type: 'treemapRootToNode', seriesId: 'map', targetNodeId: 'ind:' + st.zoom });
  } else st.zoom = null;
  renderCrumb();
}

function zoomTo(name) {
  st.zoom = name;
  chart.dispatchAction({ type: 'treemapRootToNode', seriesId: 'map', targetNodeId: 'ind:' + name });
  renderCrumb();
}

function zoomOut() {
  st.zoom = null;
  chart.dispatchAction({ type: 'treemapRootToNode', seriesId: 'map', targetNodeId: ROOT_ID });
  renderCrumb();
}

function renderCrumb() {
  const el = $('#hCrumb');
  if (st.zoom) {
    el.innerHTML = `<button type="button" id="hCrumbRoot">全市場</button> › <b>${escapeHtml(st.zoom)}</b>`;
    $('#hCrumbRoot').addEventListener('click', zoomOut);
  } else el.innerHTML = '<span class="muted">點產業標題放大</span>';
}

// ---- B: group ranking -------------------------------------------------------

async function loadGroups_() {
  try {
    const data = await getJson(`/api/history/groups?date=${st.date}&threshold=${st.threshold}&grouping=${st.grouping}`);
    st.groups = data.groups;
  } catch {
    st.groups = [];
  }
  renderGroups();
}

function renderGroups() {
  $('#hStrongTh').textContent = `≥${st.threshold}%佔比`;
  const table = $('#hGroups');
  for (const th of table.querySelectorAll('th[data-sort]')) {
    if (th.dataset.sort === st.groupSort.key) th.setAttribute('aria-sort', st.groupSort.dir === 'asc' ? 'ascending' : 'descending');
    else th.removeAttribute('aria-sort');
  }
  const pct = (v, limit) => `<td class="c" style="background:${colorFor(v, limit)}">${fmtPct(v)}</td>`;
  table.tBodies[0].innerHTML = sortRows(st.groups, st.groupSort.key, st.groupSort.dir)
    .map(
      (g) => `<tr data-group="${escapeHtml(g.name)}"${g.name === st.zoom ? ' class="hl"' : ''}>
        <td class="l">${escapeHtml(g.name)}</td>
        ${pct(g.avg_pct, 3)}
        ${pct(g.cap_pct, 3)}
        <td class="c" style="background:${colorFor(g.strong_ratio, 30)}">${g.strong_ratio === null ? '—' : g.strong_ratio.toFixed(0) + '%'}<small class="muted"> ${g.strong_count}</small></td>
        <td>${g.limit_up || ''}</td>
        <td class="c" style="background:${breadthColor(g.up, g.down)}">${g.up}/${g.down}</td>
        <td class="muted">${g.count}</td>
      </tr>`,
    )
    .join('');
}

// ---- C: rotation ------------------------------------------------------------

function rotationColor(metric, v) {
  if (v === null || v === undefined) return colorFor(null, 1);
  if (metric === 'strong_ratio') return colorFor(v, 30);
  if (metric === 'breadth') return colorFor(v - 50, 50);
  if (metric === 'limit_up') return colorFor(v, 5);
  return colorFor(v, 3); // avg_pct: industry averages rarely exceed ±3%
}

function rotationText(metric, v) {
  if (v === null || v === undefined) return '';
  if (metric === 'limit_up') return v ? String(v) : '';
  if (metric === 'avg_pct') return v.toFixed(1);
  return v.toFixed(0);
}

async function loadRotation() {
  const table = $('#hRotation');
  let data;
  try {
    data = await getJson(`/api/history/rotation?days=${st.rotDays}&metric=${st.rotMetric}&threshold=${st.threshold}&grouping=${st.grouping}`);
  } catch {
    table.innerHTML = '';
    return;
  }
  const head = data.dates.map((d) => `<th data-date="${d}" title="${d}">${d.slice(5).replace('-', '/')}</th>`).join('');
  const rows = data.groups
    .map(
      (g) =>
        `<tr><td class="name">${escapeHtml(g.name)}</td>` +
        g.values
          .map(
            (v, i) =>
              `<td data-date="${data.dates[i]}" style="background:${rotationColor(data.metric, v)}" title="${escapeHtml(g.name)} ${data.dates[i]}：${v === null ? '—' : v.toFixed(2)}">${rotationText(data.metric, v)}</td>`,
          )
          .join('') +
        '</tr>',
    )
    .join('');
  table.innerHTML = `<thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody>`;
  renderRotationSelection();
  const wrap = table.parentElement;
  wrap.scrollLeft = wrap.scrollWidth; // newest on the right
}

function renderRotationSelection() {
  for (const el of document.querySelectorAll('#hRotation [data-date]')) el.classList.toggle('sel', el.dataset.date === st.date);
}

// ---- D: movers ----------------------------------------------------------------

async function loadMovers() {
  const mode = st.moverMode;
  const value = st.moverValue[mode];
  $('#hFromWrap').hidden = mode !== 'range';
  $('#hMoverUnit').textContent = mode === 'streak' ? '天' : '%';
  $('#hMoverValue').value = value;
  let url = `/api/history/movers?to=${st.date}&mode=${mode}&value=${value}&grouping=${st.grouping}`;
  if (mode === 'range') url += `&from=${st.from}`;
  let data;
  try {
    data = await getJson(url);
  } catch {
    $('#hMovers').innerHTML = '<p class="hint">無法載入。</p>';
    return;
  }
  const total = data.groups.reduce((a, g) => a + g.stocks.length, 0);
  $('#hMoverSummary').textContent = `${total} 檔，${data.groups.length} 個族群`;
  const unit = mode === 'streak' ? '天' : '%';
  $('#hMovers').innerHTML = data.groups.length
    ? data.groups
        .map(
          (g) => `<div class="mgroup"><b>${escapeHtml(g.name)}</b><span class="count">${g.stocks.length} 檔</span>
          <div class="tags">${g.stocks
            .map((s) => {
              const shown = mode === 'streak' ? `${s.value} 天` : `${s.value >= 0 ? '+' : ''}${s.value.toFixed(1)}%`;
              return `<a class="tag" data-code="${escapeHtml(s.code)}" href="https://histock.tw/stock/${encodeURIComponent(s.code)}" target="_blank" rel="noopener noreferrer"
                 style="background:${colorFor(s.change_pct, 7)}" title="${escapeHtml(s.code)} 當日 ${fmtPct(s.change_pct)}">${escapeHtml(s.name)}<small>${shown}</small></a>`;
            })
            .join('')}</div></div>`,
        )
        .join('')
    : `<p class="hint">沒有符合條件的股票（≥ ${value}${unit}）。</p>`;
}

// ---- controls -------------------------------------------------------------------

function renderSegs() {
  for (const seg of document.querySelectorAll('#historyView .seg[data-hgroup]')) {
    const current = String(st[seg.dataset.hgroup]);
    for (const b of seg.querySelectorAll('button')) {
      b.classList.toggle('on', b.dataset.value === current);
      b.setAttribute('aria-pressed', String(b.dataset.value === current));
    }
  }
}

function renderGrouping() {
  for (const b of $('#hGrouping').querySelectorAll('button')) {
    b.classList.toggle('on', b.dataset.value === st.grouping);
    b.setAttribute('aria-pressed', String(b.dataset.value === st.grouping));
  }
}

let conceptTimer = null;
async function refreshConceptStatus() {
  let status;
  try {
    status = await getJson('/api/concepts/status');
  } catch {
    return;
  }
  const btn = $('#hGrouping [data-value=concept]');
  btn.disabled = !status.ready;
  btn.title = status.ready
    ? `Yahoo 股市概念股分類：${status.count} 個族群（更新於 ${status.saved_at?.slice(0, 10)}）`
    : status.running
      ? `概念股分類下載中 ${status.done}/${status.total}…`
      : `概念股分類尚未載入${status.error ? '：' + status.error : ''}`;
  clearTimeout(conceptTimer);
  if (!status.ready) {
    conceptTimer = setTimeout(refreshConceptStatus, 10000);
    if (st.grouping === 'concept') {
      st.grouping = 'industry';
      if (st.date) reloadGrouped();
      else renderGrouping();
    }
  }
}

function customEmpty() {
  return st.grouping === 'custom' && !getGroups().some((g) => g.codes.length);
}

/** Reload everything that depends on the grouping. */
async function reloadGrouped() {
  renderGrouping();
  if (customEmpty()) {
    $('#hEmpty').hidden = false;
    $('#hEmpty').textContent = '還沒有自訂族群（或族群內沒有股票）。按上方「管理族群」建立。';
  }
  if (!st.date) return;
  await Promise.all([loadDay(), loadGroups_(), loadMovers()]);
  loadRotation();
}

function bind() {
  $('#hGrouping').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (!b || b.disabled || b.dataset.value === st.grouping) return;
    st.grouping = b.dataset.value;
    st.zoom = null;
    savePrefs();
    reloadGrouped();
  });
  $('#hManageGroups').addEventListener('click', () => openGroupPanel());
  onGroupsChange(() => {
    if (st.grouping === 'custom') reloadGrouped();
  });
  $('#hPrev').addEventListener('click', () => {
    const i = st.days.indexOf(st.date);
    if (i < st.days.length - 1) selectDate(st.days[i + 1]);
  });
  $('#hNext').addEventListener('click', () => {
    const i = st.days.indexOf(st.date);
    if (i > 0) selectDate(st.days[i - 1]);
  });
  $('#hDate').addEventListener('change', (e) => e.target.value && selectDate(e.target.value));
  $('#hThreshold').addEventListener('change', (e) => {
    const v = Number(e.target.value);
    if (!(v >= 1 && v <= 10)) {
      e.target.value = st.threshold;
      return;
    }
    st.threshold = v;
    savePrefs();
    loadGroups_();
    loadRotation();
  });
  for (const seg of document.querySelectorAll('#historyView .seg[data-hgroup]')) {
    seg.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      const key = seg.dataset.hgroup;
      st[key] = key === 'rotDays' ? Number(b.dataset.value) : b.dataset.value;
      savePrefs();
      renderSegs();
      if (key === 'sizeBy') renderChart();
      else if (key === 'moverMode') loadMovers();
      else loadRotation();
    });
  }
  $('#hMoverValue').addEventListener('change', (e) => {
    const v = Number(e.target.value);
    if (!(v > 0)) {
      e.target.value = st.moverValue[st.moverMode];
      return;
    }
    st.moverValue[st.moverMode] = v;
    savePrefs();
    loadMovers();
  });
  $('#hFrom').addEventListener('change', (e) => {
    if (!e.target.value) return;
    st.from = e.target.value;
    loadMovers();
  });
  $('#hGroups').tHead.addEventListener('click', (e) => {
    const th = e.target.closest('th[data-sort]');
    if (!th) return;
    const key = th.dataset.sort;
    if (st.groupSort.key === key) st.groupSort.dir = st.groupSort.dir === 'asc' ? 'desc' : 'asc';
    else st.groupSort = { key, dir: key === 'name' ? 'asc' : 'desc' };
    savePrefs();
    renderGroups();
  });
  $('#hGroups').tBodies[0].addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-group]');
    if (!tr) return;
    zoomTo(tr.dataset.group);
    renderGroups();
  });
  $('#hRotation').addEventListener('click', (e) => {
    const cell = e.target.closest('[data-date]');
    if (cell) selectDate(cell.dataset.date);
  });
  document.addEventListener('keydown', (e) => {
    if ($('#historyView').hidden || e.target.matches('input')) return;
    if (e.key === 'ArrowLeft') $('#hPrev').click();
    else if (e.key === 'ArrowRight') $('#hNext').click();
    else if (e.key === 'Escape' && st.zoom) zoomOut();
  });
}

/** Called whenever the history view becomes visible. */
export async function showHistory() {
  if (!started) {
    started = true;
    loadPrefs();
    $('#hThreshold').value = st.threshold;
    await refreshConceptStatus();
    renderGrouping();
    loadGroups().catch(() => {});
    chart = echarts.init($('#hChart'));
    chart.on('click', (p) => {
      if (p.data?.stock) openHistCard(p.data.code);
      else if (p.data?.industry) zoomTo(p.data.name);
    });
    $('#hMovers').addEventListener('click', (e) => {
      const tag = e.target.closest('a.tag[data-code]');
      if (!tag || e.ctrlKey || e.metaKey) return; // ctrl/cmd-click still opens HiStock
      e.preventDefault();
      openHistCard(tag.dataset.code);
    });
    new ResizeObserver(() => chart.resize()).observe($('#hChart'));
    bind();
    renderSegs();
    renderCrumb();
    await loadDays();
    await loadRotation();
    return;
  }
  chart.resize();
  await loadDays();
  loadRotation();
}

// ---- bonus-02: stock card with a short price history ----------------------------

const CARD_DAYS = 20;
let cardChart = null;
let cardCode = null;

function cardEl() {
  let el = $('#hCard');
  if (!el) {
    el = document.createElement('aside');
    el.id = 'hCard';
    el.className = 'card';
    el.hidden = true;
    $('#historyView .hA .chart-wrap').appendChild(el);
  }
  return el;
}

function closeHistCard() {
  cardCode = null;
  cardEl().hidden = true;
  if (cardChart) {
    cardChart.dispose();
    cardChart = null;
  }
}

async function openHistCard(code) {
  cardCode = code;
  let d;
  try {
    d = await getJson(`/api/history/stock/${encodeURIComponent(code)}?to=${st.date}&days=${CARD_DAYS}`);
  } catch {
    return;
  }
  if (cardCode !== code) return; // a newer click won
  const el = cardEl();
  const dir = d.change > 0 ? 'up' : d.change < 0 ? 'down' : '';
  el.innerHTML = `
    <h3>${escapeHtml(d.code)} ${escapeHtml(d.name)} <span class="sub">${escapeHtml(d.industry)} · ${escapeHtml(d.market)} · ${escapeHtml(d.date)}</span></h3>
    <div class="px"><b class="${dir}">${fmtPrice(d.close)}</b><span class="${dir}">${fmtChange(d.change)}（${fmtPct(d.change_pct)}）</span></div>
    <div id="hCardSpark" style="height:90px"></div>
    <table>
      <tr><td>近 ${d.series.length} 日</td><td>${fmtPct(d.period_pct)}</td><td>成交值</td><td>${fmtTurnover(d.turnover_100m)}</td></tr>
      <tr><td>最高</td><td>${fmtPrice(d.high)}</td><td>最低</td><td>${fmtPrice(d.low)}</td></tr>
      <tr><td>成交量</td><td>${fmtNum(d.volume_lots, 0)} 張</td><td>市值</td><td>${fmtCap(d.market_cap)}</td></tr>
    </table>
    <div class="memb" data-memb="${escapeHtml(d.code)}"></div>
    <div class="btns">
      <a href="https://histock.tw/stock/${encodeURIComponent(d.code)}" target="_blank" rel="noopener noreferrer">HiStock ↗</a>
      <button type="button" id="hCardClose" aria-label="關閉">✕</button>
    </div>`;
  el.hidden = false;
  $('#hCardClose').addEventListener('click', closeHistCard);
  fillMembership(el);
  if (cardChart) cardChart.dispose();
  cardChart = echarts.init($('#hCardSpark'));
  const up = (d.period_pct ?? 0) >= 0;
  cardChart.setOption({
    animation: false,
    grid: { left: 2, right: 2, top: 6, bottom: 2 },
    xAxis: { type: 'category', show: false, data: d.series.map((p) => p.date) },
    yAxis: { type: 'value', show: false, scale: true },
    tooltip: { trigger: 'axis', confine: true, formatter: (ps) => `${ps[0].name}<br>${fmtPrice(ps[0].value)}` },
    series: [{
      type: 'line', data: d.series.map((p) => p.close), symbol: 'none', smooth: false,
      lineStyle: { color: up ? '#ff5c5c' : '#3fcf6f', width: 1.5 },
      areaStyle: { color: up ? 'rgba(255,92,92,.15)' : 'rgba(63,207,111,.15)' },
      markPoint: { symbol: 'circle', symbolSize: 6, data: [{ coord: [d.series.length - 1, d.close] }], itemStyle: { color: '#fff' }, label: { show: false } },
    }],
  });
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && cardCode && !$('#historyView').hidden) closeHistCard();
});

// ---- bonus-03: concept / custom group membership line on the card ----
async function fillMembership(card) {
  const slot = card.querySelector('[data-memb]');
  if (!slot) return;
  const code = slot.dataset.memb;
  let m;
  try {
    const resp = await fetch(`/api/membership/${encodeURIComponent(code)}`, { cache: 'no-store' });
    if (!resp.ok) return;
    m = await resp.json();
  } catch {
    return;
  }
  if (slot.dataset.memb !== code || !slot.isConnected) return;
  const MAX = 8;
  const line = (label, names) => {
    if (!names.length) return '';
    const shown = names.slice(0, MAX).map((n) => escapeHtml(n)).join('、');
    const more = names.length > MAX ? ` <span class="muted">等 ${names.length} 個</span>` : '';
    return `<div title="${escapeHtml(names.join('、'))}"><span class="muted">${label}</span> ${shown}${more}</div>`;
  };
  slot.innerHTML = line('概念：', m.concepts) + line('自訂：', m.custom);
}
