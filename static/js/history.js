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
import { groupMembers, limitTag, toCsv } from './transform.js';
import { breadthBarHtml, breadthShare, marketBreadth } from './transform.js';
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
const csvData = { rotation: null, movers: null }; // bonus-07: last data shown in C / D
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
  if (!st.date && st.days.length) await selectDate(hashWanted?.date || st.days[0]); // bonus-12: bookmarked day first
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
  writeHash(); // bonus-12: synchronously, so the hash never lags behind overlapping loads
  $('#hDate').value = st.date;
  const i = st.days.indexOf(st.date);
  $('#hPrev').disabled = i >= st.days.length - 1;
  $('#hNext').disabled = i <= 0;
  if (!st.from || st.from >= st.date) st.from = st.days[Math.min(i + 4, st.days.length - 1)];
  $('#hFrom').value = st.from;
  $('#hBDate').textContent = st.date;
  await Promise.all([loadDay(), loadGroups_(), loadMovers()]);
  // heavy multi-day computations start only after the day's panels are in (they compete for the server)
  loadPeriods(); // bonus-10
  loadIndex(); // bonus-04
  renderRotationSelection();
  markCalendar(); // bonus-14
}

// ---- A: day heatmap ---------------------------------------------------------

// Each loader drops responses that arrive after a newer request (fast date/grouping switches).
const tickets = { day: 0, groups: 0, rotation: 0, movers: 0 };

async function loadDay() {
  const t = ++tickets.day;
  try {
    const data = await getJson(`/api/history/day/${st.date}?grouping=${st.grouping}`);
    if (t !== tickets.day) return;
    st.stocks = data.stocks.filter((s) => s.kind === 'stock');
    if (st.grouping === 'industry') setStockNames(st.stocks);
  } catch {
    if (t !== tickets.day) return;
    st.stocks = [];
  }
  renderChart();
}

