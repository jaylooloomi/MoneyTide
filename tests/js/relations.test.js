import { test } from 'node:test';
import assert from 'node:assert/strict';

import { groupText, relText, relationsHtml } from '../../static/js/relations.js';

test('relText / groupText / relationsHtml: relations in words', () => {
  assert.equal(relText({ src_name: '菱光', dst_name: '光菱', pct: 19.07, method: '綜合公允', seats: [] }), '<b>菱光</b> 持有 <b>光菱</b> 19.07%（綜合公允）');
  assert.equal(relText({ src_name: '環泥', dst_name: '菱光', pct: 8.59, method: '', seats: ['董事'] }), '<b>環泥</b> 是 <b>菱光</b> 的董事（持股 8.59%）');
  assert.equal(relText({ src_name: '菱光', dst_name: '東友', pct: 29.69, method: '權益法', seats: ['董事', '董事'] }), '<b>菱光</b> 持有 <b>東友</b> 29.69%（權益法），派任 董事 ×2');
  assert.equal(relText({ src_name: 'A', dst_name: 'B', pct: 30, method: '' }), '<b>A</b> 持有 <b>B</b> 30%');
  assert.match(relText({ src_name: '<x>', dst_name: 'y', pct: null }), /&lt;x&gt;/);
  const g = { leader_name: '東元', size: 3, members: [{ name: '東元' }, { name: '東友' }, { name: '菱光' }] };
  assert.match(groupText(g), /以 <b>東元<\/b> 為首的集團（3 家）/);
  assert.match(groupText(g), /東元、東友、菱光/);
  assert.match(relationsHtml([{ src_name: 'A', dst_name: 'B', pct: 20, method: '權益法' }], g), /持有.*；<span[^>]*>以 <b>東元/);
  assert.equal(relationsHtml([], null), '');
  assert.match(relText({ src_name: 'A', dst_name: 'B', pct: 100 }), /B<\/b> 100%/);
});
