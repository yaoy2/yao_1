/* Pure selection of interviews with a confirmed publication time in the past week. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.NewspaperInterviews = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const CATEGORY = '访谈与对话';
  const WINDOW_MS = 7 * 24 * 60 * 60 * 1000;
  const text = value => typeof value === 'string' ? value.trim() : '';
  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const publisher = article => text(article.publisher) || text(article.source);

  function publishedTimestamp(value) {
    // A date without an explicit offset would depend on the reader's computer timezone.
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})$/.exec(text(value));
    if (!match) return null;
    const [, yearText, monthText, dayText, hourText, minuteText, secondText, , offset] = match;
    const [year, month, day, hour, minute, second] = [yearText, monthText, dayText, hourText, minuteText, secondText || '0'].map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > days[month - 1] || hour > 23 || minute > 59 || second > 59) return null;
    if (offset !== 'Z' && (Number(offset.slice(1, 3)) > 23 || Number(offset.slice(4, 6)) > 59)) return null;
    const timestamp = Date.parse(text(value));
    return Number.isFinite(timestamp) ? timestamp : null;
  }

  function matchesQuery(article, query) {
    const words = text(query).toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const fields = ['title', 'category', 'group', 'kind', 'source', 'publisher', 'summary', 'topic']
      .map(key => text(article[key]).toLocaleLowerCase());
    return words.every(word => fields.some(value => value.includes(word)));
  }

  function articleUrl(article) {
    try {
      const url = new URL(article.url);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
      url.hash = '';
      return url.href;
    } catch { return ''; }
  }

  function selectRecentInterviews(articles, options = {}) {
    const now = options.now === undefined ? Date.now() : options.now;
    if (!Number.isFinite(now)) return [];
    const hidden = new Set(options.hiddenIds || []), source = text(options.source) || '全部';
    const recent = (Array.isArray(articles) ? articles : []).flatMap(article => {
      if (!article || article.category !== CATEGORY || !text(article.id) || !text(article.title) || hidden.has(article.id)
          || (Object.prototype.hasOwnProperty.call(article, 'time_basis') && article.time_basis !== 'published')) return [];
      const timestamp = publishedTimestamp(article.published_at);
      // updated_at and discovered_at are deliberately never used to qualify an article.
      return timestamp !== null && now - WINDOW_MS <= timestamp && timestamp <= now
        ? [{article, timestamp, url: articleUrl(article)}] : [];
    }).sort((a, b) => b.timestamp - a.timestamp || compare(a.url, b.url) || compare(a.article.id, b.article.id));
    const ids = new Set(), urls = new Set();
    return recent.filter(({article, url}) => {
      if (ids.has(article.id) || (url && urls.has(url))) return false;
      ids.add(article.id); if (url) urls.add(url);
      return true;
    }).map(entry => entry.article).filter(article => (source === '全部' || publisher(article) === source) && matchesQuery(article, options.query));
  }

  return Object.freeze({CATEGORY, WINDOW_MS, publishedTimestamp, matchesQuery, selectRecentInterviews});
});
