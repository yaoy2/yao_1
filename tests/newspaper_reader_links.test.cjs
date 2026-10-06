'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const article = patch => ({id: 'fixture-article', title: '测试文章', category: '科学前沿', kind: '报道',
  source: '示例原站', url: 'https://source.example/article/fixture', summary: '来源提供的摘要。', ...patch});

function pageHarness() {
  const html = fs.readFileSync(path.join(__dirname, '../integrations/newspaper/frontend/index.html'), 'utf8');
  let code = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
  code = code.replace(/\}\)\(\);\s*$/, `window.testAPI={originalLink,articleOriginal,
    show:(raw,options={})=>{data=defaults();details.clear();pendingReads.clear();
      const article=normalizeArticle(raw);articles=[article];articleIndex=new Map([[article.id,article]]);
      state.current=article.id;state.screen='reader';state.notesOpen=false;
      if(options.detail)details.set(article.id,normalizeDetail({...options.detail,id:article.id},article));
      if(options.loading)pendingReads.set(article.id,{nonce:'pending-fixture'});
      return reader();},
    backup:(raw,id)=>{data=normalizeStore(raw);details.clear();pendingReads.clear();articles=[];articleIndex=new Map();
      state.current=id;state.screen='reader';state.notesOpen=false;return reader();},
    list:raw=>item(normalizeArticle(raw),true)
  };})();`);
  const root = {style: {setProperty() {}}, addEventListener() {}, contains() {return false;},
    querySelector() {return null;}, querySelectorAll() {return [];}, getBoundingClientRect() {return {height: 600};}};
  const window = {parent: {postMessage() {}}, addEventListener() {}};
  const context = vm.createContext({window, URL, Intl, Date, Math, navigator: {onLine: true},
    performance: {now: () => 0}, document: {getElementById: () => root, activeElement: null, hidden: false,
      hasFocus: () => true, addEventListener() {}}, localStorage: {getItem() {return null;}, setItem() {}},
    setTimeout() {return 1;}, clearTimeout() {}, setInterval() {}, requestAnimationFrame() {}, queueMicrotask() {}});
  vm.runInContext(code, context);
  return window.testAPI;
}

function assertFooter(html, lastBodyText, expectedUrl = 'https://source.example/article/fixture') {
  const footer = html.indexOf('class="article-original"'), body = html.lastIndexOf(lastBodyText);
  const actions = html.indexOf('class="reading-actions"'), related = html.indexOf('相关栏目阅读');
  assert.ok(body >= 0 && footer > body, 'original source must follow all article paragraphs or the empty state');
  assert.ok(actions > footer && related > actions, 'original source must precede reading actions and related reading');
  assert.equal((html.match(/class="article-original"/g) || []).length, 1);
  const footerHTML = html.slice(footer, actions);
  assert.match(footerHTML, /原站来源：示例原站/);
  assert.ok(footerHTML.includes(`href="${expectedUrl}"`));
  assert.match(footerHTML, />阅读原文 ↗<\/a>/);
  assert.match(footerHTML, /target="_blank" rel="noopener noreferrer"/);
  assert.ok(html.indexOf('>原文 ↗</a>') < body, 'the existing top original link remains available');
}

test('full, summary-only, loading, failed and empty readers place the original link after their content', () => {
  const api = pageHarness();
  const cases = [
    [{}, {detail: {status: 'full', paragraphs: ['完整正文第一段。', '完整正文最后一段。']}}, '完整正文最后一段。'],
    [{summary_only: true}, {}, '来源提供的摘要。'],
    [{}, {loading: true}, '来源提供的摘要。'],
    [{}, {detail: {status: 'error', paragraphs: [], message: '读取暂时失败。'}}, '来源提供的摘要。'],
    [{summary: ''}, {detail: {status: 'error', paragraphs: []}}, '此来源暂未提供摘要或可提取的正文。'],
  ];
  for (const [patch, options, lastText] of cases) assertFooter(api.show(article(patch), options), lastText);
});

test('old saved full and summary-only backups keep their source links without current feed metadata', () => {
  const api = pageHarness();
  for (const full of [true, false]) {
    const oldArticle = article({id: 'old-backup'}), detail = full
      ? {id: 'old-backup', status: 'full', paragraphs: ['旧收藏的完整正文。']} : null;
    const backup = {version: 1, records: {'old-backup': {article: oldArticle, saved: true, detail}}};
    const before = JSON.stringify(backup), html = api.backup(backup, 'old-backup');
    assertFooter(html, full ? '旧收藏的完整正文。' : '来源提供的摘要。');
    assert.equal(JSON.stringify(backup), before);
  }
});

test('missing, unsafe and credential-bearing links produce an explicit unavailable message and no invented destination', () => {
  const api = pageHarness();
  for (const url of [undefined, '', 'javascript:alert(1)', 'java\nscript:alert(1)', 'data:text/html,unsafe',
    'file:///private.txt', 'mailto:source@example.test', '/relative-article', '//source.example/article',
    'https://user:password@source.example/article']) {
    const raw = article({url}), html = api.show(raw), list = api.list(raw);
    assert.match(html, /未提供有效原文链接，暂时无法访问原文/);
    assert.match(list, /未提供有效原文链接，暂时无法访问原文/);
    assert.doesNotMatch(html, /<a\b/);
    assert.doesNotMatch(list, /<a\b/);
    assert.equal(api.originalLink(raw), '');
  }
  const legacy = {version: 1, records: {'missing-url': {article: article({id: 'missing-url', url: undefined}), saved: true}}};
  assert.match(api.backup(legacy, 'missing-url'), /未提供有效原文链接，暂时无法访问原文/);
});

test('source names and valid original URLs are escaped without changing source bylines', () => {
  const api = pageHarness(), source = '来源 "署名" <img src=x onerror=alert(1)> & 附注';
  const html = api.show(article({source, url: 'https://source.example/article?one=1&two=%22test%22'}),
    {detail: {status: 'full', paragraphs: ['原始正文。', '编辑：原站署名示例']}});
  assert.match(html, /原站来源：来源 &quot;署名&quot; &lt;img src=x onerror=alert\(1\)&gt; &amp; 附注/);
  assert.match(html, /href="https:\/\/source\.example\/article\?one=1&amp;two=%22test%22"/);
  assert.doesNotMatch(html, /<img\b/);
  assert.equal((html.match(/编辑：原站署名示例/g) || []).length, 1);
  assert.ok(html.indexOf('编辑：原站署名示例') < html.indexOf('class="article-original"'));
});

test('all expanded article summaries end with a source entry before save and mark actions', () => {
  const api = pageHarness();
  for (const patch of [{}, {summary_only: true}, {source_family: 'ai_official', summary_only: true}]) {
    const html = api.list(article(patch)), summary = html.indexOf('来源提供的摘要。');
    const footer = html.indexOf('class="article-original"'), actions = html.indexOf('class="item-actions"');
    assert.ok(summary >= 0 && footer > summary && actions > footer);
    assert.match(html, /原站来源：示例原站/);
    assert.match(html, />阅读原文 ↗<\/a>/);
  }
});
