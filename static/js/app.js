// DOM, events, ECharts binding and polling. Data shaping lives in transform.js.
import {
  ROOT_ID,
  aggregateIndustries,
  breadthColor,
  breadthShare,
  buildTreemapData,
  buildTreemapOption,
  colorFor,
  colorLimit,
  escapeHtml,
  filterStocks,
  fmtCap,
  fmtChange,
  fmtNum,
  fmtPct,
  fmtPrice,
  fmtTurnover,
  sortRows,
  watchRows,
} from './transform.js';
import { showHistory } from './history.js';
import { breadthBarHtml, marketBreadth, regroupStocks } from './transform.js';
import { addToGroup, getGroups, loadGroups, onGroupsChange, openGroupPanel, setStockNames } from './groups.js';

const SNAPSHOT_POLL_MS = 10_000;
// bonus-11: 20-day industry returns for the live matrix (declared before main() runs)
const livePeriods = { date: null, byGroup: {}, loading: false };
// bonus-17: live grouping switch state (declared before main() runs)
const liveGrouping = { by: 'industry', maps: {}, loading: {} };
try {
  const saved = JSON.parse(localStorage.getItem('openmarket.live.grouping') || '""');
  if (['industry', 'custom', 'concept'].includes(saved)) liveGrouping.by = saved;
} catch {
  /* default */
}
const PREFS_KEY = 'openmarket.prefs.v1';

const $ = (sel) => document.querySelector(sel);

const state = {
  snapshot: null,
  etag: null,
  watchCodes: [],
  settings: { poll_seconds: 60 },
  // persisted preferences
  filters: { market: 'all', includeEtf: false, watchOnly: false },
  view: { sizeBy: 'cap', colorBy: 'today' },
  tab: 'industry',
  mode: 'live',
  sort: { industry: { key: 'change_pct', dir: 'desc' }, watch: { key: null, dir: 'desc' } },
  // transient
  zoomIndustry: null,
  hoverIndustry: null,
  cardCode: null,
  cardLast: null,
  tree: null,
};

// ---- preferences ----------------------------------------------------------

function loadPrefs() {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) || '{}');
    if (p.filters) Object.assign(state.filters, p.filters);
    if (p.view) Object.assign(state.view, p.view);
    if (p.tab === 'industry' || p.tab === 'watch') state.tab = p.tab;
    if (p.mode === 'live' || p.mode === 'history') state.mode = p.mode;
    if (p.sort) Object.assign(state.sort, p.sort);
  } catch {
    /* storage unavailable or corrupt: defaults */
  }
}

function savePrefs() {
  try {
    const { filters, view, tab, sort, mode } = state;
    localStorage.setItem(PREFS_KEY, JSON.stringify({ filters, view, tab, sort, mode }));
  } catch {
    /* ignore */
  }
}

// ---- API ------------------------------------------------------------------

async function api(path, options = {}) {
  const resp = await fetch(path, { cache: 'no-store', ...options });
  let body = null;
  if (resp.status !== 304 && resp.status !== 204) {
    try {
      body = await resp.json();
    } catch {
      body = null;
    }
  }
  return { resp, body };
}

async function pollSnapshot() {
  try {
    const headers = state.etag ? { 'If-None-Match': state.etag } : {};
    const { resp, body } = await api('/api/snapshot', { headers });
    if (resp.status === 304) {
      renderStatus(); // clears a previous connection error
      return;
    }
    if (!resp.ok || !body) throw new Error(`HTTP ${resp.status}`);
    state.etag = resp.headers.get('ETag');
    state.snapshot = body;
    setStockNames(body.stocks);
    render();
  } catch (err) {
    renderStatus(`無法連線到本機伺服器（${err.message}）`);
  }
}

let pollTimer = null;
function schedulePoll(ms = SNAPSHOT_POLL_MS) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    await pollSnapshot();
    schedulePoll();
  }, ms);
}