function renderChart() {
  if (!chart) return;
  const tree = buildTreemapData(st.stocks, { sizeBy: st.sizeBy, colorBy: histColor.by }); // bonus-13
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
  renderHistBreadth(); // bonus-05
  renderHistColorSeg(); // bonus-13
  if (members.group) renderMembers(); // bonus-15
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
  const t = ++tickets.groups;
  try {
    const data = await getJson(`/api/history/groups?date=${st.date}&threshold=${st.threshold}&grouping=${st.grouping}`);
    if (t !== tickets.groups) return;
    st.groups = data.groups.map((g) => ({ ...g, leader_pct: g.leader?.change_pct ?? null })); // bonus-09
    loadPeriods({ cachedOnly: true }); // bonus-10: fetch is deferred until A/B/D have loaded
  } catch {
    if (t !== tickets.groups) return;
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
  table.tBodies[0].innerHTML = sortRows(filterGroupRows(st.groups), st.groupSort.key, st.groupSort.dir) // bonus-20
    .map(
      (g) => `<tr data-group="${escapeHtml(g.name)}"${g.name === st.zoom ? ' class="hl"' : ''}>
        <td class="l">${escapeHtml(g.name)}</td>
        ${rankCell(g)}
        ${pct(g.avg_pct, 3)}
        ${pct(g.cap_pct, 3)}
        ${periodCells(g)}
        <td class="c" style="background:${colorFor(g.strong_ratio, 30)}">${g.strong_ratio === null ? '—' : g.strong_ratio.toFixed(0) + '%'}<small class="muted"> ${g.strong_count}</small></td>
        <td>${g.limit_up || ''}</td>
        <td class="c" style="background:${breadthColor(g.up, g.down)}">${g.up}/${g.down}</td>
        <td class="l">${g.leader ? `<a href="#" class="leader" data-code="${escapeHtml(g.leader.code)}">${escapeHtml(g.leader.name)} <span class="${g.leader.change_pct > 0 ? 'up' : g.leader.change_pct < 0 ? 'down' : ''}">${fmtPct(g.leader.change_pct)}</span></a>` : '—'}</td>
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
  const t = ++tickets.rotation;
  try {
    data = await getJson(`/api/history/rotation?days=${st.rotDays}&metric=${st.rotMetric}&threshold=${st.threshold}&grouping=${st.grouping}`);
  } catch {
    if (t === tickets.rotation) table.innerHTML = '';
    return;
  }
  if (t !== tickets.rotation) return;
  csvData.rotation = data; // bonus-07
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
  const t = ++tickets.movers;
  try {
    data = await getJson(url);
  } catch {
    if (t === tickets.movers) $('#hMovers').innerHTML = '<p class="hint">無法載入。</p>';
    return;
  }
  if (t !== tickets.movers) return;
  csvData.movers = data; // bonus-07
  const total = new Set(data.groups.flatMap((g) => g.stocks.map((x) => x.code))).size;
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
  writeHash(); // bonus-12
  renderGrouping();
  if (customEmpty()) {
    $('#hEmpty').hidden = false;
    $('#hEmpty').textContent = '還沒有自訂族群（或族群內沒有股票）。按上方「管理族群」建立。';
  }
  if (!st.date) return;
  await Promise.all([loadDay(), loadGroups_(), loadMovers()]);
  loadPeriods(); // bonus-10
  loadRotation();
  loadIndex(); // bonus-04
}

function bind() {
  $('#hGrouping').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (!b || b.disabled || b.dataset.value === st.grouping) return;
    st.grouping = b.dataset.value;
    st.zoom = null;
    idx.picked = []; // E: names picked under another grouping would not exist here
    members.group = null; // bonus-15: the picked group may not exist in the new grouping
    savePrefs();
    reloadGrouped();
  });
  $('#hManageGroups').addEventListener('click', () => openGroupPanel());
  onGroupsChange(() => {
    for (const key of [...periodState.cache.keys()]) if (key.endsWith('|custom')) periodState.cache.delete(key);
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
    const leader = e.target.closest('a.leader[data-code]'); // bonus-09
    if (leader) {
      e.preventDefault();
      openHistCard(leader.dataset.code);
      return;
    }
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
    applyHashGrouping(); // bonus-12
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
    window.addEventListener('hashchange', onHashChange); // bonus-12
    await loadDays();
    await applyHashDate(); // bonus-12
    await loadRotation();
    loadIndex(); // bonus-04
    loadCalendar(); // bonus-14
    return;
  }
  chart.resize();
  const pasted = parseHash(); // bonus-12: a bookmark pasted while in live mode
  if (pasted?.date || pasted?.grouping) await onHashChange();
  else writeHash();
  await loadDays();
  loadRotation();
  loadIndex(); // bonus-04
  loadCalendar(); // bonus-14
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

// ---- bonus-04: E · cumulative group return comparison -------------------------

const IDX_DAYS = [20, 60, 120];
const idx = { days: 20, picked: [], chart: null, ticket: 0 };

function indexSection() {
  let sec = $('#hIndex');
  if (sec) return sec;
  sec = document.createElement('section');
  sec.id = 'hIndex';
  sec.className = 'panel';
  sec.style.gridColumn = '1 / -1';
  sec.innerHTML = `
    <div class="panel-h"><b>E · 族群走勢比較</b>
      <div class="seg" id="hIdxDays">${IDX_DAYS.map((d) => `<button data-value="${d}">${d} 日</button>`).join('')}</div>
      <select class="field" id="hIdxAdd" aria-label="加入族群"><option value="">＋ 加入族群…</option></select>
      <span id="hIdxChips" class="gp-codes"></span>
      <button type="button" class="icon wide" id="hIdxReset" title="改回期間累積報酬前 5 名">前 5 名</button>
      <span class="muted">等權日報酬連乘；虛線為全市場</span>
    </div>
    <div style="height:340px"><div id="hIdxChart" style="height:100%"></div></div>`;
  $('#historyView').appendChild(sec);
  $('#hIdxDays').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (!b) return;
    idx.days = Number(b.dataset.value);
    loadIndex();
  });
  $('#hIdxAdd').addEventListener('change', (e) => {
    const name = e.target.value;
    e.target.value = '';
    if (name && !idx.picked.includes(name)) {
      idx.picked.push(name);
      loadIndex();
    }
  });
  $('#hIdxChips').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-remove]');
    if (!b) return;
    idx.picked = idx.picked.filter((n) => n !== b.dataset.remove);
    loadIndex();
  });
  $('#hIdxReset').addEventListener('click', () => {
    idx.picked = [];
    loadIndex();
  });
  idx.chart = echarts.init($('#hIdxChart'));
  new ResizeObserver(() => idx.chart.resize()).observe($('#hIdxChart'));
  return sec;
}

async function loadIndex() {
  if (!st.date) return;
  indexSection();
  for (const b of $('#hIdxDays').querySelectorAll('button')) b.classList.toggle('on', Number(b.dataset.value) === idx.days);
  let url = `/api/history/index?days=${idx.days}&to=${st.date}&grouping=${st.grouping}`;
  if (idx.picked.length) url += `&groups=${encodeURIComponent(idx.picked.join(','))}`;
  const ticket = ++idx.ticket; // ignore responses that arrive after a newer request
  let d;
  try {
    d = await getJson(url);
  } catch {
    return;
  }
  if (ticket !== idx.ticket) return;
  const names = (st.groups || []).map((g) => g.name).sort((a, b) => a.localeCompare(b, 'zh-Hant'));
  $('#hIdxAdd').innerHTML = '<option value="">＋ 加入族群…</option>' +
    names.filter((n) => !idx.picked.includes(n)).map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join('');
  $('#hIdxChips').innerHTML = idx.picked
    .map((n) => `<span>${escapeHtml(n)}<button type="button" data-remove="${escapeHtml(n)}" title="移除">✕</button></span>`)
    .join('');
  const pct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  idx.chart.setOption({
    animation: false,
    color: ['#ff6b6b', '#ffb84d', '#ffe66d', '#6bcB77', '#4d96ff', '#c77dff', '#ff8fab', '#5ee7df', '#f9f871', '#a0a0ff'],
    grid: { left: 52, right: 150, top: 16, bottom: 28 },
    tooltip: { trigger: 'axis', valueFormatter: (v) => (v == null ? '—' : pct(v)) },
    legend: { type: 'scroll', orient: 'vertical', right: 0, top: 10, textStyle: { color: '#ccc' } },
    xAxis: { type: 'category', data: d.dates.map((x) => x.slice(5).replace('-', '/')), axisLabel: { color: '#999' } },
    yAxis: { type: 'value', axisLabel: { color: '#999', formatter: (v) => `${v}%` }, splitLine: { lineStyle: { color: '#262a33' } } },
    series: [
      ...d.series.map((s) => ({ name: s.name, type: 'line', data: s.values, symbol: 'none', lineStyle: { width: 2 }, endLabel: { show: false } })),
      { name: '全市場', type: 'line', data: d.market, symbol: 'none', lineStyle: { width: 1.5, type: 'dashed', color: '#aaa' }, itemStyle: { color: '#aaa' } },
    ],
  }, { notMerge: true });
}

// ---- bonus-05: market breadth for the selected day (A panel header) ----
function renderHistBreadth() {
  let el = $('#mbarHist');
  if (!el) {
    el = document.createElement('span');
    el.id = 'mbarHist';
    $('#hCrumb').after(el);
  }
  // custom/concept groupings repeat a stock once per group: count each code once
  const seen = new Set();
  const unique = st.stocks.filter((s) => !seen.has(s.code) && seen.add(s.code));
  el.innerHTML = breadthBarHtml(marketBreadth(unique));
}

// ---- bonus-06: day-by-day replay ------------------------------------------------

const REPLAY_SPEEDS = [1, 2, 4]; // seconds per trading day
const replay = { on: false, timer: null, speed: 2 };

function replayControls() {
  if ($('#hPlay')) return;
  const wrap = document.createElement('span');
  wrap.className = 'replay';
  wrap.innerHTML = `<button class="icon" id="hPlay" title="從目前日期逐日播放到最新日" aria-label="播放">▶▶</button>
    <select class="field" id="hSpeed" aria-label="播放速度" title="每個交易日停留秒數">${REPLAY_SPEEDS.map((s) => `<option value="${s}">${s} 秒/日</option>`).join('')}</select>`;
  $('#hNext').after(wrap);
  $('#hSpeed').value = String(replay.speed);
  $('#hSpeed').addEventListener('change', (e) => (replay.speed = Number(e.target.value)));
  $('#hPlay').addEventListener('click', () => (replay.on ? stopReplay() : startReplay()));
  // any manual navigation stops the replay
  for (const id of ['#hPrev', '#hNext', '#hDate']) $(id).addEventListener(id === '#hDate' ? 'change' : 'click', () => stopReplay(), true);
  $('#hRotation').addEventListener('click', () => stopReplay(), true);
}

function renderReplayButton() {
  const b = $('#hPlay');
  if (!b) return;
  b.textContent = replay.on ? '⏸' : '▶▶';
  b.title = replay.on ? '暫停播放' : '從目前日期逐日播放到最新日';
  b.classList.toggle('on', replay.on);
}

async function startReplay() {
  if (!st.days.length) return;
  let i = st.days.indexOf(st.date);
  if (i <= 0) i = Math.min(20, st.days.length - 1); // at the newest day: start 20 trading days back
  replay.on = true;
  renderReplayButton();
  await selectDate(st.days[i]);
  scheduleReplayStep();
}

function scheduleReplayStep() {
  clearTimeout(replay.timer);
  if (!replay.on) return;
  replay.timer = setTimeout(async () => {
    const i = st.days.indexOf(st.date);
    if (!replay.on || i <= 0) return stopReplay();
    await selectDate(st.days[i - 1]);
    if (i - 1 <= 0) return stopReplay();
    scheduleReplayStep();
  }, replay.speed * 1000);
}

function stopReplay() {
  replay.on = false;
  clearTimeout(replay.timer);
  renderReplayButton();
}

document.addEventListener('DOMContentLoaded', replayControls);
if (document.readyState !== 'loading') replayControls();

// ---- bonus-07: CSV export of B / C / D ----------------------------------------------

const GROUPING_LABEL = { industry: '官方產業', custom: '自訂族群', concept: '概念股' };

function downloadCsv(name, header, rows) {
  const blob = new Blob([toCsv(header, rows)], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

const CSV_EXPORTS = {
  hB: () => [
    `強勢族群_${st.date}_${GROUPING_LABEL[st.grouping]}.csv`,
    ['日期', '族群', '平均漲幅%', '市值加權%', `漲幅≥${st.threshold}%家數`, `≥${st.threshold}%佔比%`, '漲停', '跌停', '上漲', '下跌', '家數', '成交值(元)'],
    sortRows(st.groups, st.groupSort.key, st.groupSort.dir).map((g) => [
      st.date, g.name, g.avg_pct, g.cap_pct, g.strong_count, g.strong_ratio, g.limit_up, g.limit_down, g.up, g.down, g.count, g.turnover,
    ]),
  ],
  hC: () => {
    const d = csvData.rotation;
    if (!d) return null;
    return [
      `族群輪動_${d.metric}_${d.dates[d.dates.length - 1] || ''}_${GROUPING_LABEL[st.grouping]}.csv`,
      ['族群', ...d.dates],
      d.groups.map((g) => [g.name, ...g.values]),
    ];
  },
  hD: () => {
    const d = csvData.movers;
    if (!d) return null;
    return [
      `集體上漲_${d.mode}_${st.date}_${GROUPING_LABEL[st.grouping]}.csv`,
      ['日期', '族群', '代號', '名稱', d.label || '數值', '當日漲幅%', '收盤'],
      d.groups.flatMap((g) => g.stocks.map((x) => [st.date, g.name, x.code, x.name, x.value, x.change_pct, x.close])),
    ];
  },
};

function addCsvButtons() {
  for (const [cls, build] of Object.entries(CSV_EXPORTS)) {
    const head = document.querySelector(`#historyView .${cls} .panel-h`);
    if (!head || head.querySelector('.csv-btn')) continue;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'icon wide csv-btn';
    b.textContent = 'CSV';
    b.title = '匯出目前顯示的資料（Excel 可開）';
    b.addEventListener('click', () => {
      const out = build();
      if (out && out[2].length) downloadCsv(...out);
    });
    head.appendChild(b);
  }
}

if (document.readyState !== 'loading') addCsvButtons();
else document.addEventListener('DOMContentLoaded', addCsvButtons);

// ---- bonus-10: 5/20/60-day group returns in the ranking (filled in asynchronously) ----

const periodState = { ticket: 0, cache: new Map() }; // key: date|grouping → {group: perf}

function periodCells(g) {
  const cell = (v, limit) => (v === undefined ? '<td class="muted">…</td>' : `<td class="c" style="background:${colorFor(v, limit)}">${fmtPct(v)}</td>`);
  return cell(g.perf_5, 8) + cell(g.perf_20, 15) + cell(g.perf_60, 25);
}

async function loadPeriods({ cachedOnly = false } = {}) {
  const key = `${st.date}|${st.grouping}`;
  const apply = (map) => {
    st.groups = st.groups.map((g) => ({ ...g, ...(map[g.name] || { perf_5: null, perf_20: null, perf_60: null }) }));
    renderGroups();
  };
  if (periodState.cache.has(key)) return apply(periodState.cache.get(key));
  if (cachedOnly) return;
  const ticket = ++periodState.ticket;
  let data;
  try {
    data = await getJson(`/api/history/periods?date=${st.date}&grouping=${st.grouping}`);
  } catch {
    return;
  }
  periodState.cache.set(key, data.groups);
  if (ticket === periodState.ticket && key === `${st.date}|${st.grouping}`) apply(data.groups);
}

// ---- bonus-12: bookmarkable view state in the URL hash (#history/<date>/<grouping>) ----

const GROUPINGS_OK = new Set(['industry', 'custom', 'concept']);

function parseHash() {
  const m = /^#history(?:\/(\d{4}-\d{2}-\d{2}))?(?:\/(industry|custom|concept))?$/.exec(location.hash);
  return m ? { date: m[1] || null, grouping: m[2] || null } : null;
}

function writeHash() {
  if ($('#historyView').hidden || !st.date) return;
  const hash = `#history/${st.date}/${st.grouping}`;
  if (location.hash !== hash) history.replaceState(null, '', hash);
}

let hashWanted = null; // the bookmarked view, read once before the first load rewrites the hash

function applyHashGrouping() {
  const h = (hashWanted = parseHash());
  if (h?.grouping && GROUPINGS_OK.has(h.grouping)) st.grouping = h.grouping;
}

async function applyHashDate() {
  hashWanted = null; // the first selectDate already used it
  writeHash();
}

async function onHashChange() {
  const h = parseHash();
  if (!h || $('#historyView').hidden) return;
  const groupingChanged = !!h.grouping && GROUPINGS_OK.has(h.grouping) && h.grouping !== st.grouping;
  const dateChanged = !!h.date && h.date !== st.date;
  if (groupingChanged) {
    st.grouping = h.grouping;
    st.zoom = null;
    idx.picked = [];
    savePrefs();
    renderGrouping();
  }
  if (dateChanged) {
    await selectDate(h.date); // loads A/B/D/E with the (new) grouping
    if (groupingChanged) loadRotation();
  } else if (groupingChanged) await reloadGrouped();
}


// ---- bonus-13: colour the history heatmap by 1 / 5 / 20-day returns ---------------------

const histColor = { by: 'today' };
try {
  const saved = JSON.parse(localStorage.getItem('openmarket.history.color') || '""');
  if (['today', 'week', 'p20'].includes(saved)) histColor.by = saved;
} catch {
  /* default */
}

function renderHistColorSeg() {
  let seg = $('#hColorSeg');
  if (!seg) {
    seg = document.createElement('div');
    seg.className = 'seg';
    seg.id = 'hColorSeg';
    seg.title = '格子顏色依 1 日／5 日／20 日漲幅（收盤對 N 個交易日前收盤）';
    seg.innerHTML = '<button data-value="today">顏色：1日</button><button data-value="week">5日</button><button data-value="p20">20日</button>';
    document.querySelector('#historyView .hA .seg[data-hgroup="sizeBy"]').before(seg);
    seg.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-value]');
      if (!b || b.dataset.value === histColor.by) return;
      histColor.by = b.dataset.value;
      try {
        localStorage.setItem('openmarket.history.color', JSON.stringify(histColor.by));
      } catch {
        /* ignore */
      }
      renderChart();
    });
  }
  for (const b of seg.querySelectorAll('button')) b.classList.toggle('on', b.dataset.value === histColor.by);
}

