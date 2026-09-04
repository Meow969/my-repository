const USER_AGENT = 'Mozilla/5.0 (compatible; AI-Shopping-Radar/1.0)';

function strip(html) {
  return html.replace(/<script[\s\S]*?<\/script>/gi, '').replace(/<style[\s\S]*?<\/style>/gi, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}
function decode(value = '') {
  return value.replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
}
function host(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return ''; }
}
function qualityScore(item, query) {
  const h = host(item.url);
  const text = `${item.title} ${item.snippet}`.toLowerCase();
  const q = query.toLowerCase().split(/\s+/).filter(Boolean);
  const trusted = ['openai.com','blog.google','aboutamazon.com','shopify.com','mckinsey.com','stripe.com','mastercard.com','visa.com','perplexity.ai','anthropic.com','a16z.com'];
  let score = trusted.some(domain => h.includes(domain)) ? 30 : 0;
  if (/ai-bot|aigc\.cn|tool|tools|nav|daohang|kimi\.com|chatgpt\.com|baidu\.com/.test(h)) score -= 30;
  if (/工具集|导航|官网入口|免费下载|破解版|课程|培训/.test(`${item.title} ${item.snippet}`)) score -= 30;
  score += q.reduce((sum, word) => sum + (text.includes(word) ? 3 : 0), 0);
  score += /shopping|commerce|retail|agent|导购|购物|电商|智能体/i.test(text) ? 12 : 0;
  return score;
}

function curatedFallback(query) {
  return [
    { title: 'Google：Universal Cart and agentic shopping', url: 'https://blog.google/products-and-platforms/products/shopping/google-shopping-cart/', snippet: 'Google I/O 发布 Universal Cart、UCP 扩展和 agentic shopping 能力。', source: 'blog.google', score: 55 },
    { title: 'Google：UCP updates improve AI shopping for retailers', url: 'https://blog.google/products-and-platforms/products/shopping/ucp-updates/', snippet: 'Universal Commerce Protocol 帮助零售商接入 AI shopping experiences。', source: 'blog.google', score: 54 },
    { title: 'Amazon：Rufus AI shopping assistant', url: 'https://www.aboutamazon.com/news/retail/amazon-rufus', snippet: 'Amazon 原生购物助手，结合商品库、评论、问答和交易场景。', source: 'aboutamazon.com', score: 52 },
    { title: 'Google：New tools for retailers in an agentic shopping era', url: 'https://blog.google/products/ads-commerce/agentic-commerce-ai-tools-protocol-retailers-platforms/', snippet: 'Google 面向零售商的 agentic commerce 工具和开放标准。', source: 'blog.google', score: 52 },
    { title: 'Shopify：AI in Ecommerce', url: 'https://www.shopify.com/blog/ai-ecommerce', snippet: 'AI 在个性化、库存、客服和商家运营中的电商应用。', source: 'shopify.com', score: 45 }
  ].map(item => ({ ...item, score: item.score + (query.toLowerCase().includes('merchant') || query.includes('商家') ? 5 : 0) }));
}
async function searchBing(query) {
  const url = `https://www.bing.com/search?q=${encodeURIComponent(query)}&count=10`;
  const res = await fetch(url, { headers: { 'user-agent': USER_AGENT, 'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8' } });
  const html = await res.text();
  const blocks = [...html.matchAll(/<li class="b_algo"[\s\S]*?<\/li>/g)].map(m => m[0]);
  const results = [];
  for (const block of blocks) {
    const link = block.match(/<h2[\s\S]*?<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i);
    if (!link) continue;
    const snippet = block.match(/<p[^>]*>([\s\S]*?)<\/p>/i);
    const item = { title: decode(strip(link[2])), url: decode(link[1]), snippet: decode(strip(snippet?.[1] || '')) };
    if (item.url.startsWith('http')) results.push(item);
  }
  return results;
}
async function handler(req, res) {
  const query = req.query?.q || new URL(req.url, 'http://localhost').searchParams.get('q') || '';
  if (!query.trim()) return res.status(400).json({ error: 'Missing q' });
  const searchQuery = `${query} AI shopping agent commerce retail 导购 购物 智能体 case report`;
  try {
    const results = await searchBing(searchQuery);
    const deduped = [];
    const seen = new Set();
    for (const item of results) {
      const key = item.url.split('#')[0].split('?')[0];
      if (seen.has(key)) continue;
      seen.add(key);
      deduped.push({ ...item, source: host(item.url), score: qualityScore(item, searchQuery) });
    }
    const clean = deduped.filter(item => item.score >= 8);
    const merged = [];
    const mergedSeen = new Set();
    for (const item of [...clean, ...curatedFallback(query)]) {
      const key = item.url.split('#')[0].split('?')[0];
      if (mergedSeen.has(key)) continue;
      mergedSeen.add(key);
      merged.push(item);
    }
    merged.sort((a, b) => b.score - a.score);
    res.setHeader('access-control-allow-origin', '*');
    return res.status(200).json({ query, results: merged.slice(0, 6) });
  } catch (error) {
    return res.status(500).json({ error: String(error?.message || error) });
  }
}
module.exports = handler;