async function loadWatchlist() {
  const { resp, body } = await api('/api/watchlist');
  if (resp.ok && body) state.watchCodes = body.codes;
}

async function setWatched(code, watched) {
  let resp, body;
  try {
    ({ resp, body } = await api(`/api/watchlist/${encodeURIComponent(code)}`, { method: watched ? 'PUT' : 'DELETE' }));
  } catch {
    toast('自選清單更新失敗（無法連線）');
    return;
  }
  if (!resp.ok || !body) {
    toast('自選清單更新失敗');
    return;
  }
  state.watchCodes = body.codes;
  render();
}

// ---- chart ----------------------------------------------------------------

let chart = null;

function initChart() {
  chart = echarts.init($('#chart'), null, { renderer: 'canvas' });
  chart.on('click', (p) => {
    const d = p.data || {};
    if (d.stock) openCard(d.code);
    else if (d.industry) zoomTo(d.name);
  });
  new ResizeObserver(() => chart.resize()).observe($('#chart'));
}

function hasIndustry(name) {
  return !!state.tree && state.tree.data.some((d) => d.name === name);
}

function zoomTo(name) {
  if (!hasIndustry(name)) return;
  state.zoomIndustry = name;
  chart.dispatchAction({ type: 'treemapRootToNode', seriesId: 'map', targetNodeId: 'ind:' + name });
  reapplyHighlight();
  renderCrumb();
  syncMatrixZoom();
}

function zoomOut() {
  state.zoomIndustry = null;
  chart.dispatchAction({ type: 'treemapRootToNode', seriesId: 'map', targetNodeId: ROOT_ID });
  reapplyHighlight();
  renderCrumb();
  syncMatrixZoom();
}

/** Re-rooting or re-rendering rebuilds the treemap elements and drops their emphasis state. */
function reapplyHighlight() {
  if (state.hoverIndustry) chart.dispatchAction({ type: 'highlight', seriesId: 'map', name: state.hoverIndustry });
}

function syncMatrixZoom() {
  for (const row of $('#matrix').tBodies[0].rows) row.classList.toggle('hl', row.dataset.industry === state.zoomIndustry);
}

function highlightIndustry(name) {
  if (state.hoverIndustry && state.hoverIndustry !== name) {
    chart.dispatchAction({ type: 'downplay', seriesId: 'map', name: state.hoverIndustry });
  }
  state.hoverIndustry = name;
  if (name) chart.dispatchAction({ type: 'highlight', seriesId: 'map', name });
}

function renderChart(stocks) {
  state.tree = buildTreemapData(stocks, state.view);
  // setOption always resets the treemap view root: zoom state is owned here and re-applied.
  chart.setOption(buildTreemapOption(state.tree), { notMerge: true });
  if (state.zoomIndustry && hasIndustry(state.zoomIndustry)) {
    chart.dispatchAction({ type: 'treemapRootToNode', seriesId: 'map', targetNodeId: 'ind:' + state.zoomIndustry });
  } else {
    state.zoomIndustry = null;
  }
  reapplyHighlight();
}

// ---- rendering --------------------------------------------------------------

function render() {
  const snap = state.snapshot;
  renderControls();
  renderStatus();
  $('#watchCount').textContent = `(${state.watchCodes.length})`;
  const filtered = snap ? filterStocks(snap.stocks, state.filters, state.watchCodes) : [];
  const stocks = applyLiveGrouping(filtered); // bonus-17: custom / concept regrouping

  renderChart(stocks);
  const empty = emptyMessage(snap, stocks);
  $('#empty').hidden = !empty;
  $('#empty').textContent = empty || '';
  renderCrumb();
  renderNote();
  renderLegend();
  renderMatrix(withPeriods(aggregateIndustries(stocks))); // bonus-11: 20-day column
  renderLiveBreadth(filtered); // bonus-05 (each stock once, whatever the grouping)
  renderWatch(snap ? snap.stocks : []);
  renderCard();
}

