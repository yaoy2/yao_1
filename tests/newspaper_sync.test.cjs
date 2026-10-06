'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {spawnSync} = require('node:child_process');
const Sync = require('../integrations/newspaper/frontend/sync.js');
const Recommendation = require('../integrations/newspaper/frontend/recommendation.js');
const Library = require('../integrations/newspaper/frontend/library.js');
const clone = value => JSON.parse(JSON.stringify(value));
const article = id => ({id, title: `Article ${id}`, category: '教育校园', source: 'Source'});
const record = (id, patch = {}) => ({article: article(id), saved: false, hidden: false, read: false,
  mark: '', note: '', tags: '', folder: '未分类', saved_at: null, detail: null, ...patch});
const documentOf = records => ({version: 1,
  library: {version: 1, records, pins: ['教育校园'], pinsCustomized: false, following: [], lastRead: null,
    lastArticle: null, design: {columns: 3, title: 17, read: 18}},
  recommendations: {version: 1, personalized: true, strength: 'balanced', diversity: 'standard',
    profile: {version: 1, events: [], hiddenIds: []}}});
const event = (id, type = 'save', at = Date.now() - 1000) => ({id, type, at, category: '教育校园', group: '社会与民生', source: 'Source'});

test('two offline devices union new articles and independent note fields without mutating input', () => {
  const base = documentOf({a: record('a', {note: 'Base'})}), left = clone(base), right = clone(base);
  left.library.records.a.tags = 'teaching'; left.library.records.left = record('left', {saved: true});
  right.library.records.a.note = 'Revised'; right.library.records.right = record('right', {saved: true});
  const original = JSON.stringify([base, left, right]), result = Sync.mergeDocuments(base, left, right);
  assert.deepEqual(result.conflicts, []);
  assert.equal(result.document.library.records.a.note, 'Revised');
  assert.equal(result.document.library.records.a.tags, 'teaching');
  assert.deepEqual(Object.keys(result.document.library.records).sort(), ['a', 'left', 'right']);
  assert.equal(JSON.stringify([base, left, right]), original);
});

test('first migration merges independent edits to the same previously unseen article', () => {
  const base = documentOf({}), left = clone(base), right = clone(base);
  left.library.records.a = record('a', {note: 'Local note'});
  right.library.records.a = record('a', {saved: true, tags: 'Remote tag'});
  const result = Sync.mergeDocuments(base, left, right);
  assert.deepEqual(result.conflicts, []);
  assert.equal(result.document.library.records.a.note, 'Local note');
  assert.equal(result.document.library.records.a.tags, 'Remote tag');
  assert.equal(result.document.library.records.a.saved, true);
});

test('clear, unsave, unread, unhide, unpin, unfollow and feedback reset do not resurrect', () => {
  const base = documentOf({a: record('a', {saved: true, hidden: true, read: true, note: 'Old', tags: 'Old'})});
  base.library.following = ['group-0']; base.recommendations.profile = {version: 1, events: [event('a')], hiddenIds: ['a']};
  const left = clone(base), right = clone(base);
  Object.assign(left.library.records.a, {saved: false, hidden: false, read: false, note: '', tags: ''});
  left.library.pins = []; left.library.following = []; left.recommendations.profile = {version: 1, events: [], hiddenIds: []};
  right.library.records.a.folder = '工作资料'; right.recommendations.profile.events[0].at += 500;
  right.recommendations.profile.events.push(event('new'));
  const result = Sync.mergeDocuments(base, left, right);
  assert.deepEqual(result.conflicts, []);
  for (const key of ['saved', 'hidden', 'read']) assert.equal(result.document.library.records.a[key], false);
  for (const key of ['note', 'tags']) assert.equal(result.document.library.records.a[key], '');
  assert.deepEqual(result.document.library.pins, []); assert.deepEqual(result.document.library.following, []);
  assert.deepEqual(result.document.recommendations.profile.hiddenIds, []);
  assert.deepEqual(result.document.recommendations.profile.events.map(item => item.id), ['new']);
});

