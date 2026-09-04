const state = {
  articles: [],
  insights: [],
  reports: [],
  meta: {},
  userInsights: [],
  query: '',
  region: 'all',
  category: 'all',
  month: '',
  activeTab: 'feed',
  activeKeyword: 'all'
};

const USER_INSIGHTS_KEY = 'meow-ai-shopping-user-insights';
const SEEN_FEED_KEY = 'meow-ai-shopping-seen-feed';
const SEEN_INSPIRATION_KEY = 'meow-ai-shopping-seen-inspiration';
const SEARCH_CONCEPTS = {
  '记忆': ['记忆', '偏好', '画像', '复购', '长期约束', 'habit', 'personalization', 'context'],
  '信任': ['信任', '授权', '可撤回', '解释', '证据', '风险', 'trust', 'permission'],
  '闭环': ['闭环', '支付', '下单', '履约', '售后', '购物车', 'checkout', 'order'],
  '商家': ['商家', '商品库', '机器可读', 'GEO', '可见性', 'seller', 'merchant'],
  '协议': ['协议', 'UCP', 'MCP', 'agentic commerce', '接口', '跨平台', 'protocol'],
  '即时': ['即时零售', '买菜', '外卖', '日用品', '高频低风险', '复购', 'local commerce'],
  '评价': ['评价', '口碑', '测评', '评论摘要', 'social proof', 'review'],
  '视觉': ['视觉', '试穿', '图片', '风格', '非标品', 'fashion', 'style'],
  '治理': ['治理', '排序', '赞助', '公平性', '责任', 'ranking', 'governance']
};
const fmtDate = (iso) => new Date(`${iso}T00:00:00+08:00`).toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' });
const fmtMonth = (month) => month.replace('-', '年') + '月';
const unique = (arr) => [...new Set(arr)].filter(Boolean);
const escapeHtml = (text = '') => text.replace(/[&<>"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[char]));

async function loadData() {
  const [articles, insights, reports, meta] = await Promise.all([
    fetch('./data/articles.json').then(r => r.json()),
    fetch('./data/insights.json').then(r => r.json()),
    fetch('./data/monthly_reports.json').then(r => r.json()),
    fetch('./data/meta.json').then(r => r.json())
  ]);
  state.articles = articles.sort((a, b) => b.date.localeCompare(a.date) || b.valueScore - a.valueScore);
  state.insights = insights;
  state.reports = reports.sort((a, b) => b.month.localeCompare(a.month));
  state.meta = meta;
  state.month = unique(state.articles.map(article => article.date.slice(0, 7))).sort().reverse()[0] || '';
  state.userInsights = loadUserInsights();
  renderFilters();
  bindTabs();
  bindNotes();
  render();
}

function bindTabs() {
  document.querySelectorAll('.top-tab').forEach(button => {
    button.addEventListener('click', () => {
      state.activeTab = button.dataset.tab;
      document.querySelectorAll('.top-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.tab === state.activeTab));
      document.getElementById('feedTab').classList.toggle('active', state.activeTab === 'feed');
      document.getElementById('inspirationTab').classList.toggle('active', state.activeTab === 'inspiration');
      markTabSeen(state.activeTab);
    });
  });
}

function renderFilters() {
  const regionFilter = document.getElementById('regionFilter');
  const categoryFilter = document.getElementById('categoryFilter');
  unique(state.articles.map(a => a.region)).forEach(region => regionFilter.append(new Option(region, region)));
  unique(state.articles.map(a => a.category)).forEach(category => categoryFilter.append(new Option(category, category)));
  document.getElementById('searchInput').addEventListener('input', e => {
    state.query = e.target.value.trim().toLowerCase();
    renderFeed();
    renderUserInsights();
    renderInsights();
    renderGlobalStats();
  });
  regionFilter.addEventListener('change', e => { state.region = e.target.value; renderFeed(); renderGlobalStats(); });
  categoryFilter.addEventListener('change', e => { state.category = e.target.value; renderFeed(); renderGlobalStats(); });
}

function renderGlobalStats() {
  const feedCount = filteredArticles().length;
  const currentMonthCount = monthArticleCount(state.month);
  const insightCount = activeInsights().length;
  const totalInsights = state.insights.length + state.userInsights.length;
  const label = state.query
    ? `语义召回：资讯 ${feedCount} 条 · 灵感 ${insightCount} 个`
    : `${fmtMonth(state.month)} ${currentMonthCount} 条精选 · 灵感 ${totalInsights} 个`;
  document.getElementById('globalStats').textContent = label;
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
    article.category,
    article.corePoint,
    article.insight,
    ...(article.tags || []),
    ...related.flatMap(insight => [insight.title, insight.summary, ...(insight.keywords || [])])
  ].join(' ').toLowerCase();
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
  return `
    <article class="article-card">
      <div class="article-head">
        <a class="article-title" href="${article.url}" target="_blank" rel="noreferrer">${article.title}</a>
        <span class="score">价值 ${article.valueScore}</span>
      </div>
      <div class="meta">
        <span class="pill">${article.source}</span><span class="pill">${article.region}</span><span class="pill">${article.category}</span>
        ${(article.tags || []).map(tag => `<span class="pill">#${tag}</span>`).join('')}
      </div>
      <h4>核心观点</h4><p>${article.corePoint}</p>
      <h4>产品洞察</h4><p>${article.insight}</p>
      <a class="open-link" href="${article.url}" target="_blank" rel="noreferrer">打开原文 →</a>
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
  const haystack = [note.title, note.body, note.generatedInsight, ...(note.keywords || [])].join(' ').toLowerCase();
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
    return `
      <article class="insight-card">
        <span class="system-badge">AI复盘 · ${related.length}条信息源${insight.updatedAt ? ` · ${insight.updatedAt.slice(5, 10)}` : ''}</span>
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
  try { return JSON.parse(localStorage.getItem(USER_INSIGHTS_KEY) || '[]'); }
  catch { return []; }
}

function saveUserInsights() {
  localStorage.setItem(USER_INSIGHTS_KEY, JSON.stringify(state.userInsights));
}

function tokenize(text) {
  const known = unique(state.insights.flatMap(i => i.keywords || []).concat(state.articles.flatMap(a => a.tags || [])));
  const lower = text.toLowerCase();
  const hits = known.filter(word => lower.includes(word.toLowerCase()));
  const cn = (text.match(/[\u4e00-\u9fa5]{2,}/g) || []).flatMap(chunk => {
    const parts = [];
    for (let i = 0; i < chunk.length - 1; i += 2) parts.push(chunk.slice(i, i + 4));
    return parts;
  });
  const en = text.match(/[a-zA-Z][a-zA-Z\-]{2,}/g) || [];
  return unique([...hits, ...cn, ...en]).slice(0, 10);
}

function scoreLocalArticles(tokens) {
  return state.articles.map(article => {
    const haystack = [article.title, article.corePoint, article.insight, ...(article.tags || [])].join(' ').toLowerCase();
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
  const query = encodeURIComponent(note.slice(0, 80));
  const seed = [
    { title: 'Google：Universal Cart and agentic shopping', url: 'https://blog.google/products-and-platforms/products/shopping/google-shopping-cart/', source: 'Google', snippet: '跨平台购物车、UCP 和 agentic shopping 的官方产品案例。' },
    { title: 'Google：UCP updates improve AI shopping for retailers', url: 'https://blog.google/products-and-platforms/products/shopping/ucp-updates/', source: 'Google', snippet: '面向商家的 AI shopping 接入协议与能力更新。' },
    { title: 'Amazon：Rufus AI shopping assistant', url: 'https://www.aboutamazon.com/news/retail/amazon-rufus', source: 'Amazon', snippet: '平台内原生购物助手，结合商品库、评论和购买链路。' },
    { title: 'Shopify：AI in Ecommerce', url: 'https://www.shopify.com/blog/ai-ecommerce', source: 'Shopify', snippet: '商家侧 AI 在个性化、库存、客服和运营中的落点。' },
    { title: '微信文章搜索：相关中文案例', url: `https://weixin.sogou.com/weixin?type=2&query=${query}`, source: 'Sogou Weixin', snippet: '继续查找国内公众号案例和行业分析。' },
    { title: 'Google 搜索：海外 AI shopping agent 案例', url: `https://www.google.com/search?q=${query}+AI+shopping+agent+commerce+case`, source: 'Google Search', snippet: '继续查找海外产品案例和报告。' }
  ];
  const localAsWeb = local.slice(0, 2).map(article => ({ title: article.title, url: article.url, source: article.source, snippet: article.corePoint }));
  return uniqueLinks([...localAsWeb, ...seed]).slice(0, 6);
}

function buildSupportInsight(note, external, local) {
  const text = `${note} ${external.map(item => `${item.title} ${item.snippet || ''}`).join(' ')} ${local.map(item => item.corePoint).join(' ')}`;
  const points = [];
  if (/支付|checkout|下单|闭环|购物车|cart|order/i.test(text)) {
    points.push('这类想法的关键验证点不是“AI会不会推荐”，而是能否完成授权、价格库存核验、支付确认、履约追踪和售后归因。');
  }
  if (/商家|merchant|seller|GEO|可见性|商品|库存|价格/i.test(text)) {
    points.push('如果要落地为产品，必须同时建设商家侧机器可读资料层；否则AI只能做内容解释，无法稳定进入订单分配。');
  }
  if (/复购|买菜|即时|低风险|日用品|外卖|habit/i.test(text)) {
    points.push('高频低风险场景适合先跑偏好记忆和授权边界，再把信任迁移到高客单、强比较的复杂品类。');
  }
  if (/视觉|试穿|图片|fashion|style|非标/i.test(text)) {
    points.push('非标品类不要套参数比较逻辑，AI更适合做风格翻译、相似款发现、上身效果预判和后悔风险降低。');
  }
  if (/协议|protocol|ucp|agentic/i.test(text)) {
    points.push('一旦涉及跨平台购物，协议层会比单点模型能力更重要：商品、购物车、订单、售后都需要标准化接口。');
  }
  points.push('建议把这个笔记转成一个产品实验：目标用户、被省掉的决策步骤、必须接入的数据、失败兜底、成功指标各写一句。');
  return points.slice(0, 4).join('\n');
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
  const trusted = ['blog.google', 'aboutamazon.com', 'shopify.com', 'stripe.com', 'mastercard.com', 'visa.com', 'mckinsey.com', 'a16z.com', 'openai.com', 'anthropic.com', 'perplexity.ai', 'mp.weixin.qq.com'];
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

async function searchSupportLinks(note) {
  const keywords = tokenize(note).slice(0, 8);
  const local = scoreLocalArticles(keywords);
  const online = await fetchOnlineResults(note);
  const external = uniqueLinks([...(online || []), ...curatedWebFallback(note, local)]).slice(0, 6);
  const insight = buildSupportInsight(note, external, local);
  return { keywords, local, external, insight };
}

async function renderNotePreview(note) {
  const box = document.getElementById('notePreview');
  box.innerHTML = '<h4>正在联网搜索支撑材料…</h4><p>会优先匹配高质量信息源，并至少给出 3 条可继续追踪的链接。</p>';
  const result = await searchSupportLinks(note);
  box.innerHTML = `
    <h4>联网搜索与衍生洞察</h4>
    <div class="meta">${(result.keywords || []).slice(0, 8).map(token => `<span class="pill">${escapeHtml(token)}</span>`).join('') || '<span class="pill">暂无关键词</span>'}</div>
    <ul class="derived-insight">${(result.insight || '').split('\n').filter(Boolean).map(line => `<li>${escapeHtml(line)}</li>`).join('')}</ul>
    <div class="related note-links">
      ${(result.external || []).slice(0, 6).map(link => `<a href="${link.url}" target="_blank" rel="noreferrer">全网支撑：${escapeHtml(link.title)}${link.snippet ? `<small>${escapeHtml(link.snippet)}</small>` : ''}</a>`).join('')}
      ${(result.local || []).map(article => `<a href="${article.url}" target="_blank" rel="noreferrer">站内关联：${article.title}</a>`).join('')}
    </div>`;
  return result;
}

function bindNotes() {
  const input = document.getElementById('noteInput');
  document.getElementById('notePreviewBtn').addEventListener('click', async () => {
    const note = input.value.trim();
    if (!note) return;
    await renderNotePreview(note);
  });
  document.getElementById('noteSaveBtn').addEventListener('click', async () => {
    const note = input.value.trim();
    if (!note) return;
    const support = await renderNotePreview(note);
    state.userInsights.unshift({
      id: `user-${Date.now()}`,
      title: note.slice(0, 32),
      body: note,
      createdAt: new Date().toISOString(),
      keywords: (support.keywords || []).slice(0, 6),
      generatedInsight: support.insight || '',
      localIds: (support.local || []).map(article => article.id),
      external: support.external || []
    });
    saveUserInsights();
    input.value = '';
    document.getElementById('notePreview').innerHTML = '';
    renderUserInsights();
    renderGlobalStats();
  });
}

function renderUserInsights() {
  const articlesById = Object.fromEntries(state.articles.map(article => [article.id, article]));
  const visibleNotes = state.userInsights.filter(noteMatchesKeyword);
  document.getElementById('userInsightGrid').innerHTML = visibleNotes.map(note => {
    const locals = (note.localIds || []).map(id => articlesById[id]).filter(Boolean);
    return `
      <article class="insight-card user-note-card">
        <span class="user-badge">我的笔记</span>
        <h3>${escapeHtml(note.title)}</h3>
        <p>${escapeHtml(note.body)}</p>
        ${note.generatedInsight ? `<ul class="derived-insight">${note.generatedInsight.split('\n').filter(Boolean).map(line => `<li>${escapeHtml(line)}</li>`).join('')}</ul>` : ''}
        <div class="meta">${(note.keywords || []).map(word => `<span class="pill">${escapeHtml(word)}</span>`).join('')}</div>
        <div class="related">
          ${locals.map(article => `<a href="${article.url}" target="_blank" rel="noreferrer">站内支撑：${article.title}</a>`).join('')}
          ${(note.external || []).map(link => `<a href="${link.url}" target="_blank" rel="noreferrer">${link.title}</a>`).join('')}
        </div>
      </article>`;
  }).join('');
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