function emptyMessage(snap, stocks) {
  if (!snap || snap.status === 'loading') return '載入中…首次啟動需要抓取報價與產業分類資料。';
  if (!snap.stocks.length) return `目前沒有資料：${snap.message || '報價抓取失敗'}`;
  if (!stocks.length) {
    if (liveGrouping.by === 'custom') return '還沒有自訂族群（或族群內沒有符合篩選的股票）。到「歷史」頁按「管理族群」建立，或在個股資訊卡加入。'; // bonus-17
    if (state.filters.watchOnly) return '自選清單是空的（或不在目前的市場篩選中）。點個股資訊卡的「加入自選」來新增。';
    return '目前篩選條件下沒有股票。';
  }
  if (!state.tree?.data.length) return '目前篩選條件下的股票都沒有可用的格子大小資料，請切換「成交值」或「市值」。';
  return '';
}

function renderControls() {
  for (const seg of document.querySelectorAll('.seg[data-group]')) {
    const group = seg.dataset.group;
    const current = String(group in state.filters ? state.filters[group] : state.view[group]);
    for (const b of seg.querySelectorAll('button')) {
      const on = b.dataset.value === current;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', String(on));
    }
  }
  const etf = $('#includeEtf');
  etf.checked = state.filters.includeEtf;
  etf.disabled = state.filters.watchOnly;
  etf.closest('.chk').classList.toggle('disabled', state.filters.watchOnly);
  etf.closest('.chk').title = state.filters.watchOnly ? '只看自選時會顯示所有自選股（含 ETF）' : '';
  for (const b of document.querySelectorAll('.tabs button')) b.classList.toggle('on', b.dataset.tab === state.tab);
  for (const b of document.querySelectorAll('.tabs button')) b.setAttribute('aria-selected', String(b.dataset.tab === state.tab));
  $('#matrix').hidden = state.tab !== 'industry';
  $('#watch').hidden = state.tab !== 'watch';
  $('#watchEmpty').hidden = !(state.tab === 'watch' && state.watchCodes.length === 0);
}

function renderStatus(connectionError) {
  const el = $('#status');
  const snap = state.snapshot;
  let cls = 'loading';
  let text = '載入中…';
  let title = '';
  if (connectionError) {
    cls = 'error';
    text = '伺服器未連線';
    title = connectionError;
  } else if (snap) {
    cls = snap.status;
    const time = snap.as_of ? new Date(snap.as_of).toLocaleTimeString('zh-TW', { hour12: false }) : '—';
    const session = snap.market_open ? `盤中 · 每 ${state.settings.poll_seconds} 秒` : '已收盤';
    text = { ok: `${time} 更新 · ${session}`, stale: `${time} 的資料（更新失敗）· ${session}`, error: '資料抓取失敗', loading: '載入中…' }[snap.status];
    title = snap.message || '';
  }
  el.className = `status ${cls}`;
  $('#statusText').textContent = text;
  el.title = title;
}

function renderCrumb() {
  const el = $('#crumb');
  if (state.zoomIndustry) {
    el.innerHTML = `<button type="button" id="crumbRoot">全市場</button> › <b>${escapeHtml(state.zoomIndustry)}</b>`;
    $('#crumbRoot').addEventListener('click', zoomOut);
  } else {
    el.innerHTML = '<b>全市場</b> <span class="muted">（點產業標題放大）</span>';
  }
}

function renderNote() {
  const t = state.tree;
  const notes = [];
  if (t) {
    if (t.hiddenNoSize) notes.push(`${t.hiddenNoSize} 檔${state.view.sizeBy === 'cap' ? '缺市值' : '無成交值'}未顯示`);
    if (t.hiddenEtf) notes.push(`市值模式不顯示 ETF（${t.hiddenEtf} 檔，無股本資料），可切換「成交值」`);
  }
  const snap = state.snapshot;
  if (snap && snap.message && snap.status === 'ok') notes.push(snap.message);
  $('#note').textContent = notes.join('　·　');
}

