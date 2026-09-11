const state = {
  articles: [],
  insights: [],
  reports: [],
  meta: {},
  userInsights: [],
  query: '',
  region: 'all',
  contentType: 'all',
  category: 'all',
  month: '',
  activeTab: 'feed',
  activeKeyword: 'all',
  noteSupport: null,
  justSavedNoteId: ''
};

const USER_INSIGHTS_KEY = 'meow-ai-shopping-user-insights';
const SEEN_FEED_KEY = 'meow-ai-shopping-seen-feed';
const SEEN_INSPIRATION_KEY = 'meow-ai-shopping-seen-inspiration';
const DATA_VERSION = '2026-09-11-note-lab-v2';
const fetchJson = (path) => fetch(`${path}?v=${DATA_VERSION}`, { cache: 'no-store' }).then(r => r.json());
const SEARCH_CONCEPTS = {
  '记忆': ['记忆', '偏好', '画像', '复购', '长期约束', 'habit', 'personalization', 'context'],
  '信任': ['信任', '授权', '可撤回', '解释', '证据', '风险', 'trust', 'permission'],
  '闭环': ['闭环', '支付', '下单', '履约', '售后', '购物车', 'checkout', 'order'],
  '商家': ['商家', '商品库', '机器可读', 'GEO', '可见性', 'seller', 'merchant'],
  '协议': ['协议', 'UCP', 'MCP', 'agentic commerce', '接口', '跨平台', 'protocol'],
  '即时': ['即时零售', '买菜', '外卖', '日用品', '高频低风险', '复购', 'local commerce'],
  '评价': ['评价', '口碑', '测评', '评论摘要', 'social proof', 'review'],
  '视觉': ['视觉', '试穿', '图片', '风格', '非标品', 'fashion', 'style'],
  '治理': ['治理', '排序', '赞助', '公平性', '责任', 'ranking', 'governance'],
  '竞品': ['竞品', '平台案例', '淘宝', '天猫', '千问', '美团', '小美', '虾皮', 'Shopee', '得物', 'Amazon', 'Rufus'],
  '试穿': ['试穿', '试衣', '试鞋', '虚拟试穿', '视觉导购', 'try-on', 'virtual try', 'fitting'],
  '本地生活': ['本地生活', '即时零售', '美团', '小美', '淘宝闪购', '外卖', '买菜', '履约确定性']
};
const NOTE_KEYWORD_RULES = [
  ['可信赖', ['可信', '信任', '放心', '可靠', 'trust']],
  ['更懂你', ['懂你', '理解我', '个性化', '偏好', 'personal']],
  ['偏好记忆', ['记忆', '偏好', '画像', '复购', 'context']],
  ['授权边界', ['授权', '边界', '可撤回', '确认', 'permission']],
  ['结账转化', ['结账', '转化', 'checkout', '支付', '下单']],
  ['价格库存核验', ['价格', '库存', '核验', '实时', 'stock']],
  ['履约售后', ['履约', '售后', '物流', '退货', '原因']],
  ['商家资料层', ['商家', '卖家', '商品库', '机器可读', 'GEO']],
  ['视觉导购', ['试穿', '视觉', '图片', '风格', '非标', 'fashion']],
  ['即时零售', ['买菜', '外卖', '即时', '本地生活', '高频']],
  ['跨平台交易', ['跨平台', '协议', 'UCP', 'agentic commerce', '购物车']],
  ['竞品验证', ['沃尔玛', 'Walmart', 'Instacart', 'Amazon', 'Rufus', '淘宝', '天猫', '美团', 'Target']]
];
const NOTE_STOPWORDS = new Set(['这个', '那个', '因为', '所以', '但是', '然后', '应该', '需要', '重要', '很重要', '说明', '表明', '测试', '月份', '导购的', '更懂你很', '你的', '我的', '进行', '一个', '一种']);
const WEAK_NOTE_COPY = /案例主体|侧面证据|交叉验证|链路颗粒度|这条资料|这类想法的关键验证点|站内支撑|上线AI助手|补足.*视角|AI会不会推荐|标题|核心观点|基于“/;
const fmtDate = (iso) => new Date(`${iso}T00:00:00+08:00`).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' });
const fmtMonth = (month) => month.replace('-', '年') + '月';
const unique = (arr) => [...new Set(arr)].filter(Boolean);
const escapeHtml = (text = '') => text.replace(/[&<>"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));

async function loadData() {
  const [articles, insights, reports, meta] = await Promise.all([
    fetchJson('./data/articles.json'),
    fetchJson('./data/insights.json'),
    fetchJson('./data/monthly_reports.json'),
    fetchJson('./data/meta.json')
  ]);
  state.articles = articles.sort((a, b) => b.date.localeCompare(a.date) || b.valueScore - a.valueScore);
  state.insights = insights;
  state.reports = reports.sort((a, b) => b.month.localeCompare(a.month));
  state.meta = meta;
  state.month = unique(state.articles.map(article => article.date.slice(0, 7))).sort().reverse()[0] || '';
  state.userInsights = loadUserInsights();
  renderFilters();
  bindTabs();
  bindCollapsibleHeader();
  bindNotePanel();
  bindNotes();
  render();
}

function bindCollapsibleHeader() {
  const header = document.querySelector('.compact-hero');
  if (!header) return;
  let lastScrollY = window.scrollY;
  let collapsed = false;
  let downDistance = 0;
  let upDistance = 0;
  let lockedUntil = 0;
  let ticking = false;
  const setCollapsed = (nextCollapsed) => {
    if (collapsed === nextCollapsed) return;
    collapsed = nextCollapsed;
    header.classList.toggle('header-collapsed', collapsed);
    downDistance = 0;
    upDistance = 0;
    lockedUntil = performance.now() + 320;
  };
  const updateHeader = () => {
    const currentScrollY = Math.max(0, window.scrollY);
    const delta = currentScrollY - lastScrollY;
    if (currentScrollY < 72) {
      setCollapsed(false);
    } else if (performance.now() > lockedUntil && Math.abs(delta) > 2) {
      if (delta > 0) {
        downDistance += delta;
        upDistance = 0;
      } else {
        upDistance += Math.abs(delta);
        downDistance = 0;
      }
      if (!collapsed && currentScrollY > 180 && downDistance > 56) setCollapsed(true);
      if (collapsed && upDistance > 110) setCollapsed(false);
    }
    lastScrollY = currentScrollY;
    ticking = false;
  };
  window.addEventListener('scroll', () => {
    if (!ticking) {
      window.requestAnimationFrame(updateHeader);
      ticking = true;
    }
  }, { passive: true });
  document.getElementById('searchInput')?.addEventListener('focus', () => setCollapsed(false));
}

function bindTabs() {
  document.querySelectorAll('.top-tab').forEach(button => {
    button.addEventListener('click', () => {
      setActiveTab(button.dataset.tab);
    });
  });
}

function setActiveTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll('.top-tab').forEach(button => button.classList.toggle('active', button.dataset.tab === tab));
  document.getElementById('feedTab').classList.toggle('active', tab === 'feed');
  document.getElementById('inspirationTab').classList.toggle('active', tab === 'inspiration');
  markTabSeen(tab);
}

function setNotePanelOpen(open) {
  document.body.classList.toggle('note-panel-open', open);
  document.getElementById('notePanel')?.classList.toggle('open', open);
  document.getElementById('notePanel')?.setAttribute('aria-hidden', String(!open));
  document.getElementById('noteOverlay')?.classList.toggle('open', open);
  document.getElementById('noteOverlay')?.setAttribute('aria-hidden', String(!open));
  if (open) setTimeout(() => document.getElementById('noteInput')?.focus(), 80);
}

function bindNotePanel() {
  document.getElementById('floatingNoteBtn')?.addEventListener('click', () => setNotePanelOpen(true));
  document.getElementById('noteCloseBtn')?.addEventListener('click', () => setNotePanelOpen(false));
  document.getElementById('noteOverlay')?.addEventListener('click', () => setNotePanelOpen(false));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') setNotePanelOpen(false);
  });
}

