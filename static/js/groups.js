// Custom groups (自訂族群): API client, change notifications and the management panel.
import { escapeHtml } from './transform.js';

const $ = (sel) => document.querySelector(sel);
const listeners = new Set();
let groups = [];
let selected = null;
let stockNames = new Map(); // code → name, for labels and the add-stock datalist

export const getGroups = () => groups;
export const onGroupsChange = (fn) => listeners.add(fn);

async function call(method, path, body) {
  const resp = await fetch(path, {
    method,
    cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${resp.status}`);
  groups = data.groups;
  for (const fn of listeners) fn(groups);
  return groups;
}

const enc = encodeURIComponent;
export const loadGroups = () => call('GET', '/api/groups');
export const createGroup = (name) => call('PUT', `/api/groups/${enc(name)}`);
export const deleteGroup = (name) => call('DELETE', `/api/groups/${enc(name)}`);
export const renameGroup = (name, to) => call('POST', `/api/groups/${enc(name)}/rename`, { name: to });
export const addToGroup = (name, code) => call('PUT', `/api/groups/${enc(name)}/${enc(code)}`);
export const removeFromGroup = (name, code) => call('DELETE', `/api/groups/${enc(name)}/${enc(code)}`);

/** Stocks offered in the add box: [{code, name}]. */
export function setStockNames(stocks) {
  stockNames = new Map(stocks.map((s) => [s.code, s.name]));
  $('#gpStockList').innerHTML = [...stockNames]
    .map(([code, name]) => `<option value="${escapeHtml(code)} ${escapeHtml(name)}"></option>`)
    .join('');
}

function error(text) {
  $('#gpErr').textContent = text || '';
}

async function run(fn) {
  error('');
  try {
    await fn();
  } catch (err) {
    error(err.message);
  }
  render();
}

function render() {
  if (selected && !groups.some((g) => g.name === selected)) selected = null;
  if (!selected && groups.length) selected = groups[0].name;
  $('#gpList').innerHTML = groups.length
    ? groups
        .map((g) => `<li data-name="${escapeHtml(g.name)}" class="${g.name === selected ? 'on' : ''}">${escapeHtml(g.name)}<span class="n">${g.codes.length}</span></li>`)
        .join('')
    : '<li class="muted">還沒有族群</li>';
  const g = groups.find((x) => x.name === selected);
  $('#gpDetail').innerHTML = g
    ? `<div class="row"><b>${escapeHtml(g.name)}</b><span class="spacer"></span>
         <button type="button" id="gpRename">改名</button><button type="button" class="danger" id="gpDelete">刪除族群</button></div>
       <div class="row"><input class="field" id="gpAdd" list="gpStockList" placeholder="輸入代號或名稱，例如 3017 或 奇鋐"><button type="button" class="primary" id="gpAddBtn">加入</button></div>
       <div class="gp-codes">${
         g.codes
           .map((c) => `<span>${escapeHtml(c)} ${escapeHtml(stockNames.get(c) || '')}<button type="button" data-remove="${escapeHtml(c)}" title="移出">✕</button></span>`)
           .join('') || '<span class="muted">尚無股票</span>'
       }</div>`
    : '<p class="hint">先在上方建立一個族群，再把股票加進去。一檔股票可以同時屬於多個族群。</p>';
}

/** "3017 奇鋐", "3017" or "奇鋐" → code, or null. */
function resolveCode(text) {
  const t = text.trim();
  if (!t) return null;
  const head = t.split(/\s+/)[0].toUpperCase();
  if (/^[0-9A-Z]{4,6}$/.test(head)) return head;
  for (const [code, name] of stockNames) if (name === t) return code;
  return null;
}

function bindPanel() {
  $('#gpClose').addEventListener('click', closeGroupPanel);
  const create = () =>
    run(async () => {
      const name = $('#gpNewName').value.trim();
      if (!name) return;
      await createGroup(name);
      selected = name;
      $('#gpNewName').value = '';
    });
  $('#gpCreate').addEventListener('click', create);
  $('#gpNewName').addEventListener('keydown', (e) => e.key === 'Enter' && create());
  $('#gpList').addEventListener('click', (e) => {
    const li = e.target.closest('li[data-name]');
    if (li) {
      selected = li.dataset.name;
      render();
    }
  });
  $('#gpDetail').addEventListener('click', (e) => {
    const target = e.target.closest('button');
    if (!target) return;
    if (target.dataset.remove) run(() => removeFromGroup(selected, target.dataset.remove));
    else if (target.id === 'gpDelete') {
      if (confirm(`刪除族群「${selected}」？`)) run(() => deleteGroup(selected));
    } else if (target.id === 'gpRename') {
      const to = prompt('新的族群名稱', selected);
      if (to && to.trim() && to.trim() !== selected)
        run(async () => {
          await renameGroup(selected, to.trim());
          selected = to.trim();
        });
    } else if (target.id === 'gpAddBtn') addFromInput();
  });
  $('#gpDetail').addEventListener('keydown', (e) => {
    if (e.target.id === 'gpAdd' && e.key === 'Enter') addFromInput();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('#groupPanel').hidden) closeGroupPanel();
  });
}

function addFromInput() {
  const input = $('#gpAdd');
  const code = resolveCode(input.value);
  if (!code) {
    error('找不到這檔股票，請輸入代號（例如 3017）');
    return;
  }
  run(async () => {
    await addToGroup(selected, code);
    input.value = '';
  });
}

let bound = false;
export async function openGroupPanel() {
  if (!bound) {
    bindPanel();
    bound = true;
  }
  $('#groupPanel').hidden = false;
  await run(loadGroups);
  $('#gpNewName').focus();
}

export function closeGroupPanel() {
  $('#groupPanel').hidden = true;
}
