'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const Interviews = require('../integrations/newspaper/frontend/interviews.js');
const NOW = Date.parse('2026-10-06T12:00:00+08:00'), DAY = 86400000;
const article = (id, age = DAY, patch = {}) => ({id, title: `作家访谈 ${id}`, category: '访谈与对话',
  group: '阅读与文学', kind: '访谈', source: '三联生活周刊', summary: '作家谈文学与阅读。',
  published_at: new Date(NOW - age).toISOString(), url: `https://www.lifeweek.com.cn/article/${id}`,
  summary_only: true, ...patch});
const ids = values => values.map(value => value.id);

test('browser global and CommonJS expose the same storage-free interview selection', () => {
  const scope = {URL};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/newspaper/frontend/interviews.js'), 'utf8'), scope);
  assert.equal(scope.NewspaperInterviews.CATEGORY, Interviews.CATEGORY);
  assert.equal(typeof scope.NewspaperInterviews.selectRecentInterviews, 'function');
  assert.deepEqual(ids(Interviews.selectRecentInterviews([article('a')], {now: NOW})), ['a']);
});

test('the rolling seven-day range includes both exact boundaries and excludes older or future dates', () => {
  const input = [article('old', 7 * DAY + 1), article('lower', 7 * DAY), article('middle'),
    article('upper', 0), article('future', -1)];
  assert.deepEqual(ids(Interviews.selectRecentInterviews(input, {now: NOW})), ['upper', 'middle', 'lower']);
});

test('publication time must have a timezone and never falls back to update or discovery time', () => {
  const invalid = [null, undefined, '', '2026-10-05', '2026-10-05T10:30:00',
    '2026-10-05T10:30:00+24:00', '2026-10-05T10:30:00+08:60', '2026-02-30T10:30:00+08:00',
    '2026-10-05T24:00:00+08:00', '2026-10-05T10:60:00Z', '2026-10-05T10:30:60Z', 1791158400000];
  for (const published_at of invalid) {
    assert.equal(Interviews.publishedTimestamp(published_at), null, String(published_at));
    assert.deepEqual(Interviews.selectRecentInterviews([article('invalid', DAY, {published_at,
      updated_at: new Date(NOW).toISOString(), discovered_at: new Date(NOW).toISOString(), time_basis: 'collected'})], {now: NOW}), []);
  }
  assert.deepEqual(Interviews.selectRecentInterviews([article('old', 10 * DAY, {updated_at: new Date(NOW).toISOString()})], {now: NOW}), []);
});

test('timezone offsets represent the same instant and valid leap days remain supported', () => {
  for (const value of ['2026-10-06T04:00:00Z', '2026-10-06T12:00:00+08:00',
    '2026-10-05T23:00:00-05:00', '2026-10-06T09:30:00+05:30']) {
    assert.equal(Interviews.publishedTimestamp(value), NOW);
  }
  assert.equal(Interviews.publishedTimestamp('2024-02-29T08:00:00.123456+08:00'), Date.parse('2024-02-29T00:00:00.123Z'));
  assert.equal(Interviews.publishedTimestamp('2026-02-29T00:00:00Z'), null);
});

test('an explicit non-publication time basis cannot qualify as a recent interview', () => {
  for (const time_basis of ['updated', 'collected', 'unknown', '', null]) {
    assert.deepEqual(Interviews.selectRecentInterviews([article('a', DAY, {time_basis})], {now: NOW}), []);
  }
  assert.deepEqual(ids(Interviews.selectRecentInterviews([article('published', DAY, {time_basis: 'published'})], {now: NOW})), ['published']);
});

test('selection deduplicates identifiers and original links, then sorts without changing the feed', () => {
  const input = [article('older', 3 * DAY), article('id-repeat', 2 * DAY),
    article('same-url', DAY, {url: 'https://www.lifeweek.com.cn/article/shared#first'}),
    article('alias', DAY, {url: 'https://www.lifeweek.com.cn/article/shared#second'}),
    article('id-repeat', 0, {url: 'https://www.lifeweek.com.cn/article/newer'})];
  const before = JSON.stringify(input), selected = Interviews.selectRecentInterviews(input, {now: NOW});
  assert.deepEqual(ids(selected), ['id-repeat', 'alias', 'older']);
  assert.deepEqual(ids(Interviews.selectRecentInterviews([...input].reverse(), {now: NOW})), ids(selected));
  assert.equal(JSON.stringify(input), before);
});

test('selection limits the category, combines source and all query words, and respects hidden items', () => {
  const input = [article('sanlian', DAY, {title: '青年写作者的对话', summary: '谈阅读与音乐'}),
    article('writers', DAY, {title: '青年写作者的对话', publisher: '中国作家网', source: '作协访谈', summary: '谈阅读与音乐'}),
    article('hidden', DAY, {title: '青年写作者的对话'}), article('news', DAY, {category: '时政要闻'}),
    article('other', DAY, {title: '另一位作家的日常'})];
  assert.deepEqual(ids(Interviews.selectRecentInterviews(input, {now: NOW, source: '中国作家网', query: '青年 音乐'})), ['writers']);
  assert.deepEqual(ids(Interviews.selectRecentInterviews(input, {now: NOW, source: '三联生活周刊', query: '青年', hiddenIds: ['hidden']})), ['sanlian']);
  assert.equal(Interviews.selectRecentInterviews(input, {now: NOW, query: '找不到的内容'}).length, 0);
  assert.equal(Interviews.selectRecentInterviews(input, {now: NaN}).length, 0);
});