test('CAS conflict preserves both field values and survives another load until explicitly resolved', () => {
  const base = documentOf({a: record('a', {note: 'Base'})}), left = clone(base), right = clone(base);
  left.library.records.a.note = ''; right.library.records.a.note = 'Remote revision';
  const result = Sync.mergeDocuments(base, left, right);
  assert.equal(result.conflicts.length, 1); assert.equal(result.conflicts[0].local, '');
  assert.equal(result.conflicts[0].remote, 'Remote revision');
  const reload = Sync.mergeDocuments(right, result.document, right, clone(result.conflicts));
  assert.equal(reload.conflicts.length, 1);
  assert.equal(Sync.resolveConflict(reload.document, reload.conflicts[0], 'remote').library.records.a.note, 'Remote revision');
  assert.equal(Sync.resolveConflict(reload.document, reload.conflicts[0], 'local').library.records.a.note, '');
});

test('same-value concurrent edits converge; distinct scalar settings require a choice', () => {
  const base = documentOf({a: record('a')}), left = clone(base), right = clone(base);
  left.library.records.a.note = right.library.records.a.note = 'Same';
  left.recommendations.strength = 'light'; right.recommendations.strength = 'strong';
  const result = Sync.mergeDocuments(base, left, right);
  assert.equal(result.conflicts.length, 1);
  assert.deepEqual(result.conflicts[0].path, ['recommendations', 'strength']);
});

test('save acknowledgement uses sent document as ancestor and retains subsequent edits', () => {
  const sent = documentOf({a: record('a', {note: 'Sent', saved: true})}), live = clone(sent);
  live.library.records.a.note = 'Typed after sending'; live.library.records.a.saved = false;
  live.library.records.new = record('new', {saved: true});
  const result = Sync.mergeDocuments(sent, live, clone(sent));
  assert.deepEqual(result.conflicts, []); assert.equal(result.document.library.records.a.note, 'Typed after sending');
  assert.equal(result.document.library.records.a.saved, false); assert.ok(result.document.library.records.new);
});

test('resume position and source snapshots stay atomic under simultaneous updates', () => {
  const base = documentOf({a: record('a')}), left = clone(base), right = clone(base);
  left.library.lastRead = 'left'; left.library.lastArticle = article('left');
  right.library.lastRead = 'right'; right.library.lastArticle = article('right');
  left.library.records.a.article = {...article('a'), title: 'Version L', url: 'https://example.org/L'};
  right.library.records.a.article = {...article('a'), title: 'Version R', url: 'https://example.org/R'};
  const result = Sync.mergeDocuments(base, left, right);
  assert.equal(result.document.library.lastArticle.id, result.document.library.lastRead);
  assert.deepEqual(result.document.library.records.a.article, left.library.records.a.article);
  assert.deepEqual(result.conflicts, []);
});

test('events deduplicate by article/type; removed signals win over concurrent timestamp refresh', () => {
  const base = documentOf({}), left = clone(base), right = clone(base);
  base.recommendations.profile.events = [event('a')]; left.recommendations.profile.events = [event('b', 'read')];
  right.recommendations.profile.events = [event('a', 'save'), event('b', 'read', Date.now() - 500), event('b', 'important')];
  const result = Sync.mergeDocuments(base, left, right);
  assert.deepEqual(result.document.recommendations.profile.events.map(item => [item.id, item.type]).sort(), [['b', 'important'], ['b', 'read']]);
});

test('wire serialization excludes local revisions and unsafe keys fail closed', () => {
  const base = documentOf({}); base.library.revision = 'local-only';
  assert.equal('revision' in Sync.documentOf(base.library, base.recommendations).library, false);
  const unsafe = JSON.parse(JSON.stringify(base).replace('"records":{}', '"records":{"__proto__":{}}'));
  assert.throws(() => Sync.mergeDocuments(base, unsafe, base), /不安全/);
});

