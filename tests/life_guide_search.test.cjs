'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Search = require('../integrations/life_guide/frontend/search.js');
const guide = require('../integrations/life_guide/frontend/guide.json');
const live = Search.buildIndex(guide.entries, guide.sections);
const flatten = result => result.groups.flatMap(group => group.entries);
const ids = entries => entries.map(entry => entry.id);
const entry = (id, extra = {}) => ({ id, sec: 1, n: 1, title: '通勤与睡眠', human: '在书中保留的说明',
  note: '限制条件与争议原文', cost: '原文成本', gain: '原文收益', grade: 'B', ratio: '高', lens: '时间',
  money: '0', time: '少', will: '否', todo: false, dispute: false, ...extra });

test('browser and CommonJS provide the same dependency-free API', () => {
  const scope = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/life_guide/frontend/search.js'), 'utf8'), scope);
  assert.equal(typeof scope.LifeGuideSearch.directionalSearch, 'function');
  assert.equal(typeof scope.LifeGuideSearch.keywordSearch, 'function');
  assert.equal(Search.normalize(' ＡＢＣ　HPV  '), 'abc hpv');
});

test('keyword search normalizes width/case, intersects words, and supports explicit OR', () => {
  const index = Search.buildIndex([
    entry('a', { title: 'HPV 疫苗', note: '保留完整限制说明' }),
    entry('b', { title: 'HPV 检查', n: 2 }),
    entry('c', { title: '流感疫苗', n: 3 }),
  ], []);
  assert.deepEqual(ids(Search.keywordSearch(index, 'ＨＰＶ　疫苗')), ['a']);
  assert.deepEqual(ids(Search.keywordSearch(index, 'hpv 疫苗', {}, { mode: 'any' })), ['a', 'b', 'c']);
  assert.deepEqual(ids(Search.keywordSearch(index, '完整限制')), ['a']);
  assert.deepEqual(ids(Search.keywordSearch(index, '')), ['a', 'b', 'c']);
});

test('keyword sort options preserve book order, source value order, and text relevance', () => {
  const index = Search.buildIndex([
    entry('a', { n: 3, ratio: '高', grade: 'B', title: '完整通勤标题', human: '' }),
    entry('b', { n: 1, ratio: '极高', grade: 'C', title: '别的标题', human: '正文谈通勤' }),
    entry('c', { n: 2, ratio: '高', grade: 'A', title: '另一个标题', human: '正文谈通勤' }),
  ], []);
  assert.deepEqual(ids(Search.keywordSearch(index, '通勤', {}, { sort: 'book' })), ['b', 'c', 'a']);
  assert.deepEqual(ids(Search.keywordSearch(index, '通勤', {}, { sort: 'value' })), ['b', 'c', 'a']);
  assert.deepEqual(ids(Search.keywordSearch(index, '通勤', {}, { sort: 'relevance' })), ['a', 'b', 'c']);
});

test('the no-Segmenter fallback still searches source phrases without one-character matches', () => {
  const scope = { Intl: {} };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/life_guide/frontend/search.js'), 'utf8'), scope);
  const fallback = scope.LifeGuideSearch;
  const index = fallback.buildIndex(guide.entries, guide.sections);
  for (const [query, expected] of [['社保断缴了怎么办', 's7-e18'], ['朋友让我担保签不签', 's8-e18']]) {
    assert.ok(ids(flatten(fallback.directionalSearch(index, query))).includes(expected), query);
  }
  assert.equal(fallback.directionalSearch(index, '火星殖民船曲率引擎坏了').total, 0);
});

test('every filter intersects; empty arrays do not constrain and zero is a valid cost', () => {
  const index = Search.buildIndex([
    entry('a', { sec: 8, grade: 'A', lens: '金钱' }),
    entry('b', { sec: 8, n: 2, grade: 'A', lens: '金钱', money: '少' }),
    entry('c', { sec: 8, n: 3, grade: 'A', lens: '金钱', dispute: true }),
    entry('d', { sec: 8, n: 4, grade: 'A', lens: '金钱', todo: true }),
  ], []);
  const filters = { sections: [8], grades: ['A'], money: [0], time: ['少'], will: ['否'],
    lenses: ['金钱'], ratios: ['高'], excludeDisputed: true, excludeUnverified: true };
  assert.deepEqual(ids(Search.keywordSearch(index, '', filters)), ['a']);
  assert.equal(Search.keywordSearch(index, '', { sections: [], grades: [], money: [] }).length, 4);
  for (const [key, value] of Object.entries({ sections: [7], grades: ['C'], money: ['多'], time: ['多'],
    will: ['是'], lenses: ['死亡率'], ratios: ['极高'] })) {
    assert.equal(Search.keywordSearch(index, '', { ...filters, [key]: value }).length, 0, key);
  }
});

test('reference lookup accepts Arabic, full-width and Chinese section/entry numbers', () => {
  for (const query of ['第8节第17条', '第 ８ 节第 １７ 条', '第八节第十七条']) {
    assert.deepEqual(ids(Search.keywordSearch(live, query)), ['s8-e17']);
    assert.deepEqual(ids(flatten(Search.directionalSearch(live, query))), ['s8-e17']);
  }
  assert.equal(Search.directionalSearch(live, '第99节第99条').total, 0);
  assert.equal(Search.directionalSearch(live, '第8节第17条', { sections: [1] }).total, 0);
  assert.deepEqual(Search.parseReference('见第34节第11条'), { sec: 34, n: 11 });
});

