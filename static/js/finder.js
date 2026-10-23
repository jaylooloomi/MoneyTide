// N · 資金連動搜尋: groups of stocks one pool of money moved together (server: /api/history/finder).
// 找法1 searches inside the known groupings, 找法2 a pool from the day's rankings. Every threshold is
// tunable here and kept in localStorage. A result card opens K's view for its members
// (/api/history/linkage-codes). Pure HTML builders on top (node --test); panel wiring below.

import { renderBody } from './linkage.js';
import { colorFor, escapeHtml, fmtPct } from './transform.js';

export const METHODS = { known: '找法1 · 已知分類', new: '找法2 · 排行候選' };
const KIND_COLOR = { 已知族群: '#2c4a6b', 已知族群的延伸: '#6b5a1e', 跨族群新組合: '#b8301a' };
const GROUPINGS = { industry: '官方產業', custom: '自訂族群', concept: '概念股', chain: '細產業', news: '新聞族群' };
const SOURCES = { gain: '漲幅', turnover: '週轉率', share_z: '比重暴增' };

/** Tunable fields: [key, label, kind, method ('' = both), help]. Defaults come from the server. */
export const FIELDS = [
  ['daily_r', '日相關 ≥', 'num', 'known', '20 日（或下面的天數）日漲跌幅的相關係數'],
  ['daily_window', '日相關天數', 'int', 'known', ''],
  ['new_daily_r', '日相關 ≥', 'num', 'new', '新組合的歷史短，用較短的窗口'],
  ['new_daily_window', '日相關天數', 'int', 'new', ''],
  ['pool_top', '各排行取前', 'int', 'new', '漲幅、週轉率、比重暴增各取前 N 名'],
  ['intraday_r', '分時相關 ≥', 'num', '', '最近幾個交易日 5 分 K 報酬；鎖漲停的平線不計'],
  ['intraday_sessions', '分時天數', 'int', '', ''],
  ['peak_gap', '高點差 ≤（分）', 'int', '', '日內最高點（09:00–13:00）的時間差'],
  ['start_gap', '起漲差 ≤（分）', 'opt', '', '空白＝只顯示、不篩選'],
  ['require_burst', '要同時爆量', 'bool', '', '同一個 5 分鐘兩檔都爆量（≥ 3 倍自己的中位數）'],
  ['dense', '群內至少', 'num', '', '每檔要跟群內這個比例的人都符合條件（0.7＝七成）'],
  ['min_size', '最少幾檔', 'int', '', ''],
];

export function queryOf(method, params) {
  const q = new URLSearchParams({ method });
  for (const [key, , kind, m] of FIELDS) {
    if (m && m !== method) continue;
    const v = params[key];
    if (kind === 'opt') q.set(key, v === null || v === undefined || v === '' ? '' : String(v));
    else if (v !== undefined && v !== null && v !== '') q.set(key, String(v));
  }
  if (method === 'known' && params.groupings) q.set('groupings', params.groupings.join(','));
  if (method === 'new' && params.pool_sources) q.set('pool_sources', params.pool_sources.join(','));
  return q.toString();
}

const fmtR = (r) => (r === null || r === undefined ? '—' : r.toFixed(2));