function renderFilters() {
  const regionFilter = document.getElementById('regionFilter');
  const typeFilter = document.getElementById('typeFilter');
  const categoryFilter = document.getElementById('categoryFilter');
  unique(state.articles.map(a => a.region)).forEach(region => regionFilter.append(new Option(region, region)));
  unique(state.articles.map(a => a.contentType || a.category)).forEach(type => typeFilter.append(new Option(type, type)));
  unique(state.articles.map(a => a.category)).forEach(category => categoryFilter.append(new Option(category, category)));
  document.getElementById('searchInput').addEventListener('input', e => {
    state.query = e.target.value.trim().toLowerCase();
    renderFeed();
    renderUserInsights();
    renderInsights();
    renderGlobalStats();
  });
  regionFilter.addEventListener('change', e => { state.region = e.target.value; renderFeed(); renderGlobalStats(); });
  typeFilter.addEventListener('change', e => { state.contentType = e.target.value; renderFeed(); renderGlobalStats(); });
  categoryFilter.addEventListener('change', e => { state.category = e.target.value; renderFeed(); renderGlobalStats(); });
  window.addEventListener('resize', renderGlobalStats, { passive: true });
}

function renderGlobalStats() {
  const feedCount = filteredArticles().length;
  const currentMonthCount = monthArticleCount(state.month);
  const insightCount = activeInsights().length;
  const totalInsights = state.insights.length + state.userInsights.length;
  const compact = window.matchMedia('(max-width: 560px)').matches;
  const label = state.query
    ? (compact ? `${feedCount}讯 · ${insightCount}感` : `资讯 ${feedCount} · 灵感 ${insightCount}`)
    : (compact ? `${currentMonthCount}讯 · ${totalInsights}感` : `${state.month.slice(5)}月 ${currentMonthCount}条 · 灵感 ${totalInsights}`);
  const stats = document.getElementById('globalStats');
  stats.textContent = label;
  stats.title = state.query
    ? `筛选后资讯 ${feedCount} 条，灵感 ${insightCount} 条`
    : `${state.month.slice(5)}月资讯 ${currentMonthCount} 条，灵感 ${totalInsights} 条`;
}

function hasFeedUpdate() {
  return Number(state.meta.latestAdded || 0) > 0 && localStorage.getItem(SEEN_FEED_KEY) !== state.meta.lastUpdated;
}

function hasInspirationUpdate() {
  const insightTime = state.meta.lastInsightUpdated || state.meta.lastUpdated;
  return Number(state.meta.latestInsightChanged || state.meta.latestAdded || 0) > 0 && localStorage.getItem(SEEN_INSPIRATION_KEY) !== insightTime;
}

function renderUpdateBadges() {
  document.querySelector('[data-dot="feed"]')?.classList.toggle('show', hasFeedUpdate());
  document.querySelector('[data-dot="inspiration"]')?.classList.toggle('show', hasInspirationUpdate());
}

function markTabSeen(tab) {
  if (tab === 'feed' && state.meta.lastUpdated) localStorage.setItem(SEEN_FEED_KEY, state.meta.lastUpdated);
  if (tab === 'inspiration') localStorage.setItem(SEEN_INSPIRATION_KEY, state.meta.lastInsightUpdated || state.meta.lastUpdated || '');
  renderUpdateBadges();
}

function renderMonthTabs() {
  const months = unique(state.articles.map(article => article.date.slice(0, 7))).sort().reverse();
  document.getElementById('monthTabs').innerHTML = months.map(month => `
    <button class="month-tab ${state.month === month ? 'active' : ''}" data-month="${month}">${fmtMonth(month)}<span>${monthArticleCount(month)}条</span></button>
  `).join('');
  document.querySelectorAll('.month-tab').forEach(button => button.addEventListener('click', () => {
    state.month = button.dataset.month;
    renderFeed();
    renderGlobalStats();
  }));
}

function monthArticleCount(month) {
  return state.articles.filter(article => article.date.startsWith(month)).length;
}

function activeInsights() {
  return state.insights.filter(insightMatchesKeyword).concat(state.userInsights.filter(noteMatchesKeyword));
}

function articleSearchText(article) {
  const related = state.insights.filter(insight => (article.relatedInsightIds || []).includes(insight.id));
  return [
    article.title,
    article.source,
    article.region,
    article.contentType,
    article.category,
    corePointText(article.corePoint),
    article.insight,
    ...(article.tags || []),
    ...related.flatMap(insight => [insight.title, insight.summary, ...(insight.keywords || [])])
  ].join(' ').toLowerCase();
}

function corePointText(corePoint) {
  if (Array.isArray(corePoint)) return corePoint.join(' ');
  return String(corePoint || '');
}

function renderCorePoints(corePoint) {
  const points = Array.isArray(corePoint)
    ? corePoint
    : String(corePoint || '').split(/\n+|(?:^|\s)\d+[.、]\s*/).map(item => item.trim()).filter(Boolean);
  const cleanPoints = points.map(point => String(point || '').trim()).filter(Boolean);
  if (cleanPoints.length <= 1) return `<p>${escapeHtml(cleanPoints[0] || '')}</p>`;
  return `<ol class="core-points">${cleanPoints.map(point => `<li>${escapeHtml(point)}</li>`).join('')}</ol>`;
}