// ---- bonus-14: F · daily market-breadth calendar --------------------------------------

function calendarSection() {
  let sec = $('#hCalendar');
  if (sec) return sec;
  sec = document.createElement('section');
  sec.id = 'hCalendar';
  sec.className = 'panel';
  sec.style.gridColumn = '1 / -1';
  sec.innerHTML = `<div class="panel-h"><b>F · 每日廣度月曆</b>
      <span class="muted">每格一個交易日；顏色＝當天上漲家數佔比（紅多漲、綠多跌）；點格子切換日期</span></div>
    <div id="hCalBody" style="padding:8px 10px;display:grid;grid-template-columns:70px 1fr;gap:3px 8px;font-size:11px"></div>`;
  $('#historyView').appendChild(sec);
  $('#hCalBody').addEventListener('click', (e) => {
    const cell = e.target.closest('[data-date]');
    if (!cell) return;
    stopReplay(); // manual navigation ends a running replay
    selectDate(cell.dataset.date);
  });
  return sec;
}

async function loadCalendar() {
  calendarSection();
  let data;
  try {
    data = await getJson('/api/history/calendar');
  } catch {
    return;
  }
  const months = new Map();
  for (const d of data.days) {
    const m = d.date.slice(0, 7);
    if (!months.has(m)) months.set(m, []);
    months.get(m).push(d);
  }
  $('#hCalBody').innerHTML = [...months]
    .reverse()
    .map(([m, days]) => {
      const cells = days
        .map((d) => {
          const share = breadthShare(d.up, d.down);
          const title = `${d.date}：上漲 ${d.up}／下跌 ${d.down}${share === null ? '' : `（${share.toFixed(0)}%）`}，平均 ${fmtPct(d.avg_pct)}`;
          return `<span data-date="${d.date}" title="${title}" style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:22px;margin:0 2px 2px 0;border-radius:3px;cursor:pointer;color:#fff;background:${breadthColor(d.up, d.down)}">${Number(d.date.slice(8))}</span>`;
        })
        .join('');
      return `<div class="muted" style="align-self:center">${m}</div><div>${cells}</div>`;
    })
    .join('');
  markCalendar();
}

