// C · 族群輪動: the ⓘ explanation of what one cell means under each metric (pure, node --test).

import { escapeHtml } from './transform.js';

const COMMON = {
  cell: '每一格＝某個族群在某一天的數值；欄＝交易日（最右邊是選到的那天），列＝族群。',
  order: '族群依最近 3 天的平均值由高到低排，越上面代表最近越強。',
  bench: '最上面 5 列是比較用：大盤（加權）、櫃買（OTC）、電子／金融／傳產（上市），不參與排序。',
  click: '點格子會把整頁切到那一天。',
};

/** The explanation for `metric` (with the 強勢門檻 `threshold` %), as HTML. */
export function rotationInfoHtml(metric, threshold = 5) {
  const t = escapeHtml(String(threshold));
  const m = {
    strong_ratio: {
      name: '強勢佔比',
      what: `族群裡當天漲幅 ≥ ${t}%（上方「強勢門檻」）的股票佔幾 %。例：10 檔裡 3 檔漲 ≥ ${t}% → 30。`,
      color: '越紅代表越多檔一起大漲（30% 以上就很紅）。0 代表沒有任何一檔達到門檻。',
      bench: '大盤／櫃買列：全市場普通股的強勢佔比；電子／金融／傳產列：該類上市普通股的強勢佔比。',
      read: '連續幾天都是紅的族群＝資金持續攻擊；某天突然一片紅＝題材爆發。',
    },
    avg_pct: {
      name: '平均漲幅',
      what: '族群所有成分股當天漲跌幅的平均（每檔一樣重，%）。例：2.6 ＝ 平均漲 2.6%。',
      color: '紅漲綠跌，±3% 就是最深的顏色。',
      bench: '大盤／櫃買列：官方加權／櫃買指數的漲跌幅；電子／金融／傳產列：證交所官方類股指數漲跌幅。拿族群跟這幾列比，看出比大盤強還是弱。',
      read: '族群比大盤紅很多＝相對強勢；大盤跌它還紅＝逆勢有資金。',
    },
    breadth: {
      name: '上漲家數比',
      what: '族群裡上漲家數 ÷（上漲＋下跌家數）× 100，平盤不算。例：60 ＝ 有漲跌的股票裡 6 成上漲。',
      color: '50 是中間（灰），越紅＝越多檔上漲，越綠＝越多檔下跌。',
      bench: '大盤／櫃買列：全市場普通股的上漲家數比；電子／金融／傳產列：該類上市普通股。',
      read: '平均漲幅高但上漲家數比低＝只有少數幾檔在拉；兩個都高＝全面性的上漲。',
    },
    limit_up: {
      name: '漲停數',
      what: '族群當天漲停的家數（漲幅 ≥ 9.5%），空白＝0 檔。',
      color: '越紅漲停越多（5 檔以上最深）。',
      bench: '大盤／櫃買列：全市場漲停家數；電子／金融／傳產列：該類上市普通股的漲停家數。',
      read: '連續幾天都有漲停＝主流題材；只有一天＝可能是單一消息。',
    },
    share_z: {
      name: '比重 Z',
      what: '族群當天成交值占全市場的比重，跟它自己前 20 天比，高出幾個標準差（Z 值）。例：2.0 ＝ 比平常多 2 個標準差的資金湧入。',
      color: '紅＝資金比平常多（+3 最深），綠＝比平常少。',
      bench: '大盤／櫃買列：占上市櫃總成交值比重的 Z 值。',
      read: '連續幾天 Z 都是紅的＝資金持續流入這個族群（輪動到這裡了）；價格還沒動但 Z 先紅＝資金可能在佈局。',
    },
  }[metric];
  if (!m) return '';
  const row = (k, v) => `<tr><td class="muted">${k}</td><td>${v}</td></tr>`;
  return `<div class="rot-info-h"><b>ⓘ ${m.name}</b><button type="button" class="icon" data-act="close-info" aria-label="關閉">✕</button></div>
    <table class="rot-info-t">
      ${row('這格是什麼', m.what)}
      ${row('顏色', m.color)}
      ${row('參考列', `${COMMON.bench}<br>${m.bench}`)}
      ${row('怎麼讀', m.read)}
      ${row('排列', `${COMMON.cell}${COMMON.order}`)}
      ${row('操作', `${COMMON.click}上方可切 10／20／60 日與指標。`)}
    </table>`;
}