function queueHarness() {
  const sent = [], scheduled = [], timers = new Map(); let sequence = 0;
  const queue = Sync.createRequestQueue({send: value => sent.push(value), schedule: fn => scheduled.push(fn),
    setTimer: fn => {timers.set(++sequence, fn); return sequence;}, clearTimer: id => timers.delete(id)});
  return {queue, sent, flush() {while (scheduled.length) scheduled.shift()();}, timeout() {const [id, fn] = timers.entries().next().value; timers.delete(id); fn();}};
}
test('read, refresh and sync share one acknowledged channel, so Streamlit cannot discard queued actions', () => {
  const h = queueHarness();
  for (const action of ['reader_sync', 'read', 'refresh']) h.queue.enqueue({action, nonce: action});
  h.flush(); assert.deepEqual(h.sent.map(item => item.action), ['reader_sync']);
  assert.equal(h.queue.acknowledge('wrong'), false); h.flush(); assert.equal(h.sent.length, 1);
  h.queue.acknowledge('reader_sync'); h.flush(); assert.equal(h.sent[1].action, 'read');
  h.queue.acknowledge('read'); h.flush(); assert.equal(h.sent[2].action, 'refresh');
});
test('authorization loss removes all sync payloads while public news requests and timeout recovery continue', () => {
  const h = queueHarness(); let timedOut = false;
  h.queue.enqueue({action: 'reader_sync', nonce: 'cloud', document: {private: 'synthetic'}});
  h.queue.enqueue({action: 'reader_sync', nonce: 'cloud2', document: {private: 'synthetic'}});
  h.queue.enqueue({action: 'read', nonce: 'public'}, {onTimeout: () => {timedOut = true;}});
  h.flush(); h.queue.cancel(item => item.action === 'reader_sync'); h.flush();
  assert.equal(h.queue.has('reader_sync'), false); assert.equal(h.queue.acknowledge('cloud'), false);
  assert.equal(h.queue.active.action, 'read'); h.timeout(); h.flush(); assert.equal(timedOut, true);
});