function renderProductInsight(insight) {
  const parts = String(insight || '').split(/\s*｜\s*|\n+/).map(item => item.trim()).filter(Boolean);
  if (parts.length <= 1) return `<p>${escapeHtml(parts[0] || '')}</p>`;
  return `<ul class="product-insight-list">${parts.map(part => {
    const match = part.match(/^([^：:]{2,8})[：:]\s*(.+)$/);
    if (!match) return `<li>${escapeHtml(part)}</li>`;
    return `<li><strong>${escapeHtml(match[1])}</strong><span>${escapeHtml(match[2])}</span></li>`;
  }).join('')}</ul>`;
}

function expandSearchTerms(query) {
  const base = tokenize(query).concat(query).map(term => String(term || '').trim()).filter(Boolean);
  const expanded = [...base];
  const lower = query.toLowerCase();
  Object.entries(SEARCH_CONCEPTS).forEach(([concept, terms]) => {
    const conceptHit = lower.includes(concept.toLowerCase()) || terms.some(term => lower.includes(term.toLowerCase()));
    if (conceptHit) expanded.push(concept, ...terms);
  });
  return unique(expanded.map(term => term.toLowerCase()).filter(term => term.length > 1));
}

function semanticScore(text, query) {
  if (!query) return 1;
  const lower = text.toLowerCase();
  const terms = expandSearchTerms(query);
  let score = lower.includes(query.toLowerCase()) ? 12 : 0;
  terms.forEach(term => { if (lower.includes(term)) score += term.length > 3 ? 4 : 3; });
  return score;
}

function filteredArticles() {
  const results = state.articles.map(article => ({ article, score: semanticScore(articleSearchText(article), state.query) }))
    .filter(({ article, score }) => {
      const matchesSearch = !state.query || score > 0;
      const matchesMonth = state.query || !state.month || article.date.startsWith(state.month);
      return matchesSearch
        && matchesMonth
        && (state.region === 'all' || article.region === state.region)
        && (state.contentType === 'all' || (article.contentType || article.category) === state.contentType)
        && (state.category === 'all' || article.category === state.category);
    });
  if (state.query) results.sort((a, b) => b.score - a.score || b.article.valueScore - a.article.valueScore || b.article.date.localeCompare(a.article.date));
  return results.map(item => item.article);
}

function renderActiveMonthlyReport() {
  const report = state.reports.find(item => item.month === state.month);
  const articlesById = Object.fromEntries(state.articles.map(article => [article.id, article]));
  const monthCount = monthArticleCount(state.month);
  if (!report) {
    document.getElementById('activeMonthlyReport').innerHTML = '';
    return;
  }
  const topArticles = (report.topArticleIds || []).map(id => articlesById[id]).filter(Boolean).slice(0, 5);
  document.getElementById('activeMonthlyReport').innerHTML = `
    <article class="monthly-card featured-monthly">
      <div class="monthly-head"><span>${fmtMonth(report.month)} 月报 · 共${monthCount}条精选</span><strong>${report.title}</strong></div>
      <p>${report.summary}</p>
      <h4>当月最值得关注 Top${topArticles.length}</h4>
      <div class="monthly-links">${topArticles.map((article, index) => `<a href="${article.url}" target="_blank" rel="noreferrer">${index + 1}. ${article.title}</a>`).join('')}</div>
      <h4>产品启发</h4>
      <p>${report.productImplication}</p>
    </article>`;
}

function renderArticles(articles) {
  const groups = articles.reduce((acc, article) => {
    (acc[article.date] ||= []).push(article);
    return acc;
  }, {});
  const html = Object.entries(groups).map(([date, items]) => `
    <section class="day-group">
      <h3 class="day-title">${fmtDate(date)}</h3>
      <div class="article-list">${items.map(renderArticle).join('')}</div>
    </section>
  `).join('');
  document.getElementById('articleGroups').innerHTML = html || '<p class="empty">这个月暂时没有匹配的信息。</p>';
}

