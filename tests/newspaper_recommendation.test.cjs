'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const Recommendation = require('../integrations/newspaper/frontend/recommendation.js');
const NOW = Date.parse('2026-10-04T12:00:00+08:00'), DAY = 86400000;
const article = (id, group = '科技', category = '人工智能', source = '来源甲') => ({id, group, category, source,
  title: `真实候选 ${id}`, published_at: new Date(NOW - DAY).toISOString()});
function candidates() {
  return Array.from({length: 120}, (_, index) => article(`a${index}`, `版组${Math.floor(index / 24)}`,
    `栏目${Math.floor(index / 8)}`, `来源${index % 12}`));
}
function trained() {
  let profile = Recommendation.defaultProfile();
  for (let index = 0; index < 24; index++) profile = Recommendation.applyFeedback(profile,
    article(`training${index}`, '版组0', '栏目0', `来源${index % 4}`), 'important', {now: NOW - (11 - Math.floor(index / 2)) * DAY});
  return profile;
}
function histogram(items, field) {
  return items.reduce((counts, item) => { const value = item.article[field]; counts[value] = (counts[value] || 0) + 1; return counts; }, {});
}

test('browser global and CommonJS expose the same storage-free API', () => {
  const scope = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../integrations/newspaper/frontend/recommendation.js'), 'utf8'), scope);
  assert.equal(typeof scope.NewspaperRecommendation.rankRecommendations, 'function');
  assert.deepEqual(Recommendation.defaultProfile(), {version: 1, events: [], hiddenIds: []});
});

test('single strong interest still leaves multiple groups, sources and at least 40% breadth', () => {
  const result = Recommendation.rankRecommendations(candidates(), trained(), {now: NOW});
  const cold = Recommendation.rankRecommendations(candidates(), null, {now: NOW});
  assert.equal(result.items.length, 20);
  assert.ok(result.stats.counts.interest <= 12);
  assert.ok(result.stats.counts.cross + result.stats.counts.explore >= 8);
  assert.ok(result.items.filter(item => item.lane === 'cross' || item.lane === 'explore').every(item => item.article.category !== '栏目0'));
  assert.ok(Object.keys(histogram(result.items, 'group')).length >= 3);
  assert.ok(Object.keys(histogram(result.items, 'source')).length >= 5);
  for (const field of ['group', 'category', 'source']) assert.ok(Math.max(...Object.values(histogram(result.items, field))) <= result.stats.caps[field]);
  assert.ok(result.items.every(item => typeof item.reason === 'string' && item.reason && Number.isFinite(item.score)));
  assert.ok(result.stats.interests.some(interest => interest.category === '栏目0'));
  assert.ok((histogram(result.items, 'category')['栏目0'] || 0) > (histogram(cold.items, 'category')['栏目0'] || 0));
  assert.ok((histogram(result.items, 'group')['版组0'] || 0) > (histogram(cold.items, 'group')['版组0'] || 0));
});

test('strength is bounded; wide diversity has stricter caps', () => {
  for (const [strength, maximum] of [['light', 8], ['balanced', 12], ['strong', 14], ['100%', 12]]) {
    const result = Recommendation.rankRecommendations(candidates(), trained(), {now: NOW, strength, diversity: 'wide'});
    assert.equal(result.items.length, 20);
    assert.ok(result.stats.counts.interest <= maximum);
    assert.ok(result.stats.counts.cross + result.stats.counts.explore >= 6);
    for (const field of ['group', 'category', 'source']) assert.ok(Math.max(...Object.values(histogram(result.items, field))) <= result.stats.caps[field]);
  }
});

