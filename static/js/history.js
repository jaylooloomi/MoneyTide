// History view: A (day heatmap), B (group ranking), C (rotation matrix), D (movers).
import {
  ROOT_ID,
  breadthColor,
  buildTreemapData,
  buildTreemapOption,
  colorFor,
  escapeHtml,
  fmtPct,
  sortRows,
} from './transform.js';

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
    for (const k of ['threshold', 'sizeBy', 'rotDays', 'rotMetric', 'moverMode', 'groupSort']) if (p[k] !== undefined) st[k] = p[k];
    if (p.moverValue) Object.assign(st.moverValue, p.moverValue);
  } catch {
    /* defaults */
  }
}

function savePrefs() {
  try {
    const { threshold, sizeBy, rotDays, rotMetric, moverMode, moverValue, groupSort } = st;
    localStorage.setItem(PREFS_KEY, JSON.stringify({ threshold, sizeBy, rotDays, rotMetric, moverMode, moverValue, groupSort }));
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
  await Promise.all([loadDay(), loadGroups(), loadMovers()]);
  renderRotationSelection();
}

// ---- A: day heatmap ---------------------------------------------------------

async function loadDay() {
  try {
    const data = await getJson(`/api/history/day/${st.date}`);
    st.stocks = data.stocks.filter((s) => s.kind === 'stock');
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
  if (!tree.data.length) $('#hEmpty').textContent = '這一天沒有資料。';
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

async function loadGroups() {
  try {
    const data = await getJson(`/api/history/groups?date=${st.date}&threshold=${st.threshold}`);
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
    data = await getJson(`/api/history/rotation?days=${st.rotDays}&metric=${st.rotMetric}&threshold=${st.threshold}`);
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
  let url = `/api/history/movers?to=${st.date}&mode=${mode}&value=${value}`;
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
              return `<a class="tag" href="https://histock.tw/stock/${encodeURIComponent(s.code)}" target="_blank" rel="noopener noreferrer"
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

function bind() {
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
    loadGroups();
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
    chart = echarts.init($('#hChart'));
    chart.on('click', (p) => {
      if (p.data?.industry) zoomTo(p.data.name);
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