const STORE_KEY = 'newspaper-local-library-v1', PREF_KEY = 'newspaper-local-recommendation-v1', SYNC_KEY = 'newspaper-reader-sync-v1';
function pageHarness(sharedStorage = new Map(), options = {}) {
  const html = fs.readFileSync(path.join(__dirname, '../integrations/newspaper/frontend/index.html'), 'utf8');
  let code = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].at(-1)[1];
  code = code.replace(/\}\)\(\);\s*$/, `window.testAPI={defaultSyncDocument,localSyncDocument,normalizeSyncDocument,storedSyncBaseline,persistSyncResult,
    startSync,receiveSync,chooseSyncConflict,backgroundRender,requestRead,requestRefresh,saveNote,
    edit:(id,patch)=>commit(()=>{if(!data.records[id])data.records[id]=(${record.toString()})(id);Object.assign(data.records[id],patch);}),
    setLocal:wire=>{data=normalizeStore(wire.library);recommendationPreferences=normalizeRecommendations(wire.recommendations);localStorage.setItem(STORE_KEY,JSON.stringify(data));localStorage.setItem(RECOMMEND_KEY,JSON.stringify(recommendationPreferences));},
    feed:raw=>{articles=raw.map(normalizeArticle);articleIndex=new Map(articles.map(a=>[a.id,a]));},
    draft:(id,values)=>{state.current=id;state.screen='reader';state.notesOpen=true;beginNoteEdit(id);drafts[id]=values;},
    inspect:()=>({cloud,syncRequest,data,drafts,draftBases,noteConflicts})};})();`);
  // A record constructor injected above references only this test helper's article function.
  const windows = {}, docEvents = {}, rootEvents = {}, tasks = new Map(), micros = [], sent = [], writes = [];
  let timerId = 0, now = 0, failedKey = null, noteForm = null, renders = 0, rootHTML = '';
  const root = {style: {setProperty() {}}, addEventListener(name, fn) {rootEvents[name] = fn;}, contains() {return false;},
    querySelector(selector) {return selector === '[data-note-form]' ? noteForm : null;}, querySelectorAll() {return [];},
    getBoundingClientRect() {return {height: 600};}, get innerHTML() {return rootHTML;}, set innerHTML(value) {renders++; rootHTML = value;}};
  const parent = {postMessage(value) {sent.push(clone(value));}};
  const localStorage = {getItem: key => sharedStorage.get(key) ?? null, setItem(key, value) {if (key === failedKey) throw new Error('synthetic quota failure'); sharedStorage.set(key, value); writes.push(key);}};
  const testSync = {...Sync, createRequestQueue: settings => Sync.createRequestQueue({...settings, schedule: fn => micros.push(fn),
    setTimer(fn, delay = 0) {const id = ++timerId; tasks.set(id, {fn, at: now + delay}); return id;}, clearTimer: id => tasks.delete(id)})};
  const window = {parent, NewspaperSync: options.noSync ? null : testSync, NewspaperRecommendation: Recommendation, NewspaperLibrary: Library,
    addEventListener(name, fn) {windows[name] = fn;}};
  const context = vm.createContext({window, document: {getElementById: () => root, activeElement: null, hidden: false, hasFocus: () => true,
    addEventListener(name, fn) {docEvents[name] = fn;}}, localStorage, navigator: {onLine: true}, console, URL, Intl, Date, Math, performance: {now: () => now},
    FormData: class {constructor(form) {this.form = form;} get(key) {return this.form.values[key];}},
    setTimeout(fn, delay = 0) {const id = ++timerId; tasks.set(id, {fn, at: now + delay}); return id;}, clearTimeout(id) {tasks.delete(id);},
    setInterval() {}, requestAnimationFrame() {}, queueMicrotask(fn) {micros.push(fn);}, article, STORE_KEY, RECOMMEND_KEY: PREF_KEY});
  vm.runInContext(code, context);
  function flush(milliseconds = 0) {
    now += milliseconds; let cycles = 0;
    while (true) {
      while (micros.length) {if (++cycles > 300) throw new Error('request loop'); micros.shift()();}
      const found = [...tasks].find(([, value]) => value.at <= now); if (!found) break;
      const [id, item] = found; tasks.delete(id); item.fn(); if (++cycles > 300) throw new Error('timer loop');
    }
  }
  return {api: window.testAPI, storage: sharedStorage, writes, context, sent, root, flush,
    unlock() {this.receive({enabled: true, status: 'ready'}); flush();},
    receive(payload) {windows.message({source: parent, data: {type: 'streamlit:render', args: {reader_sync: payload, request_nonce: payload.nonce}}});},
    lastRequest() {return sent.filter(item => item.type === 'streamlit:setComponentValue').at(-1)?.value;},
    storageEvent(key) {windows.storage({key});}, fail(key) {failedKey = key;},
    setDraft(id, values) {noteForm = {values}; this.api.draft(id, values);}, get renders() {return renders;},
    online(value) {context.navigator.onLine = value; if (value) windows.online();},
  };
}
function loaded(h, document, sha = 'sha-1') {const request = h.lastRequest(); h.receive({enabled: true, status: 'loaded', nonce: request.nonce, document, sha}); h.flush();}
function saved(h) {const request = h.lastRequest(); h.receive({enabled: true, status: 'saved', nonce: request.nonce, document: request.document, sha: 'sha-saved'}); h.flush();}

test('page migrates an existing local library only after unlock and merges a different cloud library', () => {
  const h = pageHarness(), local = h.api.defaultSyncDocument(), remote = clone(local);
  local.library.records.local = record('local', {note: 'Local only'}); remote.library.records.remote = record('remote', {saved: true});
  h.api.setLocal(local); h.flush(2000); assert.equal(h.lastRequest(), undefined);
  h.unlock(); assert.equal(h.lastRequest().operation, 'load'); loaded(h, remote);
  const save = h.lastRequest(); assert.equal(save.operation, 'save');
  assert.deepEqual(Object.keys(save.document.library.records).sort(), ['local', 'remote']);
  saved(h); assert.equal(h.api.inspect().cloud.status, 'synced');
});