test('fresh cross-domain articles cannot consume the only source capacity for a learned interest', () => {
  const dated = (id, category, group, source, age = 0) => ({...article(id, group, category, source),
    published_at: new Date(NOW - age * DAY).toISOString()});
  const profile = Recommendation.applyFeedback(null, dated('liked', '目标栏目', '目标版组', '来源S'), 'important', {now: NOW});
  const interest = Array.from({length: 5}, (_, index) => dated(`interest${index}`, '目标栏目', '目标版组', '来源S'));
  const sameSourceCross = Array.from({length: 5}, (_, index) => dated(`cross-S${index}`, `新栏目${index}`, `新版组${index}`, '来源S'));
  const alternatives = Array.from({length: 60}, (_, index) => dated(`cross-other${index}`, `栏目${index % 10}`, `版组${index % 6}`, `其他来源${index % 8}`, 30));
  const input = [...interest, ...sameSourceCross, ...alternatives];
  const result = Recommendation.rankRecommendations(input, profile, {now: NOW, seed: 'audit'});
  const cold = Recommendation.rankRecommendations(input, null, {now: NOW, seed: 'audit'});
  assert.equal(result.items.length, 20);
  assert.equal(result.stats.counts.interest, 5);
  assert.ok(result.items.filter(item => item.article.category === '目标栏目').length > cold.items.filter(item => item.article.category === '目标栏目').length);
  assert.ok(result.items.filter(item => item.article.source === '来源S').every(item => item.lane === 'interest'));
  assert.ok(result.stats.counts.cross >= result.stats.quotas.cross);
  assert.ok(result.stats.counts.explore >= result.stats.quotas.explore);
  for (const field of ['group', 'category', 'source']) assert.ok(Math.max(...Object.values(histogram(result.items, field))) <= result.stats.caps[field]);
  assert.deepEqual(result, Recommendation.rankRecommendations([...input].reverse(), profile, {now: NOW, seed: 'audit'}));
});

test('scarce cross-domain source slots are also protected from a stronger interest pool', () => {
  let profile = Recommendation.applyFeedback(null, article('learn-A', '偏好版组A', '偏好栏目A', '来源S'), 'important', {now: NOW});
  profile = Recommendation.applyFeedback(profile, article('learn-B', '偏好版组B', '偏好栏目B', '来源T'), 'important', {now: NOW});
  const preferred = Array.from({length: 60}, (_, index) => ({...article(`preferred${index}`, `偏好版组${index % 2 ? 'B' : 'A'}`,
    `偏好栏目${index % 2 ? 'B' : 'A'}`, index < 10 ? '来源S' : `兴趣来源${index % 8}`),
    published_at: new Date(NOW - (index < 10 ? 0 : DAY)).toISOString()}));
  const cross = Array.from({length: 5}, (_, index) => article(`scarce-cross${index}`, `其他版组${index}`, `其他栏目${index}`, '来源S'));
  const explore = Array.from({length: 12}, (_, index) => article(`explore${index}`, '偏好版组B', `探索栏目${index % 3}`, `探索来源${index % 4}`));
  const result = Recommendation.rankRecommendations([...preferred, ...cross, ...explore], profile, {now: NOW});
  assert.equal(result.items.length, 20);
  assert.equal(result.stats.counts.cross, 5);
  assert.equal(result.stats.counts.explore, 3);
  assert.equal(result.stats.counts.interest, 12);
  assert.ok(cross.every(candidate => result.items.some(item => item.article.id === candidate.id)));
  for (const field of ['group', 'category', 'source']) assert.ok(Math.max(...Object.values(histogram(result.items, field))) <= result.stats.caps[field]);
});