function pageHarness() {
  const html = fs.readFileSync(path.join(__dirname, '../integrations/newspaper/frontend/index.html'), 'utf8');
  let code = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
  code = code.replace(/\}\)\(\);\s*$/, `window.testAPI={front,chrome,catalogPage,interviewsPage,interviewPreview,interviewRows,render,snapshot,
    setState:patch=>Object.assign(state,patch),
    setPins:pins=>{data.pins=pins;data.pinsCustomized=true;},
    inspect:()=>JSON.parse(JSON.stringify({state,data})),
    feed:(raw,sourceRows=[])=>{articles=raw.map(normalizeArticle).filter(Boolean);articleIndex=new Map(articles.map(a=>[a.id,a]));sources=normalizeSources(sourceRows);receivedFeed=true;stale=true;}
  };})();`);
  let now = NOW, rootHTML = '', search = '', anchors = [];
  const handlers = {}, windowHandlers = {}, storage = new Map(), sent = [], micros = [], writes = [];
  const root = {style: {setProperty() {}}, addEventListener(name, fn) {handlers[name] = fn;}, contains() {return false;},
    querySelector(selector) {return selector === '[name=q]' ? {value: search} : null;},
    querySelectorAll(selector) {return selector === '.news-title[data-action="read"]' ? anchors : [];},
    getBoundingClientRect() {return {height: 600};}, scrollTop: 80, scrollIntoView() {}, focus() {},
    get innerHTML() {return rootHTML;}, set innerHTML(value) {rootHTML = value;}};
  const parent = {postMessage(value) {sent.push(JSON.parse(JSON.stringify(value)));}};
  const window = {parent, scrollY: 160, NewspaperInterviews: Interviews,
    addEventListener(name, fn) {windowHandlers[name] = fn;}};
  class ClockDate extends Date {constructor(...args) {super(...(args.length ? args : [now]));} static now() {return now;}}
  const context = vm.createContext({window, URL, Intl, Date: ClockDate, Math, navigator: {onLine: true},
    performance: {now: () => now}, document: {getElementById: () => root, activeElement: null, hidden: false,
      hasFocus: () => true, addEventListener() {}},
    localStorage: {getItem: key => storage.get(key) ?? null, setItem(key, value) {storage.set(key, value); writes.push(key);}},
    FormData: class {constructor(form) {this.form = form;} get(key) {return this.form.values[key];}},
    setTimeout() {return 1;}, clearTimeout() {}, setInterval() {}, requestAnimationFrame() {}, queueMicrotask(fn) {micros.push(fn);}});
  vm.runInContext(code, context);
  const trigger = (action, id, scope = '') => ({dataset: {action, id}, disabled: false,
    closest(selector) {return selector === 'button[data-action]' || selector === scope ? this : null;},
    getBoundingClientRect() {return {top: 240};}});
  return {api: window.testAPI, root, writes, sent,
    click(action, id = '', scope = '') {handlers.click({target: trigger(action, id, scope)});},
    search(value) {search = value; this.click('search');},
    submit(value) {handlers.submit({preventDefault() {}, target: {values: {q: value}, hasAttribute: key => key === 'data-search-form'}});},
    anchors(ids, scope) {anchors = ids.map(id => trigger('read', id, scope));},
    advance(milliseconds) {now += milliseconds;},
    flush() {while (micros.length) micros.shift()();},
  };
}

test('main navigation, home preview and catalog expose the new section without writing pin preferences', () => {
  const h = pageHarness();
  h.api.setPins(['教育校园']);
  h.api.feed([article('fresh'), article('expired', 8 * DAY)]);
  const before = h.api.inspect().data;
  assert.match(h.api.chrome(), /data-id="interviews"[^>]*>访谈与阅读/);
  assert.match(h.api.front(), /近 7 天 · 1 篇 · 进入专栏/);
  assert.match(h.api.catalogPage(), /10 个版组 · 61 个栏目/);
  assert.match(h.api.chrome(), /61 个栏目/);
  assert.match(h.api.catalogPage(), /访谈与对话 · 1/);
  assert.deepEqual(h.api.inspect().data, before);
  assert.equal(h.writes.length, 0);
  h.click('section', '访谈与对话');
  assert.equal(h.api.inspect().state.screen, 'interviews');
  assert.match(h.root.innerHTML, /<h2 class="page-title">访谈与阅读<\/h2>/);
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 expired/);
});

