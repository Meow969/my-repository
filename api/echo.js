const DEFAULT_MODEL = 'gpt-5.5';
const DEFAULT_BASE_URL = (process.env.OPENAI_BASE_URL || 'https://api.openai.com/v1').replace(/\/$/, '');
const FREE_ECHO_ENDPOINT = 'https://text.pollinations.ai/openai';
const FREE_ECHO_MODEL = 'openai-fast';

function json(res, status, body) {
  res.setHeader('access-control-allow-origin', '*');
  res.setHeader('access-control-allow-methods', 'POST, OPTIONS');
  res.setHeader('access-control-allow-headers', 'content-type, authorization');
  return res.status(status).json(body);
}

function parseBody(req) {
  if (typeof req.body === 'object' && req.body) return req.body;
  try { return JSON.parse(req.body || '{}'); }
  catch { return {}; }
}

function systemPrompt() {
  return `你是AI购物/AI导购产品经理的深度思考伙伴。用户会给一句观点，你必须先分析理解，再回应补充，最后给下一步洞察。
要求：
1. understanding：用1-2句话说明你理解到的真实问题、隐含假设或用户需求，不要复述原话。
2. nextInsights：输出2-4条下一步洞察，每条要能推动产品判断或实验设计。
3. echoes：输出10条以内，建议6-8条；每条是高质量回声呼应，可以是关键词、关键句或短观点。
4. 每条必须对产品设计、用户需求、产品价值、机会点、方法论、创新点或验证方式有启发。
5. 避免空话、套话、重复句式；不要说“值得关注”“持续观察”这种无信息量表达。
6. 尽量贴近AI购物、导购、交易闭环、信任、商家供给、履约、用户决策。
7. 只输出JSON，格式：{"understanding":"...","nextInsights":["..."],"echoes":[{"angle":"用户需求","text":"..."}]}`;
}

function userPrompt(text, context) {
  const compactContext = JSON.stringify(context || {}).slice(0, 4200);
  return `用户观点：${text}\n\n站内近期上下文：${compactContext}\n\n请先分析你对这句话的理解，再生成下一步洞察和10个以内高质量回声。`;
}

function extractJsonObject(text = '') {
  const clean = String(text).replace(/```json|```/g, '').trim();
  const start = clean.indexOf('{');
  const end = clean.lastIndexOf('}');
  if (start < 0 || end < start) return null;
  try { return JSON.parse(clean.slice(start, end + 1)); }
  catch { return null; }
}

function normalizeEchoResponse(value, originalText = '') {
  const parsed = value?.echoes || value?.understanding || value?.nextInsights
    ? value
    : (extractJsonObject(value?.choices?.[0]?.message?.content) || {});
  const rawEchoes = parsed.echoes || [];
  const echoes = (Array.isArray(rawEchoes) ? rawEchoes : []).map((item, index) => {
    if (typeof item === 'string') return { angle: `回声 ${index + 1}`, text: item.trim() };
    return { angle: String(item.angle || item.title || `回声 ${index + 1}`).trim(), text: String(item.text || item.body || item.content || '').trim() };
  }).filter(item => item.text).slice(0, 10);
  const nextInsights = (Array.isArray(parsed.nextInsights) ? parsed.nextInsights : [])
    .map(item => typeof item === 'string' ? item.trim() : String(item?.text || item?.body || '').trim())
    .filter(Boolean)
    .slice(0, 4);
  const understanding = String(parsed.understanding || '').trim();
  const fallback = localEchoAnalysis(originalText);
  return {
    understanding: understanding || fallback.understanding,
    nextInsights: nextInsights.length ? nextInsights : fallback.nextInsights,
    echoes: echoes.length ? echoes : fallback.echoes
  };
}