test('page retains new local edits while a save is in flight and submits them next', () => {
  const h = pageHarness(), local = h.api.defaultSyncDocument(); local.library.records.a = record('a', {note: 'Before'});
  h.api.setLocal(local); h.unlock(); loaded(h, null, null); const sent = clone(h.lastRequest());
  h.api.edit('a', {note: 'After', saved: false});
  h.receive({enabled: true, status: 'saved', nonce: sent.nonce, document: sent.document, sha: 'sha-old'}); h.flush();
  assert.equal(h.api.localSyncDocument().library.records.a.note, 'After');
  assert.equal(h.lastRequest().operation, 'save'); assert.equal(h.lastRequest().document.library.records.a.note, 'After');
});

test('late save acknowledgements cannot restore authorization or send data after logout', () => {
  const h = pageHarness(); h.unlock(); const old = clone(h.lastRequest());
  h.receive({enabled: false, status: 'locked'}); h.flush();
  const sentCount = h.sent.length;
  h.receive({enabled: true, status: 'loaded', nonce: old.nonce, document: documentOf({}), sha: 'stale'}); h.flush(2000);
  assert.equal(h.api.inspect().cloud.enabled, false); assert.equal(h.api.inspect().cloud.baseline, null);
  assert.equal(h.api.inspect().syncRequest, null); assert.equal(h.sent.length, sentCount);
});

test('unchanged cloud reads do not rewrite shared baselines or make two tabs ping-pong', () => {
  const shared = new Map(), a = pageHarness(shared), b = pageHarness(shared);
  a.unlock(); loaded(a, a.api.defaultSyncDocument()); b.unlock(); loaded(b, b.api.defaultSyncDocument());
  const before = shared.get(SYNC_KEY), aWrites = a.writes.length, bRequests = b.sent.length;
  a.api.startSync(); a.flush(); loaded(a, a.api.defaultSyncDocument());
  assert.equal(shared.get(SYNC_KEY), before); assert.equal(a.writes.length, aWrites);
  b.storageEvent(SYNC_KEY); b.flush(2000); assert.equal(b.sent.length, bRequests);
});

test('another tab changing the baseline makes an old response reload rather than replace data', () => {
  const h = pageHarness(); h.unlock(); const first = clone(h.lastRequest()), wire = h.api.defaultSyncDocument();
  wire.library.records.newer = record('newer', {note: 'Newer tab'}); h.api.setLocal(wire);
  h.storage.set(SYNC_KEY, JSON.stringify({version: 1, token: 'other-tab', sha: 'newer', document: wire, conflicts: []}));
  h.receive({enabled: true, status: 'loaded', nonce: first.nonce, document: h.api.defaultSyncDocument(), sha: 'old'}); h.flush();
  assert.equal(h.api.localSyncDocument().library.records.newer.note, 'Newer tab');
  assert.equal(h.lastRequest().operation, 'load'); assert.notEqual(h.lastRequest().nonce, first.nonce);
});

test('each local storage write failure leaves an error and retains the current local note', () => {
  for (const key of [STORE_KEY, PREF_KEY, SYNC_KEY]) {
    const h = pageHarness(), local = h.api.defaultSyncDocument(); local.library.records.a = record('a', {note: 'Keep me'}); h.api.setLocal(local);
    const remote = clone(local); remote.library.records.remote = record('remote', {saved: true}); remote.recommendations.strength = 'strong';
    h.unlock(); h.fail(key); loaded(h, remote);
    assert.equal(h.api.inspect().cloud.status, 'error', key);
    assert.equal(h.api.localSyncDocument().library.records.a.note, 'Keep me', key);
    assert.equal(h.lastRequest().operation, 'load', key);
  }
});

test('applying a merge refuses a local document that changed after the merge input was captured', () => {
  const h = pageHarness(), base = h.api.defaultSyncDocument(), old = h.api.localSyncDocument();
  const current = clone(old); current.library.records.a = record('a', {note: 'Just changed'}); h.api.setLocal(current);
  assert.equal(h.api.persistSyncResult(base, 'sha', {document: old, conflicts: []}, '', old), false);
  assert.equal(h.api.localSyncDocument().library.records.a.note, 'Just changed');
});

