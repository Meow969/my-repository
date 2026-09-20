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

function fetchWithTimeout(resource, options = {}, timeoutMs = 15000) {
  if (typeof AbortController === 'undefined') return fetch(resource, options);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  return fetch(resource, { ...options, signal: controller.signal }).finally(() => clearTimeout(timer));
}

function systemPrompt() {
  return `你是一个产品思考伙伴，不是通用聊天助手，也不是固定的AI导购模板。用户会输入一句观点，你必须只围绕这句话做理解、回应和延展。
硬性要求：
1. 用户原句是最高优先级；不要把主题强行改写成AI购物、AI导购、信任、交易闭环，除非用户原句真的提到这些。
2. understanding：用1-2句话说明你理解到的真实问题、隐含假设或用户需求；必须点名用户输入里的具体对象/场景/关键词。
3. nextInsights：输出2-4条下一步洞察，每条都要从用户原句继续往下推，能转成产品判断、设计动作或验证问题。
4. echoes：输出10条以内，建议6-8条；每条是高质量回声呼应，可以是关键词、关键句或短观点。
5. 每条都必须明显回应用户原句，不要泛泛谈AI、导购、增长、体验、信任。
6. 避免空话、套话、重复句式；不要说“值得关注”“持续观察”“可以进一步探索”。
7. 输出中至少自然出现2个用户关键词；如果用户原句很短，至少复用1个关键词。
8. 只输出JSON，格式：{"understanding":"...","nextInsights":["..."],"echoes":[{"angle":"用户需求","text":"..."}]}`;
}

function userPrompt(text) {
  const keywords = extractEchoKeywords(text).join('、') || '无明显关键词';
  return `用户原句：${text}\n\n用户关键词：${keywords}\n\n请严格围绕用户原句生成：1）你对这句话的理解；2）下一步洞察；3）10个以内回声。每一部分都要能让用户看出你确实读懂了原句，不要引入和原句无关的主题。`;
}

function unique(items) {
  return [...new Set(items)].filter(Boolean);
}

function extractEchoKeywords(text = '') {
  const raw = String(text || '');
  const lower = raw.toLowerCase();
  const stopwords = new Set(['这个', '那个', '就是', '应该', '需要', '可以', '不是', '因为', '所以', '如果', '但是', '一个', '一种', '进行', '通过', '对于', '我们', '你们', '他们', '用户', '产品', '没有', '什么', '怎么', '时候', '东西', '整体', '看着', '觉得', '认为']);
  const knownTerms = ['答非所问', '没关系', '不相关', '跑偏', '很傻', '模板', '套话', '雷同', '重复', '小红书', '美团', '淘宝', '京东', 'Instacart', 'Amazon', 'OpenAI', '回声', '输入', '回应', '模型', '提示词', '页面', 'tab', '历史', '保存', '灵感', '资讯', '卡片', '来源', '搜索', '推荐', '决策', '导购', '购物', '交易', '信任'];
  const words = [];
  knownTerms.forEach(term => {
    const hit = /[A-Za-z]/.test(term) ? lower.includes(term.toLowerCase()) : raw.includes(term);
    if (hit) words.push(term);
  });
  for (const match of raw.matchAll(/[A-Za-z][A-Za-z-]{2,}/g)) {
    const word = match[0].trim();
    if (!stopwords.has(word) && word.length >= 2) words.push(word);
  }
  const chineseChunks = raw.match(/[\u4e00-\u9fa5]{2,}/g) || [];
  chineseChunks.forEach(chunk => {
    chunk.split(/(?:不是|应该|需要|可以|因为|所以|但是|然后|如果|对于|通过|进行|整体|还是|看着|觉得|认为|一个|一种|一些|很多|有点|没有|是否|是不是|什么|怎么|如何|为什么|以及|或者|并且|支持|里面|里的|下面|上面|这个|那个|东西|跟|和|与|在|里|上|下|对|给|把|被|从|到|让|会|能|要|很|的|了|是|都|还|也|只|更|再)/g)
      .map(part => part.trim())
      .filter(part => part.length >= 2 && part.length <= 12 && !stopwords.has(part))
      .forEach(part => words.push(part));
  });
  return unique(words).slice(0, 10);
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
  if (!echoes.length) return { understanding: '', nextInsights: [], echoes: [] };
  const fallback = localEchoAnalysis(originalText);
  const analysis = {
    understanding: understanding || fallback.understanding,
    nextInsights: nextInsights.length ? nextInsights : fallback.nextInsights,
    echoes: echoes.length ? echoes : fallback.echoes
  };
  return isEchoGrounded(analysis, originalText) ? analysis : { understanding: '', nextInsights: [], echoes: [] };
}

function echoAnalysisText(analysis) {
  return [
    analysis.understanding || '',
    ...(analysis.nextInsights || []),
    ...(analysis.echoes || []).flatMap(item => [item.angle || '', item.text || ''])
  ].join(' ');
}