function renderLegend() {
  const limit = colorLimit(state.view.colorBy);
  $('#legendMin').textContent = `-${limit}%`;
  $('#legendMax').textContent = `+${limit}%`;
}

function setSortHeaders(table, sort) {
  for (const th of table.querySelectorAll('th[data-sort]')) {
    if (th.dataset.sort === sort.key) th.setAttribute('aria-sort', sort.dir === 'asc' ? 'ascending' : 'descending');
    else th.removeAttribute('aria-sort');
  }
}

function pctCell(v, limit) {
  return `<td class="c" style="background:${colorFor(v, limit)}">${fmtPct(v)}</td>`;
}

function breadthCell(up, down) {
  const share = breadthShare(up, down);
  const title = share === null ? '' : `上漲家數佔 ${share.toFixed(0)}%`;
  return `<td class="c" style="background:${breadthColor(up, down)}" title="${title}">${up}/${down}</td>`;
}

function renderMatrix(rows) {
  const table = $('#matrix');
  const sort = state.sort.industry;
  setSortHeaders(table, sort);
  const sorted = sortRows(rows, sort.key, sort.dir);
  table.tBodies[0].innerHTML = sorted
    .map(
      (r) => `<tr data-industry="${escapeHtml(r.name)}"${r.name === state.zoomIndustry ? ' class="hl"' : ''}>
        <td class="l">${escapeHtml(r.name)}</td>
        ${pctCell(r.change_pct, colorLimit('today'))}
        ${pctCell(r.week_pct, colorLimit('week'))}
        ${pctCell(livePeriods.byGroup[r.name]?.perf_20 ?? null, 15)}
        <td>${r.amplitude_pct === null ? '—' : r.amplitude_pct.toFixed(2) + '%'}</td>
        <td>${r.turnover_share === null ? '—' : r.turnover_share.toFixed(1) + '%'}</td>
        ${volRatioCell(r.vol_ratio)}
        ${breadthCell(r.up_count, r.down_count)}
      </tr>`,
    )
    .join('');
}

function renderWatch(allStocks) {
  const table = $('#watch');
  const sort = state.sort.watch;
  setSortHeaders(table, sort);
  let rows = watchRows(allStocks, state.watchCodes);
  if (sort.key) rows = sortRows(rows, sort.key, sort.dir);
  table.tBodies[0].innerHTML = rows
    .map((s) =>
      s.missing
        ? `<tr data-code="${escapeHtml(s.code)}"><td class="l">${escapeHtml(s.code)}</td><td class="l muted" colspan="5">目前無報價</td>
           <td><button class="rm" data-remove="${escapeHtml(s.code)}" title="移除">✕</button></td></tr>`
        : `<tr data-code="${escapeHtml(s.code)}">
        <td class="l">${escapeHtml(s.code)}</td>
        <td class="l">${escapeHtml(s.name)}</td>
        <td>${fmtPrice(s.price)}</td>
        ${pctCell(s.change_pct, colorLimit('today'))}
        ${pctCell(s.week_pct, colorLimit('week'))}
        <td>${fmtTurnover(s.turnover_100m)}</td>
        <td><button class="rm" data-remove="${escapeHtml(s.code)}" title="移除">✕</button></td>
      </tr>`,
    )
    .join('');
}

// ---- info card ----------------------------------------------------------------

function openCard(code) {
  state.cardCode = code;
  state.cardLast = null;
  renderCard();
}

function closeCard() {
  delete $('#card').dataset.actionsSig;
  state.cardCode = null;
  state.cardLast = null;
  renderCard();
}

function groupSelect(code) {
  const groups = getGroups();
  const member = groups.filter((g) => g.codes.includes(code)).map((g) => g.name);
  const options = groups
    .filter((g) => !g.codes.includes(code))
    .map((g) => `<option value="${escapeHtml(g.name)}">${escapeHtml(g.name)}</option>`)
    .join('');
  const label = member.length ? `已在：${member.map(escapeHtml).join('、')}` : '加入自訂族群…';
  return `<select class="field" id="cardGroup" aria-label="加入自訂族群"><option value="">${label}</option>${options}<option value="__manage">管理族群…</option></select>`;
}

