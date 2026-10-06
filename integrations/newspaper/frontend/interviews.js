/* Pure selection, fixed daily batches and bounded history for text interviews. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.NewspaperInterviews = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const CATEGORY = '访谈与对话';
  const LOOKBACK_MONTHS = 6, DAILY_LIMIT = 10, MAX_SEEN = 2400;
  const BEIJING_OFFSET = 8 * 60 * 60 * 1000, EDITION_HOUR = 9;
  const text = value => typeof value === 'string' ? value.trim() : '';
  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const publisher = article => text(article.publisher) || text(article.source);
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object || {}, key);
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const clone = value => JSON.parse(JSON.stringify(value));
  const validId = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,179}$/.test(value)
    && !['constructor', 'prototype', '__proto__'].includes(value);
  const currentTime = options => options?.now === undefined ? Date.now() : options.now;
  const daysInMonth = (year, month) => [31, year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28,
    31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month];

  function publishedTimestamp(value) {
    // A date without an explicit offset would depend on the reader's computer timezone.
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:\d{2})$/.exec(text(value));
    if (!match) return null;
    const [, yearText, monthText, dayText, hourText, minuteText, secondText, , offset] = match;
    const [year, month, day, hour, minute, second] = [yearText, monthText, dayText, hourText, minuteText, secondText || '0'].map(Number);
    if (month < 1 || month > 12 || day < 1 || day > daysInMonth(year, month - 1) || hour > 23 || minute > 59 || second > 59) return null;
    if (offset !== 'Z' && (Number(offset.slice(1, 3)) > 23 || Number(offset.slice(4, 6)) > 59)) return null;
    const timestamp = Date.parse(text(value));
    return Number.isFinite(timestamp) ? timestamp : null;
  }

  function lookbackStart(now = Date.now()) {
    if (!Number.isFinite(now)) return NaN;
    const local = new Date(now + BEIJING_OFFSET), targetMonth = local.getUTCFullYear() * 12 + local.getUTCMonth() - LOOKBACK_MONTHS;
    const year = Math.floor(targetMonth / 12), month = ((targetMonth % 12) + 12) % 12;
    return Date.UTC(year, month, Math.min(local.getUTCDate(), daysInMonth(year, month)), local.getUTCHours(),
      local.getUTCMinutes(), local.getUTCSeconds(), local.getUTCMilliseconds()) - BEIJING_OFFSET;
  }

  function editionDate(now = Date.now()) {
    return Number.isFinite(now) ? new Date(now + BEIJING_OFFSET - EDITION_HOUR * 3600000).toISOString().slice(0, 10) : '';
  }

  function validEdition(value) {
    return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)
      && publishedTimestamp(`${value}T09:00:00+08:00`) !== null;
  }

  function matchesQuery(article, query) {
    const words = text(query).toLocaleLowerCase().split(/\s+/).filter(Boolean);
    const fields = ['title', 'category', 'group', 'kind', 'source', 'publisher', 'summary', 'topic']
      .map(key => text(article[key]).toLocaleLowerCase());
    return words.every(word => fields.some(value => value.includes(word)));
  }

  function originalUrl(value) {
    try {
      const url = new URL(value);
      if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
      return url.href;
    } catch { return ''; }
  }

  function canonicalUrl(value) {
    const original = originalUrl(value); if (!original) return '';
    const url = new URL(original); url.hash = '';
    for (const key of [...url.searchParams.keys()]) if (/^(?:utm_.+|spm|fbclid|gclid|yclid|igshid)$/i.test(key)) url.searchParams.delete(key);
    url.searchParams.sort(); url.protocol = 'https:';
    if (url.pathname.length > 1) url.pathname = url.pathname.replace(/\/+$/, '');
    return url.href;
  }

  function canonicalTitle(value) {
    return text(value).normalize('NFKC').toLocaleLowerCase().replace(/[\u200b-\u200d\ufeff]/g, '').replace(/[\p{P}\p{Z}\s]+/gu, '');
  }

  // SHA-256 keeps complete identity values without retaining long URLs or article titles in history.
  function sha256(value) {
    const input = new TextEncoder().encode(value), length = Math.ceil((input.length + 9) / 64) * 64;
    const bytes = new Uint8Array(length); bytes.set(input); bytes[input.length] = 0x80;
    const view = new DataView(bytes.buffer), bits = input.length * 8;
    view.setUint32(length - 8, Math.floor(bits / 4294967296)); view.setUint32(length - 4, bits >>> 0);
    const constants = [0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
      0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
      0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
      0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
      0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
      0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
      0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
      0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2];
    const hash = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    const rotate = (word, amount) => (word >>> amount) | (word << (32 - amount)), words = new Uint32Array(64);
    for (let offset = 0; offset < length; offset += 64) {
      for (let index = 0; index < 16; index++) words[index] = view.getUint32(offset + index * 4);
      for (let index = 16; index < 64; index++) {
        const a = words[index - 15], b = words[index - 2];
        words[index] = (words[index - 16] + (rotate(a, 7) ^ rotate(a, 18) ^ (a >>> 3)) + words[index - 7]
          + (rotate(b, 17) ^ rotate(b, 19) ^ (b >>> 10))) >>> 0;
      }
      let [a,b,c,d,e,f,g,h] = hash;
      for (let index = 0; index < 64; index++) {
        const first = (h + (rotate(e, 6) ^ rotate(e, 11) ^ rotate(e, 25)) + ((e & f) ^ (~e & g)) + constants[index] + words[index]) >>> 0;
        const second = ((rotate(a, 2) ^ rotate(a, 13) ^ rotate(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        h=g;g=f;f=e;e=(d+first)>>>0;d=c;c=b;b=a;a=(first+second)>>>0;
      }
      [a,b,c,d,e,f,g,h].forEach((word, index) => {hash[index] = (hash[index] + word) >>> 0;});
    }
    return hash.map(word => word.toString(16).padStart(8, '0')).join('');
  }

  function identityKeys(article) {
    if (!object(article)) return [];
    return [['id', text(article.id)], ['url', canonicalUrl(article.url)], ['title', canonicalTitle(article.title)]]
      .filter(([, value]) => value).map(([kind, value]) => `${kind}:${sha256(value)}`);
  }

  function isVideo(article) {
    return article.video === true || article.is_video === true || /^(?:(?:video|audio)(?:\/|$)|podcast$)/i.test(text(article.media_type || article.content_type))
      || /视频|音频/.test(text(article.kind))
      || /(?:^|[【\[])\s*(?:视频|直播|音频|播客)|(?:视频|音频)(?:专访|访谈|对话)|微视频/.test(text(article.title))
      || /(?:\/(?:video|videos|shipin|live)\/|\.(?:mp4|webm|m3u8)(?:[?#]|$))/i.test(text(article.url));
  }

  function eligible(article, now) {
    if (!object(article) || article.category !== CATEGORY || !validId(article.id) || !text(article.title) || article.title.length > 2000
        || article.summary_only === true || !originalUrl(article.url) || article.url.length > 8192 || isVideo(article)
        || (own(article, 'time_basis') && article.time_basis !== 'published')) return false;
    const timestamp = publishedTimestamp(article.published_at);
    return timestamp !== null && lookbackStart(now) <= timestamp && timestamp <= now;
  }

  function blockedKeys(options, articles) {
    const keys = new Set(options.excludedKeys || []), ids = new Set([...(options.hiddenIds || []), ...(options.readIds || []), ...(options.blockedIds || [])]);
    for (const article of [...(options.blockedArticles || []), ...articles.filter(article => ids.has(article?.id))])
      for (const key of identityKeys(article)) keys.add(key);
    for (const id of ids) if (text(id)) keys.add(`id:${sha256(id)}`);
    return keys;
  }

  const quality = article => (article.content_origin === 'feed_full' || article.content_origin === 'public_article' ? 2 : 0)
    + (text(article.summary) ? 1 : 0);

  function selectRecentInterviews(articles, options = {}) {
    const now = currentTime(options);
    if (!Number.isFinite(now)) return [];
    const input = Array.isArray(articles) ? articles : [], excluded = blockedKeys(options, input), source = text(options.source) || '全部';
    const recent = input.filter(article => eligible(article, now)).map(article => ({article, keys: identityKeys(article), timestamp: publishedTimestamp(article.published_at)}));
    // Connected identity matches also cover a changed title on an otherwise identical URL.
    const parents = recent.map((_, index) => index), keyOwner = new Map();
    const find = index => {while (parents[index] !== index) {parents[index] = parents[parents[index]];index = parents[index];}return index;};
    recent.forEach((row, index) => row.keys.forEach(key => {if (keyOwner.has(key)) parents[find(index)] = find(keyOwner.get(key));else keyOwner.set(key, index);}));
    const groups = new Map();
    recent.forEach((row, index) => {const group = find(index);if (!groups.has(group)) groups.set(group, []);groups.get(group).push(row);});
    return [...groups.values()].filter(rows => !rows.some(row => row.keys.some(key => excluded.has(key))))
      .map(rows => rows.sort((a, b) => quality(b.article) - quality(a.article) || b.timestamp - a.timestamp
        || compare(canonicalUrl(a.article.url), canonicalUrl(b.article.url)) || compare(a.article.id, b.article.id))[0])
      .sort((a, b) => b.timestamp - a.timestamp || compare(a.article.id, b.article.id)).map(row => row.article)
      .filter(article => (source === '全部' || publisher(article) === source) && matchesQuery(article, options.query));
  }

  function validateState(raw) {
    const fields = (value, names) => object(value) && Object.keys(value).length === names.length && names.every(key => own(value, key));
    const validKeys = keys => Array.isArray(keys) && keys.length >= 1 && keys.length <= 3
      && keys.every(key => typeof key === 'string' && /^(?:id|url|title):[0-9a-f]{64}$/.test(key))
      && new Set(keys.map(key => key.split(':')[0])).size === keys.length;
    if (!fields(raw, ['version', 'batch', 'seen']) || raw.version !== 1 || !Array.isArray(raw.seen) || raw.seen.length > MAX_SEEN
        || raw.seen.some(row => !fields(row, ['edition_date', 'keys']) || !validEdition(row.edition_date) || !validKeys(row.keys)))
      throw new Error('访谈批次或判重记录格式不受支持，原有收藏保留。');
    if (raw.batch !== null) {
      const batch = raw.batch, generated = publishedTimestamp(batch?.generated_at);
      if (!fields(batch, ['edition_date', 'generated_at', 'articles']) || !validEdition(batch.edition_date) || generated === null
          || editionDate(generated) !== batch.edition_date || !Array.isArray(batch.articles) || batch.articles.length > DAILY_LIMIT
          || batch.articles.some(article => !eligible(article, generated)))
        throw new Error('访谈每日批次格式不受支持，原有收藏保留。');
      const keys = new Set();
      for (const article of batch.articles) {
        const identities = identityKeys(article);
        if (identities.some(key => keys.has(key))) throw new Error('访谈每日批次包含重复文章，原有收藏保留。');
        identities.forEach(key => keys.add(key));
      }
    }
    return raw;
  }

  function emptyState() {return {version: 1, batch: null, seen: []};}

  function normalizeHistory(rows, now) {
    const minimum = editionDate(lookbackStart(now)), maximum = editionDate(now), index = new Map();
    for (const row of rows) {
      if (row.edition_date < minimum || row.edition_date > maximum) continue;
      const keys = [...row.keys].sort(compare), key = keys.join('|'), previous = index.get(key);
      if (!previous || previous.edition_date < row.edition_date) index.set(key, {edition_date: row.edition_date, keys});
    }
    return [...index.values()].sort((a, b) => compare(b.edition_date, a.edition_date) || compare(a.keys.join('|'), b.keys.join('|'))).slice(0, MAX_SEEN);
  }

  function normalizeState(raw, options = {}) {
    if (raw === undefined || raw === null) return emptyState();
    validateState(raw);const now = currentTime(options);
    if (!Number.isFinite(now)) throw new Error('无法确认访谈批次日期。');
    const batch = raw.batch && raw.batch.edition_date <= editionDate(now) ? clone(raw.batch) : null;
    const seen = [...raw.seen, ...(batch ? batch.articles.map(article => ({edition_date: batch.edition_date, keys: identityKeys(article)})) : [])];
    return {version: 1, batch, seen: normalizeHistory(seen, now)};
  }

  function mergeStates(states, options = {}) {
    const now = currentTime(options), normalized = states.filter(value => value !== undefined && value !== null).map(value => normalizeState(value, {now}));
    const signature = batch => batch.articles.map(article => identityKeys(article).join('|')).join('\n');
    const batches = normalized.map(value => value.batch).filter(Boolean).sort((a, b) => compare(b.edition_date, a.edition_date)
      || publishedTimestamp(a.generated_at) - publishedTimestamp(b.generated_at) || compare(signature(a), signature(b)));
    return {version: 1, batch: batches.length ? clone(batches[0]) : null, seen: normalizeHistory(normalized.flatMap(value => value.seen), now)};
  }

  function sourceRoundRobin(articles) {
    const groups = new Map();
    for (const article of articles) {const source = publisher(article);if (!groups.has(source)) groups.set(source, []);groups.get(source).push(article);}
    const queues = [...groups.values()].sort((a, b) => publishedTimestamp(b[0].published_at) - publishedTimestamp(a[0].published_at)
      || compare(publisher(a[0]), publisher(b[0]))), selected = [];
    while (selected.length < DAILY_LIMIT && queues.some(queue => queue.length)) {
      for (const queue of queues) {if (queue.length) selected.push(queue.shift());if (selected.length === DAILY_LIMIT) break;}
    }
    return selected;
  }

  function snapshotArticle(article) {
    const fields = ['id','title','group','category','kind','source','source_id','source_family','publisher','published_at','updated_at',
      'discovered_at','time_basis','date_precision','url','summary','topic','summary_origin','content_origin','summary_only','ai_category',
      'ai_section','attribution','links','canonical','attributions','rights','license','notice'];
    return Object.fromEntries(fields.filter(key => own(article, key) && article[key] !== undefined).map(key => [key, clone(article[key])]));
  }

  function planDailyBatch(articles, rawState, options = {}) {
    const now = currentTime(options), state = normalizeState(rawState, {now}), today = editionDate(now);
    if (state.batch?.edition_date === today) return state;
    const excludedKeys = [...state.seen.flatMap(row => row.keys), ...(options.excludedKeys || [])];
    const candidates = selectRecentInterviews(articles, {...options, now, source: '全部', query: '', excludedKeys});
    const selected = sourceRoundRobin(candidates), batch = {edition_date: today, generated_at: new Date(now).toISOString(), articles: selected.map(snapshotArticle)};
    return normalizeState({version: 1, batch, seen: state.seen}, {now});
  }

  function dailyBatchRows(rawState, options = {}) {
    const now = currentTime(options), state = normalizeState(rawState, {now});
    if (state.batch?.edition_date !== editionDate(now)) return [];
    const allowed = new Set(selectRecentInterviews(state.batch.articles, {...options, now}).map(article => article.id));
    return state.batch.articles.filter(article => allowed.has(article.id));
  }

  return Object.freeze({CATEGORY, LOOKBACK_MONTHS, DAILY_LIMIT, MAX_SEEN, publishedTimestamp, lookbackStart, editionDate, canonicalUrl,
    canonicalTitle, identityKeys, isVideo, matchesQuery, selectRecentInterviews, validateState, emptyState, normalizeState, mergeStates, planDailyBatch, dailyBatchRows});
});