test('directional groups rank ratio, then evidence, then relevance, without comparing lenses', () => {
  const fixtures = [
    entry('a', { n: 1, ratio: '高', grade: 'A' }),
    entry('b', { n: 2, ratio: '极高', grade: 'C' }),
    entry('c', { n: 3, ratio: '高', grade: 'B', title: '通勤' }),
    entry('d', { n: 4, ratio: '一般', grade: 'A', title: '通勤 通勤', lens: '金钱' }),
    entry('e', { n: 5, ratio: '高', grade: 'B', title: '做事', human: '通勤' }),
  ];
  const index = Search.buildIndex(fixtures, [{ n: 1, title: '不要浪费时间' }]);
  const result = Search.directionalSearch(index, '通勤');
  assert.deepEqual(ids(result.groups.find(group => group.lens === '时间').entries), ['b', 'a', 'c', 'e']);
  assert.deepEqual(ids(result.groups.find(group => group.lens === '金钱').entries), ['d']);
});

test('directional results cap at seven while preserving each available lens', () => {
  const fixtures = Array.from({ length: 20 }, (_, n) => entry(`e${n}`, { n, lens: Search.LENSES[n % 4], ratio: '极高', grade: 'A' }));
  const index = Search.buildIndex(fixtures, [{ n: 1, title: '不要浪费时间' }]);
  const result = Search.directionalSearch(index, '通勤');
  assert.equal(result.total, 7);
  assert.equal(result.groups.length, 4);
  assert.ok(result.groups.every(group => group.entries.length > 0));
  assert.ok(flatten(result).every(item => fixtures.some(source => source.id === item.id && source.note === item.note)));
});

test('TODO remains discoverable as source, but never becomes a directional result', () => {
  const index = Search.buildIndex([entry('s1-e1', { todo: true })], [{ n: 1, title: '不要浪费时间' }]);
  assert.equal(Search.keywordSearch(index, '通勤').length, 1);
  assert.equal(Search.keywordSearch(index, '通勤', { excludeUnverified: true }).length, 0);
  assert.equal(Search.directionalSearch(index, '通勤').total, 0);
  assert.match(Search.directionalSearch(index, '第1节第1条').message, /TODO/);
  for (const source of guide.entries.filter(row => row.todo)) {
    assert.equal(Search.directionalSearch(live, `第${source.sec}节第${source.n}条`).total, 0);
  }
});

test('empty, generic and unmatched questions do not manufacture recommendations', () => {
  for (const query of ['', '怎么办', '有什么建议', '我应该怎么选择', 'zxqv9987', '火星殖民船曲率引擎坏了']) {
    const result = Search.directionalSearch(live, query);
    assert.equal(result.total, 0, query);
    assert.deepEqual(result.groups, [], query);
    assert.ok(result.message.length > 0);
  }
});

test('real guarantee question returns intact entries and the signing caveat', () => {
  const result = Search.directionalSearch(live, '朋友让我担保签不签');
  const rows = flatten(result);
  assert.ok(ids(rows).includes('s8-e18'));
  assert.ok(ids(rows).includes('s8-e17'));
  assert.ok(result.sectionIds.includes(8));
  assert.ok(result.sectionIds.length <= 3);
  for (const row of rows) {
    const source = guide.entries.find(entry => entry.id === row.id);
    assert.equal(row.note, source.note);
    assert.equal(row.raw, source.raw);
    assert.equal(row.gain, source.gain);
  }
});

test('real commute result preserves its dispute and honors the dispute filter', () => {
  const result = Search.directionalSearch(live, '每天通勤两小时值不值');
  const commute = flatten(result).find(entry => entry.id === 's4-e18');
  assert.ok(commute);
  assert.equal(commute.lens, '时间');
  assert.equal(commute.dispute, true);
  assert.match(commute.note, /争议/);
  assert.ok(!ids(flatten(Search.directionalSearch(live, '每天通勤两小时值不值', { excludeDisputed: true }))).includes('s4-e18'));
});

test('real sleep and rental-deposit questions select their relevant chapters', () => {
  const sleep = Search.directionalSearch(live, '晚上总是睡不好怎么办');
  assert.ok(sleep.sectionIds.includes(3));
  assert.ok(flatten(sleep).some(entry => entry.sec === 3));
  assert.ok(!flatten(sleep).some(entry => entry.id === 's13-e33'));
  const rent = Search.directionalSearch(live, '租房押金不退怎么办');
  assert.ok(rent.sectionIds.includes(15));
  assert.ok(ids(flatten(rent)).includes('s15-e1'));
  assert.ok(!ids(flatten(rent)).includes('s7-e15'));
});

test('ordinary questions outside the scenario table use source vocabulary', () => {
  for (const [query, expected] of [['社保断缴了怎么办', 's7-e18'], ['听力下降配助听器', 's33-e17'],
    ['找工作让我交押金怎么办', 's7-e15'], ['创业担保贷款怎么申请', 's31-e16']]) {
    assert.ok(ids(flatten(Search.directionalSearch(live, query))).includes(expected), query);
  }
});

test('filtering and sorting never mutate the source corpus or search index', () => {
  const source = [entry('a', { n: 2 }), entry('b', { n: 1, grade: 'A' })];
  const before = JSON.stringify(source);
  const index = Search.buildIndex(source, [{ n: 1, title: '不要浪费时间' }]);
  const a = Search.keywordSearch(index, '通勤', {}, { sort: 'value' });
  const b = flatten(Search.directionalSearch(index, '通勤'));
  a[0].title = '修改返回对象'; b[0].note = '修改返回对象';
  assert.equal(JSON.stringify(source), before);
  assert.deepEqual(index.documents.map(doc => doc.entry.id), ['a', 'b']);
});