function renderCard() {
  const el = $('#card');
  if (!state.cardCode) {
    el.hidden = true;
    return;
  }
  const fresh = state.snapshot?.stocks.find((s) => s.code === state.cardCode);
  if (fresh) state.cardLast = fresh;
  const s = state.cardLast;
  if (!s) {
    el.hidden = true;
    state.cardCode = null;
    return;
  }
  const watched = state.watchCodes.includes(s.code);
  const dir = s.change > 0 ? 'up' : s.change < 0 ? 'down' : '';
  const dataHtml = `
    <h3>${escapeHtml(s.code)} ${escapeHtml(s.name)} <span class="sub">${escapeHtml(s.industry)} · ${escapeHtml(s.market)}</span></h3>
    <div class="px"><b class="${dir}">${fmtPrice(s.price)}</b><span class="${dir}">${fmtChange(s.change)}（${fmtPct(s.change_pct)}）</span></div>
    <table>
      <tr><td>開盤</td><td>${fmtPrice(s.open)}</td><td>昨收</td><td>${fmtPrice(s.prev_close)}</td></tr>
      <tr><td>最高</td><td>${fmtPrice(s.high)}</td><td>最低</td><td>${fmtPrice(s.low)}</td></tr>
      <tr><td>振幅</td><td>${s.amplitude_pct === null ? '—' : s.amplitude_pct.toFixed(2) + '%'}</td><td>週漲跌</td><td>${fmtPct(s.week_pct)}</td></tr>
      <tr><td>成交量</td><td>${fmtNum(s.volume_lots, 0)} 張</td><td>成交值</td><td>${fmtTurnover(s.turnover_100m)}</td></tr>
      <tr><td>市值</td><td colspan="3" style="text-align:right">${fmtCap(s.market_cap)}</td></tr>
    </table>
    ${fresh ? '' : '<div class="stale-note">資料未更新（此代號不在最新報價中）</div>'}`;
  // The action part (buttons, group dropdown, membership line) is rebuilt only when it changes,
  // so a snapshot poll does not close an open dropdown or re-fetch the membership line.
  const actionsSig = JSON.stringify([s.code, watched, getGroups()]);
  if (el.dataset.actionsSig !== actionsSig || !$('#cardData')) {
    el.dataset.actionsSig = actionsSig;
    el.innerHTML = `<div id="cardData"></div>
    <div class="btns">
      <button type="button" class="${watched ? '' : 'primary'}" id="cardWatch">${watched ? '★ 移除自選' : '☆ 加入自選'}</button>
      <a href="https://histock.tw/stock/${encodeURIComponent(s.code)}" target="_blank" rel="noopener noreferrer">HiStock ↗</a>
      <button type="button" id="cardClose" aria-label="關閉">✕</button>
    </div>
    ${groupSelect(s.code)}
    <div class="memb" data-memb="${escapeHtml(s.code)}"></div>`;
    $('#cardWatch').addEventListener('click', () => setWatched(s.code, !watched));
    $('#cardClose').addEventListener('click', closeCard);
    fillMembership(el);
    $('#cardGroup').addEventListener('change', async (e) => {
      const value = e.target.value;
      e.target.value = '';
      if (value === '__manage') return openGroupPanel();
      if (!value) return;
      try {
        await addToGroup(value, s.code);
        toast(`已加入族群「${value}」`);
      } catch (err) {
        toast(`加入失敗：${err.message}`);
      }
    });
  }
  $('#cardData').innerHTML = dataHtml;
  el.hidden = false;
}

// ---- toast ------------------------------------------------------------------

let toastTimer = null;
function toast(text) {
  const el = $('#toast');
  el.textContent = text;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 3000);
}

// ---- events -----------------------------------------------------------------