function localEchoAnalysis(text) {
  const lower = String(text || '').toLowerCase();
  const isTrust = /信任|风险|授权|自动|代买|确认|隐私|permission|trust/.test(lower);
  const isDeal = /支付|下单|结算|履约|售后|购物车|闭环|checkout|order/.test(lower);
  const isMerchant = /商家|品牌|商品库|库存|卖家|供给|merchant|seller|catalog/.test(lower);
  const isMemory = /记忆|偏好|个性化|复购|懂我|画像|personal|memory/.test(lower);
  const isSearch = /搜索|入口|答案|流量|外部|内容|种草|search|answer/.test(lower);
  const isVisual = /试穿|图片|视觉|尺码|风格|穿搭|visual|try-on|fashion/.test(lower);
  const focus = isTrust ? '信任边界' : isDeal ? '交易责任' : isMerchant ? '供给资产' : isMemory ? '可编辑偏好' : isSearch ? '意图承接' : isVisual ? '适配证据' : '购物决策';
  const understanding = `我理解你在问的不是一个功能点，而是AI导购如何在${focus}里真正替用户降低决策成本，同时不制造新的不确定和责任风险。`;
  const nextInsights = [
    '先把这个观点落到一个具体链路节点：表达需求、比较候选、确认风险、授权动作或购后兜底，避免讨论停在概念层。',
    '下一步要定义AI“可以做”和“必须停下来问用户”的边界，尤其是涉及价格、库存、支付、履约和售后的动作。',
    '验证时不要只看生成质量，而要看用户是否少了一次人工核对、是否更愿意继续授权、以及失败时是否更容易接管。'
  ];
  const echoes = [
    { angle: '用户需求', text: `这句话背后的需求不是“让AI更聪明”，而是让用户少承担一次${focus}里的不确定：不知道怎么选、不知道能不能买、不知道错了谁负责。` },
    { angle: '产品价值', text: '如果要把它做成产品主张，可以从“替用户给答案”改成“替用户保存判断过程”：约束、证据、取舍和下一步动作都可回看。' },
    { angle: '机会点', text: isDeal ? '交易闭环里最容易被低估的是异常处理。缺货、涨价、超时、售后失败时，AI如果能主动给替代方案，价值会比推荐本身更明显。' : `可以找一个高频但低风险的小场景先落地，让用户感受到${focus}被减轻，再逐步扩大到更高客单或更强授权。` },
    { angle: '设计点', text: '界面上不要只展示“AI建议”。更有启发的设计是同时展示：它用了哪些证据、排除了哪些选项、还缺哪条信息、用户可以改哪里。' },
    { angle: '方法论', text: '把这个观点拆成四层验证：入口是否自然、信息是否足够、用户是否愿意授权、结果失败时是否能兜底。任何一层断掉，AI体验都会退回普通搜索。' },
    { angle: '反向提醒', text: '不要把它包装成万能助手。越接近交易，AI越应该克制：能建议就不代办，能代填就不代付，需要确认时明确停下来。' },
    { angle: '指标启发', text: '可以少看“对话轮次”和“点击率”，多看约束补全率、候选采纳率、二次确认通过率、异常接管率和用户是否愿意下次继续授权。' },
    { angle: '下一步', text: '把原观点变成一句实验题：在一个具体品类/场景里，AI是否能让用户少一次比较、少一次人工核对，且不增加误买和售后风险。' }
  ];
  if (isMerchant) echoes.splice(3, 0, { angle: '供给侧', text: 'C端导购体验的上限可能在B端：商品卖点、适用人群、禁忌、库存和履约承诺如果不可读，AI只能生成漂亮但不可靠的话术。' });
  if (isMemory) echoes.splice(3, 0, { angle: '记忆设计', text: '记忆应该是一张“我的购买规则”，而不是后台画像。用户能看见、能修改、能暂停，才会愿意把长期偏好交给AI。' });
  if (isVisual) echoes.splice(3, 0, { angle: '创新点', text: '视觉能力的价值不是生成更好看的图，而是把“不适合我”的风险提前暴露：尺码冲突、风格不搭、场景不符都应该进入推荐理由。' });
  return { understanding, nextInsights, echoes: echoes.slice(0, 10) };
}

async function callModel(text, context) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey || /[^\x20-\x7E]/.test(apiKey)) return null;
  const response = await fetch(`${DEFAULT_BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model: DEFAULT_MODEL,
      messages: [
        { role: 'system', content: systemPrompt() },
        { role: 'user', content: userPrompt(text, context) }
      ],
      temperature: 0.72,
      response_format: { type: 'json_object' }
    })
  });
  if (!response.ok) throw new Error(`Model request failed: ${response.status}`);
  const analysis = normalizeEchoResponse(await response.json(), text);
  return analysis.echoes.length ? analysis : null;
}

async function callFreeModel(text, context) {
  const response = await fetch(FREE_ECHO_ENDPOINT, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model: FREE_ECHO_MODEL,
      messages: [
        { role: 'system', content: systemPrompt() },
        { role: 'user', content: userPrompt(text, context) }
      ],
      temperature: 0.72
    })
  });
  if (!response.ok) throw new Error(`Free model request failed: ${response.status}`);
  const analysis = normalizeEchoResponse(await response.json(), text);
  return analysis.echoes.length ? analysis : null;
}

async function handler(req, res) {
  if (req.method === 'OPTIONS') return json(res, 200, {});
  if (req.method && req.method !== 'POST') return json(res, 405, { error: 'Method not allowed' });
  const { text, context } = parseBody(req);
  const trimmed = String(text || '').trim();
  if (!trimmed) return json(res, 400, { error: 'Missing text' });
  try {
    const analysis = await callModel(trimmed, context);
    if (analysis) return json(res, 200, { ...analysis, mode: 'ai', model: DEFAULT_MODEL });
  } catch (error) {
    console.warn(error);
  }
  try {
    const analysis = await callFreeModel(trimmed, context);
    if (analysis) return json(res, 200, { ...analysis, mode: 'free-ai', model: 'gpt-oss-20b' });
  } catch (error) {
    console.warn(error);
  }
  return json(res, 200, { ...localEchoAnalysis(trimmed), mode: 'local' });
}

module.exports = handler;
