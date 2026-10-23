// K · 族群連動性: daily / intraday correlation of a group's top members and the animated intraday-high
// timeline (server: /api/history/linkage). Pure HTML builders on top (node --test); panel wiring below.

import { mountRace } from './race.js';
import { colorFor, escapeHtml, fmtPct } from './transform.js';

const VERDICT_COLOR = { 群體圍攻: '#b8301a', 高度同步: '#b8301a', 中度連動: '#6b5a1e', 普通: '#6b5a1e', 單兵作戰: '#2c4a6b', 時間錯落: '#2c4a6b', 資料不足: '#3a3e48' };

// shown until a group is picked in B, so the panel is easy to find
const HINT = '<p class="hint" style="margin:4px 0">👆 在上方 <b>B 強勢族群排行</b>點一個族群，這裡會顯示它前 8 大成分股的日相關、分時相關與日內最高點時間（09:00–13:00）。</p>';
const fmtR = (r) => (r === null || r === undefined ? '—' : r.toFixed(2));
const badge = (text) => `<span class="link-badge" style="background:${VERDICT_COLOR[text] || '#3a3e48'}">${escapeHtml(text)}</span>`;

/** Correlation heat table: rows/cols = member names, r −1…1 coloured red (together) / green (apart). */
export function matrixHtml(names, matrix) {
  if (!matrix?.length) return '<p class="hint">資料不足</p>';
  const head = names.map((n) => `<th title="${escapeHtml(n)}"><span class="clip" style="max-width:4em">${escapeHtml(n)}</span></th>`).join('');
  const rows = matrix
    .map(
      (row, i) =>
        `<tr><td class="l"><span class="clip" style="max-width:6em" title="${escapeHtml(names[i])}">${escapeHtml(names[i])}</span></td>${row
          .map((r, j) => (i === j ? '<td class="muted">—</td>' : `<td class="c" style="background:${colorFor(r === null ? null : (r - 0.3) * 100, 50)}" title="${escapeHtml(names[i])} × ${escapeHtml(names[j])}">${fmtR(r)}</td>`))
          .join('')}</tr>`,
    )
    .join('');
  return `<table class="grid link-matrix"><thead><tr><th></th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

const SMALL_MATRIX = 12; // up to this many members the matrix shows its numbers

/**
 * Order for a large matrix so members that move together sit next to each other: start from the
 * member with the highest mean R, then keep appending the unplaced member closest to the last one.
 */
export function clusterOrder(matrix) {
  const n = matrix.length;
  const mean = (i) => {
    const v = matrix[i].filter((r, j) => j !== i && r !== null);
    return v.length ? v.reduce((a, r) => a + r, 0) / v.length : -Infinity;
  };
  const left = new Set(Array.from({ length: n }, (_, i) => i));
  let cur = [...left].sort((a, b) => mean(b) - mean(a))[0];
  const order = [];
  while (left.size) {
    order.push(cur);
    left.delete(cur);
    if (!left.size) break;
    const row = matrix[cur];
    cur = [...left].sort((a, b) => (row[b] ?? -Infinity) - (row[a] ?? -Infinity) || mean(b) - mean(a))[0];
  }
  return order;
}

/** The n most correlated pairs [{a, b, r}] (names), strongest first. */
export function topPairs(names, matrix, n = 10) {
  const pairs = [];
  for (let i = 0; i < matrix.length; i++) for (let j = i + 1; j < matrix.length; j++) if (matrix[i][j] !== null) pairs.push({ a: names[i], b: names[j], r: matrix[i][j] });
  return pairs.sort((x, y) => y.r - x.r).slice(0, n);
}

/** The n members with the lowest mean R to the others [{name, r}] (moving on their own). */
export function loners(names, matrix, n = 5) {
  const out = [];
  for (let i = 0; i < matrix.length; i++) {
    const v = matrix[i].filter((r, j) => j !== i && r !== null);
    if (v.length) out.push({ name: names[i], r: v.reduce((a, r) => a + r, 0) / v.length });
  }
  return out.sort((x, y) => x.r - y.r).slice(0, n);
}

/** A matrix of any size: numbers when small; for many members a cluster-ordered heat grid + the conclusions. */
export function matrixBlock(names, matrix) {
  if (!matrix?.length || names.length <= SMALL_MATRIX) return matrixHtml(names, matrix);
  const order = clusterOrder(matrix);
  const cells = order
    .map(
      (i) =>
        `<tr><td class="l"><span class="clip" style="max-width:5em" title="${escapeHtml(names[i])}">${escapeHtml(names[i])}</span></td>${order
          .map((j) => {
            const r = matrix[i][j];
            if (i === j) return '<td class="self"></td>';
            return `<td style="background:${colorFor(r === null ? null : (r - 0.3) * 100, 50)}" title="${escapeHtml(names[i])} × ${escapeHtml(names[j])}：${fmtR(r)}"></td>`;
          })
          .join('')}</tr>`,
    )
    .join('');
  const pairs = topPairs(names, matrix)
    .map((p) => `<li>${escapeHtml(p.a)} × ${escapeHtml(p.b)} <b>${fmtR(p.r)}</b></li>`)
    .join('');
  const alone = loners(names, matrix)
    .map((p) => `<li>${escapeHtml(p.name)} <span class="muted">平均 ${fmtR(p.r)}</span></li>`)
    .join('');
  return `<div class="link-heat-wrap"><table class="link-heat"><tbody>${cells}</tbody></table></div>
    <div class="link-concl"><div><div class="muted">連動最強的 10 對</div><ol>${pairs}</ol></div><div><div class="muted">最獨立的 5 檔</div><ol>${alone}</ol></div></div>
    <small class="muted">紅＝一起動、綠＝反向；已把互相連動的排在一起（滑鼠移到格子看 R）</small>`;
}

export function summaryHtml(d) {
  const src = d.intraday.sessions.map((s) => `${s.date.slice(5)} ${s.source === 'recorded' ? '自錄' : s.source === 'yahoo' ? 'Yahoo' : '無'}`).join('、');
  const lag = d.leader_lag_min === null ? '—' : `${d.leader_lag_min > 0 ? '+' : ''}${d.leader_lag_min.toFixed(0)} 分`;
  return `<div class="link-summary">
    <div><span class="muted">日相關 R20／R60</span> <b>${fmtR(d.daily.r20)}</b>／${fmtR(d.daily.r60)} ${badge(d.verdict.daily)}</div>
    <div><span class="muted">分時相關（5 分 K）</span> <b>${fmtR(d.intraday.r)}</b> ${badge(d.verdict.intraday)} <small class="muted">${escapeHtml(src)}</small></div>
    <div><span class="muted">日內最高點時間標準差</span> <b>${d.peak_std_min === null ? '—' : d.peak_std_min.toFixed(0) + ' 分'}</b> ${badge(d.verdict.timing)}</div>
    <div title="龍頭（族群市值最大）到達日內最高點後，其他成員平均晚幾分鐘到達"><span class="muted">龍頭領先</span> <b>${lag}</b></div>
  </div>`;
}

// ---- panels -------------------------------------------------------------------------------------

/** K's body: summary, both matrices and the animated timeline; returns stop() for the animation. */
function renderBody(body, d, win, onStock, raceNote) {
  const names = d.members.map((m) => m.name);
  body.innerHTML = `${summaryHtml(d)}
    <div class="link-grid">
      <div><div class="muted">日相關（<span class="link-win">${win}</span> 日漲跌幅）</div><div class="link-daily">${matrixBlock(names, d.daily[`matrix${win}`])}</div></div>
      <div><div class="muted">分時相關（最近 ${d.intraday.sessions.length} 個交易日 5 分 K）</div>${matrixBlock(names, d.intraday.matrix)}</div>
    </div>
    <div class="race"><div class="muted" title="日內最高點＝每檔在 09:00–13:00 之間價格最高的那個時間點（同價取最早）">${escapeHtml(d.date)} 日內最高點時間＋漲幅（按 ▶ 從 09:00 播到 13:30，依當下漲跌幅排名；👑 龍頭；${raceNote}）</div><div class="race-box"></div></div>`;
  return mountRace(body.querySelector('.race-box'), d, { onStock });
}

/** The 20/60-day toggle only redraws the daily matrix, so a running replay is left alone. */
function wireWindow(sec, state, body) {
  sec.querySelector('.link-win-seg').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-value]');
    if (!b) return;
    state.win = b.dataset.value;
    for (const x of sec.querySelectorAll('.link-win-seg button')) x.classList.toggle('on', x === b);
    const d = state.data;
    if (!d) return;
    body.querySelector('.link-win').textContent = state.win;
    body.querySelector('.link-daily').innerHTML = matrixBlock(d.members.map((m) => m.name), d.daily[`matrix${state.win}`]);
  });
}

export function mountLinkagePanel(container, { onStock }) {
  const sec = document.createElement('section');
  sec.id = 'hLinkPanel';
  sec.className = 'panel hK';
  sec.innerHTML = `<div class="panel-h"><b>K · 族群連動性</b><span id="hLinkTitle"></span>
      <span class="muted">市值前 8 大；R &gt; 0.7 群體圍攻、&lt; 0.3 單兵作戰（分時 0.5／0.2）；日內最高點時間差 ≤ 10 分高度同步、≥ 60 分時間錯落</span>
      <div class="seg link-win-seg" id="hLinkWin"><button data-value="20" class="on">20 日</button><button data-value="60">60 日</button></div>
      <span class="muted" id="hLinkNote" style="margin-left:auto"></span>
      <button type="button" class="icon" id="hLinkClose" aria-label="關閉">✕</button></div>
    <div id="hLinkBody" style="padding:8px 10px">${HINT}</div>`;
  container.appendChild(sec);
  const body = sec.querySelector('#hLinkBody');
  const state = { ticket: 0, data: null, win: '20', group: null, date: null, grouping: null, stopRace: () => {} };
  wireWindow(sec, state, body);
  const reset = () => {
    state.ticket += 1; // drop a request still in flight
    state.group = null;
    state.data = null;
    state.stopRace();
    sec.querySelector('#hLinkTitle').textContent = '';
    sec.querySelector('#hLinkNote').textContent = '';
    sec.classList.remove('loading');
    body.innerHTML = HINT;
  };
  sec.querySelector('#hLinkClose').addEventListener('click', reset);
  async function show(group, date, grouping) {
    if (!group || !date) {
      reset();
      return;
    }
    Object.assign(state, { group, date, grouping });
    const t = ++state.ticket;
    sec.querySelector('#hLinkTitle').textContent = `${group} · ${date}`;
    sec.classList.add('loading');
    try {
      const resp = await fetch(`/api/history/linkage?date=${encodeURIComponent(date)}&grouping=${encodeURIComponent(grouping)}&group=${encodeURIComponent(group)}`, { cache: 'no-store' });
      const data = await resp.json();
      if (t !== state.ticket) return;
      if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
      state.data = data;
      sec.querySelector('#hLinkNote').textContent = data.notes.join('；');
      state.stopRace();
      state.stopRace = renderBody(body, data, state.win, onStock, '點一列看那檔的分時走勢');
    } catch (err) {
      if (t !== state.ticket) return;
      state.data = null;
      body.innerHTML = `<p class="hint">${escapeHtml(err.message)}</p>`;
    } finally {
      if (t === state.ticket) sec.classList.remove('loading');
    }
  }
  return {
    show,
    refresh(date, grouping) {
      if (state.group) show(state.group, date, grouping);
    },
    hide: reset,
  };
}