function isEchoGrounded(analysis, originalText = '') {
  const keywords = extractEchoKeywords(originalText);
  if (!keywords.length) return true;
  const body = echoAnalysisText(analysis).toLowerCase();
  const hits = keywords.filter(keyword => body.includes(keyword.toLowerCase())).length;
  return hits >= Math.min(2, keywords.length);
}

function echoQuote(text, max = 58) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  return clean.length > max ? `${clean.slice(0, max)}…` : clean;
}

function echoFocus(text) {
  const keywords = extractEchoKeywords(text);
  return {
    keywords,
    primary: keywords[0] || '这句话',
    subject: keywords.slice(0, 3).join(' / ') || '这句话'
  };
}

function localEchoAnalysis(text) {
  const quoted = echoQuote(text);
  const { keywords, primary, subject } = echoFocus(text);
  const keywordText = keywords.length ? keywords.slice(0, 4).join('、') : quoted;
  const isQualityComplaint = /答非所问|无关|没关系|跑偏|很傻|傻|模板|套话|空泛|不符合|不满意|雷同|重复/.test(text);
  const isBuildRequest = /页面|tab|输入框|保存|历史|发送|生成|接入|调用|能力|体验|流程|功能|改|做|支持/.test(text);
  const isSearchDecision = /搜索|推荐|内容|种草|决策|比较|筛选|结果/.test(text);
  let understanding;
  let nextInsights;
  let echoes;
  if (isQualityComplaint) {
    understanding = `我理解你说的「${quoted}」是在指出：回声没有真正咬住“${subject}”，而是输出了一段可套到任何场景的内容，所以显得答非所问。`;
    nextInsights = [
      `先把“相关性”做成硬标准：结果里必须自然回应「${keywordText}」，否则直接丢弃，不让不相关内容进入历史。`,
      isBuildRequest
        ? '把这个需求拆成体验闭环：输入前给出预期，生成时围绕原句，生成后允许保存、复盘和继续追问。'
        : '把这句话转成一个验证问题：谁在什么场景下遇到什么阻力，什么产品动作能让这个阻力变小。',
      `输出结构要先说明“我听懂了什么”，再给洞察；如果第一段都没有点名「${primary}」，后面的启发再多也不可信。`
    ];
    echoes = [
      { angle: '原句锚点', text: `「${quoted}」的重点应该先被保留下来：回声必须围绕“${subject}”继续思考，而不是换成系统预设主题。` },
      { angle: '用户需求', text: `这句话背后的需求是“被准确理解”：用户不是要更多文字，而是要看到输入里的「${primary}」被接住、被拆解、被推进。` },
      { angle: '产品价值', text: '回声的价值可以定义为“把一句话变成下一步判断”：补出隐含假设、可能机会、风险边界和一个能马上验证的问题。' },
      { angle: '设计点', text: `结果区可以固定展示“抓住的关键词：${keywordText}”，让用户一眼知道回应为什么来自自己的输入。` },
      { angle: '机会点', text: `把「${primary}」做成可编辑锚点：用户可以删掉、补充或强调关键词，下一轮回声就围绕新的锚点继续深化。` },
      { angle: '质量门槛', text: `如果一条回声没有回应「${quoted}」里的对象、矛盾或情绪，即使文字流畅，也应该判定为失败输出。` },
      { angle: '验证问题', text: '可以让用户轻点“相关/跑偏”，用这个反馈持续调优：到底是关键词没抓住、场景误判，还是洞察太泛。' },
      { angle: '下一步', text: '下一版优先做两件事：强制引用原句关键词；对不相关模型结果自动丢弃，改用更贴近原句的回声。' }
    ];
  } else if (isSearchDecision) {
    understanding = `我理解你说的「${quoted}」是在指出“${subject}”之间的错位：内容推荐更擅长激发兴趣，但当用户要完成决策时，需要的是可比较、可解释、可收敛的判断支持。`;
    nextInsights = [
      '先区分搜索意图：用户是在随便逛、找灵感、做比较，还是已经接近下结论；不同意图不该共用一套结果页。',
      `围绕「${primary}」设计“决策视图”：把差异、适合谁、不适合谁、证据和待确认项放到同一屏。`,
      '验证时不要只看浏览深度，也要看用户是否减少二次搜索、减少收藏后不行动、减少跳到外部平台找答案。'
    ];
    echoes = [
      { angle: '原句张力', text: `「${quoted}」里的矛盾是：推荐让用户看得更多，但决策需要用户更快收敛。` },
      { angle: '用户需求', text: `当用户在「${primary}」里带着明确问题进入时，他要的不是内容流，而是能帮他判断“选哪个、为什么、有什么坑”的结构化答案。` },
      { angle: '产品价值', text: '搜索如果只优化停留和点击，会天然偏向内容消费；如果要帮决策，就要优化“少搜一次、少比一次、敢做选择”。' },
      { angle: '机会点', text: '可以在结果页增加“结论层”：先给少量候选，再解释排序依据、差异点和排除理由，让推荐服务于判断。' },
      { angle: '设计点', text: '把笔记、评价、达人内容拆成证据卡，而不是瀑布流；每张证据卡回答一个决策问题：适合谁、不适合谁、凭什么。' },
      { angle: '方法论', text: '把搜索结果分成探索型和决策型两套指标：前者看发现效率，后者看比较完成率、采纳率和反悔率。' },
      { angle: '反向风险', text: '如果小红书继续用内容推荐逻辑承接强决策意图，用户会在平台内种草、在平台外完成判断和交易。' },
      { angle: '下一步', text: `可以找一个高频决策场景验证：用户搜索「${primary}」后，是否更快得到可执行结论，而不是继续刷内容。` }
    ];
  } else {
    understanding = `我理解你说的「${quoted}」不是要泛泛扩写，而是希望围绕“${subject}”拆出背后的需求、判断标准和下一步可验证动作。`;
    nextInsights = [
      `先把这句话落到具体对象：谁会在什么场景里关心「${primary}」，他现在被什么卡住。`,
      `把“${subject}”转成产品假设：如果我们改变某个入口、规则或反馈，用户行为会不会更清晰地往前走。`,
      '验证时看真实行为变化，而不是只看用户口头认可：是否少一步犹豫、少一次返工、少一次解释成本。'
    ];
    echoes = [
      { angle: '原句锚点', text: `「${quoted}」可以先被当作一个未完成的产品假设，而不是一句结论。` },
      { angle: '用户需求', text: `围绕「${primary}」继续追问：用户真正缺的是信息、判断、信心、操作路径，还是一个更低成本的替代方案。` },
      { angle: '产品价值', text: `如果“${subject}”成立，产品要提供的不是更多内容，而是让用户更快形成判断、更少反复确认。` },
      { angle: '机会点', text: '可以把这句话拆成三个入口：用户主动表达时怎么接住，系统识别到时怎么提示，失败时怎么让用户修正。' },
      { angle: '设计点', text: '界面上可以明确展示“依据、取舍、下一步”，让洞察从一句建议变成用户能继续行动的线索。' },
      { angle: '风险', text: `不要把「${primary}」扩成过大的命题；越大的概念越难验证，越容易生成漂亮但无用的结论。` },
      { angle: '验证问题', text: `最小实验可以问：当我们围绕「${keywordText}」提供一个更明确的下一步时，用户是否更愿意继续使用。` }
    ];
  }
  return { understanding, nextInsights, echoes: echoes.slice(0, 10) };
}