function markCalendar() {
  for (const el of document.querySelectorAll('#hCalBody [data-date]')) {
    el.style.outline = el.dataset.date === st.date ? '2px solid #fff' : '';
  }
}

// ---- bonus-15: member table for the group picked in B ---------------------------------

const members = { group: null, sort: { key: 'change_pct', dir: 'desc' } };

function membersBox() {
  let box = $('#hMembers');
  if (box) return box;
  box = document.createElement('div');
  box.id = 'hMembers';
  box.hidden = true;
  box.style.cssText = 'border-top:1px solid var(--line);max-height:230px;overflow:auto;flex-shrink:0';
  document.querySelector('#historyView .hB').appendChild(box);
  box.addEventListener('click', (e) => {
    const th = e.target.closest('th[data-msort]');
    if (th) {
      const key = th.dataset.msort;
      members.sort = members.sort.key === key
        ? { key, dir: members.sort.dir === 'asc' ? 'desc' : 'asc' }
        : { key, dir: key === 'name' || key === 'code' ? 'asc' : 'desc' };
      renderMembers();
      return;
    }
    if (e.target.closest('#hMembersClose')) {
      members.group = null;
      renderMembers();
      return;
    }
    const tr = e.target.closest('tr[data-code]');
    if (tr) openHistCard(tr.dataset.code);
  });
  return box;
}