export function cardHtml(g, i) {
  const title =
    g.sources?.length
      ? g.sources.map((s) => `${escapeHtml(s.label)}：${escapeHtml(s.group)}`).join('／')
      : g.matches?.length
        ? `最接近 ${escapeHtml(g.matches[0].label)}：${escapeHtml(g.matches[0].group)}（${Math.round(g.matches[0].overlap * 100)}%）`
        : '對不到已知分類';
  const outside = g.matches?.[0] && g.matches[0].overlap < 1 ? new Set(g.matches[0].outside) : new Set();
  const chips = g.members
    .map((m) => {
      const extra = [m.peak ? `高點 ${m.peak}` : '', m.locked_at ? `🔒${m.locked_at}` : '', m.start ? `起漲 ${m.start}` : ''].filter(Boolean).join('　');
      const pool = g.pool?.[m.code]?.length ? `（${g.pool[m.code].join('、')}）` : '';
      return `<span class="fd-chip${outside.has(m.code) ? ' out' : ''}" style="background:${colorFor(m.change_pct, 7)}" title="${escapeHtml(m.code)} ${escapeHtml(m.name)}${pool}　${extra}${m.turnover_rate != null ? `　週轉率 ${m.turnover_rate.toFixed(1)}%` : ''}${outside.has(m.code) ? '　（不在最接近的分類裡）' : ''}">${escapeHtml(m.name)} <small>${fmtPct(m.change_pct)}</small>${m.locked_at ? ' 🔒' : ''}</span>`;
    })
    .join('');
  const facts = [
    `日 R <b>${fmtR(g.daily_r)}</b>`,
    `分時 R <b>${fmtR(g.intraday_r)}</b>`,
    `高點差 <b>${g.peak_spread ?? '—'}</b> 分`,
    g.start_spread != null ? `起漲差 ${g.start_spread} 分` : '',
    g.together_bursts?.length ? `同時爆量 ${g.together_bursts.slice(0, 3).join('、')}` : '',
    g.inst_net ? `法人 ${g.inst_net > 0 ? '+' : '−'}${Math.abs(g.inst_net) >= 1e8 ? `${(Math.abs(g.inst_net) / 1e8).toFixed(1)} 億` : `${Math.round(Math.abs(g.inst_net) / 1e4).toLocaleString()} 萬`}` : '',
    g.resolution === 5 ? '<span class="muted">5 分 K</span>' : '',
  ]
    .filter(Boolean)
    .join('　');
  const news = g.news?.length ? `<div class="fd-news">📰 ${g.news.map((t) => escapeHtml(t)).join('<br>📰 ')}</div>` : '';
  return `<div class="fd-card" data-i="${i}">
    <div class="fd-top"><span class="link-badge" style="background:${KIND_COLOR[g.kind] || '#3a3e48'}">${escapeHtml(g.kind)}</span>
      <span class="fd-title">${title}</span><span class="muted">${g.members.length} 檔</span></div>
    <div class="fd-chips">${chips}</div>
    <div class="fd-facts">${facts}</div>${news}
  </div>`;
}

export function statsText(d) {
  const s = d.stats || {};
  const sec = s.seconds?.total ?? Object.values(s.seconds || {}).reduce((a, x) => a + x, 0);
  const parts = [
    d.method === 'new' ? `候選池 ${s.pool} 檔` : `分類 ${d.groupings?.join('、') || ''}`,
    `日相關通過 ${s.candidates} 組`,
    `抓分 K ${s.fetched} 檔`,
    `找到 ${s.groups} 群`,
    d.cached ? '（已存結果）' : `（${sec.toFixed(1)} 秒）`,
  ];
  if (d.missing_groupings?.length) parts.push(`尚未載入：${d.missing_groupings.map((g) => GROUPINGS[g] || g).join('、')}`);
  return parts.join('　·　');
}

// ---- panel --------------------------------------------------------------------------------------

const PREF_KEY = 'openmarket.history.finder';
const DEFAULTS = {
  daily_r: 0.8, daily_window: 20, new_daily_r: 0.8, new_daily_window: 10, pool_top: 50,
  intraday_r: 0.5, intraday_sessions: 3, peak_gap: 8, start_gap: '', require_burst: false, dense: 0.7, min_size: 2,
  groupings: Object.keys(GROUPINGS), pool_sources: Object.keys(SOURCES),
};