async function callModel(text) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey || /[^\x20-\x7E]/.test(apiKey)) return null;
  const response = await fetchWithTimeout(`${DEFAULT_BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model: DEFAULT_MODEL,
      messages: [
        { role: 'system', content: systemPrompt() },
        { role: 'user', content: userPrompt(text) }
      ],
      temperature: 0.45,
      response_format: { type: 'json_object' }
    })
  }, 20000);
  if (!response.ok) throw new Error(`Model request failed: ${response.status}`);
  const analysis = normalizeEchoResponse(await response.json(), text);
  return analysis.echoes.length ? analysis : null;
}

async function callFreeModel(text) {
  const response = await fetchWithTimeout(FREE_ECHO_ENDPOINT, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      model: FREE_ECHO_MODEL,
      messages: [
        { role: 'system', content: systemPrompt() },
        { role: 'user', content: userPrompt(text) }
      ],
      temperature: 0.45,
      response_format: { type: 'json_object' }
    })
  }, 12000);
  if (!response.ok) throw new Error(`Free model request failed: ${response.status}`);
  const analysis = normalizeEchoResponse(await response.json(), text);
  return analysis.echoes.length ? analysis : null;
}

async function handler(req, res) {
  if (req.method === 'OPTIONS') return json(res, 200, {});
  if (req.method && req.method !== 'POST') return json(res, 405, { error: 'Method not allowed' });
  const { text } = parseBody(req);
  const trimmed = String(text || '').trim();
  if (!trimmed) return json(res, 400, { error: 'Missing text' });
  try {
    const analysis = await callModel(trimmed);
    if (analysis) return json(res, 200, { ...analysis, mode: 'ai', model: DEFAULT_MODEL });
  } catch (error) {
    console.warn('model echo failed', error?.message || error);
  }
  try {
    const analysis = await callFreeModel(trimmed);
    if (analysis) return json(res, 200, { ...analysis, mode: 'free-ai', model: 'gpt-oss-20b' });
  } catch (error) {
    console.warn('free echo failed', error?.message || error);
  }
  return json(res, 200, { ...localEchoAnalysis(trimmed), mode: 'local' });
}

module.exports = handler;
