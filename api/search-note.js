const QUALITY_DOMAINS = [
  'openai.com', 'blog.google', 'aboutamazon.com', 'shopify.com', 'mckinsey.com',
  'stripe.com', 'mastercard.com', 'visa.com', 'perplexity.ai', 'a16z.com',
  '36kr.com', 'huxiu.com', 'iyiou.com', 'geekpark.net', 'leiphone.com', 'mp.weixin.qq.com'
];

function stripTags(html) {
  return html.replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/\s+/g, ' ').trim();
}

function decodeUrl(url) {
  try { return decodeURIComponent(url); } catch { return url; }
}

function extractBingResults(html) {
  const blocks = html.match(/<li class="b_algo"[\s\S]*?<\/li>/g) || [];
  return blocks.map(block => {
    const link = block.match(/<h2[\s\S]*?<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i);
    const snippet = block.match(/<p[^>]*>([\s\S]*?)<\/p>/i);
    if (!link) return null;
    return {
      title: stripTags(link[2]),
      url: decodeUrl(link[1]),
      snippet: snippet ? stripTags(snippet[1]) : ''
    };
  }).filter(Boolean).filter(item => /^https?:\/\//.test(item.url));
}

function tokenize(text) {
  const cn = (text.match(/[\u4e00-\u9fa5]{2,}/g) || []).flatMap(chunk => {
    const arr = [];
    for (let i = 0; i < chunk.length - 1; i += 2) arr.push(chunk.slice(i, i + 4));
    return arr;
  });
  const en = text.match(/[a-zA-Z][a-zA-Z\-]{2,}/g) || [];
  return [...new Set([...cn, ...en])].slice(0, 16);
}

function scoreResult(result, note) {
  const haystack = `${result.title} ${result.snippet} ${result.url}`.toLowerCase();
  const tokens = tokenize(note).map(token => token.toLowerCase());
  let score = tokens.reduce((sum, token) => sum + (haystack.includes(token) ? 2 : 0), 0);
  score += QUALITY_DOMAINS.some(domain => result.url.includes(domain)) ? 8 : 0;
  score += /ai|agent|shopping|commerce|retail|导购|购物|电商|智能体|零售|支付|履约/i.test(haystack) ? 6 : 0;
  score -= /招聘|培训|下载|破解|广告|招商|课程/.test(haystack) ? 10 : 0;
  return score;
}

async function searchWeb(note) {
  const queries = [
    `${note} AI购物 导购 智能体 案例`,
    `${note} Agentic Commerce shopping agent retail case`,
    `${note} site:mp.weixin.qq.com AI购物 OR AI导购`,
    `${note} site:blog.google OR site:aboutamazon.com OR site:shopify.com AI shopping`
  ];
  const results = [];
  for (const query of queries) {
    const url = `https://www.bing.com/search?q=${encodeURIComponent(query)}&count=10`;
    try {
      const res = await fetch(url, { headers: { 'user-agent': 'Mozilla/5.0', 'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8' } });
      const html = await res.text();
      results.push(...extractBingResults(html));
    } catch (_) {}
  }
  const deduped = [];
  const seen = new Set();
  for (const result of results) {
    const key = result.url.replace(/[#?].*$/, '');
    if (!seen.has(key)) { seen.add(key); deduped.push(result); }
  }
  return deduped.map(result => ({ ...result, score: scoreResult(result, note) }))
    .filter(result => result.score > 3)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6);
}

function synthesize(note, results) {
  const names = results.slice(0, 3).map(item => `《${item.title}》`).join('、') || '搜索结果';
  const lower = note.toLowerCase();
  let angle = '这个想法的关键不是单点功能，而是要验证它能否改变用户决策链路。';
  if (/复购|日常|买菜|低风险|高频/.test(note)) angle = '这个方向适合先做高频低风险场景，用偏好记忆和履约稳定性建立授权习惯，再逐步迁移到更复杂品类。';
  if (/信任|授权|代买|自动/.test(note)) angle = '这个方向的核心是信任阶梯：先解释、再筛选、再加购、最后授权下单，自动化必须建立在可撤回和可追责之上。';
  if (/商家|品牌|geo|可见性|商品/.test(lower)) angle = '这个方向本质是商家信息资产问题：商品卖点、证据、库存、价格和售后必须机器可读，AI才敢把候选资格交给品牌。';
  if (/支付|checkout|闭环|履约/.test(lower)) angle = '这个方向会进入交易基础设施层，重点不再是推荐多准，而是价格、库存、支付、售后和责任边界是否可靠。';
  return `基于你的观点和${names}，可延展出一个产品判断：${angle} 下一步可以把它拆成三个验证问题：用户是否愿意交出这类决策权、AI是否有足够证据做判断、推荐之后能否稳定完成交易或后续服务。`;
}

async function handle(note) {
  const trimmed = String(note || '').trim();
  if (!trimmed) return { results: [], insight: '', keywords: [] };
  let results = await searchWeb(trimmed);
  if (results.length < 3) {
    const q = encodeURIComponent(trimmed);
    results = results.concat([
      { title: '微信文章搜索：相关中文案例', url: `https://weixin.sogou.com/weixin?type=2&query=${q}`, snippet: '用于继续查找中文公众号案例和分析。', score: 4 },
      { title: 'Google 搜索：海外 AI shopping agent 案例', url: `https://www.google.com/search?q=${q}+AI+shopping+agent+case`, snippet: '用于继续查找海外产品案例。', score: 4 },
      { title: 'Google 搜索：Agentic Commerce report', url: `https://www.google.com/search?q=${q}+Agentic+Commerce+retail+report`, snippet: '用于继续查找行业报告和协议动态。', score: 4 }
    ]).slice(0, 6);
  }
  return { keywords: tokenize(trimmed).slice(0, 8), results: results.slice(0, 6), insight: synthesize(trimmed, results) };
}

module.exports = async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });
  try {
    const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : (req.body || {});
    res.status(200).json(await handle(body.note));
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
};