test('cloud changes preserve a live note form and draft and keep its old edit ancestor', () => {
  const h = pageHarness(), local = h.api.defaultSyncDocument(); local.library.records.a = record('a', {note: 'Base'}); h.api.setLocal(local);
  h.unlock(); loaded(h, local); h.setDraft('a', {note: 'Unsaved draft', tags: 'tag', folder: '未分类'}); h.api.startSync(); h.flush();
  const before = h.renders, remote = clone(local); remote.library.records.a.note = 'Other device'; loaded(h, remote);
  assert.equal(h.renders, before); assert.equal(h.api.inspect().drafts.a.note, 'Unsaved draft');
  assert.equal(h.api.inspect().draftBases.a.note, 'Base'); assert.equal(h.api.localSyncDocument().library.records.a.note, 'Other device');
  h.api.saveNote(); assert.equal(h.api.inspect().noteConflicts.a.latest.note, 'Other device');
  assert.equal(h.api.inspect().noteConflicts.a.draft.note, 'Unsaved draft');
});

test('missing sync module still allows serialized public read and refresh requests', () => {
  const h = pageHarness(new Map(), {noSync: true}); h.api.feed([article('a')]);
  h.api.requestRead('a'); h.api.requestRefresh(); h.flush(); assert.equal(h.lastRequest().action, 'read');
  const nonce = h.lastRequest().nonce; h.receive({enabled: false, status: 'locked', nonce}); h.flush();
  assert.equal(h.lastRequest().action, 'refresh');
});

test('two offline pages resolve a real CAS conflict explicitly and persist unresolved versions across reloads', () => {
  const a = pageHarness(), b = pageHarness(), base = a.api.defaultSyncDocument(); base.library.records.a = record('a', {note: 'Base'});
  for (const h of [a, b]) {h.api.setLocal(base); h.unlock(); loaded(h, base, 'sha-0');}
  a.online(false); b.online(false); a.api.edit('a', {note: 'Device A'}); b.api.edit('a', {note: 'Device B'});
  a.flush(1000); b.flush(1000); assert.equal(a.api.inspect().cloud.status, 'offline');
  a.online(true); b.online(true); a.flush(); b.flush(); loaded(a, base, 'sha-0'); loaded(b, base, 'sha-0');
  const aSave = clone(a.lastRequest()), bSave = clone(b.lastRequest()); assert.equal(bSave.expected_sha, 'sha-0');
  a.receive({enabled: true, status: 'saved', nonce: aSave.nonce, document: aSave.document, sha: 'sha-A'}); a.flush();
  b.receive({enabled: true, status: 'conflict', nonce: bSave.nonce, document: aSave.document, sha: 'sha-A'}); b.flush();
  assert.equal(b.api.inspect().cloud.status, 'conflict'); assert.equal(b.api.inspect().cloud.conflicts[0].local, 'Device B');
  const reload = pageHarness(b.storage); reload.unlock(); assert.equal(reload.api.inspect().cloud.status, 'conflict');
  assert.equal(reload.api.inspect().cloud.conflicts[0].remote, 'Device A'); assert.equal(reload.lastRequest(), undefined);
  reload.api.chooseSyncConflict(0, 'local'); reload.flush(1000); loaded(reload, aSave.document, 'sha-A');
  assert.equal(reload.lastRequest().operation, 'save'); assert.equal(reload.lastRequest().expected_sha, 'sha-A');
  assert.equal(reload.lastRequest().document.library.records.a.note, 'Device B'); saved(reload);
  assert.equal(reload.api.inspect().cloud.status, 'synced');
});

