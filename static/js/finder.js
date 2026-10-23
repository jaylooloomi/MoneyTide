// N · 資金連動搜尋: groups of stocks one pool of money moved together (server: /api/history/finder).
// 找法1 searches inside the known groupings, 找法2 a pool from the day's rankings. Every threshold is
// tunable here and kept in localStorage. A result card opens K's view for its members
// (/api/history/linkage-codes). Pure HTML builders on top (node --test); panel wiring below.

import { addToGroup, createGroup } from './groups.js';
import { renderBody } from './linkage.js';
import { colorFor, escapeHtml, fmtPct, fmtTurnover, toCsv } from './transform.js';

export const METHODS = { known: '找法1 · 已知分類', new: '找法2 · 排行候選' };
const KIND_COLOR = { 已知族群: '#2c4a6b', 已知族群的延伸: '#6b5a1e', 跨族群新組合: '#b8301a' };
const GROUPINGS = { industry: '官方產業', custom: '自訂族群', concept: '概念股', chain: '細產業', news: '新聞族群' };
const SOURCES = { gain: '漲幅', turnover: '週轉率', share_z: '比重暴增' };

/** Tunable fields: [key, label, kind, method ('' = both), help]. Defaults come from the server. */
export const FIELDS = [
  ['min_amplitude', '振幅 >（%）', 'num', 'known', '只看當天振幅（最高 − 最低）÷ 昨收 超過這個 % 的股票'],
  ['min_volume_lots', '成交量 ≥（張）', 'int', 'known', '只看當天成交量至少這麼多張的股票（1 張＝1,000 股）'],
  ['daily_r', '日相關 ≥', 'num', 'known', '20 日（或下面的天數）日漲跌幅的相關係數'],
  ['daily_window', '日相關天數', 'int', 'known', ''],
  ['new_daily_r', '日相關 ≥', 'num', 'new', '新組合的歷史短，用較短的窗口'],
  ['new_daily_window', '日相關天數', 'int', 'new', ''],
  ['pool_top', '各排行取前', 'int', 'new', '漲幅、週轉率、比重暴增各取前 N 名'],
  ['new_min_volume_lots', '成交量 ≥（張）', 'int', 'new', '候選池只收當天成交量至少這麼多張的股票（1 張＝1,000 股）'],
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
const NAME_MAX = 30; // groups.py MAX_NAME_LEN

/**
 * Default name when a found group is saved as a 自訂族群: "N1022 華經+驊宏資…" — the date and the
 * members, cut to the server's 30-character limit, without the characters a group name may not hold.
 */
export function defaultGroupName(g, date) {
  const md = String(date || '').slice(5).replace('-', '');
  const names = g.members.map((m) => m.name.replace(/[*＊]/g, '')).join('+');
  const raw = `N${md} ${names}`.replace(/[/\\<>"',]/g, '');
  return raw.length > NAME_MAX ? `${raw.slice(0, NAME_MAX - 1)}…` : raw;
}

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
      const themes = m.themes?.length ? `　📰 ${m.themes.join('、')}` : '';
      return `<span class="fd-chip${outside.has(m.code) ? ' out' : ''}" style="background:${colorFor(m.change_pct, 7)}" title="${escapeHtml(m.code)} ${escapeHtml(m.name)}${pool}　${extra}${m.turnover_rate != null ? `　週轉率 ${m.turnover_rate.toFixed(1)}%` : ''}${escapeHtml(themes)}${outside.has(m.code) ? '　（不在最接近的分類裡）' : ''}">${escapeHtml(m.name)} <small>${fmtPct(m.change_pct)}</small>${m.locked_at ? ' 🔒' : ''}</span>`;
    })
    .join('');
  const money = g.turnover_100m != null
    ? `<div class="fd-money">💰 成交值 <b>${fmtTurnover(g.turnover_100m)}</b>${g.turnover_share != null ? `（占全市場 <b>${g.turnover_share.toFixed(2)}%</b>）` : ''}　平均漲幅 <b class="${g.avg_pct > 0 ? 'up' : g.avg_pct < 0 ? 'down' : ''}">${fmtPct(g.avg_pct)}</b></div>`
    : '';
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
  const themes = g.themes?.length
    ? `<div class="fd-themes" title="近 3 個新聞日提到這幾檔的題材關鍵字（括號＝提到幾檔）">📰 題材：${g.themes.map((t) => `${escapeHtml(t.term)}${g.members.length > 1 ? `（${t.count}）` : ''}`).join('、')}</div>`
    : '';
  const seen = g.seen_days?.length
    ? `<span class="fd-seen" title="前幾天也找到同一組合（成員重疊過半）：${g.seen_days.map((x) => x.slice(5)).join('、')}">🔁 近 ${g.checked_days + 1} 天第 ${g.seen_days.length + 1} 次</span>`
    : g.checked_days
      ? '<span class="fd-seen new" title="前幾天的結果裡沒有這個組合">🆕 首次</span>'
      : '';
  return `<div class="fd-card" data-i="${i}">
    <div class="fd-top"><span class="link-badge" style="background:${KIND_COLOR[g.kind] || '#3a3e48'}">${escapeHtml(g.kind)}</span>
      <span class="fd-title">${title}</span>${seen}<span class="muted">${g.members.length} 檔</span>
      <button type="button" class="icon fd-save" data-save="${i}" title="把這群股票存成自訂族群，之後在 B／C／K 追蹤">＋族群</button></div>
    <div class="fd-chips">${chips}</div>${money}
    <div class="fd-facts">${facts}</div>${themes}${news}
  </div>`;
}

