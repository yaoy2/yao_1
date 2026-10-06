'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const Interviews = require('../integrations/newspaper/frontend/interviews.js');
const NOW = Date.parse('2026-10-06T12:00:00+08:00'), DAY = 86400000;
const article = (id, age = DAY, patch = {}) => ({id, title: `作家访谈 ${id}`, category: '访谈与对话',
  group: '阅读与文学', kind: '访谈', source: '三联生活周刊', summary: '作家谈文学与阅读。',
  published_at: new Date(NOW - age).toISOString(), url: `https://www.lifeweek.com.cn/article/${id}`,
  summary_only: false, ...patch});
const ids = values => Array.from(values, value => value.id);

test('browser global and CommonJS expose the same storage-free interview selection', () => {
  const scope = {URL};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/newspaper/frontend/interviews.js'), 'utf8'), scope);
  assert.equal(scope.NewspaperInterviews.CATEGORY, Interviews.CATEGORY);
  assert.equal(typeof scope.NewspaperInterviews.selectRecentInterviews, 'function');
  assert.deepEqual(ids(Interviews.selectRecentInterviews([article('a')], {now: NOW})), ['a']);
});

test('the six-calendar-month range includes both exact boundaries and excludes older or future dates', () => {
  const age = NOW - Interviews.lookbackStart(NOW);
  const input = [article('old', age + 1), article('lower', age), article('middle', 30 * DAY),
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
  assert.deepEqual(Interviews.selectRecentInterviews([article('old', 200 * DAY, {updated_at: new Date(NOW).toISOString()})], {now: NOW}), []);
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
  const input = [article('sanlian', DAY, {title: '青年写作者甲的对话', summary: '谈阅读与音乐'}),
    article('writers', DAY, {title: '青年写作者乙的对话', publisher: '中国作家网', source: '作协访谈', summary: '谈阅读与音乐'}),
    article('hidden', DAY, {title: '青年写作者丙的对话'}), article('news', DAY, {category: '时政要闻'}),
    article('other', DAY, {title: '另一位作家的日常'})];
  assert.deepEqual(ids(Interviews.selectRecentInterviews(input, {now: NOW, source: '中国作家网', query: '青年 音乐'})), ['writers']);
  assert.deepEqual(ids(Interviews.selectRecentInterviews(input, {now: NOW, source: '三联生活周刊', query: '青年', hiddenIds: ['hidden']})), ['sanlian']);
  assert.equal(Interviews.selectRecentInterviews(input, {now: NOW, query: '找不到的内容'}).length, 0);
  assert.equal(Interviews.selectRecentInterviews(input, {now: NaN}).length, 0);
});

test('calendar subtraction clamps month ends in Beijing and the edition changes exactly at 09:00', () => {
  const examples = [
    ['2026-08-31T12:34:56.123+08:00', '2026-02-28T12:34:56.123+08:00'],
    ['2024-08-31T01:02:03+08:00', '2024-02-29T01:02:03+08:00'],
    ['2026-03-31T00:00:00+08:00', '2025-09-30T00:00:00+08:00'],
    ['2026-10-06T08:00:00+08:00', '2026-04-06T08:00:00+08:00'],
  ];
  for (const [now, expected] of examples) assert.equal(Interviews.lookbackStart(Date.parse(now)), Date.parse(expected));
  assert.equal(Interviews.editionDate(Date.parse('2026-10-06T08:59:59.999+08:00')), '2026-10-05');
  assert.equal(Interviews.editionDate(Date.parse('2026-10-06T09:00:00+08:00')), '2026-10-06');
});

test('identity hashes cover complete normalized titles and URLs without merging different interviews with one person', () => {
  const digest = value => crypto.createHash('sha256').update(value).digest('hex');
  const a = article('unicode-😀', DAY, {title: '某人：谈 ＡＩ 与文学！', url: 'http://source.example/interview/?b=2&utm_source=feed&a=1#part'});
  const keys = Interviews.identityKeys(a);
  assert.deepEqual(keys, [`id:${digest(a.id)}`, `url:${digest('https://source.example/interview?a=1&b=2')}`,
    `title:${digest('某人谈ai与文学')}`]);
  assert.equal(Interviews.identityKeys(article('copy', DAY, {title: '某人 谈 AI 与文学'}))[2], keys[2]);
  assert.notEqual(Interviews.identityKeys(article('different', DAY, {title: '某人谈自己的童年'}))[2], keys[2]);
  for (const value of ['abc', '中文访谈', '😀', 'x'.repeat(200)])
    assert.equal(Interviews.identityKeys({id: value})[0], `id:${digest(value)}`);
});

test('only readable text interviews enter the pool and duplicate publications keep the better readable version', () => {
  const input = [article('summary', DAY, {summary_only: true}), article('video', DAY, {title: '【视频】人物专访'}),
    article('video-url', DAY, {url: 'https://source.example/video/123'}), article('unsafe', DAY, {url: 'javascript:alert(1)'}),
    article('new-copy', DAY, {title: '同一篇访谈', source: '转载来源', content_origin: 'source_summary'}),
    article('full-original', 2 * DAY, {title: '同一篇：访谈', source: '独立博客', content_origin: 'feed_full'})];
  assert.deepEqual(ids(Interviews.selectRecentInterviews(input, {now: NOW})), ['full-original']);
  assert.deepEqual(ids(Interviews.planDailyBatch(input, undefined, {now: NOW}).batch.articles), ['full-original']);
});

test('a daily batch rotates publishers, favors their newer articles and stays fixed through refresh and filters', () => {
  const input = [...Array.from({length: 30}, (_, index) => article(`large${index}`, DAY + index * 1000, {source: '大型来源'})),
    article('blog', 2 * DAY, {source: '独立博客'}), article('talk', 3 * DAY, {source: '访谈刊物'})];
  const first = Interviews.planDailyBatch(input, undefined, {now: NOW});
  assert.equal(first.batch.articles.length, 10);
  assert.deepEqual(ids(first.batch.articles).slice(0, 3), ['large0', 'blog', 'talk']);
  assert.equal(first.seen.length, 10);
  assert.ok(first.seen.every(row => Object.keys(row).sort().join(',') === 'edition_date,keys' && row.keys.length === 3));
  const before = JSON.stringify(first);
  const refreshed = Interviews.planDailyBatch([article('brand-new', 0), ...input].reverse(), first, {now: NOW + 3600000, source: '独立博客', query: 'new'});
  assert.deepEqual(refreshed, first);
  assert.deepEqual(ids(Interviews.dailyBatchRows(first, {now: NOW, source: '独立博客'})), ['blog']);
  assert.deepEqual(Interviews.dailyBatchRows(first, {now: NOW, query: 'not-found'}), []);
  assert.equal(JSON.stringify(first), before);
});

test('new editions do not repeat previous batches or already read/hidden reposts, and never pad shortages', () => {
  const input = Array.from({length: 14}, (_, index) => article(`a${index}`, DAY + index * 1000));
  const first = Interviews.planDailyBatch(input, undefined, {now: NOW});
  const blocked = [article('old-read-id', DAY, {title: input[10].title}), article('a11', DAY)];
  const next = Interviews.planDailyBatch(input, first, {now: NOW + DAY, blockedArticles: blocked});
  assert.deepEqual(ids(next.batch.articles), ['a12', 'a13']);
  assert.equal(next.batch.edition_date, '2026-10-07');
  assert.equal(next.seen.length, 12);
  const alias = article('new-alias', DAY, {title: input[0].title, url: 'https://other.example/reposted'});
  const exhausted = Interviews.planDailyBatch([alias, ...input], next, {now: NOW + 2 * DAY, blockedArticles: blocked});
  assert.deepEqual(exhausted.batch.articles, []);
  assert.deepEqual(Interviews.planDailyBatch([article('late-arrival', 0)], exhausted, {now: NOW + 2 * DAY + 1000}), exhausted);
  assert.equal(Interviews.dailyBatchRows(first, {now: NOW, readIds: ['a0'], hiddenIds: ['a1']}).length, 8);
  assert.equal(first.batch.articles.length, 10);
});

test('history merges as a bounded union and concurrent batches deterministically keep the first batch of the newer edition', () => {
  const first = Interviews.planDailyBatch([article('a')], undefined, {now: NOW});
  const concurrent = Interviews.planDailyBatch([article('b')], undefined, {now: NOW + 60000});
  const merged = Interviews.mergeStates([first, concurrent], {now: NOW + DAY});
  assert.deepEqual(ids(merged.batch.articles), ['a']);
  assert.equal(merged.seen.length, 2);
  assert.deepEqual(merged, Interviews.mergeStates([concurrent, first], {now: NOW + DAY}));
  const newer = Interviews.planDailyBatch([article('c')], merged, {now: NOW + DAY});
  assert.deepEqual(ids(Interviews.mergeStates([first, newer], {now: NOW + DAY}).batch.articles), ['c']);
  const history = prefix => ({version: 1, batch: null, seen: Array.from({length: 1500}, (_, index) => ({edition_date: '2026-10-06',
    keys: [`id:${crypto.createHash('sha256').update(`${prefix}-${index}`).digest('hex')}`]}))});
  assert.equal(Interviews.mergeStates([history('a'), history('b')], {now: NOW}).seen.length, Interviews.MAX_SEEN);
  const stale = {version: 1, batch: null, seen: [
    {edition_date: '2026-04-05', keys: Interviews.identityKeys(article('expired-history'))},
    {edition_date: '2026-04-06', keys: Interviews.identityKeys(article('boundary-history'))},
  ]};
  assert.equal(Interviews.normalizeState(stale, {now: NOW}).seen.length, 1);
});

test('history at the six-month boundary keeps the previous edition before the Beijing 09:00 change', () => {
  const now = Date.parse('2026-10-06T08:30:00+08:00');
  const recent = article('boundary', 0, {published_at: '2026-04-06T08:40:00+08:00'});
  const history = {version: 1, batch: null, seen: [{edition_date: '2026-04-05', keys: Interviews.identityKeys(recent)}]};
  assert.equal(Interviews.normalizeState(history, {now}).seen.length, 1);
  assert.deepEqual(Interviews.planDailyBatch([recent], history, {now}).batch.articles, []);
  assert.equal(Interviews.normalizeState(history, {now: now + 3600000}).seen.length, 0);
});

function pageHarness() {
  const html = fs.readFileSync(path.join(__dirname, '../integrations/newspaper/frontend/index.html'), 'utf8');
  let code = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
  code = code.replace(/\}\)\(\);\s*$/, `window.testAPI={front,chrome,catalogPage,catalog,arts,interviewsPage,interviewPreview,interviewRows,render,snapshot,
    setState:patch=>Object.assign(state,patch),
    setPins:pins=>{data.pins=pins;data.pinsCustomized=true;},
    inspect:()=>JSON.parse(JSON.stringify({state,data})),
    feed:(raw,sourceRows=[])=>{articles=raw.map(normalizeArticle).filter(Boolean);articleIndex=new Map(articles.map(a=>[a.id,a]));sources=normalizeSources(sourceRows);receivedFeed=true;stale=true;render();}
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
  return {api: window.testAPI, root, writes, sent, storage,
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
  h.api.feed([article('fresh'), article('expired', 200 * DAY)]);
  const before = h.api.inspect().data;
  assert.match(h.api.chrome(), /data-id="interviews"[^>]*>访谈与阅读/);
  assert.match(h.api.front(), /本期 1\/10 篇 · 进入专栏/);
  assert.match(h.api.catalogPage(), /11 个版组 · 61 个栏目/);
  assert.match(h.api.chrome(), /61 个栏目/);
  assert.match(h.api.catalogPage(), /访谈与对话 · 1/);
  assert.deepEqual(h.api.inspect().data, before);
  assert.equal(h.writes.length, 1); // Only the new daily batch is persisted; preferences and records stay unchanged.
  assert.deepEqual(Object.keys(h.api.inspect().data.records), []);
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
  assert.match(h.root.innerHTML, /本期暂无符合当前来源或搜索条件的未读访谈/);
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
    {id: 'media_lifeweek_interviews', name: '三联生活周刊', scope: '公开媒体 · 访谈与对话', status: 'ok', count: 0, note: '半年内暂无文字访谈'},
    {id: 'media_chinawriter_interviews', name: '中国作家网', scope: '公开媒体 · 访谈与对话', status: 'ok', count: 1},
  ];
  h.api.feed([article('writers', DAY, {source_id: 'media_chinawriter_interviews', source: '中国作家网'})], configured);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /三联生活周刊 · 半年内 0 篇文字访谈/);
  assert.match(h.root.innerHTML, /中国作家网 · 半年内 1 篇文字访谈/);
  assert.match(h.root.innerHTML, /data-action="interview-source" data-id="三联生活周刊"/);
  h.click('interview-source', '三联生活周刊');
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 writers|本次读取失败/);
  h.api.feed([], [{...configured[0], status: 'error', error: '公开来源暂不可用'}]);
  h.api.render();
  assert.match(h.root.innerHTML, /三联生活周刊 · 本次读取失败/);
  assert.doesNotMatch(h.root.innerHTML, /三联生活周刊 · 半年内 0 篇文字访谈/);
});

test('normalization does not relabel an explicit unknown or collected time basis as publication', () => {
  const h = pageHarness();
  h.api.feed([article('valid', DAY, {time_basis: 'published'}), article('unknown-basis', DAY, {time_basis: 'unknown'}),
    article('collected', DAY, {time_basis: 'collected'})]);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /作家访谈 valid/);
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 unknown-basis|作家访谈 collected/);
});

test('page normalization preserves exclusions from explicit video and audio flags', () => {
  const h = pageHarness();
  h.api.feed([article('text'), article('video', DAY, {video: true}), article('flag', DAY, {is_video: true}),
    article('audio', DAY, {media_type: 'audio'}), article('mime', DAY, {content_type: 'video/mp4'})]);
  assert.deepEqual(ids(h.api.inspect().data.interviews.batch.articles), ['text']);
});

test('cross-industry interviews use an independent group without moving existing literature or film topics', () => {
  const h = pageHarness();
  h.api.feed([article('science', DAY, {title: '科学人物访谈', group: '科技与科学', source_id: 'media_general', source: '综合媒体'}),
    article('essay', DAY, {title: '原有文学栏目', category: '散文随笔', kind: '散文'})], [
    {id: 'media_general', name: '综合媒体', scope: '综合公开新闻', status: 'ok', count: 1},
    {id: 'future_interviews', name: '后续访谈来源', scope: '公开媒体 · 访谈与对话', status: 'ok', count: 0},
  ]);
  assert.equal(h.api.catalog[8][0], '阅读与文学');
  assert.equal(h.api.catalog[9][0], '电影与电视');
  assert.equal(h.api.catalog[10][0], '人物与访谈');
  assert.deepEqual(Array.from(h.api.catalog[10][1]), ['访谈与对话']);
  assert.doesNotMatch(h.api.arts(), /科学人物访谈/);
  assert.match(h.api.arts(), /原有文学栏目/);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /各行业、各领域人物与名人文字访谈/);
  assert.match(h.root.innerHTML, /科学人物访谈/);
  assert.match(h.root.innerHTML, /综合媒体 · 半年内 1 篇文字访谈/);
  assert.match(h.root.innerHTML, /后续访谈来源 · 半年内 0 篇文字访谈/);
  assert.match(h.root.innerHTML, /data-action="interview-source" data-id="后续访谈来源"/);
});

test('retained snapshots and home previews discard interviews as their publication dates age out', () => {
  const h = pageHarness();
  h.api.feed([article('expires', NOW - Interviews.lookbackStart(NOW)), article('unknown', 0, {published_at: null}), article('future', -DAY)]);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /作家访谈 expires/);
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 unknown|作家访谈 future/);
  h.advance(1); h.api.render();
  assert.doesNotMatch(h.root.innerHTML, /作家访谈 expires/);
  assert.match(h.root.innerHTML, /本期暂无符合当前来源或搜索条件的未读访谈/);
  assert.match(h.api.interviewPreview(), /本期 1\/10 篇/);
  assert.match(h.api.catalogPage(), /访谈与对话 · 0/);
});

test('daily snapshots remain readable after a shorter refreshed feed without sending a browser URL or unknown ID to the backend', () => {
  const h = pageHarness();
  h.api.feed([article('kept', DAY, {title: '固定批次访谈'})]);
  const before = JSON.stringify(h.api.inspect().data.interviews);
  h.api.feed([]);
  h.click('nav', 'interviews');
  assert.match(h.root.innerHTML, /固定批次访谈/);
  h.click('read', 'kept'); h.flush();
  assert.match(h.root.innerHTML, /这篇访谈保留在本期快照中/);
  assert.match(h.root.innerHTML, /当前来源列表已不再提供正文入口/);
  assert.match(h.root.innerHTML, /href="https:\/\/www\.lifeweek\.com\.cn\/article\/kept"/);
  assert.equal(h.sent.filter(value => value.type === 'streamlit:setComponentValue' && value.value.action === 'read').length, 0);
  assert.equal(JSON.stringify(h.api.inspect().data.interviews), before);
});

test('read and hidden daily articles disappear without replacements or fabricated read marks, while saved records survive the next edition', () => {
  const h = pageHarness(), input = Array.from({length: 16}, (_, index) => article(`item${index}`, DAY + index * 1000));
  h.api.feed(input); h.click('nav', 'interviews');
  const originalBatch = JSON.stringify(h.api.inspect().data.interviews.batch);
  h.click('save', 'item0'); h.click('read-status', 'item1'); h.click('hide', 'item2');
  assert.equal(h.api.interviewRows().length, 8);
  assert.equal(JSON.stringify(h.api.inspect().data.interviews.batch), originalBatch);
  assert.equal(h.api.inspect().data.records.item0.saved, true);
  assert.equal(h.api.inspect().data.records.item0.read, false);
  assert.equal(h.api.inspect().data.records.item1.read, true);
  assert.equal(h.api.inspect().data.records.item2.hidden, true);
  assert.deepEqual(Object.keys(h.api.inspect().data.records).sort(), ['item0', 'item1', 'item2']);
  const records = JSON.stringify(h.api.inspect().data.records);
  h.api.feed([article('new-during-day', 0), ...input]);
  assert.equal(JSON.stringify(h.api.inspect().data.interviews.batch), originalBatch);
  h.advance(DAY); h.api.feed(input);
  assert.equal(JSON.stringify(h.api.inspect().data.records), records);
  assert.equal(h.api.inspect().data.interviews.batch.articles.length, 6);
  assert.ok(h.api.inspect().data.interviews.batch.articles.every(value => Number(value.id.replace('item', '')) >= 10));
});

test('batch generation respects another tab changing the stored library before the next edition', () => {
  const h = pageHarness(); h.api.feed([article('first')]); h.click('save', 'first');
  const key = 'newspaper-local-library-v1', newer = JSON.parse(h.storage.get(key));
  newer.revision = 'changed-by-another-tab'; newer.records.first.note = '另一标签页的新笔记';
  h.storage.set(key, JSON.stringify(newer));
  const writesBefore = h.writes.length;
  h.advance(DAY); h.api.feed([article('second')]);
  assert.equal(h.writes.length, writesBefore);
  assert.equal(h.api.inspect().data.records.first.note, '另一标签页的新笔记');
  h.api.render();
  assert.equal(JSON.parse(h.storage.get(key)).records.first.note, '另一标签页的新笔记');
  assert.deepEqual(ids(h.api.inspect().data.interviews.batch.articles), ['second']);
});

test('initial missing or failed interview sources do not freeze an empty edition before a successful refresh', () => {
  const h = pageHarness(), ordinary = article('ordinary', DAY, {category: '教育校园'});
  h.api.feed([ordinary]);
  assert.equal(Object.hasOwn(h.api.inspect().data, 'interviews'), false);
  const source = {id: 'media_chinawriter_interviews', name: '中国作家网', scope: '公开媒体 · 访谈与对话', status: 'error', count: 0};
  h.api.feed([ordinary], [source]); h.click('nav', 'interviews');
  assert.equal(Object.hasOwn(h.api.inspect().data, 'interviews'), false);
  assert.match(h.root.innerHTML, /请更新来源后重试；尚未固定本期批次/);
  h.api.feed([article('recovered', DAY, {source: source.name, source_id: source.id})], [{...source, status: 'ok', count: 1}]);
  assert.deepEqual(ids(h.api.inspect().data.interviews.batch.articles), ['recovered']);
  assert.match(h.root.innerHTML, /作家访谈 recovered/);
});

test('a successful source check with no new readable candidates may persist an honest empty edition', () => {
  const h = pageHarness(), source = {id: 'media_chinawriter_interviews', name: '中国作家网', scope: '公开媒体 · 访谈与对话', status: 'ok', count: 0};
  h.api.feed([], [source]); h.click('nav', 'interviews');
  assert.equal(h.api.inspect().data.interviews.batch.articles.length, 0);
  assert.match(h.root.innerHTML, /本期不以旧内容或重复内容凑数/);
  h.api.feed([article('later')], [{...source, count: 1}]);
  assert.equal(h.api.inspect().data.interviews.batch.articles.length, 0);
});

test('previously displayed candidates cannot freeze an empty next edition while their source is unavailable', () => {
  const h = pageHarness(), source = {id: 'media_chinawriter_interviews', name: '中国作家网', scope: '公开媒体 · 访谈与对话', status: 'ok', count: 1};
  const old = article('old', DAY, {source: source.name, source_id: source.id});
  h.api.feed([old], [source]); h.click('nav', 'interviews');
  const previous = JSON.stringify(h.api.inspect().data.interviews), writesBefore = h.writes.length;
  h.advance(DAY);
  h.api.feed([old], [{...source, status: 'error'}]);
  assert.equal(h.api.interviewRows().length, 0);
  assert.equal(JSON.stringify(h.api.inspect().data.interviews), previous);
  assert.equal(h.writes.length, writesBefore);
  assert.match(h.root.innerHTML, /请更新来源后重试；尚未固定本期批次/);
  const recovered = article('new', 0, {source: source.name, source_id: source.id});
  h.api.feed([old, recovered], [{...source, count: 2}]);
  assert.equal(h.api.inspect().data.interviews.batch.edition_date, '2026-10-07');
  assert.deepEqual(ids(h.api.inspect().data.interviews.batch.articles), ['new']);
  assert.equal(h.api.inspect().data.interviews.seen.length, 2);
  const fixed = JSON.stringify(h.api.inspect().data.interviews.batch);
  h.api.feed([old, recovered, article('later')], [{...source, count: 3}]);
  assert.equal(JSON.stringify(h.api.inspect().data.interviews.batch), fixed);
});