test('a same-lane substitution fills a feasible slot blocked by intersecting caps', () => {
  const profile = Recommendation.applyFeedback(null, article('learn', 'G0', 'C0', 'S0'), 'important', {now: NOW});
  const rows = [
    ['C5', 'G2', 'S3', 9], ['C1', 'G0', 'S1', 11], ['C1', 'G0', 'S3', 3], ['C1', 'G0', 'S2', 10],
    ['C4', 'G2', 'S2', 3], ['C5', 'G2', 'S3', 11], ['C2', 'G1', 'S3', 10], ['C1', 'G0', 'S0', 8],
    ['C5', 'G2', 'S2', 6], ['C4', 'G2', 'S2', 10],
  ];
  const input = rows.map(([category, group, source, age], index) => ({...article(`a${index}`, group, category, source),
    published_at: new Date(NOW - age * DAY).toISOString()}));
  const result = Recommendation.rankRecommendations(input, profile, {now: NOW, limit: 6, seed: 'fixed'});
  assert.equal(result.items.length, 6);
  assert.deepEqual(result.stats.counts, {interest: 3, cross: 1, explore: 2, balance: 0});
  assert.ok(result.items.some(item => item.article.source === 'S1'));
  assert.equal(result.stats.degraded, false);
  assert.equal(new Set(result.items.map(item => item.article.id)).size, 6);
  for (const field of ['group', 'category', 'source']) assert.ok(Math.max(...Object.values(histogram(result.items, field))) <= result.stats.caps[field]);
  assert.deepEqual(result, Recommendation.rankRecommendations([...input].reverse(), profile, {now: NOW, limit: 6, seed: 'fixed'}));
});

test('short clicks do not train; repeated article and same-column clicking are capped', () => {
  const target = article('read');
  let profile = Recommendation.applyFeedback(null, target, 'read', {now: NOW, dwellMs: 14999});
  assert.equal(profile.events.length, 0);
  profile = Recommendation.applyFeedback(profile, target, 'read', {now: NOW, dwellMs: 15000});
  for (let index = 0; index < 20; index++) profile = Recommendation.applyFeedback(profile, target, 'read', {now: NOW + 1000, dwellMs: 60000});
  assert.equal(profile.events.length, 1);
  for (let index = 0; index < 20; index++) profile = Recommendation.applyFeedback(profile, article(`other${index}`), 'read', {now: NOW + 2000, dwellMs: 60000});
  assert.equal(profile.events.length, 4);
  profile = Recommendation.applyFeedback(profile, target, 'read', {now: NOW + 31 * DAY, dwellMs: 15000});
  assert.equal(profile.events.filter(event => event.id === 'read').length, 1);
});

test('save and important outweigh reading, and signals decay by half in 14 days', () => {
  const sample = article('weight');
  const getWeight = (type, now = NOW) => {
    const profile = Recommendation.applyFeedback(null, sample, type, {now: NOW, dwellMs: 15000});
    return Recommendation.rankRecommendations([sample], profile, {now}).stats.interests[0]?.weight || 0;
  };
  assert.ok(getWeight('save') > getWeight('read'));
  assert.ok(getWeight('important') > getWeight('save'));
  assert.equal(getWeight('important', NOW + 14 * DAY), getWeight('important') / 2);
  assert.equal(getWeight('important', NOW + 91 * DAY), 0);
});

test('negative feedback reduces similar preference without banning its entire domain', () => {
  let profile = Recommendation.applyFeedback(null, article('liked'), 'important', {now: NOW});
  const before = Recommendation.rankRecommendations([article('similar')], profile, {now: NOW}).stats.interests[0].weight;
  profile = Recommendation.applyFeedback(profile, article('disliked'), 'dislike', {now: NOW});
  const after = Recommendation.rankRecommendations([article('similar')], profile, {now: NOW}).stats.interests[0].weight;
  assert.ok(after < before && after > 0);
  const result = Recommendation.rankRecommendations([article('similar'), article('disliked')], profile, {now: NOW});
  assert.ok(result.items.some(item => item.article.id === 'similar'));
  assert.ok(!result.items.some(item => item.article.id === 'disliked'));
});

test('hidden candidates are always excluded from profile, library and article flags', () => {
  const profile = Recommendation.applyFeedback(null, article('hidden-profile'), 'hide', {now: NOW});
  const hiddenArticle = {...article('hidden-flag'), hidden: true};
  const result = Recommendation.rankRecommendations([article('hidden-profile'), article('hidden-library'), hiddenArticle,
    article('visible', '其他版组', '其他栏目', '其他来源')], profile, {now: NOW, hiddenIds: ['hidden-library']});
  assert.deepEqual(result.items.map(item => item.article.id), ['visible']);
  assert.equal(result.stats.available, 1);
  const restored = Recommendation.applyFeedback(profile, article('hidden-profile'), 'restore', {now: NOW});
  assert.equal(restored.hiddenIds.length, 0);
  assert.equal(restored.events.length, 0);
});