const KINDS = ['已知族群', '已知族群的延伸', '跨族群新組合'];

/**
 * Filter chips over the found groups (no recompute): 找法1 by the grouping a group came from (a group
 * found in several groupings counts under each), 找法2 by kind. → [{key, label, n}], 全部 first.
 */
export function filterOptions(d) {
  const groups = d?.groups || [];
  const opts = [{ key: 'all', label: '全部', n: groups.length }];
  if (d?.method === 'new') {
    for (const k of KINDS) opts.push({ key: k, label: k === '已知族群的延伸' ? '延伸' : k, n: groups.filter((g) => g.kind === k).length });
  } else {
    for (const label of d?.groupings || []) opts.push({ key: label, label, n: groups.filter((g) => g.sources?.some((s) => s.label === label)).length });
  }
  return opts;
}

export function matchesFilter(g, key, method) {
  if (!key || key === 'all') return true;
  return method === 'new' ? g.kind === key : !!g.sources?.some((s) => s.label === key);
}

export function filterHtml(d, current) {
  return `<div class="fd-filter seg">${filterOptions(d)
    .map((o) => `<button type="button" data-filter="${escapeHtml(o.key)}"${o.key === current ? ' class="on"' : ''}${o.n ? '' : ' disabled'}>${escapeHtml(o.label)} <small>${o.n}</small></button>`)
    .join('')}</div>`;
}

/**
 * CSV of the cards on screen (the chip filter applies): one row per member, with its group's figures
 * and the thresholds used, so runs with different settings can be compared in Excel.
 * → [file name, header, rows] or null when nothing is shown.
 */
export function csvExport(d, filter = 'all') {
  if (!d?.groups?.length) return null;
  const groups = d.groups.map((g, i) => [g, i + 1]).filter(([g]) => matchesFilter(g, filter, d.method));
  if (!groups.length) return null;
  const p = d.params || {};
  const cond =
    d.method === 'new'
      ? `排行前${p.pool_top} 成交量≥${p.new_min_volume_lots}張 日R≥${p.new_daily_r}(${p.new_daily_window}日)`
      : `振幅>${p.min_amplitude}% 成交量≥${p.min_volume_lots}張 日R≥${p.daily_r}(${p.daily_window}日)`;
  const header = [
    '日期', '找法', '群組#', '類型', '來源／最接近分類', '代號', '名稱', '漲幅%', '週轉率%', '振幅%', '高點時間', '起漲時間', '鎖漲停',
    '群組日R', '群組分時R', '高點差(分)', '起漲差(分)', '群組成交值(億)', '占全市場%', '群組平均漲幅%', '條件',
  ];
  const rows = groups.flatMap(([g, n]) => {
    const src = g.sources?.length ? g.sources.map((s) => `${s.label}:${s.group}`).join('／') : g.matches?.[0] ? `${g.matches[0].label}:${g.matches[0].group}(${Math.round(g.matches[0].overlap * 100)}%)` : '';
    const cut = (v) => (v == null ? '' : Math.round(v * 100) / 100);
    return g.members.map((m) => [
      d.date, METHODS[d.method] || d.method, n, g.kind, src, m.code, m.name, cut(m.change_pct), cut(m.turnover_rate), cut(m.amplitude_pct), m.peak || '', m.start || '', m.locked_at || '',
      g.daily_r ?? '', g.intraday_r ?? '', g.peak_spread ?? '', g.start_spread ?? '', g.turnover_100m ?? '', g.turnover_share ?? '', g.avg_pct ?? '', `${cond} 分時R≥${p.intraday_r} 高點差≤${p.peak_gap}分`,
    ]);
  });
  const tag = filter && filter !== 'all' ? `_${filter}` : '';
  return [`資金連動搜尋_${d.method === 'new' ? '找法2' : '找法1'}_${d.date}${tag}.csv`, header, rows];
}