export function mountFinderPanel(container, { onStock }) {
  const sec = document.createElement('section');
  sec.id = 'hFinderPanel';
  sec.className = 'panel hN';
  const pref = { method: 'known', params: { ...DEFAULTS } };
  try {
    const saved = JSON.parse(localStorage.getItem(PREF_KEY) || '{}');
    if (saved.method in METHODS) pref.method = saved.method;
    Object.assign(pref.params, saved.params || {});
  } catch {
    /* defaults */
  }
  const save = () => {
    try {
      localStorage.setItem(PREF_KEY, JSON.stringify(pref));
    } catch {
      /* ignore */
    }
  };
  sec.innerHTML = `<div class="panel-h"><b>N · 資金連動搜尋</b>
      <div class="seg" id="hFinderMethod">${Object.entries(METHODS).map(([k, l]) => `<button data-value="${k}">${l}</button>`).join('')}</div>
      <button type="button" class="icon wide" id="hFinderToggle">條件 ▾</button>
      <button type="button" class="icon wide" id="hFinderRun" title="用目前的條件重新計算這一天">重新計算</button>
      <span class="muted" id="hFinderStats" style="margin-left:auto"></span></div>
    <div class="fd-form" id="hFinderForm" hidden></div>
    <div id="hFinderBody" style="padding:8px 10px"><p class="hint">捲到這裡就會載入這一天的結果。</p></div>
    <div id="hFinderDetail" class="fd-detail" hidden></div>`;
  container.appendChild(sec);
  const body = sec.querySelector('#hFinderBody');
  const form = sec.querySelector('#hFinderForm');
  const detail = sec.querySelector('#hFinderDetail');
  const state = { ticket: 0, date: null, data: null, loadedKey: null, timer: null, visible: false, stopRace: () => {}, detailTicket: 0 };

  function drawMethod() {
    for (const b of sec.querySelectorAll('#hFinderMethod button')) b.classList.toggle('on', b.dataset.value === pref.method);
    const p = pref.params;
    const fields = FIELDS.filter(([, , , m]) => !m || m === pref.method)
      .map(([key, label, kind, , help]) => {
        const v = p[key];
        const input =
          kind === 'bool'
            ? `<input type="checkbox" data-key="${key}"${v ? ' checked' : ''}>`
            : `<input class="field" data-key="${key}" data-kind="${kind}" value="${escapeHtml(v ?? '')}" size="4">`;
        return `<label title="${escapeHtml(help)}">${escapeHtml(label)} ${input}</label>`;
      })
      .join('');
    const lists =
      pref.method === 'known'
        ? `<span class="fd-list">分類：${Object.entries(GROUPINGS).map(([k, l]) => `<label><input type="checkbox" data-list="groupings" value="${k}"${p.groupings.includes(k) ? ' checked' : ''}>${l}</label>`).join('')}</span>`
        : `<span class="fd-list">候選池：${Object.entries(SOURCES).map(([k, l]) => `<label><input type="checkbox" data-list="pool_sources" value="${k}"${p.pool_sources.includes(k) ? ' checked' : ''}>${l}</label>`).join('')}</span>`;
    form.innerHTML = `${fields}${lists}<button type="button" class="icon wide" data-act="defaults">恢復預設</button>`;
  }
  form.addEventListener('change', (e) => {
    const el = e.target;
    const p = pref.params;
    if (el.dataset.list) {
      const set = new Set(p[el.dataset.list]);
      if (el.checked) set.add(el.value);
      else set.delete(el.value);
      p[el.dataset.list] = [...set];
    } else if (el.dataset.key) {
      const k = el.dataset.key;
      if (el.type === 'checkbox') p[k] = el.checked;
      else if (el.dataset.kind === 'opt') p[k] = el.value.trim() === '' ? '' : Number(el.value);
      else if (el.value.trim() !== '' && Number.isFinite(Number(el.value))) p[k] = Number(el.value);
    }
    save();
    schedule(true);
  });
  form.addEventListener('click', (e) => {
    if (e.target.dataset.act !== 'defaults') return;
    pref.params = { ...DEFAULTS };
    save();
    drawMethod();
    schedule(true);
  });
  sec.querySelector('#hFinderToggle').addEventListener('click', (e) => {
    form.hidden = !form.hidden;
    e.target.textContent = form.hidden ? '條件 ▾' : '條件 ▴';
  });
  sec.querySelector('#hFinderMethod').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (!b || b.dataset.value === pref.method) return;
    pref.method = b.dataset.value;
    save();
    drawMethod();
    schedule(true);
  });
  sec.querySelector('#hFinderRun').addEventListener('click', () => load(true));

  const key = () => `${state.date}|${queryOf(pref.method, pref.params)}`;
  async function load(refresh = false) {
    if (!state.date || (!refresh && key() === state.loadedKey)) return;
    state.loadedKey = key();
    const t = ++state.ticket;
    sec.classList.add('loading');
    try {
      const resp = await fetch(`/api/history/finder?date=${encodeURIComponent(state.date)}&${queryOf(pref.method, pref.params)}${refresh ? '&refresh=1' : ''}`, { cache: 'no-store' });
      const data = await resp.json();
      if (t !== state.ticket) return;
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      state.data = data;
      sec.querySelector('#hFinderStats').textContent = statsText(data);
      body.innerHTML = data.groups.length
        ? `<div class="fd-cards">${data.groups.map(cardHtml).join('')}</div><p class="hint" style="margin:6px 0 0">點卡片看這群股票的連動動畫與走勢</p>`
        : '<p class="hint">這一天沒有符合全部條件的群組。可以在「條件」放寬門檻。</p>';
      closeDetail();
    } catch (err) {
      if (t !== state.ticket) return;
      body.innerHTML = `<p class="hint">${escapeHtml(err.message)}</p>`;
    } finally {
      if (t === state.ticket) sec.classList.remove('loading');
    }
  }

  function closeDetail() {
    state.detailTicket += 1;
    state.stopRace();
    detail.hidden = true;
    detail.innerHTML = '';
    for (const c of body.querySelectorAll('.fd-card')) c.classList.remove('on');
  }
  body.addEventListener('click', async (e) => {
    const card = e.target.closest('.fd-card');
    if (!card || !state.data) return;
    const g = state.data.groups[Number(card.dataset.i)];
    const wasOn = card.classList.contains('on');
    closeDetail();
    if (wasOn) return;
    card.classList.add('on');
    const t = state.detailTicket;
    detail.hidden = false;
    detail.innerHTML = '<p class="hint">載入連動資料…</p>';
    try {
      const codes = g.members.map((m) => m.code).join(',');
      const resp = await fetch(`/api/history/linkage-codes?date=${encodeURIComponent(state.date)}&codes=${encodeURIComponent(codes)}`, { cache: 'no-store' });
      const d = await resp.json();
      if (t !== state.detailTicket) return;
      if (!resp.ok) throw new Error(d.detail || `HTTP ${resp.status}`);
      detail.innerHTML = `<div class="panel-h"><b>${escapeHtml(g.members.map((m) => m.name).join('、'))}</b><button type="button" class="icon" data-act="close" aria-label="關閉" style="margin-left:auto">✕</button></div><div class="fd-detail-body"></div>`;
      state.stopRace = renderBody(detail.querySelector('.fd-detail-body'), d, '20', onStock, '點一列看那檔的分時走勢');
    } catch (err) {
      if (t === state.detailTicket) detail.innerHTML = `<p class="hint">${escapeHtml(err.message)}</p>`;
    }
  });
  detail.addEventListener('click', (e) => {
    if (e.target.closest('[data-act="close"]')) closeDetail();
  });

  // follows the date, but only loads while on screen (results are precomputed after the close)
  const onScreen = () => {
    const r = sec.getBoundingClientRect();
    return r.bottom > 0 && r.top < innerHeight;
  };
  // now = the user changed the method or a threshold: load whether or not the panel is on screen
  function schedule(now = false) {
    clearTimeout(state.timer);
    if (now || state.visible || onScreen()) state.timer = setTimeout(load, now ? 300 : 700);
  }
  new IntersectionObserver((entries) => {
    state.visible = entries.some((x) => x.isIntersecting);
    schedule();
  }).observe(sec);
  container.addEventListener('scroll', () => (key() !== state.loadedKey ? schedule() : null), { passive: true });
  drawMethod();
  return {
    refresh(date) {
      state.date = date;
      schedule();
    },
  };
}
