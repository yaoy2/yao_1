/* Pure helpers for local library backups and concurrent note editing. */
(function (root, factory) {
  const interviews = typeof module === 'object' && module.exports ? require('./interviews.js') : root?.NewspaperInterviews;
  const api = factory(interviews);
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.NewspaperLibrary = api;
})(typeof globalThis === 'object' ? globalThis : this, function (interviews) {
  'use strict';
  const MAX_BACKUP_BYTES = 10 * 1024 * 1024;
  const MAX_RECORDS = 20000;
  const NOTE_FIELDS = ['note', 'tags', 'folder'];
  const FOLDERS = ['未分类', '工作资料', '长读收藏', '书影资料'];
  const MARKS = ['', '待读', '重要', '待核实'];
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const object = value => !!value && typeof value === 'object' && !Array.isArray(value);
  const clone = value => JSON.parse(JSON.stringify(value));
  const validId = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,179}$/.test(value)
    && !['constructor', 'prototype', '__proto__'].includes(value);

  function noteFields(record) {
    return {note: typeof record?.note === 'string' ? record.note : '',
      tags: typeof record?.tags === 'string' ? record.tags : '',
      folder: FOLDERS.includes(record?.folder) ? record.folder : '未分类'};
  }

  function mergeNoteDraft(base, draft, latest) {
    const before = noteFields(base), mine = noteFields(draft), saved = noteFields(latest);
    const patch = {}, conflicts = [];
    for (const key of NOTE_FIELDS) {
      if (mine[key] === before[key]) patch[key] = saved[key];
      else if (saved[key] === before[key] || saved[key] === mine[key]) patch[key] = mine[key];
      else { conflicts.push(key); patch[key] = saved[key]; }
    }
    return {patch, conflicts};
  }

  function parseBackup(contents) {
    if (typeof contents !== 'string') throw new Error('请选择 JSON 格式的收藏备份。');
    if (new TextEncoder().encode(contents).length > MAX_BACKUP_BYTES) throw new Error('备份超过 10 MiB，未导入任何内容。');
    let raw;
    try { raw = JSON.parse(contents.replace(/^\uFEFF/, ''), (key, value) => {
      if (['__proto__', 'constructor', 'prototype'].includes(key)) throw new Error('unsafe key');
      return value;
    }); }
    catch { throw new Error('无法解析备份文件，请选择原始导出的 JSON 文件。'); }
    if (!object(raw) || raw.format !== 'newspaper-local-library') throw new Error('这不是 Newspaper 收藏备份。');
    if (raw.version !== 1) throw new Error('此备份版本暂不支持，未导入任何内容。');
    if (!object(raw.records)) throw new Error('备份缺少有效的收藏记录。');
    const entries = Object.entries(raw.records);
    if (entries.length > MAX_RECORDS) throw new Error('备份条目过多，未导入任何内容。');
    for (const [id, record] of entries) {
      if (!validId(id) || !object(record) || !object(record.article) || record.article.id !== id
          || typeof record.article.title !== 'string' || !record.article.title.trim()) {
        throw new Error('备份包含无效的文章记录，未导入任何内容。');
      }
      for (const key of ['saved', 'hidden', 'read']) {
        if (own(record, key) && typeof record[key] !== 'boolean') throw new Error('备份的阅读或收藏状态格式不正确。');
      }
      for (const [key, limit] of [['note', 8000], ['tags', 500]]) {
        if (own(record, key) && (typeof record[key] !== 'string' || record[key].length > limit)) {
          throw new Error('备份的笔记或标签格式不正确，原内容未被截断或写入。');
        }
      }
      if ((own(record, 'folder') && !FOLDERS.includes(record.folder))
          || (own(record, 'mark') && !MARKS.includes(record.mark))) throw new Error('备份的归档或标记格式不受支持。');
      if (record.detail != null && (!object(record.detail) || record.detail.id !== id
          || (own(record.detail, 'paragraphs') && (!Array.isArray(record.detail.paragraphs)
            || record.detail.paragraphs.some(value => typeof value !== 'string'))))) {
        throw new Error('备份的文章快照格式不正确。');
      }
    }
    if (own(raw, 'interviews')) {
      if (!interviews) throw new Error('访谈记录模块暂未载入，未导入任何内容。');
      interviews.validateState(raw.interviews);
    }
    return raw;
  }

  function mergeLibraries(current, incoming, options = {}) {
    const library = clone(current), conflicts = [];
    let added = 0, overlap = 0, filled = 0;
    for (const [id, source] of Object.entries(incoming.records)) {
      if (!own(library.records, id)) { library.records[id] = clone(source); added++; continue; }
      overlap++;
      const target = library.records[id], before = JSON.stringify(target), fields = [];
      for (const key of ['note', 'tags', 'mark', 'folder']) {
        const empty = value => !value || (key === 'folder' && value === '未分类');
        if (empty(target[key])) { if (!empty(source[key])) target[key] = source[key]; }
        else if (!empty(source[key]) && target[key] !== source[key]) fields.push(key);
      }
      if (fields.length) conflicts.push({id, title: target.article.title, fields});
      if (!target.saved && source.saved) { target.saved = true; target.saved_at = source.saved_at || null; }
      target.read = target.read === true || source.read === true;
      if (!target.article.summary_only && source.detail?.status === 'full' && target.detail?.status !== 'full') {
        target.detail = clone(source.detail);
      }
      // Current hidden state, article identity, non-empty notes and settings remain authoritative.
      if (JSON.stringify(target) !== before) filled++;
    }
    if (own(current, 'interviews') || own(incoming, 'interviews')) {
      if (!interviews) throw new Error('访谈记录模块暂未载入，原有收藏保留。');
      library.interviews = interviews.mergeStates([current.interviews, incoming.interviews], options);
    }
    return {library, stats: {incoming: Object.keys(incoming.records).length, added, overlap, filled,
      conflicts: conflicts.length, total: Object.keys(library.records).length}, conflicts};
  }

  return Object.freeze({MAX_BACKUP_BYTES, MAX_RECORDS, noteFields, mergeNoteDraft, parseBackup, mergeLibraries});
});
