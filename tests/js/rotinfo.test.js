import { test } from 'node:test';
import assert from 'node:assert/strict';

import { rotationInfoHtml } from '../../static/js/rotinfo.js';

test('rotationInfoHtml: every C metric explained, with the 強勢門檻 in it', () => {
  for (const m of ['strong_ratio', 'avg_pct', 'breadth', 'limit_up', 'share_z']) {
    const html = rotationInfoHtml(m, 5);
    assert.match(html, /這格是什麼/);
    assert.match(html, /顏色/);
    assert.match(html, /參考列/);
    assert.match(html, /data-act="close-info"/);
  }
  assert.match(rotationInfoHtml('strong_ratio', 7), /漲幅 ≥ 7%/);
  assert.match(rotationInfoHtml('avg_pct'), /官方類股指數/);
  assert.equal(rotationInfoHtml('nope'), '');
});
