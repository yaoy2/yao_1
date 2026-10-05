'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const Library = require('../integrations/newspaper/frontend/library.js');
const article = id => ({id, title: `Article ${id}`, source: 'Source'});
const record = (id, patch = {}) => ({article: article(id), saved: false, hidden: false, read: false,
  note: '', tags: '', folder: '未分类', mark: '', detail: null, ...patch});
const store = records => ({version: 1, revision: 'current', records, pins: ['教育校园'], design: {title: 19}});
const backup = records => ({format: 'newspaper-local-library', ...store(records)});

test('accepts previous v1 exports and BOM without requiring new article metadata', () => {
  const raw = backup({old: {article: article('old'), saved: true, note: 'Old note'}});
  assert.deepEqual(Library.parseBackup('\uFEFF' + JSON.stringify(raw)), raw);
});

test('rejects invalid JSON, formats, versions, state types and inconsistent IDs', () => {
  for (const raw of ['{', '{}', JSON.stringify({...backup({}), version: 2}),
    JSON.stringify(backup({a: record('other')})), JSON.stringify(backup({a: record('a', {saved: 'yes'})})),
    JSON.stringify(backup({a: record('a', {detail: {id: 'b', paragraphs: ['Wrong snapshot']}})})),
    JSON.stringify(backup({constructor: record('constructor')}))]) assert.throws(() => Library.parseBackup(raw));
});

test('rejects oversized backups and overlong notes without truncation', () => {
  assert.throws(() => Library.parseBackup(' '.repeat(Library.MAX_BACKUP_BYTES + 1)), /10 MiB/);
  assert.throws(() => Library.parseBackup(JSON.stringify(backup({a: record('a', {note: 'x'.repeat(8001)})}))), /截断/);
});

test('rejects unsafe object keys at any backup nesting level', () => {
  const encoded = JSON.stringify(backup({a: record('a')}));
  assert.throws(() => Library.parseBackup(encoded.replace('"title":"Article a"', '"title":"Article a","metadata":{"__proto__":{"polluted":true}}')));
  assert.equal({}.polluted, undefined);
});

test('merge adds new articles and fills missing fields while retaining current notes and hidden state', () => {
  const current = store({a: record('a', {note: 'Current note', hidden: false})});
  const incoming = store({a: record('a', {note: 'Backup note', tags: 'tag', saved: true, hidden: true}),
    b: record('b', {note: 'New note'})});
  const original = JSON.stringify([current, incoming]), merged = Library.mergeLibraries(current, incoming);
  assert.equal(merged.library.records.a.note, 'Current note');
  assert.equal(merged.library.records.a.tags, 'tag');
  assert.equal(merged.library.records.a.saved, true);
  assert.equal(merged.library.records.a.hidden, false);
  assert.equal(merged.library.records.b.note, 'New note');
  assert.deepEqual(merged.stats, {incoming: 2, added: 1, overlap: 1, filled: 1, conflicts: 1, total: 2});
  assert.deepEqual(merged.library.pins, current.pins);
  assert.equal(JSON.stringify([current, incoming]), original);
});

test('merge never upgrades a summary-only source to a full snapshot', () => {
  const current = store({a: record('a', {article: {...article('a'), summary_only: true}})});
  const result = Library.mergeLibraries(current, store({a: record('a', {detail: {id: 'a', status: 'full', paragraphs: ['text']}})}));
  assert.equal(result.library.records.a.detail, null);
});

test('three-way notes merge independent field edits and do not lose latest untouched fields', () => {
  const base = {note: 'Original', tags: '', folder: '未分类'};
  const result = Library.mergeNoteDraft(base, {...base, tags: 'My tag'}, {...base, note: 'Latest note'});
  assert.deepEqual(result, {patch: {note: 'Latest note', tags: 'My tag', folder: '未分类'}, conflicts: []});
});

test('three-way notes detect real concurrent conflicts and accept identical resolutions', () => {
  const base = {note: 'Original', tags: '', folder: '未分类'};
  assert.deepEqual(Library.mergeNoteDraft(base, {...base, note: 'Mine'}, {...base, note: 'Latest'}).conflicts, ['note']);
  assert.deepEqual(Library.mergeNoteDraft(base, {...base, note: 'Same'}, {...base, note: 'Same'}).conflicts, []);
});
