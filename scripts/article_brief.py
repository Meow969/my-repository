"""Readable, evidence-linked article cards. Facts remain separate from product hypotheses."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from difflib import SequenceMatcher

VERSION='article-brief-v1'
ENTITIES=[
 ('Amazon',r'\bamazon\b|亚马逊'),('Rufus',r'\brufus\b'),('Meta',r'\bmeta\b'),('Muse',r'\bmuse\b'),
 ('Google',r'\bgoogle\b|谷歌'),('Gemini',r'\bgemini\b'),('OpenAI',r'\bopenai\b'),('ChatGPT',r'\bchatgpt\b'),
 ('Walmart',r'\bwalmart\b|沃尔玛'),('Sparky',r'\bsparky\b'),('Stripe',r'\bstripe\b'),
 ('Constructor',r'\bconstructor\b'),('Shopify',r'\bshopify\b'),('Instacart',r'\binstacart\b'),
 ('Perplexity',r'\bperplexity\b'),('TikTok',r'\btiktok\b'),('Gap',r'\bGap(?: Inc\.?| expands| rolls| partners| launches| bets| joins| products|[’\x27]s)\b'),('Alta Daily',r'alta daily'),
 ('Ask TRR',r'ask trr'),('The RealReal',r'the realreal'),('Visa',r'\bvisa\b'),('Mastercard',r'\bmastercard\b'),
 ('Authvia',r'authvia'),('Skyfire',r'skyfire'),('Crossmint',r'crossmint'),('Asda',r'\basda\b'),('Rokt',r'\brokt\b'),
 ('Newegg',r'newegg'),('Myprotein',r'myprotein'),('PayPal',r'paypal'),('Zalando',r'zalando'),('Pinterest',r'pinterest'),
 ('淘宝',r'淘宝|taobao'),('天猫',r'天猫|tmall'),('京东',r'京东|京言|\bjd\.com\b'),('美团',r'美团|问小团|小美'),
 ('豆包',r'豆包|doubao'),('抖音',r'抖音'),('小红书',r'小红书'),('得物',r'得物'),('Shopee',r'shopee|虾皮'),
 ('Lazada',r'lazada'),('eBay',r'\bebay\b'),('阿里巴巴',r'阿里巴巴|alibaba'),
 ('BCG',r'\bbcg\b|boston consulting'),('Bain',r'\bbain\b|贝恩'),('Deloitte',r'deloitte|德勤'),
 ('McKinsey',r'mckinsey|麦肯锡'),('Adobe',r'adobe'),('Salesforce',r'salesforce'),('Mars',r'\bmars\b'),
]

# Match only supplied source text; neither generated tags nor previous insights can trigger a theme.
PROFILES=[
 dict(id='access',pattern=r'block|restrict|ban(?:s|ned)?\b|shut out|封锁|屏蔽|限制访问|切断|禁止',keywords=['平台开放','跨平台购物'],
      thesis='先验证“买得到”，再追求“推荐得好”',
      insight='把商家允许的访问与交易范围作为候选筛选条件，而不是等用户选定商品后才发现无法执行。跨平台导购应区分可代购、仅可跳转和暂不可用三类路径。',
      thought='平台封锁不是模型理解力问题：平台要保留客户关系、支付与售后控制权，导购却希望降低跨平台摩擦。靠页面自动化绕开接口，会把功能可用性变成随时可能失效的依赖。',
      test='同一购买任务并行测试官方接入与跳转确认，记录可执行商品覆盖率、权限失败率、任务完成率；不要只比较推荐相关性。'),
 dict(id='identity',pattern=r'identity|KYA|who.s behind|身份|代理.*认证',keywords=['智能体身份','支付授权'],
      thesis='识别“谁在行动”，还要明确“能替谁做什么”',
      insight='导购从建议走向代办时，需要把代理身份、用户身份、允许的动作与授权期限拆开建模。识别到一个合法智能体，不代表它有权用当前用户的钱购买任何商品。',
      thought='身份验证解决主体是否真实，授权解决本次行为是否越界。若两者合并成一次登录，后续改价、换商家、替代商品可能扩大用户原本没有同意的权限。',
      test='在购买链路插入改价、换店和授权过期场景；检查是否重新确认，并记录越权拦截率、误拒率和恢复任务的成本。'),
 dict(id='authorization',pattern=r'permission|authoriz|intent.*payment|consent|patent|授权|同意|专利',keywords=['意图与授权','交易安全'],
      thesis='“我想买”不能直接等同于“替我付款”',
      insight='把需求表达、商品确认、支付授权作为三个不同状态。聊天上下文可辅助理解需求，但金额、收款方、数量和有效期应成为执行前可检查的结构化约束。',
      thought='减少确认步骤会改善效率，也会提高用户误授权的损失。真正值得优化的是“在风险不增加时减少确认”，而不是把对话中的倾向性表达当成付款指令。',
      test='对低风险复购与高客单首次购买采用不同确认强度，联合比较完成率、误购撤销率、超额支付拦截率和争议率。'),
 dict(id='ads',pattern=r'\brokt\b|sponsored|advertis|retail media|广告|赞助|竞价|relevant offers',keywords=['商业推荐','增量与信任'],
      thesis='推荐收益与用户决策收益，要分开计算',
      insight='把自然推荐与商业曝光显式区分，先满足用户约束，再判断赞助商品是否具备展示资格。结账环节的加购推荐不能挤占原任务或制造新的确认负担。',
      thought='曝光收入上涨可能来自流量、季节和广告库存变化，不一定说明导购让用户买得更合适。若只追广告收益，系统可能牺牲购物效率与推荐信任。',
      test='对同类订单保留不展示商业推荐的对照组，同时观察增量毛利、结账完成率、无关推荐反馈和后续退货，区分平台收入与用户受益。'),
 dict(id='returns',pattern=r'return rate|fewer returns|product returns|退货率|减少退货|退货成本',keywords=['购买匹配','退货成本'],
      thesis='把购后结果放回推荐质量的评价里',
      insight='导购的目标不应止于支付转化，还要减少因尺码、适配、功能误解造成的买错。推荐时展示不适用条件，比单纯增加“为什么值得买”更有助于降低后悔。',
      thought='退货下降也可能来自品类结构、优惠和物流政策；使用助手的用户还可能本身更明确。未经同品类、同意图对照，不能把结果直接归因于AI。',
      test='对照有无适配核验，分别追踪支付率、30天退货率、退货原因及单位订单利润，避免把阻止购买误判为提升质量。'),
 dict(id='visual',pattern=r'try.on|virtual.*fit|styling|outfit|avatar|试穿|试衣|穿搭|数字衣橱',keywords=['视觉导购','适配判断'],
      thesis='从“生成一张图”推进到“解释为什么适合”',
      insight='把图像体验接到明确的决策问题：这件衣服如何搭配已有衣橱、尺码依据是什么、哪些场景不适合。图片可以触发兴趣，但商品事实和适配约束决定是否值得购买。',
      thought='视觉效果越逼真，用户越可能把展示效果误认为实物保证。应分开标明风格模拟与尺寸判断的边界，而不是把生成质量当成退货风险降低的证据。',
      test='比较单纯试穿图与“图＋搭配依据＋不适配提醒”，分尺码、体型和品类看采纳率、支付转化及适配相关退货。'),
 dict(id='catalog',pattern=r'merchant feed|product feed|catalog|product data|inventory|商品数据|商品库|商品目录|库存',keywords=['商品事实','实时数据'],
      thesis='商品可被AI理解，比多一个聊天入口更基础',
      insight='为导购建立可核验的商品事实层：价格、库存、规格、配送与退换政策各自带来源和有效期。模型负责理解与比较，动态事实则应由可信系统提供。',
      thought='商家数据更结构化并不意味着更中立。资料缺失的商品可能被系统性排除，商家自述也可能替代第三方评价；需要区分“能被推荐”与“值得被推荐”。',
      test='选库存变动频繁的品类，对照基础商品页和结构化数据，跟踪事实错误率、过期价格率、商家覆盖及有效订单，而非仅看引用量。'),
 dict(id='protocol',pattern=r'protocol|\bACP\b|\bAP2\b|x402|toolkit|single API|标准|协议|工具包',keywords=['商家接入','交易协议'],
      thesis='协议减少接入成本，不自动解决交易责任',
      insight='把接入拆成商品发现、报价、授权、订单和售后五个能力模块。优先接入覆盖当前任务的最小集合，保持替换支付和商家服务的能力，避免协议绑定整个产品架构。',
      thought='接口统一能缩短开发周期，但失败重试、重复扣款、跨平台退货仍需明确责任。可调用的接口数量不是用户可完成的购物任务数量。',
      test='用一条真实购物任务验收全链路，覆盖报价过期、缺货、支付失败与撤单；记录端到端完成率、重复执行风险和接入维护成本。'),
 dict(id='checkout',pattern=r'checkout|purchase.*chat|buy direct|结账|下单|购物车|支付',keywords=['交易闭环','任务连续性'],
      thesis='缩短跳转路径，还要保留可确认、可恢复的交易状态',
      insight='把需求、候选与交易状态串成连续任务，减少用户在对话、商品页和结账页间重复输入。结账前仍要明确最终价格、商品、地址和履约承诺，而不是用“无缝”隐藏确认。',
      thought='单界面更顺畅，不代表所有品类都适合一步成交。首次购买、高客单或兼容性复杂的商品需要可回看证据；支付后还能查单、修改与退款，才形成真正闭环。',
      test='对照现有跳转流程，测任务完成时间、结账成功率和中途信息丢失；把误购、撤销与售后自助完成率一起作为上线门槛。'),
 dict(id='memory',pattern=r'personaliz|preference|memory|记忆|偏好|个性化|复购',keywords=['偏好记忆','可控推荐'],
      thesis='区分长期偏好与本次任务的临时条件',
      insight='把预算、用途、收货时效等临时约束与长期偏好分别存储。让用户知道推荐使用了哪些记忆，并能在本次任务里覆写，而不是把历史行为永久固化成画像。',
      thought='个性化越强，错误记忆的影响也越大。更高的点击率可能来自缩窄候选而非更懂用户，需要保留探索机会，避免赠礼和代买污染本人偏好。',
      test='比较无记忆、不可见记忆与可编辑记忆，观察澄清轮次、推荐采纳率、纠错成本和跨品类复用，单独检查送礼任务。'),
 dict(id='local',pattern=r'grocery|instacart|local commerce|即时|外卖|买菜|配送|问小团|小美',keywords=['即时需求','履约约束'],
      thesis='先限定此时此地可履约的候选，再优化推荐',
      insight='先确定位置、送达时间、预算和替代接受范围，再生成可购买方案。即时购物的正确答案同时依赖实时库存与配送能力，不能只根据文本匹配给出理想商品。',
      thought='低客单高频场景容易验证效率，却不能直接迁移到所有购物任务。缺货替代可能满足商品相似性，但不满足用户的过敏、品牌或时间约束。',
      test='选择常购清单试点，高峰与非高峰分开测完成时间、缺货替代接受率、履约达成率和取消率，再决定是否扩大自动执行。'),
 dict(id='discovery',pattern=r'search|discover|assistant|recommend|agent|购物|搜索|导购|推荐|助手',keywords=['需求澄清','商品发现'],
      thesis='把模糊需求变成可修改的候选条件',
      insight='导购应先澄清预算、用途与必须满足的条件，再给少量可比较的候选。每个推荐都要解释满足了哪些条件、牺牲了什么，并允许用户修改而不必重新开始对话。',
      thought='更快给出答案也可能过早收敛，把探索性购物变成系统替用户决定。明确购买任务需要效率，逛购任务需要发现空间，两类任务不宜共用一个转化指标。',
      test='区分明确购买与探索任务，对照传统搜索，分别看候选修改次数、决策时间、任务成功率和商品覆盖，避免只追聊天轮次。'),
]
RESEARCH_PATTERN=r'\bsurvey\b|\bstudy\b|\bresearch\b|\bforecast\b|\breport\b|\bpredict|\b203\d\b|调查|调研|研究报告|预测|\d+%'


def source_text(a):
    return a.get('title','')+' '+' '.join(a.get('corePoint',[]))


def input_hash(a):
    value={k:a.get(k) for k in ('title','titleZh','corePoint','summaryZh','evidenceLevel','sourceCaveatsZh','contentKinds')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def clean_sentence(text):
    text=re.sub(r'^[•·\-\d]+[.、\s]+','',str(text).strip())
    text=re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])','',text)
    text=text.replace(' ,','，').replace(', ','，').replace(' .','。')
    text=re.sub(r'([，。])\s+(?=[\u4e00-\u9fff])',r'\1',text)
    return text if re.search(r'[。！？…]$|\.{3}$',text) else text.rstrip('.,，;；')+'。'


def case_profile(a):
    # Specific headline signals win before generic assistant/search references.
    for text in (a['title'],' '.join(a.get('corePoint',[]))):
        for profile in PROFILES:
            if re.search(profile['pattern'],text,re.I):return profile
    return PROFILES[-1]


def build_brief(a):
    profile=case_profile(a);raw=source_text(a)
    entities=[name for _,name in sorted((re.search(pattern,a['title'],re.I).start(),name) for name,pattern in ENTITIES if re.search(pattern,a['title'],re.I))]
    # Article-specific keywords must be attributable to the source, never only old tags.
    extra=[name for name,pattern in ENTITIES if name not in entities and re.search(pattern,raw,re.I)]
    keywords=list(dict.fromkeys(entities[:2]+profile['keywords']+extra[:1]))[:5]
    facts=[]
    for value in a.get('summaryZh',[])[:3]:
        point=clean_sentence(value)
        if not any(SequenceMatcher(None,point,old).ratio()>.78 for old in facts):facts.append(point)
    if a.get('evidenceLevel')=='headline':
        facts=['目前仅保存标题线索：'+a['titleZh'].rstrip('。')+'。正文尚未核实，暂不能确认产品细节或实际效果。']
    elif a.get('evidenceLevel')=='abstract':
        facts[0]='据目前可获取的摘要，'+facts[0].lstrip('据')
    is_research=bool(re.search(RESEARCH_PATTERN,a['title'],re.I)) or '研究报告' in a.get('contentKinds',[])
    is_prediction=bool(re.search(r'forecast|predict|203\d|预测|预计',a['title'],re.I))
    label='趋势预测' if is_prediction else '研究发现' if is_research else '产品动作' if re.search(r'launch|roll|introduc|expand|add|unveil|上线|推出|发布|升级',a['title'],re.I) else '核心信息'
    if is_prediction:
        evidence_limit='这里的规模与时点属于预测，不是已实现的采用或成交；应核对假设、情景范围及替代路径。'
    elif is_research:
        evidence_limit='本条属于研究或调查线索；需核对样本、时间窗和指标定义，使用意愿、实际采用与增量成交不能互相替代。'
    elif a.get('sourceKind') in ('official','press_release'):
        evidence_limit='发布方材料可说明能力主张，但没有对照数据时，不能把产品上线直接视为转化或留存提升。'
    else:
        evidence_limit='这条报道提供观察线索，具体开放范围与效果仍应以可验证的产品路径及数据为准。'
    actor=' / '.join(entities[:2])
    heading=(actor+'：' if actor else '')+profile['thesis']
    thought=profile['thought']
    if a.get('evidenceLevel')!='fulltext':thought='当前只有摘要或标题证据，以下是待验证的产品问题，不是对此产品效果的判断。'+thought
    brief=dict(version=VERSION,inputHash=input_hash(a),keywords=keywords,summary=facts,summaryLabel=label,
        research=dict(topic=profile['id'],heading=heading,insight=profile['insight'],deepThought=thought,
                      evidenceLimit=evidence_limit,validation=profile['test'],basisArticleId=a['id'],method='规则辅助研究假设'))
    overrides_path=Path(__file__).with_name('editorial_briefs.json')
    overrides=json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    editorial=overrides.get(a['id'])
    if editorial and editorial.get('sourceHash')==hashlib.sha256(json.dumps(a.get('corePoint',[]),ensure_ascii=False).encode()).hexdigest():
        if editorial.get('summary'):brief['summary']=editorial['summary']
        brief['research'].update(editorial.get('research',{}));brief['research']['method']='基于原文线索的编辑研究假设'
    return brief


def refresh_briefs(articles):
    for article in articles:article['brief']=build_brief(article)
    return articles