function renderArticle(article) {
  const openLabel = article.url.includes('weixin.sogou.com/weixin') ? '检索原文' : '打开原文';
  return `
    <article class="article-card">
      <div class="article-head">
        <a class="article-title" href="${article.url}" target="_blank" rel="noreferrer">${article.title}</a>
        <span class="score">价值 ${article.valueScore}</span>
      </div>
      <div class="meta">
        <span class="pill">${article.source}</span><span class="pill">${article.region}</span><span class="pill type-pill">${article.contentType || article.category}</span><span class="pill">${article.category}</span>
        ${(article.tags || []).map(tag => `<span class="pill">#${tag}</span>`).join('')}
      </div>
      <h4>核心观点</h4>${renderCorePoints(article.corePoint)}
      <h4>产品洞察</h4>${renderProductInsight(article.insight)}
      <a class="open-link" href="${article.url}" target="_blank" rel="noreferrer">${openLabel} →</a>
    </article>`;
}

function renderWordCloud() {
  const opinionKeywords = state.insights.flatMap((insight, index) => (insight.keywords || []).map(keyword => ({ keyword, weight: 11 - Math.min(index, 8) })));
  const counts = {};
  opinionKeywords.forEach(({ keyword, weight }) => { counts[keyword] = Math.max(counts[keyword] || 0, weight); });
  const words = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 32);
  const reset = `<button class="word word-button ${state.activeKeyword === 'all' ? 'active' : ''}" data-keyword="all" style="font-size:15px">全部观点</button>`;
  document.getElementById('wordCloud').innerHTML = reset + words.map(([word, weight], index) => {
    const size = 13 + weight * 1.5 + (index % 3);
    return `<button class="word word-button ${state.activeKeyword === word ? 'active' : ''}" data-keyword="${escapeHtml(word)}" style="font-size:${size}px">${word}</button>`;
  }).join('');
  document.querySelectorAll('.word-button').forEach(button => {
    button.addEventListener('click', () => {
      state.activeKeyword = button.dataset.keyword || 'all';
      renderWordCloud();
      renderUserInsights();
      renderInsights();
      renderGlobalStats();
    });
  });
}

function insightMatchesKeyword(insight) {
  const haystack = [insight.title, insight.summary, insight.trendNote, ...(insight.takeaways || []), ...(insight.keywords || [])].join(' ').toLowerCase();
  if (state.query && semanticScore(haystack, state.query) <= 0) return false;
  if (state.activeKeyword === 'all') return true;
  const keyword = state.activeKeyword.toLowerCase();
  return haystack.includes(keyword);
}

function noteMatchesKeyword(note) {
  const haystack = [note.title, note.summary, note.body, note.generatedInsight, ...(note.keywords || [])].join(' ').toLowerCase();
  if (state.query && semanticScore(haystack, state.query) <= 0) return false;
  if (state.activeKeyword === 'all') return true;
  const keyword = state.activeKeyword.toLowerCase();
  return haystack.includes(keyword);
}

function renderInsights() {
  const visibleInsights = state.insights.filter(insightMatchesKeyword);
  const html = visibleInsights.map(insight => {
    const articleMap = Object.fromEntries(state.articles.map(article => [article.id, article]));
    const explicit = (insight.relatedArticleIds || []).map(id => articleMap[id]).filter(Boolean);
    const inferred = state.articles.filter(article => (article.relatedInsightIds || []).includes(insight.id));
    const related = uniqueLinks([...explicit, ...inferred])
      .sort((a, b) => b.valueScore - a.valueScore || b.date.localeCompare(a.date));
    const visibleRelated = related.slice(0, 8);
    const isSpark = String(insight.id || '').startsWith('spark-');
    const badge = isSpark ? '资讯触发的产品灵感' : '产品原则灵感';
    return `
      <article class="insight-card ${isSpark ? 'spark-insight-card' : ''}">
        <span class="system-badge">${badge} · ${related.length}条来源${insight.updatedAt ? ` · ${insight.updatedAt.slice(5, 10)}` : ''}</span>
        <h3>${insight.title}</h3>
        <p>${insight.summary}</p>
        ${insight.trendNote ? `<p class="trend-note">${insight.trendNote}</p>` : ''}
        <ul>${(insight.takeaways || []).map(item => `<li>${item}</li>`).join('')}</ul>
        <div class="meta">${(insight.keywords || []).map(word => `<span class="pill">${word}</span>`).join('')}</div>
        <div class="related">${visibleRelated.map(article => `<a href="${article.url}" target="_blank" rel="noreferrer">关联：${article.title}</a>`).join('')}</div>
      </article>`;
  }).join('');
  document.getElementById('insightGrid').innerHTML = html || `<p class="empty">没有匹配“${escapeHtml(state.activeKeyword)}”的系统灵感。</p>`;
}

function loadUserInsights() {
  try {
    return JSON.parse(localStorage.getItem(USER_INSIGHTS_KEY) || '[]').map(note => enrichSavedNote(note));
  }
  catch { return []; }
}

function saveUserInsights() {
  localStorage.setItem(USER_INSIGHTS_KEY, JSON.stringify(state.userInsights));
}

function tokenize(text) {
  const known = unique(state.insights.flatMap(i => i.keywords || []).concat(state.articles.flatMap(a => a.tags || [])));
  const lower = text.toLowerCase();
  const ruleHits = NOTE_KEYWORD_RULES.filter(([, terms]) => terms.some(term => lower.includes(term.toLowerCase()))).map(([label]) => label);
  const hits = known.filter(word => lower.includes(word.toLowerCase()));
  const cn = (text.match(/[\u4e00-\u9fa5]{2,}/g) || []).flatMap(chunk => {
    const parts = [];
    for (let i = 0; i < chunk.length - 1; i += 3) parts.push(chunk.slice(i, i + 4));
    return parts;
  });
  const en = text.match(/[a-zA-Z][a-zA-Z\-]{2,}/g) || [];
  return unique([...ruleHits, ...hits, ...cn, ...en]
    .map(token => String(token || '').trim())
    .filter(token => token.length > 1 && !NOTE_STOPWORDS.has(token) && !/^\d+$/.test(token)))
    .slice(0, 12);
}

function noteKeywords(note, external = [], local = []) {
  const lower = note.toLowerCase();
  const ruleHits = NOTE_KEYWORD_RULES
    .filter(([, terms]) => terms.some(term => lower.includes(term.toLowerCase())))
    .map(([label]) => label);
  const entities = ['Walmart', '沃尔玛', 'Instacart', 'Amazon', 'Rufus', 'Google', 'Gemini', '淘宝', '天猫', '千问', '美团', '小美', '京东']
    .filter(name => lower.includes(name.toLowerCase()));
  const supportTags = local.flatMap(article => article.tags || []).filter(tag => !['AI购物', '竞品案例'].includes(tag));
  const externalSignals = external.map(item => item.source || getHost(item.url)).filter(Boolean).slice(0, 2);
  return unique([...entities, ...ruleHits, ...supportTags, ...externalSignals]).slice(0, 8);
}

function noteAngle(note) {
  const lower = note.toLowerCase();
  if (/沃尔玛|walmart|结账|checkout|转化|conversion/.test(lower)) {
    return {
      title: 'AI内结账不等于自动提升转化',
      summary: '这条笔记的核心判断是：把结账留在AI界面里只是减少跳转摩擦，真正决定转化的是授权、核价、库存、支付确认、履约追踪和售后责任是否一起闭环。',
      need: '用户需求：用户想少跳转、少重复确认，但不会因为界面更顺就放弃对价格、库存、配送和售后的确定性要求。',
      opportunity: '产品机会：把“AI内结账”拆成可验证链路，而不是一个按钮；每一步都要显示AI核验了什么、还缺什么、是否需要用户确认。',
      method: '验证方法：分别看AI界面内完成率、跳转后完成率、价格库存变更导致的退出率、售后咨询率，避免只用点击率判断成败。'
    };
  }
  if (/可信|信任|可靠|放心|更懂你|懂你|偏好|记忆|personal|trust/.test(lower)) {
    return {
      title: '可信赖和更懂你要被设计成可见机制',
      summary: '这条笔记的核心判断是：AI导购不能只声称“懂你”，而要让用户看见它用了哪些偏好、依据哪些证据、在哪些动作上需要授权。',
      need: '用户需求：用户要的是“被理解但不被冒犯”——预算、尺码、品牌禁忌、风险偏好可以被记住，但必须能查看、修改和撤回。',
      opportunity: '产品机会：做一个“我的购买规则”层，把偏好记忆、推荐证据、授权边界放在同一个可编辑面板里。',
      method: '设计方法：每次推荐都解释调用了哪条记忆、排除了哪些候选、为什么值得信任，让“懂你”从黑箱画像变成用户可控资产。'
    };
  }
  if (/商家|卖家|商品库|机器可读|库存|价格|merchant|seller|catalog|geo/.test(lower)) {
    return {
      title: 'AI导购的上限取决于商家资料层',
      summary: '这条笔记指向供给侧机会：如果商品卖点、适用场景、禁忌、库存、价格和履约承诺不可读，AI再会聊天也只能给模糊建议。',
      need: '用户需求：用户想要确定答案，而不是漂亮话；确定性来自商品事实、评价证据和履约承诺。',
      opportunity: '产品机会：商家后台从“填写商品信息”升级为“训练AI如何理解和推荐我的商品”。',
      method: '方法论：把商家资料完整度、AI引用率、推荐后转化和售后问题做成闭环指标。'
    };
  }
  if (/试穿|视觉|图片|风格|穿搭|非标|fashion|style|visual/.test(lower)) {
    return {
      title: '视觉导购要回答“适不适合我”',
      summary: '这条笔记的价值在于把视觉能力从生成效果图拉回购买决策：尺码、风格、场景适配和后悔风险才是用户真正关心的证据。',
      need: '用户需求：非标品决策里，用户不是缺商品，而是缺“我买了会不会后悔”的预判。',
      opportunity: '产品机会：把试穿、相似款、风格翻译和退货风险做进推荐排序与对比卡片。',
      method: '设计方法：展示适配点和不适配点，让AI不仅推荐商品，也解释为什么不推荐某些商品。'
    };
  }
  if (/复购|买菜|外卖|即时|本地生活|高频|低风险|日用品/.test(lower)) {
    return {
      title: 'AI购物应先从高频低风险建立信任',
      summary: '这条笔记指向一个落地顺序：先让AI在补货、买菜、外卖、凑单这类低风险场景里形成习惯，再迁移到复杂高客单决策。',
      need: '用户需求：日常消费里用户更在意省心、准时、少出错，而不是长篇解释。',
      opportunity: '产品机会：把复购周期、常买偏好、配送时效和优惠门槛做成自动提醒/半自动任务。',
      method: '验证方法：看复购提醒采纳率、替代品接受率、履约失败率和用户主动授权次数。'
    };
  }
  if (/评价|评论|口碑|测评|review|种草|小红书|达人|社媒|social/.test(lower)) {
    return {
      title: 'AI导购要把口碑翻译成决策证据',
      summary: '这条笔记关注的是“别人怎么说”如何真正帮助购买：AI不应只摘要评论，而要把口碑拆成适用人群、使用场景、风险点和反例。',
      need: '用户需求：用户缺的不是更多评价，而是知道“哪些评价和我有关、哪些评价只是噪音”。',
      opportunity: '产品机会：把评论、测评、达人内容沉淀成可追问的证据卡，支持按肤质、尺码、预算、场景等个人约束重排。',
      method: '设计方法：每个推荐都给出支持证据和反对证据，尤其暴露退货原因、差评聚类和不适合人群。'
    };
  }
  if (/价格|优惠|比价|预算|省钱|补贴|券|price|deal/.test(lower)) {
    return {
      title: '价格型AI导购必须先建立“算得清”信任',
      summary: '这条笔记指向价格决策的核心：用户愿意让AI帮忙省钱，但前提是优惠、凑单、券后价、配送费和售后成本都能被透明核算。',
      need: '用户需求：用户想知道自己到底省了多少钱，而不是被复杂优惠规则带着走。',
      opportunity: '产品机会：把比价、凑单、用券、保价和替代方案做成一张可审计账单，让AI解释每一步省钱依据。',
      method: '验证方法：看用户是否愿意采纳AI凑单方案，以及是否因为价格解释减少退出、投诉和重复核对。'
    };
  }
  if (/逛|发现|灵感|种草|不知道买什么|discovery|browse/.test(lower)) {
    return {
      title: 'AI导购不只回答问题，也要制造可继续逛的理由',
      summary: '这条笔记强调“逛”的价值：很多购物意图一开始并不清晰，AI要把模糊兴趣变成可探索路径，而不是急着收敛到一个商品。',
      need: '用户需求：用户在逛的时候要的是被启发、被理解和低压力试探，而不是立刻被逼下单。',
      opportunity: '产品机会：把对话结果变成可保存的主题货架、风格路线和后续提醒，让探索过程也沉淀为资产。',
      method: '设计方法：用“继续看相似灵感/换个预算/换个场景/排除不喜欢”替代单一商品列表。'
    };
  }
  return {
    title: summarizeNoteTitle(note),
    summary: `这条笔记要保留的不是原句，而是一个可验证的产品假设：${compactNote(note, 78)}。下一步应判断它影响的是发现、比较、信任、授权、交易还是购后。`,
    need: '用户需求：先定位用户在哪个购物环节有不确定性，是表达不清、比较太累、证据不足、风险太高，还是履约不可控。',
    opportunity: '产品机会：把这条想法压成一个可落地机制，明确入口、需要哪些数据、给用户什么输出、失败时如何兜底。',
    method: '验证方法：不要只看点击，至少观察决策耗时、推荐采纳、二次核对、退出原因和售后问题是否发生变化。'
  };
}

function compactNote(note, max = 64) {
  const clean = String(note || '').replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

function summarizeNoteTitle(note) {
  const clean = compactNote(note, 42).replace(/[。！？.!?，,：:；;]$/, '');
  if (/AI导购|购物智能体|导购/.test(clean)) return clean;
  return `围绕“${clean}”的产品灵感`;
}

function isWeakNoteTitle(title = '', body = '') {
  const cleanTitle = String(title || '').trim();
  if (!cleanTitle) return true;
  if (body && (body.startsWith(cleanTitle) || cleanTitle === body.slice(0, 32))) return true;
  return /很重要|测试表明|^AI导购的|月份的测试|并不会自动|围绕“/.test(cleanTitle) || WEAK_NOTE_COPY.test(cleanTitle);
}

function isWeakNoteSummary(summary = '', body = '') {
  const cleanSummary = String(summary || '').trim();
  if (!cleanSummary) return true;
  if (body && (cleanSummary === body || body.startsWith(cleanSummary) || cleanSummary.startsWith(body.slice(0, 24)))) return true;
  return WEAK_NOTE_COPY.test(cleanSummary) || /核心判断是：?$/.test(cleanSummary);
}

function isWeakNoteInsight(insight = '') {
  const cleanInsight = String(insight || '').trim();
  if (!cleanInsight) return true;
  if (WEAK_NOTE_COPY.test(cleanInsight)) return true;
  return !/(用户需求|产品机会|设计方法|验证方法|方法论)/.test(cleanInsight);
}

function enrichSavedNote(note) {
  const body = note.body || note.note || note.title || '';
  const angle = noteAngle(body);
  return {
    ...note,
    title: isWeakNoteTitle(note.title, body) ? angle.title : note.title,
    summary: isWeakNoteSummary(note.summary, body) ? angle.summary : note.summary,
    keywords: noteKeywords(body, note.external || [], []),
    generatedInsight: isWeakNoteInsight(note.generatedInsight) ? [angle.need, angle.opportunity, angle.method].join('\n') : note.generatedInsight,
    body
  };
}

function scoreLocalArticles(tokens) {
  return state.articles.map(article => {
    const haystack = [article.title, corePointText(article.corePoint), article.insight, ...(article.tags || [])].join(' ').toLowerCase();
    const score = tokens.reduce((sum, token) => sum + (haystack.includes(token.toLowerCase()) ? 1 : 0), 0);
    return { article, score };
  }).filter(item => item.score > 0).sort((a, b) => b.score - a.score || b.article.valueScore - a.article.valueScore).slice(0, 5).map(item => item.article);
}

function uniqueLinks(items) {
  const seen = new Set();
  return items.filter(item => {
    const key = (item.url || '').split('#')[0].split('?')[0];
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function curatedWebFallback(note, local) {
  const lower = note.toLowerCase();
  const query = encodeURIComponent(note.slice(0, 80));
  const contextual = [];
  if (/沃尔玛|walmart|结账|checkout|转化|conversion/.test(lower)) {
    contextual.push(
      { title: 'Walmart：AI discovery and effortless shopping experiences', url: 'https://corporate.walmart.com/news/2026/01/11/walmart-and-google-turn-ai-discovery-into-effortless-shopping-experiences', source: 'Walmart', snippet: '用于观察外部AI入口进入零售交易时，价格、库存、账户和履约如何影响转化。' },
      { title: 'Google：Universal Cart and agentic shopping', url: 'https://blog.google/products-and-platforms/products/shopping/google-shopping-cart/', source: 'Google', snippet: '跨平台购物车与 agentic shopping，可用来拆解AI内交易的授权和结算边界。' }
    );
  }
  if (/可信|信任|可靠|放心|更懂你|懂你|偏好|记忆|personal|trust/.test(lower)) {
    contextual.push(
      { title: 'Amazon：Rufus AI shopping assistant', url: 'https://www.aboutamazon.com/news/retail/amazon-rufus', source: 'Amazon', snippet: '平台内助手结合商品库、评论和购买链路，适合观察信任证据如何嵌进导购。' },
      { title: 'OpenAI：Powering product discovery in ChatGPT', url: 'https://openai.com/index/powering-product-discovery-in-chatgpt/', source: 'OpenAI', snippet: 'ChatGPT 商品发现强调推荐依据和购物入口，可用于思考AI如何解释“为什么推荐”。' }
    );
  }
  if (/试穿|视觉|图片|风格|穿搭|非标|fashion|style|visual/.test(lower)) {
    contextual.push(
      { title: 'Google Shopping：Virtual try-on for apparel', url: 'https://blog.google/products/shopping/virtual-try-on-google-shopping/', source: 'Google', snippet: '虚拟试穿把视觉能力用于尺码、风格和上身效果判断，而不是只生成好看的图。' },
      { title: 'Google：AI shopping features for apparel discovery', url: 'https://blog.google/products/shopping/ai-shopping-features/', source: 'Google', snippet: '适合参考视觉搜索、风格理解和个性化推荐如何串联。' }
    );
  }
  if (/商家|卖家|商品库|机器可读|库存|价格|merchant|seller|catalog|geo/.test(lower)) {
    contextual.push(
      { title: 'Google：New tools for retailers in an agentic shopping era', url: 'https://blog.google/products/ads-commerce/agentic-commerce-ai-tools-protocol-retailers-platforms/', source: 'Google', snippet: '面向零售商的 agentic commerce 工具，适合拆商家资料层和协议接入。' },
      { title: 'Shopify：AI in Ecommerce', url: 'https://www.shopify.com/blog/ai-ecommerce', source: 'Shopify', snippet: '商家侧AI在商品信息、个性化、客服和运营中的落点。' }
    );
  }
  const seed = [
    { title: 'Instacart：AI-powered shopping and fulfillment', url: 'https://www.instacart.com/company/', source: 'Instacart', snippet: '即时零售平台围绕购物助手、库存、配送和履约体验的官方入口。' },
    { title: 'Google：UCP updates improve AI shopping for retailers', url: 'https://blog.google/products-and-platforms/products/shopping/ucp-updates/', source: 'Google', snippet: '面向商家的 AI shopping 接入协议与能力更新。' },
    { title: 'Amazon：Rufus AI shopping assistant', url: 'https://www.aboutamazon.com/news/retail/amazon-rufus', source: 'Amazon', snippet: '平台内原生购物助手，结合商品库、评论和购买链路。' },
    { title: 'OpenAI：Powering product discovery in ChatGPT', url: 'https://openai.com/index/powering-product-discovery-in-chatgpt/', source: 'OpenAI', snippet: 'ChatGPT 内商品发现与购物意图承接，适合参考AI入口如何影响选品。' },
    { title: 'Shopify：AI in Ecommerce', url: 'https://www.shopify.com/blog/ai-ecommerce', source: 'Shopify', snippet: '商家侧 AI 在个性化、库存、客服和运营中的落点。' },
    { title: '微信文章搜索：相关中文案例', url: `https://weixin.sogou.com/weixin?type=2&query=${query}`, source: 'Sogou Weixin', snippet: '继续查找国内公众号案例和行业分析。' },
    { title: 'Google 搜索：海外 AI shopping agent 案例', url: `https://www.google.com/search?q=${query}+AI+shopping+agent+commerce+case`, source: 'Google Search', snippet: '继续查找海外产品案例和报告。' }
  ];
  const scored = [...contextual, ...seed].map(item => ({ ...item, score: scoreWebResult(item, note) }));
  const localAsWeb = local.slice(0, 2).map(article => ({ title: article.title, url: article.url, source: article.source, snippet: corePointText(article.corePoint) }));
  return uniqueLinks([...localAsWeb, ...scored.sort((a, b) => b.score - a.score)]).slice(0, 6);
}

