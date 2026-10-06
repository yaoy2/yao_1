/* Pure three-way reader-state merge and an ordered Streamlit request channel. */
(function (root, factory) {
  const interviews = typeof module === 'object' && module.exports ? require('./interviews.js') : root?.NewspaperInterviews;
  const api = factory(interviews);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.NewspaperSync = api;
})(typeof globalThis === 'object' ? globalThis : this, function (interviews) {
  'use strict';
  const absent = Symbol('absent');
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object || {}, key);
  const forbidden = new Set(['__proto__', 'prototype', 'constructor']);
  const copy = value => value === absent ? absent : JSON.parse(JSON.stringify(value));
  const object = value => value !== absent && value !== null && typeof value === 'object' && !Array.isArray(value);
  function equal(a, b) {
    if (a === b) return true;
    if (a === absent || b === absent || typeof a !== typeof b || a === null || b === null) return false;
    if (Array.isArray(a)) return Array.isArray(b) && a.length === b.length && a.every((item, i) => equal(item, b[i]));
    if (object(a) && object(b)) {
      const keys = Object.keys(a);
      return keys.length === Object.keys(b).length && keys.every(key => own(b, key) && equal(a[key], b[key]));
    }
    return false;
  }
  function safe(value) {
    if (!value || typeof value !== 'object') return;
    for (const [key, item] of Object.entries(value)) {
      if (forbidden.has(key)) throw new Error('同步数据包含不安全字段，未修改本地内容。');
      safe(item);
    }
  }
  function documentOf(library, recommendations) {
    const result = {version: 1, library: {}, recommendations: {}};
    for (const key of ['version', 'records', 'pins', 'pinsCustomized', 'following', 'lastArticle', 'lastRead', 'design']) result.library[key] = copy(library[key]);
    if (own(library, 'interviews')) result.library.interviews = copy(library.interviews);
    for (const key of ['version', 'personalized', 'strength', 'diversity', 'profile']) result.recommendations[key] = copy(recommendations[key]);
    safe(result); return result;
  }
  function valueAt(document, path) {
    let value = document;
    for (const key of path) { if (!own(value, key)) return absent; value = value[key]; }
    return value;
  }
  function setAt(document, path, value) {
    if (!Array.isArray(path) || !path.length || path.some(key => typeof key !== 'string' || forbidden.has(key)))
      throw new Error('同步冲突位置不受支持，本地内容保留。');
    let target = document;
    path.slice(0, -1).forEach(key => { if (!object(target[key])) target[key] = {}; target = target[key]; });
    if (value === absent) delete target[path[path.length - 1]];
    else target[path[path.length - 1]] = copy(value);
  }
  function conflict(path, base, local, remote) {
    return {path: [...path], baseExists: base !== absent, localExists: local !== absent, remoteExists: remote !== absent,
      base: base === absent ? null : copy(base), local: local === absent ? null : copy(local), remote: remote === absent ? null : copy(remote)};
  }
  function mergeSet(base, local, remote) {
    const b = new Set(base), l = new Set(local), r = new Set(remote);
    return [...new Set([...local, ...remote, ...base])].filter(id => b.has(id) ? l.has(id) && r.has(id) : l.has(id) || r.has(id));
  }
  function mergeEvents(base, local, remote) {
    const index = rows => new Map(rows.map(row => [JSON.stringify([row.id, row.type]), row]));
    const b = index(base), l = index(local), r = index(remote), result = [];
    for (const key of new Set([...b.keys(), ...l.keys(), ...r.keys()])) {
      // Retractions and resets remove existing signals even if another device refreshes them.
      if (b.has(key) && (!l.has(key) || !r.has(key))) continue;
      const a = l.get(key), z = r.get(key);
      if (a || z) result.push(copy(!a ? z : !z ? a : Number(a.at) >= Number(z.at) ? a : z));
    }
    return result.sort((a, b) => b.at - a.at || a.id.localeCompare(b.id) || a.type.localeCompare(b.type)).slice(0, 600);
  }
  const recordDefaults = {saved: false, hidden: false, read: false, mark: '', note: '', tags: '', folder: '未分类', saved_at: null, detail: null};
  function mergeDocuments(base, local, remote, unresolved = [], options = {}) {
    [base, local, remote, unresolved].forEach(safe);
    base = copy(base);
    // Keep the original common ancestor for unresolved fields across reloads/polls.
    for (const item of unresolved) if (Array.isArray(item.path) && item.path.length && !item.path.some(key => forbidden.has(key)))
      setAt(base, item.path, item.baseExists ? item.base : absent);
    const conflicts = [];
    function merge(b, l, r, path) {
      if (path.join('.') === 'library.interviews') {
        if (!interviews) throw new Error('访谈记录模块暂未载入，原有收藏保留。');
        return interviews.mergeStates([b, l, r].map(value => value === absent ? undefined : value), options);
      }
      if (equal(l, r)) return copy(l);
      if (equal(l, b)) return copy(r);
      if (equal(r, b)) return copy(l);
      const name = path.join('.');
      if (['library.pins', 'library.following', 'recommendations.profile.hiddenIds'].includes(name))
        return mergeSet(b === absent ? [] : b, l, r);
      if (name === 'recommendations.profile.events') return mergeEvents(b === absent ? [] : b, l, r);
      if (path.length === 4 && path[0] === 'library' && path[1] === 'records' && ['article', 'detail'].includes(path[3])) {
        // Source snapshots are atomic; user-authored fields below remain conflict checked.
        if (path[3] === 'detail') return copy(l?.status === 'full' ? l : r?.status === 'full' ? r : l ?? r);
        const time = item => Date.parse(item?.updated_at || item?.published_at || item?.discovered_at) || 0;
        return copy(time(r) > time(l) ? r : l);
      }
      if (path.length === 4 && path[0] === 'library' && path[1] === 'records' && path[3] === 'saved_at')
        return copy(Date.parse(l) >= Date.parse(r) ? l : r);
      if (object(l) && object(r) && (object(b) || b === absent)) {
        const result = {}, baseObject = b === absent && path.length === 3 && path[1] === 'records' ? recordDefaults : b;
        for (const key of new Set([...Object.keys(baseObject === absent ? {} : baseObject), ...Object.keys(l), ...Object.keys(r)])) {
          if (name === 'library' && ['lastRead', 'lastArticle'].includes(key)) continue;
          const value = merge(own(baseObject, key) ? baseObject[key] : absent, own(l, key) ? l[key] : absent, own(r, key) ? r[key] : absent, [...path, key]);
          if (value !== absent) result[key] = value;
        }
        if (name === 'library') {
          // The resume hint is an atomic pair. Concurrent reading keeps this device's position.
          const position = equal([l.lastRead, l.lastArticle], [b.lastRead, b.lastArticle]) ? r : l;
          result.lastRead = copy(position.lastRead); result.lastArticle = copy(position.lastArticle);
        }
        return result;
      }
      conflicts.push(conflict(path, b, l, r)); return copy(l);
    }
    const document = merge(base, local, remote, []);
    // Union is also required when an unchanged whole document takes an early merge return.
    if ([base, local, remote].some(value => own(value.library, 'interviews'))) {
      if (!interviews) throw new Error('访谈记录模块暂未载入，原有收藏保留。');
      document.library.interviews = interviews.mergeStates([base.library.interviews, local.library.interviews, remote.library.interviews], options);
    }
    return {document, conflicts: conflicts.filter(item => item.path.slice(0, 2).join('.') !== 'library.interviews')};
  }
  function resolveConflict(document, item, side) {
    safe(item); if (!['local', 'remote'].includes(side)) throw new Error('invalid conflict choice');
    const result = copy(document);
    setAt(result, item.path, item[`${side}Exists`] ? item[side] : absent);
    return result;
  }
  function sameConflictValue(document, item, side = 'local') {
    return equal(valueAt(document, item.path), item[`${side}Exists`] ? item[side] : absent);
  }
  function createRequestQueue(options) {
    const schedule = options.schedule || (callback => queueMicrotask(callback));
    const setTimer = options.setTimer || setTimeout, clearTimer = options.clearTimer || clearTimeout;
    let queue = [], active = null, disabled = false, scheduled = false;
    function drain() {
      scheduled = false; if (disabled || active || !queue.length) return;
      active = queue.shift(); const item = active;
      item.timer = setTimer(() => { if (active !== item) return; active = null; item.onTimeout?.(item.value); wake(); }, item.timeout || 90000);
      options.send(copy(item.value));
    }
    function wake() { if (!scheduled) { scheduled = true; schedule(drain); } }
    return {
      enqueue(value, settings = {}) { if (active?.value.nonce === value.nonce || queue.some(item => item.value.nonce === value.nonce)) return; queue.push({value: copy(value), ...settings}); wake(); },
      acknowledge(nonce) { if (!nonce || active?.value.nonce !== nonce) return false; clearTimer(active.timer); active = null; wake(); return true; },
      cancel(predicate) { queue = queue.filter(item => !predicate(item.value)); if (active && predicate(active.value)) { clearTimer(active.timer); active = null; } wake(); },
      setDisabled(value) { disabled = value === true; if (!disabled) wake(); },
      has(action) { return active?.value.action === action || queue.some(item => item.value.action === action); },
      get active() { return active ? copy(active.value) : null; },
      get size() { return queue.length + Number(Boolean(active)); },
    };
  }
  return Object.freeze({equal, documentOf, mergeDocuments, resolveConflict, sameConflictValue, createRequestQueue});
});
