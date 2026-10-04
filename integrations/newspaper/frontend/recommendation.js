/* Local, deterministic recommendations. This module has no storage or network access. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.NewspaperRecommendation = api;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';

  const DAY = 86400000;
  const LIMITS = Object.freeze({events: 600, hiddenIds: 2000, retentionDays: 90,
    halfLifeDays: 14, repeatDays: 30, readDwellMs: 15000, recommendations: 50});
  const WEIGHTS = Object.freeze({read: 0.6, save: 3, important: 4, dislike: -2.5});
  const DAILY_CAPS = Object.freeze({read: 4, save: 3, important: 2, dislike: 3});
  const RATIOS = Object.freeze({light: [0.4, 0.35, 0.25], balanced: [0.6, 0.25, 0.15], strong: [0.7, 0.2, 0.1]});
  const LANES = ['interest', 'cross', 'explore', 'balance'];
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const text = (value, length = 100) => typeof value === 'string'
    ? value.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, length) : '';
  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const timestamp = value => value instanceof Date ? value.getTime()
    : typeof value === 'number' ? value : typeof value === 'string' ? Date.parse(value) : NaN;
  function currentTime(options) {
    const value = timestamp(options && options.now);
    return Number.isFinite(value) ? value : Date.now();
  }
  function dimensions(article) {
    if (!article || typeof article !== 'object') return null;
    const id = text(article.id, 180);
    return id ? {id, category: text(article.category) || '未分类',
      group: text(article.group) || '未分组', source: text(article.source || article.publisher) || '来源未注明'} : null;
  }
  function defaultProfile() { return {version: 1, events: [], hiddenIds: []}; }
  function normalizeIds(values, maximum) {
    if (!Array.isArray(values)) return [];
    return [...new Set(values.map(value => text(value, 180)).filter(Boolean))].slice(-maximum);
  }

  // Profiles deliberately omit titles, URLs, article text, notes and user identifiers.
  // The library's complete hiddenIds should also be passed to rankRecommendations;
  // its user-controlled hidden list remains authoritative beyond this bounded profile.
  function normalizeProfile(raw, options = {}) {
    const result = defaultProfile(), now = currentTime(options);
    if (!raw || typeof raw !== 'object' || (raw.version !== undefined && raw.version !== 1)) return result;
    result.hiddenIds = normalizeIds(raw.hiddenIds, LIMITS.hiddenIds);
    const seen = new Set();
    result.events = (Array.isArray(raw.events) ? raw.events : []).map(event => {
      if (!event || typeof event !== 'object' || !own(WEIGHTS, event.type)) return null;
      const values = dimensions(event), at = timestamp(event.at);
      if (!values || !Number.isFinite(at) || at > now || now - at > LIMITS.retentionDays * DAY) return null;
      return {...values, type: event.type, at};
    }).filter(Boolean).sort((a, b) => b.at - a.at || compare(a.id, b.id) || compare(a.type, b.type))
      .filter(event => {
        const key = JSON.stringify([event.id, event.type]);
        if (seen.has(key)) return false;
        seen.add(key); return true;
      }).slice(0, LIMITS.events);
    return result;
  }

  function applyFeedback(raw, article, type, options = {}) {
    const now = currentTime(options), profile = normalizeProfile(raw, {now}), values = dimensions(article);
    if (!values) return profile;
    if (type === 'restore') {
      profile.hiddenIds = profile.hiddenIds.filter(id => id !== values.id);
      profile.events = profile.events.filter(event => !(event.id === values.id && event.type === 'dislike'));
      return profile;
    }
    if (type === 'unsave' || type === 'unimportant') {
      const removed = type === 'unsave' ? 'save' : 'important';
      profile.events = profile.events.filter(event => !(event.id === values.id && event.type === removed));
      return profile;
    }
    if (type === 'hide' || type === 'dislike') {
      profile.hiddenIds = normalizeIds([...profile.hiddenIds, values.id], LIMITS.hiddenIds);
      type = 'dislike';
    }
    if (!own(WEIGHTS, type)) return profile;
    if (type === 'read' && (!Number.isFinite(options.dwellMs) || options.dwellMs < LIMITS.readDwellMs)) return profile;
    if (profile.events.some(event => event.id === values.id && event.type === type && now - event.at < LIMITS.repeatDays * DAY)) return profile;
    // A rolling 24-hour cap prevents clicking many same-column stories from dominating.
    if (profile.events.filter(event => event.category === values.category && event.type === type && now - event.at < DAY).length >= DAILY_CAPS[type]) return profile;
    profile.events = profile.events.filter(event => !(event.id === values.id && event.type === type));
    profile.events.unshift({...values, type, at: now});
    return normalizeProfile(profile, {now});
  }

  function buildModel(profile, now) {
    const model = {category: new Map(), group: new Map(), source: new Map(),
      seenCategory: new Map(), seenSource: new Map(), categoryGroups: new Map()};
    for (const event of profile.events) {
      const value = WEIGHTS[event.type] * Math.pow(0.5, (now - event.at) / (LIMITS.halfLifeDays * DAY));
      for (const key of ['category', 'group', 'source']) model[key].set(event[key], (model[key].get(event[key]) || 0) + value);
      model.seenCategory.set(event.category, (model.seenCategory.get(event.category) || 0) + Math.abs(value));
      model.seenSource.set(event.source, (model.seenSource.get(event.source) || 0) + Math.abs(value));
      if (value > 0) {
        if (!model.categoryGroups.has(event.category)) model.categoryGroups.set(event.category, new Map());
        const groups = model.categoryGroups.get(event.category);
        groups.set(event.group, (groups.get(event.group) || 0) + value);
      }
    }
    const preferred = (map, max) => {
      const entries = [...map].filter(([, value]) => value > 0.2).sort((a, b) => b[1] - a[1] || compare(a[0], b[0]));
      return new Set(entries.filter(([, value]) => value >= Math.max(0.2, (entries[0]?.[1] || 0) * 0.35)).slice(0, max).map(([key]) => key));
    };
    model.preferredCategory = preferred(model.category, 4);
    model.preferredGroup = preferred(model.group, 2);
    model.preferredSource = preferred(model.source, 3);
    model.interests = [...model.category].filter(([, value]) => value > 0.2)
      .sort((a, b) => b[1] - a[1] || compare(a[0], b[0])).slice(0, 4).map(([category, weight]) => ({
        category, group: [...(model.categoryGroups.get(category) || [])].sort((a, b) => b[1] - a[1] || compare(a[0], b[0]))[0]?.[0] || '',
        weight: Math.round(weight * 1000) / 1000,
      }));
    return model;
  }
  const squash = value => value / (4 + Math.abs(value));
  function affinity(values, model) {
    return 0.55 * squash(model.category.get(values.category) || 0)
      + 0.3 * squash(model.group.get(values.group) || 0)
      + 0.15 * squash(model.source.get(values.source) || 0);
  }
  function hash(value) {
    let result = 2166136261;
    for (let i = 0; i < value.length; i++) result = Math.imul(result ^ value.charCodeAt(i), 16777619);
    return (result >>> 0) / 4294967296;
  }
  function quotaFor(limit, strength, cold) {
    const quotas = {interest: 0, cross: 0, explore: 0, balance: 0};
    if (cold) { quotas.balance = limit; return quotas; }
    const ratios = RATIOS[strength];
    quotas.interest = Math.floor(limit * ratios[0]);
    quotas.cross = Math.floor(limit * ratios[1]);
    quotas.explore = limit - quotas.interest - quotas.cross;
    return quotas;
  }

  function rankRecommendations(articles, rawProfile, options = {}) {
    const now = currentTime(options), profile = normalizeProfile(rawProfile, {now}), model = buildModel(profile, now);
    const strength = own(RATIOS, options.strength) ? options.strength : 'balanced';
    const wide = options.diversity === 'wide';
    const requested = Number.isFinite(options.limit) ? Math.min(LIMITS.recommendations, Math.max(0, Math.floor(options.limit))) : 20;
    const hidden = new Set([...profile.hiddenIds, ...normalizeIds(options.hiddenIds, Infinity)]);
    const seen = new Set(), seed = text(String(options.seed ?? Math.floor(now / DAY)), 80);
    const candidates = (Array.isArray(articles) ? articles : []).map(article => {
      const values = dimensions(article);
      if (!values || hidden.has(values.id) || article.hidden === true || seen.has(values.id)) return null;
      seen.add(values.id);
      const at = timestamp(article.published_at || article.updated_at || article.discovered_at);
      const freshness = Number.isFinite(at) ? Math.exp(-Math.max(0, now - at) / (7 * DAY)) : 0;
      const fit = affinity(values, model);
      const interest = fit > 0.015 && (model.preferredCategory.has(values.category) || model.preferredGroup.has(values.group) || model.preferredSource.has(values.source));
      const cross = !model.preferredCategory.has(values.category) && !model.preferredGroup.has(values.group);
      const newCategory = !model.seenCategory.has(values.category), newSource = !model.seenSource.has(values.source);
      const novelty = 0.65 / (1 + (model.seenCategory.get(values.category) || 0)) + 0.35 / (1 + (model.seenSource.get(values.source) || 0));
      return {article, ...values, freshness, affinity: fit, interest, cross, newCategory, newSource, novelty,
        // Another publisher of the same preferred column is not thematic breadth.
        explore: !model.preferredCategory.has(values.category) && (!interest || newCategory || newSource),
        tie: hash(seed + '|' + values.id)};
    }).filter(Boolean);
    const cold = model.interests.length === 0, quotas = quotaFor(requested, strength, cold);
    const counts = {interest: 0, cross: 0, explore: 0, balance: 0};
    const caps = {source: Math.max(1, Math.ceil(requested * (wide ? 0.2 : 0.25))),
      category: Math.max(1, Math.ceil(requested * (wide ? 0.25 : 0.35))),
      group: Math.max(1, Math.ceil(requested * (wide ? 0.45 : 0.6)))};
    const used = new Set(), usedDimensions = {source: new Map(), category: new Map(), group: new Map()}, items = [], notes = [];
    const baseScore = (candidate, lane) => lane === 'interest' ? candidate.affinity * 40 + candidate.freshness * 12
      : lane === 'explore' ? candidate.novelty * 20 + candidate.freshness * 8 + candidate.affinity * 4 + candidate.tie * 4
      : candidate.freshness * 12 + candidate.novelty * 8 + candidate.affinity * (lane === 'balance' ? 12 : 6);
    const eligible = candidate => !used.has(candidate.id) && ['source', 'category', 'group'].every(key => (usedDimensions[key].get(candidate[key]) || 0) < caps[key]);
    function reason(candidate, lane) {
      if (lane === 'interest') {
        if ((model.category.get(candidate.category) || 0) > 0.2) return `与你近期关注的「${candidate.category}」栏目相关`;
        if ((model.group.get(candidate.group) || 0) > 0.2) return `与你近期关注的「${candidate.group}」版组相关`;
        return `来自你近期关注的来源「${candidate.source}」`;
      }
      if (lane === 'cross') return `跨领域补充：来自近期较少关注的「${candidate.group}」版组`;
      if (lane === 'explore') return candidate.newCategory ? `探索新栏目：「${candidate.category}」`
        : candidate.newSource ? `探索较少接触的来源：「${candidate.source}」` : `拓展阅读：近期较少接触的「${candidate.category}」栏目`;
      return '暂无足够兴趣记录，结合发布时间、栏目与来源均衡选择';
    }
    function select(lane, maximum, predicate) {
      let added = 0;
      while (added < maximum && items.length < requested) {
        let best = null, bestScore = -Infinity;
        for (const candidate of candidates) {
          if (!eligible(candidate) || !predicate(candidate)) continue;
          const penalty = (usedDimensions.group.get(candidate.group) || 0) * (wide ? 6 : 4)
            + (usedDimensions.category.get(candidate.category) || 0) * 3
            + (usedDimensions.source.get(candidate.source) || 0) * 2;
          const score = baseScore(candidate, lane) - penalty;
          if (score > bestScore || (score === bestScore && (!best || candidate.tie > best.tie || (candidate.tie === best.tie && compare(candidate.id, best.id) < 0)))) {
            best = candidate; bestScore = score;
          }
        }
        if (!best) break;
        used.add(best.id);
        for (const key of ['source', 'category', 'group']) usedDimensions[key].set(best[key], (usedDimensions[key].get(best[key]) || 0) + 1);
        counts[lane]++; added++;
        items.push({article: best.article, lane, reason: reason(best, lane), score: Math.round(bestScore * 1000) / 1000});
      }
    }
    if (cold) select('balance', requested, () => true);
    else {
      // Reserve breadth first so a very strong interest cannot consume its slots.
      select('cross', quotas.cross, candidate => candidate.cross);
      select('explore', quotas.explore, candidate => candidate.explore);
      select('interest', quotas.interest, candidate => candidate.interest);
      // Unfilled interest slots may become breadth; breadth slots never become interest.
      select('cross', requested - items.length, candidate => candidate.cross);
      select('explore', requested - items.length, candidate => candidate.explore);
    }
    const unmet = !cold && ['interest', 'cross', 'explore'].some(lane => counts[lane] < quotas[lane]);
    if (!candidates.length) notes.push('当前没有可推荐的未隐藏新闻。');
    else if (items.length < requested) notes.push(`候选内容或来源、栏目、版组多样性不足，本次仅推荐 ${items.length} 条真实新闻。`);
    if (unmet) notes.push('受候选分布与多样性上限影响，实际兴趣、跨领域与探索比例已调整；未用兴趣内容填满保留位置。');
    // Interleave lanes for reading; do not place all interest recommendations together.
    const queues = Object.fromEntries(LANES.map(lane => [lane, items.filter(item => item.lane === lane)]));
    const ordered = [];
    while (ordered.length < items.length) for (const lane of ['interest', 'cross', 'interest', 'explore', 'balance']) {
      if (queues[lane].length) ordered.push(queues[lane].shift());
    }
    return {items: ordered, stats: {requested, available: candidates.length, returned: ordered.length,
      quotas, counts, degraded: ordered.length < requested || unmet, notes, interests: model.interests,
      strength, diversity: wide ? 'wide' : 'standard', caps, coldStart: cold, activeSignals: profile.events.length}};
  }

  return Object.freeze({defaultProfile, resetProfile: defaultProfile, reset: defaultProfile,
    normalizeProfile, applyFeedback, rankRecommendations, LIMITS});
});