function buildSupportInsight(note, external, local) {
  const angle = noteAngle(note);
  const sources = unique([
    ...external.map(item => item.source || getHost(item.url)).filter(Boolean),
    ...local.map(item => item.source).filter(Boolean)
  ]).slice(0, 4);
  const sourceLine = sources.length
    ? `支撑信号：优先用 ${sources.join('、')} 的案例核对入口、授权、证据、交易和兜底是否真的成立。`
    : '支撑信号：当前资料不足时，优先补竞品实测、官方发布和用户反馈，不急着沉淀成产品结论。';
  return [angle.need, angle.opportunity, angle.method, sourceLine].join('\n');
}

function decodeBingRedirect(url) {
  try {
    const parsed = new URL(url);
    const encoded = parsed.searchParams.get('u');
    if (!encoded) return url;
    let payload = encoded.replace(/^a1/, '').replace(/-/g, '+').replace(/_/g, '/');
    while (payload.length % 4) payload += '=';
    const decoded = atob(payload);
    return decoded.startsWith('http') ? decoded : url;
  } catch {
    return url;
  }
}

function getHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch { return ''; }
}

function cleanResultText(text = '') {
  const textarea = document.createElement('textarea');
  textarea.innerHTML = text.replace(/\*\*/g, '').replace(/<[^>]+>/g, '');
  return textarea.value.trim();
}