test('actual normalized browser documents, snapshots and resume positions satisfy the backend wire contract', () => {
  const h = pageHarness(), base = h.api.defaultSyncDocument(), raw = clone(base);
  raw.library.records.a = record('a', {saved: true, note: '教学笔记', tags: 'AI,教学', folder: '工作资料',
    article: {...article('a'), url: 'https://example.org/article', attribution: {label: 'Synthetic source', links: ['https://example.org']},
      canonical: 'https://example.org/article', summary: 'Synthetic summary'},
    detail: {id: 'a', status: 'full', paragraphs: ['第一段。', 'Second paragraph.'], source: 'Source', url: 'https://example.org/article'}});
  raw.library.lastRead = 'a'; raw.library.lastArticle = raw.library.records.a.article;
  raw.recommendations.profile.events = [event('a')];
  const docs = [base, h.api.normalizeSyncDocument(raw)];
  const result = spawnSync(process.env.PYTHON || 'python', ['-X', 'utf8', '-c',
    'import json,sys; from utils.newspaper_reader_sync import validate_reader_document; docs=json.load(sys.stdin); [validate_reader_document(doc) for doc in docs]; print(len(docs))'],
  {cwd: path.join(__dirname, '..'), input: JSON.stringify(docs), encoding: 'utf8'});
  assert.equal(result.status, 0, result.stderr || result.error?.message); assert.equal(result.stdout.trim(), '2');
});

test('baseline write failure recovers the original conflict and another cloud edit is never silently overwritten', () => {
  const h = pageHarness(), base = h.api.defaultSyncDocument(); base.library.records.a = record('a', {note: 'Base'});
  h.api.setLocal(base); h.unlock(); loaded(h, base, 'sha-0'); h.api.edit('a', {note: 'Mine'}); h.flush(1000);
  const remote = clone(base); remote.library.records.a.note = 'Theirs'; h.fail(SYNC_KEY); loaded(h, remote, 'sha-1');
  assert.equal(h.api.inspect().cloud.status, 'error'); assert.equal(h.api.localSyncDocument().library.records.a.note, 'Mine');
  h.fail(null); h.api.startSync(); h.flush(); loaded(h, remote, 'sha-1');
  assert.equal(h.api.inspect().cloud.conflicts.length, 1); h.api.chooseSyncConflict(0, 'local'); h.flush(1000);
  remote.library.records.a.note = 'Their newer edit'; loaded(h, remote, 'sha-2');
  assert.equal(h.api.inspect().cloud.status, 'conflict'); assert.equal(h.api.inspect().cloud.conflicts[0].remote, 'Their newer edit');
});

test('an unrelated saved change can sync while an unsaved note draft remains local to the form', () => {
  const h = pageHarness(), base = h.api.defaultSyncDocument(); base.library.records.a = record('a', {note: 'Saved note'});
  h.api.setLocal(base); h.unlock(); loaded(h, base, 'sha-0');
  h.setDraft('a', {note: 'Private unsaved draft', tags: '', folder: '未分类'});
  h.api.edit('a', {tags: 'Saved tag'}); h.flush(1000); loaded(h, base, 'sha-0');
  const payload = h.lastRequest(); assert.equal(payload.operation, 'save');
  assert.equal(payload.document.library.records.a.note, 'Saved note'); assert.equal(payload.document.library.records.a.tags, 'Saved tag');
  assert.equal(h.api.inspect().drafts.a.note, 'Private unsaved draft');
});

test('incomplete cloud version receipts never clear local data or become an acknowledged baseline', () => {
  for (const reply of [{status: 'saved', document: null, sha: null}, {status: 'loaded', document: documentOf({}), sha: null}]) {
    const h = pageHarness(), base = h.api.defaultSyncDocument(); base.library.records.a = record('a', {note: 'Keep local'});
    h.api.setLocal(base); h.unlock(); const nonce = h.lastRequest().nonce;
    h.receive({enabled: true, nonce, ...reply}); h.flush();
    assert.equal(h.api.inspect().cloud.status, 'error'); assert.equal(h.api.localSyncDocument().library.records.a.note, 'Keep local');
    assert.equal(h.storage.has(SYNC_KEY), false);
  }
});
