// ⑤ Why did the top movers move? Server: /api/ai/reasons (GET = cached only, POST = ask the AI).
// Pure HTML builders on top (node --test); the panel / overlay wiring below.

import { escapeHtml, fmtPct, fmtTurnover } from './transform.js';

const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '#');

export function moverCardHtml(r) {
  const cls = r.change_pct > 0 ? 'up' : r.change_pct < 0 ? 'down' : '';
  let body;
  if (r.error) body = `<div class="muted">⚠ ${escapeHtml(r.error)}</div>`;
  else if (r.reason === null || r.reason === undefined) body = '<div class="muted">尚未分析</div>';
  else body = `<div>${escapeHtml(r.reason)}</div>`;
  const links = (r.links || [])
    .map(
      (l) =>
        `<li><a href="${escapeHtml(safeUrl(l.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(l.title)}</a>` +
        `${l.source ? ` <span class="muted">— ${escapeHtml(l.source)}</span>` : ''}</li>`,
    )
    .join('');
  return `<div class="ai-card" style="border:1px solid var(--line,#2a2e37);border-radius:6px;padding:8px 10px;margin-bottom:8px">
    <div><b>${escapeHtml(r.code)} ${escapeHtml(r.name)}</b> <span class="${cls}">${fmtPct(r.change_pct)}</span>
      <span class="muted">${escapeHtml(r.industry || '')}　成交值 ${fmtTurnover(r.turnover_100m)}${r.cached ? '　（已快取）' : ''}</span></div>
    <div style="margin-top:4px;line-height:1.55">${body}</div>
    ${links ? `<ul style="margin:6px 0 0 18px;padding:0;font-size:12px">${links}</ul>` : ''}
  </div>`;
}

export function reasonsHtml(data) {
  const col = (title, rows) =>
    `<div style="flex:1;min-width:280px"><div class="muted" style="margin-bottom:6px">${title}</div>${
      rows.length ? rows.map(moverCardHtml).join('') : '<div class="muted">沒有符合條件的股票（成交值需 ≥ 1 億）</div>'
    }</div>`;
  return `<div style="display:flex;gap:12px;flex-wrap:wrap">${col('漲幅前 3 名', data.gainers || [])}${col('跌幅前 3 名', data.losers || [])}</div>`;
}

export function aiStatusText(ai) {
  if (!ai?.configured) {
    return '未設定 AI：請設定環境變數 OPENMARKET_AI_KEY（可選 OPENMARKET_AI_FORMAT／OPENMARKET_AI_BASE_URL／OPENMARKET_AI_MODEL）後重新啟動。';
  }
  return `AI：${ai.model}（${ai.host}）。只根據新聞標題整理，不構成投資建議。`;
}

// ---- DOM ---------------------------------------------------------------------------------------

let statusPromise = null;
function aiStatus() {
  statusPromise ??= fetch('/api/ai/status', { cache: 'no-store' })
    .then((r) => r.json())
    .catch(() => {
      statusPromise = null;
      return { configured: false };
    });
  return statusPromise;
}

async function request(method, query) {
  const resp = await fetch(`/api/ai/reasons?${query}`, {
    method,
    cache: 'no-store',
    headers: method === 'POST' ? { 'X-OpenMarket-Action': 'explain' } : {},
  });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(body.detail || `HTTP ${resp.status}`);
  return body;
}

/** Wire a results box + button. query() returns the query string (or null = not available). */
function controller({ box, button, note, query }) {
  const state = { ticket: 0, busy: false };
  async function show(method) {
    const q = query();
    if (!q) return;
    const t = ++state.ticket;
    const ai = await aiStatus();
    button.disabled = !ai.configured || state.busy;
    note.textContent = aiStatusText(ai);
    if (method === 'POST') {
      state.busy = true;
      button.disabled = true;
      box.innerHTML = '<div class="muted">分析中：搜尋新聞並請 AI 整理（約 30 秒）…</div>';
    }
    try {
      const data = await request(method, q);
      if (t !== state.ticket) return;
      box.innerHTML = reasonsHtml(data);
    } catch (err) {
      if (t !== state.ticket) return;
      box.innerHTML = `<div class="muted">⚠ ${escapeHtml(err.message)}</div>`;
    } finally {
      if (method === 'POST') {
        state.busy = false;
        button.disabled = !ai.configured;
      }
    }
  }
  button.addEventListener('click', () => show('POST'));
  return { load: () => show('GET') };
}

/** History panel I: follows the selected date. */
export function mountHistoryAiPanel(container, getDate) {
  const sec = document.createElement('section');
  sec.id = 'hAiPanel';
  sec.className = 'panel';
  sec.style.gridColumn = '1 / -1';
  sec.innerHTML = `<div class="panel-h"><b>I · 漲跌原因（AI 新聞分析）</b>
      <button type="button" class="icon wide" id="hAiRun">分析這一天</button>
      <span class="muted" id="hAiNote" style="margin-left:auto"></span></div>
    <div id="hAiBox" style="padding:8px 10px"></div>`;
  container.appendChild(sec);
  const c = controller({
    box: sec.querySelector('#hAiBox'),
    button: sec.querySelector('#hAiRun'),
    note: sec.querySelector('#hAiNote'),
    query: () => (getDate() ? `source=history&date=${encodeURIComponent(getDate())}` : null),
  });
  return { load: c.load };
}

/** Live: an "AI 解讀" button that opens an overlay; usable after the close only. */
export function mountLiveAiButton(controls, isMarketOpen) {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'icon wide';
  btn.id = 'liveAiBtn';
  btn.textContent = 'AI 解讀';
  controls.appendChild(btn);
  const panel = document.createElement('aside');
  panel.id = 'liveAiPanel';
  panel.hidden = true;
  panel.style.cssText =
    'position:fixed;top:90px;right:16px;width:min(720px,calc(100vw - 32px));max-height:calc(100vh - 110px);overflow:auto;z-index:50;background:var(--panel,#16191f);border:1px solid #444a57;border-radius:8px;box-shadow:0 8px 24px #0008';
  panel.innerHTML = `<div class="panel-h"><b>今日漲跌原因（AI 新聞分析）</b>
      <button type="button" class="icon wide" id="liveAiRun">分析</button>
      <span class="muted" id="liveAiNote"></span>
      <button type="button" class="icon" id="liveAiClose" style="margin-left:auto" aria-label="關閉">✕</button></div>
    <div id="liveAiBox" style="padding:8px 10px"></div>`;
  document.body.appendChild(panel);
  const c = controller({
    box: panel.querySelector('#liveAiBox'),
    button: panel.querySelector('#liveAiRun'),
    note: panel.querySelector('#liveAiNote'),
    query: () => 'source=live',
  });
  btn.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) c.load();
  });
  panel.querySelector('#liveAiClose').addEventListener('click', () => {
    panel.hidden = true;
  });
  return {
    sync() {
      const open = isMarketOpen();
      btn.disabled = open;
      btn.title = open ? '盤中不分析，收盤後再用' : '今日漲跌幅前 3 名的新聞原因（AI 整理）';
      if (open) panel.hidden = true;
    },
  };
}