function scoreWebResult(item, note) {
  const host = getHost(item.url);
  const text = `${item.title} ${item.snippet} ${item.url}`.toLowerCase();
  const noteTokens = tokenize(note).map(token => token.toLowerCase()).filter(token => token.length > 1);
  const trusted = ['blog.google', 'aboutamazon.com', 'corporate.walmart.com', 'instacart.com', 'shopify.com', 'stripe.com', 'mastercard.com', 'visa.com', 'mckinsey.com', 'a16z.com', 'openai.com', 'anthropic.com', 'perplexity.ai', 'mp.weixin.qq.com'];
  let score = trusted.some(domain => host.includes(domain)) ? 24 : 0;
  score += /shopping|commerce|retail|agentic|assistant|checkout|merchant|导购|购物|电商|智能体|商家|支付/.test(text) ? 18 : -12;
  score += noteTokens.reduce((sum, token) => sum + (text.includes(token) ? 4 : 0), 0);
  if (/工具集|导航|入口|破解版|下载|课程|培训|招聘|login|signin/i.test(text)) score -= 30;
  return score;
}

function parseJinaSearch(markdown, note) {
  const blocks = [...markdown.matchAll(/\d+\.\s+##\s+\[([^\]]+)\]\(([^)]+)\)\s*\n+([\s\S]*?)(?=\n+\d+\.\s+##|$)/g)];
  return blocks.map(match => {
    const url = decodeBingRedirect(cleanResultText(match[2]));
    const item = {
      title: cleanResultText(match[1]),
      url,
      source: getHost(url),
      snippet: cleanResultText(match[3]).split('\n').filter(Boolean).slice(0, 2).join(' ')
    };
    return { ...item, score: scoreWebResult(item, note) };
  }).filter(item => item.url.startsWith('http') && item.score >= 8)
    .sort((a, b) => b.score - a.score);
}

async function fetchStaticWebResults(note) {
  const queries = [
    `${note} AI购物 导购 智能体 案例`,
    `${note} agentic commerce shopping assistant retail case report`,
    `${note} site:blog.google OR site:aboutamazon.com OR site:shopify.com AI shopping agent`
  ];
  const results = [];
  for (const query of queries) {
    try {
      const target = `https://www.bing.com/search?q=${encodeURIComponent(query)}&count=10`;
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      const response = await fetch(`https://r.jina.ai/http://r.jina.ai/http://${target}`, { signal: controller.signal });
      clearTimeout(timer);
      if (!response.ok) continue;
      results.push(...parseJinaSearch(await response.text(), note));
      if (uniqueLinks(results).length >= 6) break;
    } catch (error) {
      console.warn('static web search failed', error);
    }
  }
  return uniqueLinks(results).slice(0, 6);
}

async function fetchOnlineResults(note) {
  const endpoints = [`/api/search-support?q=${encodeURIComponent(note)}`, `/.netlify/functions/search-support?q=${encodeURIComponent(note)}`];
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(endpoint);
      if (!response.ok) continue;
      const data = await response.json();
      if (Array.isArray(data.results) && data.results.length) return data.results;
    } catch (error) {
      console.warn('search endpoint failed', endpoint, error);
    }
  }
  return fetchStaticWebResults(note);
}

