(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.LifeGuideSearch = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const LENSES = ['死亡率', '金钱', '时间', '自由'];
  const RATIOS = { '极高': 0, '高': 1, '一般': 2 };
  const GRADES = { A: 0, B: 1, C: 2 };
  const STOP_WORDS = new Set(('怎么 怎么办 如何 什么 为什么 是否 是不是 有没有 有什么 哪些 哪里 ' +
    '多少 可以 应该 需要 值得 值不值 好不好 划算 比较 总是 每天 天天 最近 现在 请问 ' +
    '我想 我要 我的 自己 这个 那个 这种 那种 这样 那样 事情 问题 办法 处理 选择 ' +
    '小时 分钟 时候 时间 一下 一些 还有 然后 已经 可能 一个 两个 朋友 让我 不知道 ' +
    '不太 怎么样 不好 更好 帮忙 建议 推荐 有用 相关 性价比 人生 指南 不值 不签 不退 坏了').split(/\s+/));
  const BOUNDARY_PARTICLES = new Set('的 了 着 过 在 把 被 让 给 对 从 为 和 或 与 就 都 很 太 又 要 该 能 应 吗 吧 呢 啊 呀 么 我 你 他 她 它 这 那 个 点 种 配 去 来 才 也 想 最 不 没'.split(' '));

  // These are retrieval synonyms and chapter hints, never generated advice.
  const SCENARIOS = [
    { test: /担保|保证人|连带责任|替人还债|帮人还债/, skip: /创业担保贷款/,
      terms: ['担保', '保证人', '连带责任', '签字'], focus: ['担保', '保证人', '连带责任'],
      sections: /法律与财产安全|创业与做生意/ },
    { test: /通勤|上班路上|上下班路上|上下班.*(?:小时|分钟)|上班.*太远/,
      terms: ['通勤', '上下班', '职住'], focus: ['通勤', '职住'],
      sections: /不要浪费时间|租房与买房/ },
    { test: /失眠|睡不着|睡不好|睡眠|难入睡|入睡困难|老是醒|总是醒/,
      terms: ['睡眠', '失眠', '入睡', '睡觉', '作息', '起床', '睡前', '咖啡因'],
      focus: ['睡眠', '失眠', '入睡', '睡觉', '作息', '起床', '睡前', '咖啡因'],
      sections: /不要慢慢死|不要浪费精力/ },
    { test: /(?:租房|房东|退租|租金|押金).*(?:不退|扣|要回|退还)|押金/,
      skip: /求职|找工作|面试|入职|培训|招聘|出国打工|劳务/,
      terms: ['押金', '退租', '房东', '租房'], focus: ['押金', '退租'],
      sections: /租房与买房/ },
    { test: /租房|租赁|房东|租客|租约/,
      skip: /押金|退租/, terms: ['租房', '租赁', '房东', '租客'],
      sections: /租房与买房/ },
    { test: /拖欠工资|欠工资|欠薪|讨薪/,
      terms: ['欠薪', '工钱', '工资', '劳动监察', '劳动仲裁'], focus: ['欠薪', '工钱', '劳动监察'],
      sections: /没钱的时候怎么活|在职、离职和工伤/ },
    { test: /被裁|裁员|辞退|开除|离职|辞职/,
      terms: ['裁员', '辞退', '离职', '解除劳动合同', '经济补偿', '失业'],
      sections: /在职、离职和工伤|没钱的时候怎么活|遭遇重大打击/ },
    { test: /诈骗|被骗|电诈|骗子/,
      terms: ['诈骗', '被骗', '反诈', '止付', '骗子'], sections: /法律与财产安全|账号与信息安全/ },
    { test: /账号被盗|帐号被盗|盗号|密码泄露|两步验证|二步验证/,
      terms: ['账号', '被盗', '密码', '双重', '两步', '二步'], sections: /账号与信息安全/ },
    { test: /运动|锻炼|健身/,
      terms: ['运动', '锻炼', '力量训练', '活动'], focus: ['运动', '锻炼', '力量训练'],
      sections: /不要慢慢死|怎么放松/ },
    { test: /学习效率|学不会|记不住|怎么学|如何学/,
      terms: ['学习', '复习', '练习', '技能', '记忆'], sections: /学什么技能划算/ },
    { test: /压力大|压力太大|减压|放松/,
      terms: ['压力', '减压', '放松', '情绪'], sections: /怎么放松|不要浪费精力/ },
    { test: /购房|买房|房贷/,
      terms: ['买房', '购房', '房贷'], sections: /租房与买房|不要浪费钱/ },
    { test: /看病太贵|看病贵|医疗费|医药费/,
      terms: ['看病', '医保', '药费', '医疗费'], sections: /看病：|得了慢性病|没钱的时候怎么活/ },
  ];

  let segmenter;
  try {
    if (typeof Intl !== 'undefined' && Intl.Segmenter) segmenter = new Intl.Segmenter('zh', { granularity: 'word' });
  } catch (_) { /* Exact phrases and corpus n-grams also work without Intl.Segmenter. */ }

  function normalize(value) {
    return String(value == null ? '' : value).normalize('NFKC').toLowerCase().replace(/\s+/g, ' ').trim();
  }

  function unique(values) { return [...new Set(values)]; }

  function usefulTerm(value) {
    return value.length >= 2 && !STOP_WORDS.has(value) && /[\p{L}]/u.test(value) &&
      !/^[的了着吧呢吗啊呀么]|[的了着吧呢吗啊呀么]$/.test(value) && !/^\d+$/.test(value);
  }

  function words(value) {
    const text = normalize(value);
    if (segmenter) return [...segmenter.segment(text)].filter(part => part.isWordLike).map(part => part.segment);
    return text.match(/[a-z][a-z0-9+.#-]*|[\p{Script=Han}]{2,}/gu) || [];
  }

  function buildIndex(entries, sections) {
    const sectionList = Array.isArray(sections) ? sections.slice() : [];
    const sectionMap = new Map(sectionList.map(section => [Number(section.n), section]));
    const lexicon = new Set();
    const documents = (Array.isArray(entries) ? entries : []).map((entry, order) => {
      const section = sectionMap.get(Number(entry.sec)) || {};
      const title = normalize(entry.title);
      const human = normalize(entry.human);
      const body = normalize([entry.cost, entry.gain, entry.note].filter(Boolean).join(' '));
      const coreText = normalize([entry.title, entry.human, entry.cost, entry.gain].filter(Boolean).join(' '));
      const content = normalize([entry.title, entry.human, entry.cost, entry.gain, entry.note].filter(Boolean).join(' '));
      const directionalText = content || normalize(entry.raw);
      const keywordText = normalize([entry.id, entry.title, entry.human, entry.cost, entry.gain,
        entry.grade, entry.src, entry.note, entry.raw, section.title,
        `第${entry.sec}节第${entry.n}条`].filter(Boolean).join(' '));
      for (const term of words([entry.title, entry.human, section.title, section.question].filter(Boolean).join(' '))) {
        if (usefulTerm(term)) lexicon.add(term);
      }
      // A short source phrase can be found even where platform word boundaries differ.
      for (const run of title.match(/[\p{Script=Han}]+/gu) || []) {
        for (let length = 2; length <= Math.min(6, run.length); length++) {
          for (let start = 0; start + length <= run.length; start++) {
            const term = run.slice(start, start + length);
            if (usefulTerm(term)) lexicon.add(term);
          }
        }
      }
      return { entry, order, title, human, body, coreText, directionalText, keywordText };
    });
    return { entries: documents.map(doc => doc.entry), sections: sectionList, sectionMap, documents, lexicon };
  }

  function parseChineseNumber(value) {
    if (/^\d+$/.test(value)) return Number(value);
    const digits = { 零: 0, 〇: 0, 一: 1, 二: 2, 两: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9 };
    if (value === '十') return 10;
    if (value.includes('十')) {
      const parts = value.split('十');
      return (parts[0] ? digits[parts[0]] : 1) * 10 + (parts[1] ? digits[parts[1]] : 0);
    }
    return digits[value];
  }

  function parseReference(query) {
    const text = normalize(query);
    const match = text.match(/第\s*([0-9零〇一二两三四五六七八九十]+)\s*节(?:\s*[，,、的]?\s*第?\s*([0-9零〇一二两三四五六七八九十]+)\s*条)?/);
    if (!match) return null;
    const sec = parseChineseNumber(match[1]);
    const n = match[2] ? parseChineseNumber(match[2]) : null;
    return Number.isFinite(sec) && (n == null || Number.isFinite(n)) ? { sec, n } : null;
  }

  function passesFilters(entry, filters) {
    const f = filters || {};
    const fields = { sections: 'sec', grades: 'grade', money: 'money', time: 'time', will: 'will', lenses: 'lens', ratios: 'ratio' };
    for (const [key, field] of Object.entries(fields)) {
      if (Array.isArray(f[key]) && f[key].length && !f[key].some(value => normalize(value) === normalize(entry[field]))) return false;
    }
    return !(f.excludeDisputed && entry.dispute) && !(f.excludeUnverified && entry.todo);
  }

  function bookOrder(a, b) {
    return Number(a.entry.sec) - Number(b.entry.sec) || Number(a.entry.n) - Number(b.entry.n) || a.order - b.order;
  }

  function valueOrder(a, b) {
    return (RATIOS[a.entry.ratio] ?? 3) - (RATIOS[b.entry.ratio] ?? 3) ||
      (GRADES[String(a.entry.grade).toUpperCase()] ?? 3) - (GRADES[String(b.entry.grade).toUpperCase()] ?? 3) ||
      b.score - a.score || bookOrder(a, b);
  }

  function copyResult(result) {
    return { ...result.entry, score: result.score || 0, matchedTerms: (result.matchedTerms || []).slice() };
  }

  function keywordSearch(index, query, filters, options) {
    const config = options || {};
    const terms = unique(normalize(query).split(/\s+/).filter(Boolean));
    const reference = parseReference(query);
    const exactReference = reference && /^第\s*[0-9零〇一二两三四五六七八九十]+\s*节(?:\s*[，,、的]?\s*第?\s*[0-9零〇一二两三四五六七八九十]+\s*条)?$/.test(normalize(query));
    const results = [];
    for (const doc of index.documents) {
      if (!passesFilters(doc.entry, filters)) continue;
      if (exactReference && (Number(doc.entry.sec) !== reference.sec || (reference.n != null && Number(doc.entry.n) !== reference.n))) continue;
      const matchedTerms = terms.filter(term => doc.keywordText.includes(term));
      if (!exactReference && terms.length && (config.mode === 'any' ? !matchedTerms.length : matchedTerms.length !== terms.length)) continue;
      const score = matchedTerms.reduce((sum, term) => sum + (doc.title.includes(term) ? 10 : 0) +
        (doc.human.includes(term) ? 4 : 0) + 1, 0);
      results.push({ ...doc, score, matchedTerms: exactReference ? [normalize(query)] : matchedTerms });
    }
    if (config.sort === 'value') results.sort(valueOrder);
    else if (config.sort === 'relevance') results.sort((a, b) => b.score - a.score || bookOrder(a, b));
    else results.sort(bookOrder);
    return results.map(copyResult);
  }

  function extractTerms(index, query) {
    const text = normalize(query);
    const scenes = SCENARIOS.filter(scene => scene.test.test(text) && !(scene.skip && scene.skip.test(text)));
    const core = text.replace(/请问|怎么办|怎么样|怎么做|值不值|好不好|有没有|是不是|有必要|要不要|需不需要|签不签|有什么|应该|每天|总是|最近/g, ' ')
      .replace(/[零一二两三四五六七八九十百\d]+\s*(?:个)?(?:小时|分钟)/g, ' ');
    let original = words(core).filter(usefulTerm);
    if (segmenter) {
      const parts = [...segmenter.segment(core)].filter(part => part.isWordLike);
      for (let i = 0; i < parts.length; i++) {
        if (BOUNDARY_PARTICLES.has(parts[i].segment) || STOP_WORDS.has(parts[i].segment)) continue;
        for (let j = i; j < parts.length; j++) {
          const term = core.slice(parts[i].index, parts[j].index + parts[j].segment.length);
          if (term.length > 12) break;
          if (!/^[\p{Script=Han}]+$/u.test(term)) break;
          if (BOUNDARY_PARTICLES.has(parts[j].segment) || STOP_WORDS.has(parts[j].segment)) continue;
          if (usefulTerm(term) && index.lexicon.has(term)) original.push(term);
        }
      }
    } else {
      for (const run of core.match(/[\p{Script=Han}]+/gu) || []) {
        for (let length = 2; length <= Math.min(6, run.length); length++) {
          for (let start = 0; start + length <= run.length; start++) {
            const term = run.slice(start, start + length);
            if (!BOUNDARY_PARTICLES.has(term[0]) && !BOUNDARY_PARTICLES.has(term[term.length - 1]) && usefulTerm(term) && index.lexicon.has(term)) original.push(term);
          }
        }
      }
    }
    original = unique(original).filter(term => index.documents.some(doc => doc.directionalText.includes(term)));
    // Do not split an original phrase into a collection of overlapping fragments.
    original = original.filter(term => !original.some(longer => longer.length > term.length && longer.includes(term)));
    original.sort((a, b) => b.length - a.length || text.indexOf(a) - text.indexOf(b));
    original = original.slice(0, 10);
    const expanded = unique(scenes.flatMap(scene => scene.terms).map(normalize));
    const terms = unique([...original, ...expanded]).filter(term => index.documents.some(doc => doc.directionalText.includes(term)));
    const focus = unique(scenes.flatMap(scene => scene.focus || scene.terms).map(normalize));
    return { terms, original, scenes, focus };
  }

  function scoreDocument(index, doc, profile, frequencies) {
    let score = 0;
    const matchedTerms = [];
    for (const term of profile.terms) {
      if (!doc.directionalText.includes(term)) continue;
      const weight = (profile.original.includes(term) ? 1 : 0.72) *
        (1 + Math.log(1 + index.documents.length / (1 + frequencies.get(term))));
      const fieldScore = (doc.title.includes(term) ? 10 : 0) + (doc.human.includes(term) ? 5 : 0) +
        (doc.body.includes(term) ? 2 : 0) || 1;
      score += weight * fieldScore;
      matchedTerms.push(term);
    }
    return { ...doc, score, matchedTerms };
  }

  function groupResults(results) {
    const names = unique([...LENSES, ...results.map(result => result.entry.lens || '未标明口径')]);
    const pools = names.map(lens => ({ lens, rows: results.filter(result => (result.entry.lens || '未标明口径') === lens).sort(valueOrder) }))
      .filter(group => group.rows.length);
    // Reserve a result for every present lens; allocation is round-robin, not a cross-lens value comparison.
    const groups = pools.map(group => ({ lens: group.lens, entries: [] }));
    let count = 0;
    for (let round = 0; count < 7 && pools.some(pool => pool.rows.length > round); round++) {
      for (let i = 0; i < pools.length && count < 7; i++) {
        if (pools[i].rows[round]) { groups[i].entries.push(copyResult(pools[i].rows[round])); count++; }
      }
    }
    return groups.filter(group => group.entries.length);
  }

  function directionalSearch(index, query, filters) {
    const empty = (terms, message, sectionIds) => ({ terms, sectionIds: sectionIds || [], groups: [], total: 0, message });
    const text = normalize(query);
    if (!text) return empty([], '请输入具体问题，或使用“第8节第17条”定位原文。');
    const reference = parseReference(text);
    if (reference) {
      const matches = index.documents.filter(doc => Number(doc.entry.sec) === reference.sec &&
        (reference.n == null || Number(doc.entry.n) === reference.n) && passesFilters(doc.entry, filters));
      const verified = matches.filter(doc => !doc.entry.todo).map(doc => ({ ...doc, score: 1, matchedTerms: [text] }));
      if (!verified.length) return empty([text], matches.length ? '该条目标有 TODO，尚未核实，未纳入定向结果；可在关键词检索或目录中查看原文。' :
        '未找到符合该节、条编号及筛选条件的原文。', [reference.sec]);
      const groups = groupResults(verified);
      return { terms: [text], sectionIds: [reference.sec], groups, total: groups.reduce((n, group) => n + group.entries.length, 0),
        message: '已按节、条编号定位原文，备注与证据限制一并保留。' };
    }

    const profile = extractTerms(index, text);
    if (!profile.terms.length) return empty([], '书中未找到对应条目。请换成更具体的主题词，或使用关键词检索。');
    const frequencies = new Map(profile.terms.map(term => [term, index.documents.filter(doc => doc.directionalText.includes(term)).length]));
    let candidates = index.documents.filter(doc => !doc.entry.todo && passesFilters(doc.entry, filters))
      .map(doc => scoreDocument(index, doc, profile, frequencies)).filter(doc => doc.score > 0);
    if (profile.focus.length) candidates = candidates.filter(doc => profile.focus.some(term => doc.coreText.includes(term)));
    if (!candidates.length) return empty(profile.terms, '书中未找到符合当前问题和筛选条件的已核实条目。');

    const sectionScores = [];
    const hinted = new Set(index.sections.filter(section => profile.scenes.some(scene => scene.sections.test(section.title || ''))).map(section => Number(section.n)));
    for (const sec of unique(candidates.map(doc => Number(doc.entry.sec)))) {
      const rows = candidates.filter(doc => Number(doc.entry.sec) === sec).sort((a, b) => b.score - a.score);
      const section = index.sectionMap.get(sec) || {};
      const question = normalize([section.title, section.question].join(' '));
      const questionMatches = profile.original.filter(term => question.includes(term)).length;
      const score = (rows[0].score + rows.slice(1, 4).reduce((sum, row) => sum + row.score * 0.2, 0)) *
        (hinted.has(sec) ? 2.5 : hinted.size ? 0.5 : 1) + questionMatches * 8;
      sectionScores.push({ sec, score });
    }
    sectionScores.sort((a, b) => b.score - a.score || a.sec - b.sec);
    const sectionIds = sectionScores.filter(section => section.score >= sectionScores[0].score * 0.3).slice(0, 3).map(section => section.sec);
    candidates = candidates.filter(doc => sectionIds.includes(Number(doc.entry.sec)));
    const maximum = Math.max(...candidates.map(doc => doc.score));
    candidates = candidates.filter(doc => doc.score >= maximum * 0.18);
    const groups = groupResults(candidates);
    const total = groups.reduce((n, group) => n + group.entries.length, 0);
    return { terms: profile.terms, sectionIds, groups, total,
      message: `已在第 ${sectionIds.join('、')} 节找到相关原文。各收益口径分别列出，组内按性价比、证据等级、相关度排序；最多展示 7 条。` };
  }

  return { buildIndex, keywordSearch, directionalSearch, normalize, parseReference, passesFilters, extractTerms, LENSES: LENSES.slice() };
}));