function renderMembers() {
  const box = membersBox();
  if (!members.group) {
    box.hidden = true;
    return;
  }
  const list = sortRows(groupMembers(st.stocks, members.group), members.sort.key, members.sort.dir);
  const th = (key, label, cls = '') => {
    const aria = members.sort.key === key ? ` aria-sort="${members.sort.dir === 'asc' ? 'ascending' : 'descending'}"` : '';
    return `<th data-msort="${key}" class="${cls}"${aria}>${label}</th>`;
  };
  const cell = (v, limit) => `<td class="c" style="background:${colorFor(v, limit)}">${fmtPct(v)}</td>`;
  box.innerHTML = `<div class="panel-h" style="position:sticky;top:0;background:var(--panel);z-index:2"><b>${escapeHtml(members.group)}</b>
      <span class="muted">${list.length} 檔成分股 · ${escapeHtml(st.date || '')} · 點股票看卡片</span><span class="spacer"></span>
      <button type="button" class="icon" id="hMembersClose" aria-label="關閉">✕</button></div>
    <table class="grid"><thead><tr>${th('code', '代號', 'l')}${th('name', '名稱', 'l')}${th('change_pct', '漲幅')}${th('week_pct', '5日')}${th('period_20', '20日')}${th('turnover_100m', '成交值')}</tr></thead>
    <tbody>${list
      .map((s) => `<tr data-code="${escapeHtml(s.code)}"><td class="l">${escapeHtml(s.code)}</td><td class="l">${escapeHtml(s.name)}${limitTag(s.change_pct) ? ` <span class="muted">${limitTag(s.change_pct)}</span>` : ''}</td>${cell(s.change_pct, 7)}${cell(s.week_pct, 15)}${cell(s.period_20, 25)}<td>${fmtTurnover(s.turnover_100m)}</td></tr>`)
      .join('')}</tbody></table>`;
  box.hidden = false;
}