const waitFrame = () => new Promise(resolve => requestAnimationFrame(resolve));

function renderNoteProgress(activeStep = '分析观点') {
  const steps = ['分析观点', '匹配站内资料', '联网找支撑', '生成灵感卡片'];
  const activeIndex = activeStep === '完成' ? steps.length : steps.indexOf(activeStep);
  return `<div class="note-progress">${steps.map((step, index) => `<span class="${step === activeStep ? 'active' : ''} ${index < activeIndex ? 'done' : ''}">${step}</span>`).join('')}</div>`;
}

function setNoteBusy(busy, label = '处理中…') {
  const previewBtn = document.getElementById('notePreviewBtn');
  const saveBtn = document.getElementById('noteSaveBtn');
  [previewBtn, saveBtn].forEach(button => {
    if (!button) return;
    button.disabled = busy;
    button.classList.toggle('is-loading', busy);
  });
  if (previewBtn) previewBtn.textContent = busy ? label : '智能搜索支撑';
  if (saveBtn) saveBtn.textContent = busy ? '正在生成…' : '加入灵感集';
}

function showToast(message) {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 2600);
}

async function searchSupportLinks(note, onProgress = () => {}) {
  onProgress('分析观点');
  await waitFrame();
  const localTokens = tokenize(note).slice(0, 12);
  onProgress('匹配站内资料');
  await waitFrame();
  const local = scoreLocalArticles(localTokens);
  onProgress('联网找支撑');
  await waitFrame();
  const online = await fetchOnlineResults(note);
  onProgress('生成灵感卡片');
  await waitFrame();
  const external = uniqueLinks([...(online || []), ...curatedWebFallback(note, local)]).slice(0, 6);
  const keywords = noteKeywords(note, external, local);
  const insight = buildSupportInsight(note, external, local);
  const angle = noteAngle(note);
  return { title: angle.title, summary: angle.summary, keywords, local, external, insight };
}