function bindEvents() {
  for (const seg of document.querySelectorAll('.seg[data-group]')) {
    seg.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      const group = seg.dataset.group;
      if (group in state.filters) {
        state.filters[group] = group === 'watchOnly' ? b.dataset.value === 'true' : b.dataset.value;
      } else {
        state.view[group] = b.dataset.value;
      }
      savePrefs();
      render();
    });
  }
  $('#includeEtf').addEventListener('change', (e) => {
    state.filters.includeEtf = e.target.checked;
    savePrefs();
    render();
  });
  for (const b of document.querySelectorAll('.tabs button')) {
    b.addEventListener('click', () => {
      state.tab = b.dataset.tab;
      savePrefs();
      renderControls();
    });
  }
  for (const [tableId, sortKey] of [['#matrix', 'industry'], ['#watch', 'watch']]) {
    const table = $(tableId);
    table.tHead.addEventListener('click', (e) => {
      const th = e.target.closest('th[data-sort]');
      if (!th) return;
      const sort = state.sort[sortKey];
      const key = th.dataset.sort;
      const textual = key === 'name' || key === 'code';
      if (sort.key === key) sort.dir = sort.dir === 'asc' ? 'desc' : 'asc';
      else Object.assign(sort, { key, dir: textual ? 'asc' : 'desc' });
      savePrefs();
      render();
    });
  }
  const matrixBody = $('#matrix').tBodies[0];
  matrixBody.addEventListener('mouseover', (e) => {
    const tr = e.target.closest('tr[data-industry]');
    if (tr && tr.dataset.industry !== state.hoverIndustry) highlightIndustry(tr.dataset.industry);
  });
  matrixBody.addEventListener('mouseleave', () => highlightIndustry(null));
  matrixBody.addEventListener('click', (e) => {
    const tr = e.target.closest('tr[data-industry]');
    if (!tr) return;
    zoomTo(tr.dataset.industry);
  });
  $('#watch').tBodies[0].addEventListener('click', (e) => {
    const rm = e.target.closest('[data-remove]');
    if (rm) {
      e.stopPropagation();
      setWatched(rm.dataset.remove, false);
      return;
    }
    const tr = e.target.closest('tr[data-code]');
    if (tr && state.snapshot?.stocks.some((s) => s.code === tr.dataset.code)) openCard(tr.dataset.code);
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || state.mode !== 'live') return;
    if (!$('#settings').hidden) $('#settings').hidden = true;
    else if (state.cardCode) closeCard();
    else if (state.zoomIndustry) zoomOut();
  });

  // refresh
  $('#refreshBtn').addEventListener('click', async () => {
    const btn = $('#refreshBtn');
    btn.disabled = true;
    try {
      const { resp, body } = await api('/api/refresh', { method: 'POST' });
      if (resp.status === 429) toast(`${body?.retry_after ?? 30} 秒後可再更新`);
      else if (resp.ok) {
        toast('更新中…');
        schedulePoll(2500);
      } else toast('更新失敗');
    } catch {
      toast('更新失敗（無法連線）');
    } finally {
      setTimeout(() => (btn.disabled = false), 1500);
    }
  });

  // settings
  $('#settingsBtn').addEventListener('click', () => {
    const pop = $('#settings');
    pop.hidden = !pop.hidden;
    if (!pop.hidden) {
      $('#pollSeconds').value = state.settings.poll_seconds;
      $('#settingsErr').textContent = '';
      $('#pollSeconds').focus();
    }
  });
  $('#settingsCancel').addEventListener('click', () => ($('#settings').hidden = true));
  const save = async () => {
    const value = Number($('#pollSeconds').value);
    if (!Number.isInteger(value) || value < 30 || value > 600) {
      $('#settingsErr').textContent = '請輸入 30 到 600 之間的整數';
      return;
    }
    let resp, body;
    try {
      ({ resp, body } = await api('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ poll_seconds: value }),
      }));
    } catch {
      $('#settingsErr').textContent = '儲存失敗（無法連線）';
      return;
    }
    if (!resp.ok || !body) {
      $('#settingsErr').textContent = '儲存失敗';
      return;
    }
    state.settings = body;
    $('#settings').hidden = true;
    renderStatus();
    toast(`盤中每 ${body.poll_seconds} 秒更新`);
  };
  $('#settingsSave').addEventListener('click', save);
  $('#pollSeconds').addEventListener('keydown', (e) => e.key === 'Enter' && save());
}