// pick a group from B (the existing B click handler also zooms A to it)
document.addEventListener('click', (e) => {
  const tr = e.target.closest('#hGroups tbody tr[data-group]');
  if (!tr || e.target.closest('a.leader')) return;
  members.group = tr.dataset.group;
  renderMembers();
}, true); // capture: the B handler re-renders the rows, detaching the clicked one


// ---- bonus-18: rank change vs the previous trading day -----------------------------
function rankCell(g) {
  if (g.rank == null) return '<td class="muted">—</td>';
  const ch = g.rank_change;
  const delta = ch == null ? '' : ch > 0 ? ` <span class="up">▲${ch}</span>` : ch < 0 ? ` <span class="down">▼${-ch}</span>` : ' <span class="muted">–</span>';
  return `<td title="今日名次 ${g.rank}">${g.rank}${delta}</td>`;
}

// ---- bonus-20: filter the B ranking by group name ------------------------------------
const groupFilter = { text: '' };

function filterGroupRows(rows) {
  ensureGroupFilterBox();
  const t = groupFilter.text.trim().toLowerCase();
  return t ? rows.filter((g) => g.name.toLowerCase().includes(t)) : rows;
}

function ensureGroupFilterBox() {
  if ($('#hGroupFilter')) return;
  const input = document.createElement('input');
  input.id = 'hGroupFilter';
  input.className = 'field';
  input.type = 'search';
  input.placeholder = '篩選族群名稱…';
  input.style.width = '140px';
  input.setAttribute('aria-label', '篩選族群名稱');
  $('#hBDate').after(input);
  input.addEventListener('input', () => {
    groupFilter.text = input.value;
    renderGroups();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      input.value = '';
      groupFilter.text = '';
      renderGroups();
    }
  });
}

// ---- bonus-21: fullscreen button for the history heatmap (A) -------------------------
(function addHistFullscreen() {
  const wrap = document.querySelector('#historyView .hA .chart-wrap');
  if (!wrap || !document.fullscreenEnabled) return;
  const b = document.createElement('button');
  b.type = 'button';
  b.className = 'fs-btn';
  b.title = '全螢幕（Esc 離開）';
  b.setAttribute('aria-label', '全螢幕');
  b.textContent = '⛶';
  b.addEventListener('click', () => (document.fullscreenElement ? document.exitFullscreen() : wrap.requestFullscreen()));
  wrap.appendChild(b);
})();