async function renderNotePreview(note) {
  const box = document.getElementById('notePreview');
  state.noteSupport = null;
  const updateProgress = (step) => {
    box.innerHTML = `${renderNoteProgress(step)}<h4>${step}中…</h4><p>会把你的原始观点转成标题、摘要、产品洞察，并匹配站内资料和全网支撑链接。</p>`;
  };
  const result = await searchSupportLinks(note, updateProgress);
  state.noteSupport = { note, result };
  box.innerHTML = `
    ${renderNoteProgress('完成')}
    <h4>已生成：${escapeHtml(result.title)}</h4>
    <p class="note-preview-summary">${escapeHtml(result.summary)}</p>
    <div class="meta">${(result.keywords || []).slice(0, 8).map(token => `<span class="pill">${escapeHtml(token)}</span>`).join('') || '<span class="pill">暂无关键词</span>'}</div>
    <ul class="derived-insight">${(result.insight || '').split('\n').filter(Boolean).map(line => `<li>${escapeHtml(line)}</li>`).join('')}</ul>
    <p class="note-preview-ok">已匹配 ${(result.external || []).length} 条全网支撑、${(result.local || []).length} 条站内关联。点击“加入灵感集”后会保存为你的灵感卡片。</p>
    <div class="related note-links">
      ${(result.external || []).slice(0, 6).map(link => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer">全网支撑：${escapeHtml(link.title)}${link.snippet ? `<small>${escapeHtml(link.snippet)}</small>` : ''}</a>`).join('')}
      ${(result.local || []).map(article => `<a href="${escapeHtml(article.url)}" target="_blank" rel="noreferrer">站内关联：${escapeHtml(article.title)}</a>`).join('')}
    </div>`;
  return result;
}

function bindNotes() {
  const input = document.getElementById('noteInput');
  document.getElementById('notePreviewBtn').addEventListener('click', async () => {
    const note = input.value.trim();
    if (!note) return showToast('先写一点想法，我再帮你找支撑。');
    setNoteBusy(true, '正在搜索…');
    try {
      await renderNotePreview(note);
      showToast('已生成支撑洞察，可以加入灵感集。');
    } catch (error) {
      console.warn(error);
      document.getElementById('notePreview').innerHTML = '<h4>搜索失败</h4><p>网络暂时不稳定，可以稍后再试；也可以先直接加入灵感集。</p>';
      showToast('搜索支撑失败了，请稍后重试。');
    } finally {
      setNoteBusy(false);
    }
  });
  document.getElementById('noteSaveBtn').addEventListener('click', async () => {
    const note = input.value.trim();
    if (!note) return showToast('先写一点想法，再加入灵感集。');
    setNoteBusy(true, '正在保存…');
    try {
      let support = state.noteSupport?.note === note ? state.noteSupport.result : null;
      if (!support) support = await renderNotePreview(note);
      const newNote = {
        id: `user-${Date.now()}`,
        title: support.title,
        summary: support.summary,
        body: note,
        createdAt: new Date().toISOString(),
        keywords: (support.keywords || []).slice(0, 6),
        generatedInsight: support.insight || '',
        localIds: (support.local || []).map(article => article.id),
        external: support.external || []
      };
      state.userInsights.unshift(enrichSavedNote(newNote));
      state.justSavedNoteId = newNote.id;
      saveUserInsights();
      input.value = '';
      document.getElementById('notePreview').innerHTML = '';
      state.noteSupport = null;
      renderUserInsights();
      renderGlobalStats();
      setActiveTab('inspiration');
      setNotePanelOpen(false);
      showToast('已加入灵感集，放在最上面了。');
      setTimeout(() => {
        document.querySelector(`[data-card-id="${newNote.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        state.justSavedNoteId = '';
        renderUserInsights();
      }, 180);
    } catch (error) {
      console.warn(error);
      const angle = noteAngle(note);
      const fallbackNote = enrichSavedNote({
        id: `user-${Date.now()}`,
        title: angle.title,
        summary: angle.summary,
        body: note,
        createdAt: new Date().toISOString(),
        keywords: noteKeywords(note),
        generatedInsight: [angle.need, angle.opportunity, angle.method].join('\n'),
        localIds: [],
        external: curatedWebFallback(note, [])
      });
      state.userInsights.unshift(fallbackNote);
      state.justSavedNoteId = fallbackNote.id;
      saveUserInsights();
      input.value = '';
      document.getElementById('notePreview').innerHTML = '';
      state.noteSupport = null;
      renderUserInsights();
      renderGlobalStats();
      setActiveTab('inspiration');
      setNotePanelOpen(false);
      showToast('搜索不稳定，但已先加入灵感集。');
      setTimeout(() => {
        document.querySelector(`[data-card-id="${fallbackNote.id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        state.justSavedNoteId = '';
        renderUserInsights();
      }, 180);
    } finally {
      setNoteBusy(false);
    }
  });
}

function deleteUserInsight(noteId) {
  const note = state.userInsights.find(item => item.id === noteId);
  if (!note) return;
  const ok = window.confirm(`确定删除这条笔记吗？\n\n${note.title}`);
  if (!ok) return;
  state.userInsights = state.userInsights.filter(item => item.id !== noteId);
  saveUserInsights();
  renderUserInsights();
  renderGlobalStats();
}

function renderUserInsights() {
  const articlesById = Object.fromEntries(state.articles.map(article => [article.id, article]));
  const visibleNotes = state.userInsights.filter(noteMatchesKeyword);
  document.getElementById('userInsightGrid').innerHTML = visibleNotes.map(note => {
    const locals = (note.localIds || []).map(id => articlesById[id]).filter(Boolean);
    return `
      <article class="insight-card user-note-card ${state.justSavedNoteId === note.id ? 'just-saved' : ''}" data-card-id="${escapeHtml(note.id)}">
        <div class="user-note-head">
          <span class="user-badge">我的笔记</span>
          <button class="delete-note-btn" data-note-id="${escapeHtml(note.id)}" type="button">删除</button>
        </div>
        <h3>${escapeHtml(note.title)}</h3>
        ${note.summary ? `<p class="note-summary">${escapeHtml(note.summary)}</p>` : ''}
        <div class="original-note"><strong>原始笔记</strong><p>${escapeHtml(note.body)}</p></div>
        ${note.generatedInsight ? `<ul class="derived-insight">${note.generatedInsight.split('\n').filter(Boolean).map(line => `<li>${escapeHtml(line)}</li>`).join('')}</ul>` : ''}
        <div class="meta">${(note.keywords || []).map(word => `<span class="pill">${escapeHtml(word)}</span>`).join('')}</div>
        <div class="related">
          ${locals.map(article => `<a href="${escapeHtml(article.url)}" target="_blank" rel="noreferrer">站内支撑：${escapeHtml(article.title)}</a>`).join('')}
          ${(note.external || []).map(link => `<a href="${escapeHtml(link.url)}" target="_blank" rel="noreferrer">${escapeHtml(link.title)}</a>`).join('')}
        </div>
      </article>`;
  }).join('');
  document.querySelectorAll('.delete-note-btn').forEach(button => {
    button.addEventListener('click', () => deleteUserInsight(button.dataset.noteId));
  });
}

function renderFeed() {
  renderMonthTabs();
  renderActiveMonthlyReport();
  renderArticles(filteredArticles());
}

function render() {
  renderFeed();
  renderWordCloud();
  renderUserInsights();
  renderInsights();
  renderGlobalStats();
  renderUpdateBadges();
}

loadData().catch(error => {
  console.error(error);
  document.body.insertAdjacentHTML('afterbegin', '<p style="padding:20px;color:red">数据加载失败，请检查 data 目录。</p>');
});