export function statsText(d) {
  const s = d.stats || {};
  const sec = s.seconds?.total ?? Object.values(s.seconds || {}).reduce((a, x) => a + x, 0);
  const parts = [
    d.method === 'new' ? `候選池 ${s.pool} 檔` : '',
    `日相關通過 ${s.candidates} 組`,
    `抓分 K ${s.fetched} 檔`,
    `找到 ${s.groups} 群`,
    d.cached ? '（已存結果）' : `（${sec.toFixed(1)} 秒）`,
  ];
  if (d.missing_groupings?.length) parts.push(`尚未載入：${d.missing_groupings.map((g) => GROUPINGS[g] || g).join('、')}`);
  return parts.filter(Boolean).join('　·　');
}

/**
 * The funnel under the stats line: pairs reaching the intraday stage, what removed them (most first)
 * and how many passed — which threshold to loosen when nothing is found.
 */
export function funnelText(d) {
  const f = d?.stats?.funnel;
  if (!f?.pairs) return '';
  const why = Object.entries(f.rejected || {}).map(([k, n]) => `${k} ${n}`);
  if (f.no_bars) why.push(`沒有分 K ${f.no_bars}`);
  return `漏斗：進入分時比對 ${f.pairs} 對 → 刷掉：${why.join('、') || '無'} → 三關都過 ${f.passed} 對 → ${d.stats.groups} 群`;
}

/** Progress of a running search → {pct, text}: 日相關 0–15%, 抓分 K 15–90% (by stock), 比對 90–100%. */
export function progressView(p) {
  if (!p?.running) return { pct: 3, text: '準備中…' };
  const sec = p.seconds != null ? `　${p.seconds.toFixed(0)} 秒` : '';
  if (p.stage === 'daily') return { pct: 8, text: `① 計算日相關${sec}` };
  if (p.stage === 'fetch') {
    const frac = p.total ? p.done / p.total : 1;
    return { pct: 15 + Math.round(frac * 75), text: `② 抓分 K ${p.done}／${p.total} 檔${sec}` };
  }
  return { pct: 95, text: `③ 分時相關與高點比對${sec}` };
}

/**
 * One-click threshold sets. They only touch the linkage thresholds (daily R, intraday R, high gap);
 * 振幅, 成交量, groupings and pool settings stay as the user set them. 寬鬆 mostly loosens intraday R,
 * the test that removes the most pairs (10/22 funnel: 143 of 197).
 */
export const PRESETS = {
  strict: { label: '嚴格', values: { daily_r: 0.85, new_daily_r: 0.85, intraday_r: 0.6, peak_gap: 5 } },
  standard: { label: '標準', values: { daily_r: 0.8, new_daily_r: 0.8, intraday_r: 0.5, peak_gap: 8 } },
  loose: { label: '寬鬆', values: { daily_r: 0.7, new_daily_r: 0.75, intraday_r: 0.35, peak_gap: 15 } },
};

/** The preset the current values match exactly, or null (自訂). */
export function presetOf(params) {
  for (const [k, p] of Object.entries(PRESETS)) {
    if (Object.entries(p.values).every(([f, v]) => Number(params[f]) === v)) return k;
  }
  return null;
}

// ---- B's 🔗: N's stored 找法1 cards indexed by the group they came from -----------------

/** {`${grouping label}|${group}`: [found group]} from N's stored cards (a card can name several sources). */
export function finderMarkIndex(result) {
  const out = new Map();
  for (const g of result?.groups || []) {
    for (const s of g.sources || []) {
      const k = `${s.label}|${s.group}`;
      if (!out.has(k)) out.set(k, []);
      out.get(k).push(g);
    }
  }
  return out;
}