function setMode(mode) {
  state.mode = mode;
  savePrefs();
  const live = mode === 'live';
  $('#liveView').hidden = !live;
  $('#liveControls').hidden = !live;
  $('#historyView').hidden = live;
  $('#histControls').hidden = live;
  for (const b of $('#modeSwitch').querySelectorAll('button')) {
    b.classList.toggle('on', b.dataset.mode === mode);
    b.setAttribute('aria-pressed', String(b.dataset.mode === mode));
  }
  if (live) {
    chart.resize();
    if (location.hash !== '#live') history.replaceState(null, '', '#live'); // bonus-12
  }
  else showHistory();
}

// ---- boot -------------------------------------------------------------------

async function main() {
  loadPrefs();
  if (typeof echarts === 'undefined') {
    $('#empty').hidden = false;
    $('#empty').textContent = '無法載入 ECharts（需要網路連線到 cdnjs.cloudflare.com）。';
    return;
  }
  initChart();
  bindEvents();
  onGroupsChange(() => {
    renderCard();
    if (liveGrouping.by === 'custom') loadLiveMapping('custom', true); // bonus-17
  });
  loadGroups().catch(() => {});
  $('#modeSwitch').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-mode]');
    if (b) setMode(b.dataset.mode);
  });
  render();
  if (location.hash.startsWith('#history')) state.mode = 'history'; // bonus-12: bookmarked view
  else if (location.hash === '#live') state.mode = 'live';
  setMode(state.mode);
  window.addEventListener('hashchange', () => {
    // bonus-12: a pasted bookmark switches mode; history.js then applies its date/grouping
    const want = location.hash.startsWith('#history') ? 'history' : location.hash === '#live' ? 'live' : null;
    if (want && want !== state.mode) setMode(want);
  });
  try {
    const [{ body: settings }] = await Promise.all([api('/api/settings'), loadWatchlist()]);
    if (settings) state.settings = settings;
  } catch {
    /* rendered as connection error by pollSnapshot */
  }
  await pollSnapshot();
  schedulePoll();
}

main();

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

// ---- bonus-05: market breadth bar in the live top bar ----
function renderLiveBreadth(stocks) {
  let el = $('#mbarLive');
  if (!el) {
    el = document.createElement('span');
    el.id = 'mbarLive';
    $('#status').before(el);
  }
  el.innerHTML = breadthBarHtml(marketBreadth(stocks));
}

// ---- bonus-11: 20-day industry return in the live matrix (from stored history) ----

function withPeriods(rows) {
  ensureLivePeriods();
  return rows.map((r) => ({ ...r, perf_20: livePeriods.byGroup[r.name]?.perf_20 ?? null, vol_ratio: volRatio(r) }));
}

async function ensureLivePeriods() {
  if (livePeriods.loading || Date.now() - (livePeriods.checkedAt || 0) < 10 * 60 * 1000) return;
  livePeriods.loading = true;
  livePeriods.checkedAt = Date.now();
  try {
    const days = await fetch('/api/history/days', { cache: 'no-store' }).then((r) => r.json());
    const latest = days.days.find((d) => d.status === 'ok')?.date;
    if (latest && latest !== livePeriods.date) {
      const data = await fetch(`/api/history/periods?date=${latest}&grouping=industry`, { cache: 'no-store' }).then((r) => r.json());
      const turnover = await fetch('/api/history/turnover-avg?days=20', { cache: 'no-store' }).then((r) => r.json()); // bonus-16
      livePeriods.byGroup = data.groups || {};
      livePeriods.turnoverAvg = turnover.avg || {};
      livePeriods.date = latest; // only after both succeeded, so a failure is retried
      render();
    }
  } catch {
    /* history not available yet: column stays empty */
  } finally {
    livePeriods.loading = false;
  }
}

