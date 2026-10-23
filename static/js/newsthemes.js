// J · 新聞熱門族群: hot groups found in recent headlines (server: /api/news-themes).
// Pure HTML builder on top (node --test); the panel wiring below.

import { colorFor, escapeHtml, fmtPct } from './transform.js';

const MAX_CHIPS = 12;
const safeUrl = (u) => (/^https?:\/\//i.test(u || '') ? u : '#');

export function trendHtml(score, prev) {
  if (!prev) return '<span class="up" title="前 3 天沒有">新</span>';
  const d = score - prev;
  if (d > 0) return `<span class="up" title="前 3 天 ${prev} 則">▲${d}</span>`;
  if (d < 0) return `<span class="down" title="前 3 天 ${prev} 則">▼${-d}</span>`;
  return '<span class="muted">–</span>';
}

export function themesTableHtml(data) {
  const themes = data?.themes || [];
  if (!themes.length) return '<p class="hint" style="padding:8px 10px">這一天還沒有新聞族群資料（背景回補中，或當天新聞不足）。</p>';
  const rows = themes
    .map((t, i) => {
      const chips = t.members
        .slice(0, MAX_CHIPS)
        .map(
          (m) =>
            `<a href="#" class="tag" data-code="${escapeHtml(m.code)}" style="background:${colorFor(m.change_pct, 7)}" title="${escapeHtml(m.code)} ${fmtPct(m.change_pct)}">${escapeHtml(m.name)}<small>${m.change_pct === null || m.change_pct === undefined ? '' : fmtPct(m.change_pct)}</small></a>`,
        )
        .join('');
      const more = t.members.length > MAX_CHIPS ? `<span class="muted">等 ${t.members.length} 檔</span>` : '';
      const news = t.titles
        .slice(0, 2)
        .map((n) => `<a href="${escapeHtml(safeUrl(n.url))}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(n.source || '')}">${escapeHtml(n.title)}</a>`)
        .join('<br>');
      const aliases = t.aliases?.length ? ` <small class="muted" title="同義詞">（${escapeHtml(t.aliases.join('、'))}）</small>` : '';
      return `<tr data-theme="${escapeHtml(t.name)}">
        <td class="muted">${i + 1}</td>
        <td class="l"><a href="#" class="theme-pick" title="切到「新聞族群」分組並放大這個族群">${escapeHtml(t.name)}</a>${aliases}</td>
        <td>${t.score} 則 ${trendHtml(t.score, t.prev_score)}</td>
        <td class="muted">${t.members.length}</td>
        <td class="c" style="background:${colorFor(t.avg_pct, 3)}">${fmtPct(t.avg_pct)}</td>
        <td class="c" style="background:${colorFor(t.strong_ratio, 30)}">${t.strong_ratio === null || t.strong_ratio === undefined ? '—' : t.strong_ratio.toFixed(0) + '%'}</td>
        <td class="l"><div class="tags" style="margin:0">${chips}${more}</div></td>
        <td class="l news-cell">${news}</td>
      </tr>`;
    })
    .join('');
  return `<table class="grid news-themes"><thead><tr><th></th><th class="l">族群</th><th title="近 3 個交易日被提到的新聞則數；▲▼ 與前 3 天比">熱度</th><th>成員</th><th>平均漲跌</th><th>≥5%</th><th class="l">成員股</th><th class="l">代表新聞</th></tr></thead><tbody>${rows}</tbody></table>`;
}

export function methodText(data, status) {
  const parts = [];
  if (data?.news_date) parts.push(`新聞日 ${data.news_date}`);
  if (data?.method === 'ai') parts.push('AI 整理');
  else if (data?.method === 'keyword') parts.push('關鍵字比對（設定 AI 金鑰後會自動合併同義族群）');
  if (status?.running) parts.push(`回補中 ${status.done}/${status.total}`);
  return parts.join('　·　');
}

/** Panel J under A/B. onPick(themeName) switches the history view; onStock(code) opens a card. */
export function mountNewsPanel(container, { getDate, onPick, onStock }) {
  const sec = document.createElement('section');
  sec.id = 'hNewsPanel';
  sec.className = 'panel hJ';
  sec.innerHTML = `<div class="panel-h"><b>J · 新聞熱門族群</b>
      <span class="muted">近 3 個交易日新聞最常提到的族群；點族群名稱切到「新聞族群」分組</span>
      <span class="muted" id="hNewsNote" style="margin-left:auto"></span></div>
    <div class="table-wrap" id="hNewsBox" style="max-height:340px"></div>`;
  container.appendChild(sec);
  const box = sec.querySelector('#hNewsBox');
  const note = sec.querySelector('#hNewsNote');
  let ticket = 0;
  box.addEventListener('click', (e) => {
    const pick = e.target.closest('a.theme-pick');
    if (pick) {
      e.preventDefault();
      onPick(pick.closest('tr').dataset.theme);
      return;
    }
    const tag = e.target.closest('a.tag[data-code]');
    if (tag && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      onStock(tag.dataset.code);
    }
  });
  async function load() {
    const date = getDate();
    if (!date) return;
    const t = ++ticket;
    sec.classList.add('loading');
    try {
      const [data, status] = await Promise.all([
        fetch(`/api/news-themes?date=${encodeURIComponent(date)}`, { cache: 'no-store' }).then((r) => r.json()),
        fetch('/api/news-themes/status', { cache: 'no-store' }).then((r) => r.json()),
      ]);
      if (t !== ticket) return;
      box.innerHTML = themesTableHtml(data);
      note.textContent = methodText(data, status);
    } catch (err) {
      if (t !== ticket) return;
      box.innerHTML = `<p class="hint" style="padding:8px 10px">無法載入：${escapeHtml(err.message)}</p>`;
    } finally {
      if (t === ticket) sec.classList.remove('loading');
    }
  }
  return { load };
}