export function finderMarkTitle(found) {
  const r = (v) => (v == null ? '—' : v.toFixed(2));
  return `N 資金連動搜尋（找法1）在這個族群找到共同注資：\n${found
    .map((g) => `${g.members.map((m) => m.name).join('、')}（日R ${r(g.daily_r)}、分時R ${r(g.intraday_r)}、高點差 ${g.peak_spread ?? '—'} 分）`)
    .join('\n')}`;
}

// ---- panel --------------------------------------------------------------------------------------

const PREF_KEY = 'openmarket.history.finder';
const DEFAULTS = {
  min_amplitude: 3,
  min_volume_lots: 300,
  new_min_volume_lots: 300,
  daily_r: 0.8, daily_window: 20, new_daily_r: 0.8, new_daily_window: 10, pool_top: 50,
  intraday_r: 0.5, intraday_sessions: 3, peak_gap: 8, start_gap: '', require_burst: false, dense: 0.7, min_size: 2,
  groupings: Object.keys(GROUPINGS), pool_sources: Object.keys(SOURCES),
};

export function mountFinderPanel(container, { onStock }) {
  const sec = document.createElement('section');
  sec.id = 'hFinderPanel';
  sec.className = 'panel hN';
  const pref = { method: 'known', params: { ...DEFAULTS }, filter: { known: 'all', new: 'all' } };
  try {
    const saved = JSON.parse(localStorage.getItem(PREF_KEY) || '{}');
    if (saved.method in METHODS) pref.method = saved.method;
    Object.assign(pref.params, saved.params || {});
    Object.assign(pref.filter, saved.filter || {});
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
      <button type="button" class="icon wide" id="hFinderCsv" title="匯出目前顯示的卡片（依上面的篩選；Excel 可開）">CSV</button>
      <span class="muted" id="hFinderStats" style="margin-left:auto"></span></div>
    <div class="fd-funnel muted" id="hFinderFunnel" title="每一關刷掉幾對：卡最多的那一關，就是要放寬的條件"></div>
    <div class="fd-form" id="hFinderForm" hidden></div>
    <div class="fd-progress" id="hFinderProgress" hidden><div class="fd-bar"><span></span></div><div class="fd-ptext"></div></div>
    <div id="hFinderBody" style="padding:8px 10px"><p class="hint">捲到這裡就會載入這一天的結果。</p></div>
    <div id="hFinderDetail" class="fd-detail" hidden></div>`;
  container.appendChild(sec);
  const body = sec.querySelector('#hFinderBody');
  const form = sec.querySelector('#hFinderForm');
  const detail = sec.querySelector('#hFinderDetail');
  const state = { ticket: 0, date: null, data: null, loadedKey: null, timer: null, visible: false, stopRace: () => {}, detailTicket: 0, poll: null };
  const bar = sec.querySelector('#hFinderProgress');
  function showProgress(p) {
    const v = progressView(p);
    bar.querySelector('.fd-bar span').style.width = `${v.pct}%`;
    bar.querySelector('.fd-ptext').textContent = v.text;
  }
  function startProgress(query) {
    clearInterval(state.poll);
    showProgress(null);
    // a stored result comes back at once: only show the bar when the search takes a moment
    const shown = setTimeout(() => (bar.hidden = false), 400);
    state.poll = setInterval(async () => {
      try {
        const r = await fetch(`/api/history/finder/progress?date=${encodeURIComponent(state.date)}&${query}`, { cache: 'no-store' });
        if (r.ok) showProgress(await r.json());
      } catch {
        /* keep the last state */
      }
    }, 500);
    return () => {
      clearTimeout(shown);
      clearInterval(state.poll);
      bar.hidden = true;
    };
  }

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
    const now = presetOf(p);
    const presets = `<span class="fd-presets seg" title="只改日相關、分時相關、高點差三個門檻">${Object.entries(PRESETS)
      .map(([k, x]) => `<button type="button" data-preset="${k}"${k === now ? ' class="on"' : ''}>${x.label}</button>`)
      .join('')}${now ? '' : '<button type="button" class="on" disabled>自訂</button>'}</span>`;
    form.innerHTML = `${presets}${fields}${lists}<button type="button" class="icon wide" data-act="defaults">恢復預設</button>`;
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
    drawMethod(); // the preset buttons follow the edited values (a hand edit becomes 自訂)
    schedule(true);
  });
  form.addEventListener('click', (e) => {
    const preset = e.target.closest('button[data-preset]')?.dataset.preset;
    if (preset) {
      Object.assign(pref.params, PRESETS[preset].values);
    } else if (e.target.dataset.act === 'defaults') {
      pref.params = { ...DEFAULTS };
    } else {
      return;
    }
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
  sec.querySelector('#hFinderCsv').addEventListener('click', () => {
    const out = csvExport(state.data, state.data ? pref.filter[state.data.method] : 'all');
    if (!out) return;
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([toCsv(out[1], out[2])], { type: 'text/csv;charset=utf-8' }));
    a.download = out[0];
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  const key = () => `${state.date}|${queryOf(pref.method, pref.params)}`;
  async function load(refresh = false) {
    if (!state.date || (!refresh && key() === state.loadedKey)) return;
    state.loadedKey = key();
    const t = ++state.ticket;
    sec.classList.add('loading');
    const query = queryOf(pref.method, pref.params);
    const stopProgress = startProgress(query);
    try {
      const resp = await fetch(`/api/history/finder?date=${encodeURIComponent(state.date)}&${query}${refresh ? '&refresh=1' : ''}`, { cache: 'no-store' });
      const data = await resp.json();
      if (t !== state.ticket) return;
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      state.data = data;
      sec.querySelector('#hFinderStats').textContent = statsText(data);
      sec.querySelector('#hFinderFunnel').textContent = funnelText(data);
      drawCards();
    } catch (err) {
      if (t !== state.ticket) return;
      body.innerHTML = `<p class="hint">${escapeHtml(err.message)}</p>`;
    } finally {
      if (t === state.ticket) {
        sec.classList.remove('loading');
        stopProgress();
      }
    }
  }

  // cards of the stored result, filtered by the chips (switching a chip never recomputes)
  function drawCards() {
    const data = state.data;
    if (!data) return;
    if (!data.groups.length) {
      body.innerHTML = '<p class="hint">這一天沒有符合全部條件的群組。可以在「條件」放寬門檻。</p>';
      closeDetail();
      return;
    }
    let f = pref.filter[data.method] || 'all';
    if (!filterOptions(data).some((o) => o.key === f && o.n)) f = 'all';
    const cards = data.groups.map((g, i) => (matchesFilter(g, f, data.method) ? cardHtml(g, i) : '')).join('');
    body.innerHTML = `${filterHtml(data, f)}<div class="fd-cards">${cards}</div><p class="hint" style="margin:6px 0 0">點卡片看這群股票的連動動畫與走勢</p>`;
    closeDetail();
  }
  body.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-filter]');
    if (!b || !state.data) return;
    e.stopPropagation();
    pref.filter[state.data.method] = b.dataset.filter;
    save();
    drawCards();
  });

  function closeDetail() {
    state.detailTicket += 1;
    state.stopRace();
    detail.hidden = true;
    detail.innerHTML = '';
    for (const c of body.querySelectorAll('.fd-card')) c.classList.remove('on');
  }
  // ＋族群: save a found group as a 自訂族群 (the existing group API; creating one is idempotent)
  body.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-save]');
    if (!btn || !state.data) return;
    e.stopPropagation();
    const g = state.data.groups[Number(btn.dataset.save)];
    const name = window.prompt('存成自訂族群，名稱：', defaultGroupName(g, state.date));
    if (!name || !name.trim()) return;
    btn.disabled = true;
    btn.textContent = '儲存中…';
    try {
      await createGroup(name.trim());
      for (const m of g.members) await addToGroup(name.trim(), m.code);
      btn.textContent = '✓ 已存';
      btn.title = `已存成自訂族群「${name.trim()}」，可在「管理族群」修改`;
    } catch (err) {
      btn.disabled = false;
      btn.textContent = '＋族群';
      window.alert(`儲存失敗：${err.message}`);
    }
  }, true);
  body.addEventListener('click', async (e) => {
    if (e.target.closest('button[data-save]')) return;
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
      // the card's 🔁 and 📰 come along into the detail header
      const seen = card.querySelector('.fd-seen')?.outerHTML || '';
      const themes = card.querySelector('.fd-themes')?.textContent || '';
      detail.innerHTML = `<div class="panel-h"><b>${escapeHtml(g.members.map((m) => m.name).join('、'))}</b>${seen}${themes ? `<span class="fd-themes">${escapeHtml(themes)}</span>` : ''}<button type="button" class="icon" data-act="close" aria-label="關閉" style="margin-left:auto">✕</button></div><div class="fd-detail-body"></div>`;
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