// ---- bonus-16: 量能 — today's industry turnover vs its 20-day daily average ---------------

const SESSION_MINUTES = 270; // 09:00–13:30

/** Share of the session elapsed at the snapshot time (1 after the close); intraday turnover is
 * compared with the same share of a full day's average, the usual intraday relative-volume rule. */
function sessionFraction() {
  const snap = state.snapshot;
  if (!snap?.market_open || !snap.as_of) return 1;
  const t = new Date(snap.as_of);
  const taipei = new Date(t.getTime() + (t.getTimezoneOffset() + 480) * 60000);
  const minutes = (taipei.getHours() - 9) * 60 + taipei.getMinutes();
  return Math.min(Math.max(minutes / SESSION_MINUTES, 0.05), 1);
}

function volRatio(r) {
  const avg = livePeriods.turnoverAvg?.[r.name];
  if (!avg || state.filters.watchOnly) return null;
  const markets = state.filters.market === 'all' ? Object.keys(avg) : [state.filters.market];
  const base = markets.reduce((a, m) => a + (avg[m] || 0), 0) * sessionFraction();
  return base > 0 ? (r.turnover_100m * 1e8) / base : null;
}

function volRatioCell(v) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '<td class="muted">—</td>';
  return `<td class="c" style="background:${colorFor((v - 1) * 50, 50)}">${v.toFixed(1)}x</td>`;
}

// ---- bonus-17: live heatmap grouping switch (官方產業／自訂族群／概念股) ----------------------


function applyLiveGrouping(stocks) {
  renderLiveGroupingSeg();
  if (liveGrouping.by === 'industry') return stocks;
  const map = liveGrouping.maps[liveGrouping.by];
  if (!map) {
    loadLiveMapping(liveGrouping.by);
    return stocks; // official industries until the mapping arrives
  }
  return regroupStocks(stocks, map);
}

async function loadLiveMapping(name, force = false) {
  if (liveGrouping.loading[name] || (liveGrouping.maps[name] && !force)) return;
  liveGrouping.loading[name] = true;
  try {
    const resp = await fetch(`/api/groupings/${name}`, { cache: 'no-store' });
    if (!resp.ok) throw new Error(resp.status === 404 ? '概念股分類尚未載入完成' : `HTTP ${resp.status}`);
    liveGrouping.maps[name] = (await resp.json()).mapping;
    render();
  } catch (err) {
    if (liveGrouping.by === name) {
      toast(`無法使用此分組：${err.message}`);
      setLiveGrouping('industry');
    }
  } finally {
    liveGrouping.loading[name] = false;
  }
}

function setLiveGrouping(by) {
  liveGrouping.by = by;
  state.zoomIndustry = null; // names differ between groupings
  try {
    localStorage.setItem('openmarket.live.grouping', JSON.stringify(by));
  } catch {
    /* ignore */
  }
  render();
}

function renderLiveGroupingSeg() {
  let seg = $('#liveGrouping');
  if (!seg) {
    seg = document.createElement('div');
    seg.className = 'seg';
    seg.id = 'liveGrouping';
    seg.setAttribute('role', 'group');
    seg.setAttribute('aria-label', '族群分類');
    seg.innerHTML = '<button data-value="industry">官方產業</button><button data-value="custom">自訂族群</button><button data-value="concept">概念股</button>';
    $('#liveControls .seg[data-group="market"]').before(seg);
    seg.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-value]');
      if (b && b.dataset.value !== liveGrouping.by) setLiveGrouping(b.dataset.value);
    });
  }
  for (const b of seg.querySelectorAll('button')) {
    b.classList.toggle('on', b.dataset.value === liveGrouping.by);
    b.setAttribute('aria-pressed', String(b.dataset.value === liveGrouping.by));
  }
}