test('cold start balances sources and sections without inventing preferences', () => {
  const result = Recommendation.rankRecommendations(candidates(), null, {now: NOW});
  assert.equal(result.items.length, 20);
  assert.equal(result.stats.coldStart, true);
  assert.deepEqual(result.stats.interests, []);
  assert.ok(result.items.every(item => item.lane === 'balance'));
  assert.equal(Object.keys(histogram(result.items, 'group')).length, 5);
  assert.ok(Object.keys(histogram(result.items, 'source')).length >= 8);
});

test('Atom items with only an update timestamp receive their actual freshness weight', () => {
  const updated = {...article('atom-updated'), published_at: '', updated_at: new Date(NOW - 60000).toISOString()};
  const older = {...article('older-published'), published_at: new Date(NOW - 21 * DAY).toISOString()};
  const result = Recommendation.rankRecommendations([older, updated], null, {now: NOW});
  assert.equal(result.items[0].article.id, 'atom-updated');
  assert.ok(result.items[0].score > result.items[1].score);
  assert.equal(result.items[0].article.published_at, '', 'an update time is never rewritten as publication time');
});

test('reset removes all learning; inverse feedback removes only the matching signal', () => {
  const target = article('both');
  let profile = Recommendation.applyFeedback(null, target, 'save', {now: NOW});
  profile = Recommendation.applyFeedback(profile, target, 'important', {now: NOW});
  profile = Recommendation.applyFeedback(profile, target, 'unsave', {now: NOW});
  assert.deepEqual(profile.events.map(event => event.type), ['important']);
  assert.deepEqual(Recommendation.applyFeedback(profile, target, 'unimportant', {now: NOW}), Recommendation.defaultProfile());
  assert.deepEqual(Recommendation.resetProfile(profile), Recommendation.defaultProfile());
  assert.deepEqual(Recommendation.reset(profile), Recommendation.defaultProfile());
});

test('sparse or concentrated candidates honestly return fewer items without fabricating breadth', () => {
  const sparse = Recommendation.rankRecommendations([article('one'), article('one'), article('two')], null, {now: NOW});
  assert.equal(sparse.stats.available, 2);
  assert.equal(sparse.items.length, 2);
  assert.equal(sparse.stats.degraded, true);
  assert.ok(sparse.stats.notes.length);
  const onlyInterest = Array.from({length: 30}, (_, index) => article(`same${index}`, '版组0', '栏目0', '来源0'));
  const result = Recommendation.rankRecommendations(onlyInterest, trained(), {now: NOW});
  assert.equal(result.stats.counts.cross, 0);
  assert.equal(result.stats.counts.explore, 0);
  assert.ok(result.items.length <= result.stats.caps.source);
  assert.equal(result.stats.degraded, true);
  const differentPublishers = onlyInterest.map((item, index) => ({...item, source: `新来源${index}`}));
  const sameColumn = Recommendation.rankRecommendations(differentPublishers, trained(), {now: NOW});
  assert.equal(sameColumn.stats.counts.explore, 0, 'a different publisher of the same interest is not exploratory breadth');
  const empty = Recommendation.rankRecommendations([], null, {now: NOW});
  assert.deepEqual(empty.items, []);
  assert.equal(empty.stats.returned, 0);
  assert.deepEqual(empty.stats.notes, ['当前没有可推荐的未隐藏新闻。']);
});