test('interview search and source controls stay in the section and return from reading with their state', () => {
  const h = pageHarness();
  h.api.feed([article('sanlian', DAY, {title: '青年作家的阅读对话'}),
    article('writers', DAY, {title: '另一位作家的对话', source: '中国作家网'})]);
  h.click('nav', 'interviews');
  h.click('interview-source', '三联生活周刊');
  h.search('青年 阅读');
  assert.equal(h.api.inspect().state.screen, 'interviews');
  assert.match(h.root.innerHTML, /青年作家的阅读对话/);
  assert.doesNotMatch(h.root.innerHTML, /另一位作家的对话/);
  h.anchors(['sanlian'], '.interview-news-grid');
  h.click('read', 'sanlian', '.interview-news-grid');
  const returnTo = h.api.inspect().state.returnTo;
  assert.equal(returnTo.screen, 'interviews');
  assert.equal(returnTo.query, '青年 阅读');
  assert.equal(returnTo.interviewSource, '三联生活周刊');
  assert.equal(returnTo.anchor, 'sanlian');
  assert.equal(returnTo.anchorScope, '.interview-news-grid');
  h.api.setState({query: 'elsewhere', interviewSource: '全部'});
  h.click('back');
  assert.equal(h.api.inspect().state.screen, 'interviews');
  assert.equal(h.api.inspect().state.query, '青年 阅读');
  assert.equal(h.api.inspect().state.interviewSource, '三联生活周刊');
  h.submit('没有匹配');
  assert.equal(h.api.inspect().state.screen, 'interviews');
  assert.match(h.root.innerHTML, /当前来源或搜索条件下没有访谈/);
  h.click('clear-interview-filters');
  assert.equal(h.api.inspect().state.query, '');
  assert.equal(h.api.inspect().state.interviewSource, '全部');
  assert.match(h.root.innerHTML, /另一位作家的对话/);
});

test('interviews retain source links and reading actions, while refresh preserves section filters', () => {
  const h = pageHarness();
  h.api.feed([article('a', DAY, {summary_only: false})]);
  h.click('nav', 'interviews');
  h.click('interview-source', '三联生活周刊');
  h.submit('文学');
  assert.match(h.root.innerHTML, /href="https:\/\/www\.lifeweek\.com\.cn\/article\/a"/);
  assert.match(h.root.innerHTML, /作家谈文学与阅读。/);
  for (const action of ['read', 'save', 'mark', 'hide']) assert.match(h.root.innerHTML, new RegExp(`data-action="${action}" data-id="a"`));
  h.click('refresh'); h.flush();
  assert.equal(h.sent.find(value => value.type === 'streamlit:setComponentValue').value.action, 'refresh');
  assert.equal(h.api.inspect().state.screen, 'interviews');
  assert.equal(h.api.inspect().state.interviewSource, '三联生活周刊');
  assert.equal(h.api.inspect().state.query, '文学');
});

test('configured sources remain filterable with zero recent items and failures are labeled separately', () => {
  const h = pageHarness(), configured = [
    {id: 'media_lifeweek_interviews', name: '三联生活周刊', scope: '公开媒体 · 访谈与对话', status: 'ok', count: 0, note: '近 7 天暂无新访谈'},
    {id: 'media_chinawriter_interviews', name: '中国作家网', scope: '公开媒体 · 访谈与对话', status: 'ok', count: 1},
  ];
  h.api.feed([article('writers', DAY, {source_id: 'media_chinawriter_interviews', source: '中国作家网'})], configured);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /三联生活周刊 · 近 7 天 0 篇/);
  assert.match(h.root.innerHTML, /中国作家网 · 近 7 天 1 篇/);
  assert.match(h.root.innerHTML, /data-action="interview-source" data-id="三联生活周刊"/);
  h.click('interview-source', '三联生活周刊');
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 writers|本次读取失败/);
  h.api.feed([], [{...configured[0], status: 'error', error: '公开来源暂不可用'}]);
  h.api.render();
  assert.match(h.root.innerHTML, /三联生活周刊 · 本次读取失败/);
  assert.match(h.root.innerHTML, /部分来源读取失败，可更新重试/);
  assert.doesNotMatch(h.root.innerHTML, /三联生活周刊 · 近 7 天 0 篇/);
});

test('normalization does not relabel an explicit unknown or collected time basis as publication', () => {
  const h = pageHarness();
  h.api.feed([article('valid', DAY, {time_basis: 'published'}), article('unknown-basis', DAY, {time_basis: 'unknown'}),
    article('collected', DAY, {time_basis: 'collected'})]);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /作家访谈 valid/);
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 unknown-basis|作家访谈 collected/);
});

test('retained snapshots and home previews discard interviews as their publication dates age out', () => {
  const h = pageHarness();
  h.api.feed([article('expires', 7 * DAY), article('unknown', 0, {published_at: null}), article('future', -DAY)]);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /作家访谈 expires/);
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 unknown|作家访谈 future/);
  h.advance(1); h.api.render();
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 expires/);
  assert.match(h.root.innerHTML, /近 7 天暂未收录可确认发布时间的访谈/);
  assert.match(h.api.interviewPreview(), /近 7 天 · 0 篇/);
  assert.match(h.api.catalogPage(), /访谈与对话 · 0/);
});