test('sparse breadth is reported as an actual percentage rather than a guaranteed target', () => {
  let profile = Recommendation.applyFeedback(null, article('like-a', '组A', '栏目A', '来源A'), 'important', {now: NOW});
  profile = Recommendation.applyFeedback(profile, article('like-b', '组A', '栏目B', '来源B'), 'important', {now: NOW});
  const preferred = Array.from({length: 30}, (_, index) => article(`preferred${index}`, '组A', index % 2 ? '栏目A' : '栏目B', `兴趣来源${index % 8}`));
  const input = [...preferred, article('outside', '别的组', '别的栏目', '别的来源')];
  const result = Recommendation.rankRecommendations(input, profile, {now: NOW});
  assert.ok(result.items.length > 1, 'retain available news instead of creating an empty quota-compliant result');
  assert.equal(result.stats.coverage.targetBreadthPercent, 40);
  assert.equal(result.stats.coverage.breadthPercent, Math.round(1 / result.items.length * 1000) / 10);
  assert.equal(result.stats.coverage.belowBreadthTarget, true);
  assert.ok(result.stats.notes.some(note => note.includes(`${result.stats.coverage.breadthPercent}%`) && note.includes('目标 40%')));
  const cold = Recommendation.rankRecommendations(input, null, {now: NOW});
  assert.equal(cold.stats.coverage.balancePercent, 100);
  assert.equal(cold.stats.coverage.targetBreadthPercent, null);
  assert.equal(cold.stats.coverage.belowBreadthTarget, false);
});

test('sorting is deterministic, independent of candidate order, and never mutates inputs', () => {
  const input = candidates(), profile = trained(), original = JSON.stringify([input, profile]);
  const first = Recommendation.rankRecommendations(input, profile, {now: NOW, seed: 'stable'});
  const second = Recommendation.rankRecommendations([...input].reverse(), profile, {now: NOW, seed: 'stable'});
  assert.deepEqual(first, second);
  assert.equal(JSON.stringify([input, profile]), original);
  const different = Recommendation.rankRecommendations(input, profile, {now: NOW, seed: 'different'});
  assert.notDeepEqual(first.items.map(item => item.article.id), different.items.map(item => item.article.id));
});

test('a thousand candidates preserve deterministic selection, breadth and dimension caps', () => {
  const input = Array.from({length: 1000}, (_, index) => article(`large${index}`, `版组${Math.floor(index / 50)}`,
    `栏目${Math.floor(index / 10)}`, `来源${index % 24}`));
  const result = Recommendation.rankRecommendations(input, trained(), {now: NOW, seed: 'large'});
  assert.equal(result.items.length, 20);
  assert.ok(result.stats.counts.cross + result.stats.counts.explore >= 8);
  for (const field of ['group', 'category', 'source']) assert.ok(Math.max(...Object.values(histogram(result.items, field))) <= result.stats.caps[field]);
  assert.deepEqual(result, Recommendation.rankRecommendations([...input].reverse(), trained(), {now: NOW, seed: 'large'}));
});

test('profile normalization bounds fields, drops invalid or expired events, and strips article content', () => {
  const events = Array.from({length: 1000}, (_, index) => ({...article(`id${index}`), type: 'read', at: NOW - index,
    title: 'not retained', url: 'https://example.com/private', note: 'not retained'}));
  events.push({...events[0], at: NOW + DAY}, {...events[0], id: 'expired', at: NOW - 91 * DAY}, {...events[0], type: '__proto__'});
  const profile = Recommendation.normalizeProfile({version: 1, events, hiddenIds: Array.from({length: 2100}, (_, index) => `hidden${index}`)}, {now: NOW});
  assert.equal(profile.events.length, 600);
  assert.equal(profile.hiddenIds.length, 2000);
  assert.deepEqual(Object.keys(profile.events[0]).sort(), ['id', 'category', 'group', 'source', 'type', 'at'].sort());
  assert.ok(profile.events.every(event => event.at <= NOW && event.id !== 'expired'));
  assert.deepEqual(Recommendation.normalizeProfile({version: 99, events}, {now: NOW}), Recommendation.defaultProfile());
  assert.equal(Recommendation.rankRecommendations(candidates(), null, {now: NOW, limit: 0}).items.length, 0);
});
