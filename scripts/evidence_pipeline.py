#!/usr/bin/env python3
"""Evidence-first daily radar. No model/key required; never presents a hypothesis as fact."""
from __future__ import annotations
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import re
import tempfile
import os
import urllib.parse
import xml.etree.ElementTree as ET
import requests
import feedparser
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
TZ = dt.timezone(dt.timedelta(hours=8))
VERSION = 'evidence-v1'
SOURCES = json.loads((Path(__file__).with_name('radar_sources.json')).read_text())
KINDS = {'official':'官方一手', 'research':'研究资料', 'industry':'行业媒体', 'media':'综合媒体', 'analysis':'观点分析', 'press_release':'新闻通稿', 'unknown':'待核验来源'}
QUERIES = [(x['region'],x['query']) for x in json.loads(Path(__file__).with_name('radar_queries.json').read_text())]

AI = r'(?<![a-z])ai(?![a-z])|artificial intelligence|agentic|chatgpt|rufus|sparky|perplexity|智能体|人工智能|大模型|千问|豆包|京言|小美|问小团'
COMMERCE = r'shopping|commerce|retail|merchant|checkout|payment|try.on|product discovery|购物|电商|零售|导购|商家|消费者购物|试穿|试衣|外卖|买菜|支付|商品|种草'
NOISE = r'cookie|subscribe|sign up|privacy policy|all rights reserved|广告合作|下载.*app|免责声明|版权声明|登录后|点击关注|Cohead of|GTM Head|Head of AMER|Watch more:|share this article|Wise Software Glitch Leads|Coinbase Looks to Cash|Let us know what you think|[\w.+-]+@[\w.-]+\.[a-z]{2,}|For more information|Follow us|Read more:|Learn more:|Scroll down|Keep scrolling|Shop now|Streaming and digital subscriptions|Telecommunications Leader'

# Each lens has a distinct causal mechanism, counter-case and measurable experiment.
LENSES = [
 {'id':'payments','title':'代付之前，先把授权做成产品','terms':r'checkout|payment|支付|结账|授权|下单|购物车',
  'mechanism':'推荐正确不等于执行正确：金额、商家和时间约束必须在执行层再次校验。少一次确认可能提高完成率，也可能放大误购和争议成本。',
  'boundary':'宣布接入支付或支持下单，只能证明能力存在；没有完成率、退款率和授权撤回数据，不能证明用户愿意放权。',
  'experiment':'在同一品类比较“生成购物车后确认”与“限额授权代下单”；同时记录任务完成率、改价拦截率、撤销率和退款率。只有效率提升且损失不增加才扩大授权。',
  'keywords':['授权边界','交易确认','误购成本']},
 {'id':'visual','title':'试穿的目标不是好看，而是少买错','terms':r'try.on|virtual.*fit|试穿|试衣|试鞋|尺码',
  'mechanism':'生成图降低风格想象成本，但未必解决尺码与材质判断；点击或停留上涨可能只是新奇效应，而非更好的购买决策。',
  'boundary':'效果演示不是适配证据；缺少真实尺码、不同体型覆盖及退货原因数据时，不应承诺“合身”。',
  'experiment':'对照展示“仅生成图”与“生成图＋尺码依据＋不适配提示”；跟踪加购到支付转化、尺码相关退货率，并分体型和品类复盘。',
  'keywords':['视觉导购','适配证据','退货率']},
 {'id':'merchant','title':'商家接入的瓶颈从文案转向商品事实','terms':r'merchant|seller|feed|catalog|商家|卖家|商品库|经营|协议|protocol|\bmcp\b|\bucp\b',
  'mechanism':'智能体能否推荐商品，受价格、库存、规格、履约信息的可读取性和新鲜度限制。新增协议入口不会自动补齐数据，也不意味着商家获得增量。',
  'boundary':'发布接口、接入商家数和合作名单都不是成交效果；还需要区分自然流量迁移与真正新增订单。',
  'experiment':'选一个库存变化快的品类，对比基础商品页与结构化实时信息；记录引用准确率、库存失配率、有效导流和增量订单，单独标记赞助推荐。',
  'keywords':['商品事实层','库存核验','增量归因']},
 {'id':'memory','title':'记住偏好，也要允许用户改变主意','terms':r'memory|personaliz|preference|记忆|偏好|个性化|复购',
  'mechanism':'长期偏好可以减少重复澄清，但把一次性任务当作稳定偏好会让推荐越用越窄；记忆价值取决于时效、可纠正性和跨场景边界。',
  'boundary':'个性化功能发布不等于长期留存提升；必须排除价格优惠与用户自选择影响，检查错误记忆的修正成本。',
  'experiment':'对照无记忆与可编辑偏好卡；统计澄清轮次、推荐采纳率、记忆纠错率和四周复购，临时送礼需求默认不沉淀为长期个人偏好。',
  'keywords':['偏好记忆','纠错成本','长期留存']},
 {'id':'trust','title':'把“推荐理由”升级成可检查的证据','terms':r'trust|review|fraud|privacy|bias|信任|评价|隐私|欺诈|风险|幻觉|监管',
  'mechanism':'对话语气越确定，用户越可能忽略证据缺口。来源、适用条件与不推荐理由可降低误信，但增加信息量也可能提高决策负担。',
  'boundary':'满意度和使用意愿不代表真实购买表现；需要观察错误推荐、广告识别与投诉，不能只看问卷或单次演示。',
  'experiment':'比较普通推荐与“理由＋证据日期＋风险提示”；同时测决策耗时、事实核验正确率、广告识别率和购后后悔率，避免只优化点击。',
  'keywords':['证据引用','推荐可信度','反向指标']},
 {'id':'local','title':'即时购物要先满足可履约，再讨论聪明','terms':r'grocery|delivery|instacart|local commerce|即时|外卖|买菜|小美|问小团|配送',
  'mechanism':'即时场景的可选集合同时受位置、时间、库存和配送能力约束；语义理解提升如果不能同步到履约系统，会更快地产生不可执行答案。',
  'boundary':'演示一次点单无法说明高峰期可用性；商家覆盖、缺货替代与配送延迟都可能抵消交互效率收益。',
  'experiment':'从常购低风险任务试点；同时跟踪从意图到有效订单的耗时、缺货替代接受率、履约达成率及取消率，高峰和非高峰分开分析。',
  'keywords':['履约确定性','缺货替代','高频任务']},
 {'id':'discovery','title':'入口变化之后，谁拥有最终候选集？','terms':r'search|discovery|assistant|搜索|导购|助手|推荐|shopping|购物',
  'mechanism':'当用户先向助手表达需求，竞争从搜索排序前移到“哪些商品进入候选集”。但更短的答案也可能隐藏取舍，减少用户探索和商家的可见性。',
  'boundary':'上线入口或公布使用人数并不证明决策质量提升；渗透率、重复使用、候选覆盖和增量转化需要分别验证。',
  'experiment':'对照传统搜索与可编辑约束的对话导购；测候选修改次数、决策耗时、任务成功率和品类覆盖，区分新客与老客、探索与明确购买任务。',
  'keywords':['候选集','需求澄清','入口迁移']},
]

def now(): return dt.datetime.now(TZ)
def load(name, default):
    path = DATA / name
    return json.loads(path.read_text()) if path.exists() else default

def write(name, value):
    DATA.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=DATA, delete=False) as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.write('\n'); tmp = f.name
    os.replace(tmp, DATA / name)

def text(value):
    import html
    value=str(value or '')
    clean=BeautifulSoup(value, 'html.parser').get_text(' ',strip=True) if '<' in value else html.unescape(value)
    return re.sub(r'\s+', ' ', clean).strip()

def date_value(value):
    """Invalid/missing dates stay unknown. Never turn old content into today's news."""
    if not value: return ''
    try:
        from email.utils import parsedate_to_datetime
        d = dt.datetime.fromisoformat(str(value).strip().replace('Z','+00:00')) if re.match(r'^\d{4}-\d{2}-\d{2}',str(value)) else parsedate_to_datetime(str(value))
        day = d.astimezone(TZ).date() if d.tzinfo else d.date()
        return day.isoformat() if dt.date(2000,1,1) <= day <= now().date() else ''
    except (ValueError, TypeError, OverflowError): return ''

def public_url(url):
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or '').lower()
        import ipaddress
        if p.scheme not in ('https','http') or not host or p.username or p.password or p.port not in (None,80,443): return ''
        if host == 'localhost' or host.endswith(('.local','.internal','.jd.com')) or '.' not in host: return ''
        try:
            if not ipaddress.ip_address(host).is_global: return ''
        except ValueError: pass
        query = [(k,v) for k,v in urllib.parse.parse_qsl(p.query) if not k.startswith('utm_') and k not in ('gclid','fbclid','spm')]
        return urllib.parse.urlunsplit((p.scheme,host,p.path or '/',urllib.parse.urlencode(query),''))
    except ValueError: return ''

def get(url):
    for _ in range(5):
        url = public_url(url)
        if not url: raise ValueError('非公开网页地址')
        r = requests.get(url, headers={'User-Agent':'Mozilla/5.0 (compatible; ShoppingRadar/2.0)'},timeout=(5,12),allow_redirects=False,stream=True)
        if r.is_redirect:
            url = urllib.parse.urljoin(url, r.headers['Location']); r.close(); continue
        r.raise_for_status()
        buf = bytearray()
        for chunk in r.iter_content(65536):
            buf.extend(chunk)
            if len(buf)>4_000_000: r.close(); raise ValueError('响应超过大小上限')
        r.close(); r._content=bytes(buf); r.encoding=r.apparent_encoding or 'utf-8'
        return r
    raise ValueError('重定向次数过多')

def related(title, excerpt=''):
    # Shopping must be central, not a footer mention or generic 'consumer AI'.
    if re.search(r'\bB2B\b|Senior Manager|Commerce Architect|(?<![-\w])stock(?![-\w])|stock trades|For Investing|summit review|外卖云监管|食安封签|SPAC Listing|stock market debut|retail bank|corporate treasury|transaction banks|digital currencies|landing page|digital marketing.*\bDMEAI\b|manage store portfolios|暑期实践|学子.*(?:获|奖)|大赛.*(?:获|奖)|校企合作|trade shows|media landscape|ARR|股价|美股|市值|shares (?:climb|rise|fall)|stock price|bullish analyst|融资|催收|座舱|OTA|Token|世界模型|new ecommerce tools|copywriter grades',title,re.I):return False
    if re.search(AI,title,re.I) and re.search(COMMERCE,title,re.I):return True
    if re.search(COMMERCE,title,re.I) and re.search(AI,excerpt[:1800],re.I):return True
    return bool(re.search(r'Rufus|Sparky|京言|AI购|小美|问小团',title,re.I))

def parse_feed(body, source):
    feed=feedparser.parse(body)
    if not feed.entries and not feed.version: raise ValueError('未返回 RSS/Atom')
    out=[]
    for e in feed.entries[:100]:
        title=text(e.get('title','')); url=public_url(e.get('link',''))
        date=date_value(e.get('published') or e.get('updated'))
        snippet=text(e.get('summary',''))[:2400]
        publisher=text(e.get('source',{}).get('title','')) if source['kind']=='discovery' else source['name']
        if publisher and source['kind']=='discovery': title=re.sub(r'\s+[-–—]\s+'+re.escape(publisher)+r'$','',title).strip()
        if title and url and date:
            out.append(dict(title=title,url=url,date=date,dateBasis='RSS/Atom 发布时间',snippet=snippet,source=publisher or source['name'],region=source['region'],sourceKind=source['kind']))
    return out

def sitemap_candidates(body, source, depth=0):
    root=ET.fromstring(body); out=[]
    if root.tag.endswith('sitemapindex'):
        # Do not recursively crawl a complete corporate site.
        locs=[n.text for n in root.findall('.//{*}loc') if n.text]
        locs=sorted(locs,key=lambda u:bool(re.search('news|press|article',u,re.I)),reverse=True)
        if depth<1:
            for url in locs[:2]:
                try: out+=sitemap_candidates(get(url).content,source,depth+1)
                except (requests.RequestException,ValueError,ET.ParseError): pass
        return out
    for node in root.findall('{*}url'):
        url=public_url(node.findtext('{*}loc',''))
        if url and re.search(source.get('match','.'),url,re.I):
            # Sitemap lastmod is NOT publication date. Verify the actual page later.
            out.append(dict(title=urllib.parse.unquote(url.split('/')[-1]).replace('-',' '),url=url,date='',dateBasis='等待原文日期',snippet='',source=source['name'],region=source['region'],sourceKind=source['kind'],sitemapModified=node.findtext('{*}lastmod','')))
    return sorted(out,key=lambda x:x.get('sitemapModified',''),reverse=True)[:35]

def fetch_source(source):
    h=dict(name=source['name'],url=source['url'],kind=source['kind'],region=source['region'],checkedAt=now().isoformat(timespec='seconds'))
    try:
        r=get(source['url'])
        items=sitemap_candidates(r.content,source) if source.get('format')=='sitemap' else parse_feed(r.content,source)
        h.update(status='ok',candidateCount=len(items),message='可连接；无新内容也属正常')
        return items,h
    except Exception as e:
        h.update(status='failed',candidateCount=0,message=f'{type(e).__name__}: {str(e)[:120]}')
        return [],h

def publisher_kind(url):
    host=(urllib.parse.urlsplit(url).hostname or '').removeprefix('www.')
    matches=[s for s in SOURCES if host==(urllib.parse.urlsplit(s['url']).hostname or '').removeprefix('www.')]
    if matches:return matches[0]['kind']
    if any(host==d or host.endswith('.'+d) for d in ['mckinsey.com','bcg.com','bain.com','deloitte.com','accenture.com','pwc.com','kpmg.com','capgemini.com','forrester.com','gartner.com','emarketer.com','iresearch.com.cn','iimedia.cn','questmobile.com.cn','cbndata.com']):return 'research'
    if any(host==d or host.endswith('.'+d) for d in ['shopify.com','stripe.com','visa.com','mastercard.com','paypal.com','alibabagroup.com','jdcorporateblog.com','meituan.com','instacart.com','perplexity.ai','newsroom.pinterest.com','ebayinc.com','etsy.com','zalando.com','adobe.com','salesforce.com','alibabacloud.com','lazada.com','shopee.com']):return 'official'
    if any(host==d or host.endswith('.'+d) for d in ['prnewswire.com','businesswire.com','globenewswire.com']):return 'press_release'
    if any(host==d or host.endswith('.'+d) for d in ['retail-systems.com','retailtouchpoints.com','chainstoreage.com','retailtechinnovationhub.com','retailtechnology.co.uk','cnbc.com','reuters.com','cbndata.com','cgtn.com','finextra.com','finovate.com','cgtmag.com','pymnts.com']):return 'industry'
    if host.endswith(('arxiv.org','stanford.edu','mit.edu')):return 'research'
    return 'unknown'

def title_key(s): return re.sub(r'[^\w\u4e00-\u9fff]','',s.lower())

def duplicate(a,b):
    if public_url(a.get('url','')).rstrip('/') == public_url(b.get('url','')).rstrip('/') and a.get('url'):return True
    left,right=urllib.parse.urlsplit(a.get('url','')),urllib.parse.urlsplit(b.get('url',''))
    if all((u.hostname or '').endswith('36kr.com') for u in (left,right)):
        ids=[re.search(r'/p/(\d+)',u.path) for u in (left,right)]
        if all(ids) and ids[0].group(1)==ids[1].group(1):return True
    x,y=title_key(a.get('title','')),title_key(b.get('title',''))
    if x and x==y:return True
    # No broad 'same platform + same day' or template-insight dedupe.
    if min(len(x),len(y))<=22 or 2*min(len(x),len(y))/(len(x)+len(y))<=.9:return False
    matcher=SequenceMatcher(None,x,y)
    return matcher.quick_ratio()>.9 and matcher.ratio()>.9

def extract_page(body, url):
    soup=BeautifulSoup(body,'html.parser')
    dates=[]
    for tag in soup.select('meta[property="article:published_time"], meta[name="date"], meta[name="pubdate"], meta[itemprop="datePublished"]'):
        dates.append(tag.get('content'))
    def visit(obj):
        if isinstance(obj,dict):
            if obj.get('datePublished'): dates.append(obj['datePublished'])
            for v in obj.values(): visit(v)
        elif isinstance(obj,list):
            for v in obj:visit(v)
    for script in soup.select('script[type="application/ld+json"]'):
        try:visit(json.loads(script.string or script.get_text()))
        except (ValueError,TypeError):pass
    published=next((v for v in map(date_value,dates) if v),'')
    if not published:
        match=re.search(r'/(20\d{2})[/-](\d{2})[/-](\d{2})(?:/|-)',url)
        if match:published=date_value('-'.join(match.groups()))
    desc=next((t.get('content','') for t in soup.select('meta[name="description"],meta[property="og:description"]') if t.get('content')),'')
    for t in soup.select('script,style,noscript,nav,header,footer,aside,form'):t.decompose()
    body_root=soup.find('article') or soup.find('main') or soup
    paras=[text(p.get_text(' ',strip=True)) for p in body_root.find_all('p')]
    paras=[p for p in paras if len(p)>=40 and not re.search(NOISE,p,re.I)]
    return dict(published=published,paragraphs=list(dict.fromkeys(paras))[:80],description=text(desc))

def sentences(content):
    content=re.sub(r'^Get [^.!?]{0,150}? in your Inbox\s*', '', content, flags=re.I)
    content=re.sub(r'^By [A-Z][^.!?]{0,180}? (?=(?:If|As|When|In|The)\b)', '', content)
    content=re.sub(r'\b(Inc|Corp|Ltd|Mr|Ms|Dr)\.',r'\1∯',content)
    s=re.split(r'(?<=[。！？])\s*|(?<=[.!?][”"])\s+(?=[A-Z0-9“"(])|(?<=[.!?])\s+(?=[A-Z0-9“"(])',content)
    return [v.replace('∯','.').strip() for v in s if 35<=len(v.strip())<=650 and not re.search(NOISE+r'|The post .*appeared first|\[.…*\]',v,re.I)]

def evidence_points(content,title):
    points=sentences(content)
    if not points:return []
    stop={'with','from','that','this','into','what','when','will','have','your','more','adds','launches','shopping','commerce','new','how','the','and','for'}
    keys=set(re.findall(r'[a-z]{3,}|[\u4e00-\u9fff]{2,4}',title.lower()))-stop
    entities={w.lower() for w in re.findall(r'\b[A-Z][a-zA-Z]{2,}\b',title) if w.lower() not in stop}
    def rank(pair):
        index,value=pair; lower=value.lower()
        match=sum(bool(re.search(r'\b'+re.escape(k)+r'\b',lower)) for k in entities)
        common=sum(k in lower for k in keys)
        concrete=bool(re.search(r'launch|introduc|unveil|allow|can |let |support|推出|支持|上线|提供|允许',value,re.I))
        vague=bool(re.match(r'That |This |The open standard|这一|这也',value))
        return match*5+min(common,4)*2+concrete*3+max(0,6-index*.4)-vague*5
    # Anchor the abstract in the lede, not a tangential background sentence.
    first=next((v for v in points[:5] if any(k in v.lower() for k in keys)),points[0])
    selected=[first]
    for _,value in sorted(enumerate(points),key=rank,reverse=True):
        if not any(SequenceMatcher(None,value,q).ratio()>.75 for q in selected):selected.append(value)
        if len(selected)==3:break
    return selected

def short_quotes(points, budget=60):
    """Publish short evidence excerpts and links, not a mirror of publisher articles."""
    result=[]
    for value in points:
        tokens=list(re.finditer(r'[\u4e00-\u9fff]|[^\s\u4e00-\u9fff]+',value))
        if budget<10:break
        if len(tokens)<=budget:result.append(value);budget-=len(tokens)
        else:result.append(value[:tokens[budget-1].end()].rstrip()+' …');break
    return result

def choose_lens(article):
    # Headline is more discriminative than broad paragraphs listing every AI capability.
    s=article['title']+' '+article.get('excerpt','')[:800]
    ranked=sorted(LENSES,key=lambda l:len(re.findall(l['terms'],article['title'],re.I))*5+len(re.findall(l['terms'],s,re.I)),reverse=True)
    return ranked[0]

def claim_type(title):
    types=[
      (r'survey|research|study|report|调查|研究|报告|%|percent',dict(label='研究 / 数据',question='样本和分母是否可比',limit='首先核对样本范围、时间窗与问题定义；意愿、自报行为、实际订单不是同一指标。',test='先建立指标口径表，要求样本量、对照组与统计周期，缺项时不搬用增长数字。')),
      (r'partner|power|integrat|协议|合作|接入|protocol|standard',dict(label='合作 / 基础设施',question='接入之后是否真正可用',limit='合作或协议发布不证明上线覆盖与消费者可用性，商家接入也可能只是试点。',test='从公开可用路径核对地区、商家和失败兜底，再观察真实任务漏斗。')),
      (r'launch|roll|expand|introduc|add|上线|推出|升级|发布|拓展',dict(label='功能 / 上线',question='发布能力能否转成持续使用',limit='产品公告说明能力或范围变化，不能据此推断用户采用和留存。',test='先记录入口、开放地区、使用门槛与操作步骤；两周后检查重复使用和任务成功率。')),
    ]
    return next((v for pattern,v in types if re.search(pattern,title,re.I)),dict(label='分析 / 观点',question='这个解释有哪些反例',limit='解释性文章提出的是机制或预测，不应当作已发生的用户行为。',test='把观点改写为可被推翻的假设，寻找相反案例与最小对照实验。'))


def same_event(a,b):
    # Conservative event bundling: specific entity + action + release wording + <=3 days.
    try:
        if abs((dt.date.fromisoformat(a['date'])-dt.date.fromisoformat(b['date'])).days)>3:return False
    except (ValueError,KeyError):return False
    def sig(title):
        entity=next((name for name,pat in [('constructor',r'constructor'),('tiktok',r'tiktok|抖音'),('openai',r'openai|chatgpt'),('gap',r'\bgap\b'),('amazon',r'amazon|rufus|亚马逊'),('google',r'google|谷歌'),('walmart',r'walmart|sparky|沃尔玛')] if re.search(pat,title,re.I)),None)
        action=next((name for name,pat in [('tryon',r'try.on|试穿|试衣'),('checkout',r'checkout|结账|一键支付'),('assistant',r'shopping assistant|购物助手')] if re.search(pat,title,re.I)),None)
        release=bool(re.search(r'launch|roll|expand|introduc|add|embed|上线|推出|发布',title,re.I))
        return (entity,action) if entity and action and release else None
    sa,sb=sig(a['title']),sig(b['title'])
    return bool(sa and sa==sb)

def content_kinds(a):
    title=a['title']; categories=[]
    if a.get('sourceKind')=='research':categories.append('研究报告')
    if re.search(r'咨询|麦肯锡|贝恩|德勤|普华永道|mckinsey|bcg|bain|deloitte|accenture|pwc|kpmg|capgemini|forrester|gartner',a.get('url','')+' '+a.get('source',''),re.I):categories.insert(0,'咨询洞察')
    if re.search(r'研究|报告|调研|调查|survey|research|study|report|benchmark',title,re.I):categories.append('研究报告')
    if re.search(r'竞品|对比|体验|实测|review|comparison|hands.on|versus',title,re.I):categories.append('竞品分析')
    if re.search(r'淘宝|京东|美团|抖音|豆包|小红书|得物|拼多多|阿里|唯品会|amazon|rufus|walmart|sparky|chatgpt|google|perplexity|shopify|instacart|zalando|pinterest|shopee|lazada|ebay|\bgap\b|constructor|myprotein|realreal',title,re.I):categories.append('竞品动态')
    if re.search(r'案例|case study|launch|roll|introduc|add|expand|unveil|上线|推出|发布',title,re.I):categories.append('产品案例')
    if not categories:categories.append('行业分析' if a.get('sourceKind') not in ('official',) else '产品案例')
    priority=['咨询洞察','研究报告','竞品分析','产品案例','竞品动态','行业分析']
    return sorted(set(categories),key=lambda label:priority.index(label))

def enrich(raw, verify=True):
    a=dict(raw); a['url']=public_url(a.get('url',''))
    if not a['url']: return None,'unsafe_url'
    if (urllib.parse.urlsplit(a['url']).hostname or '')=='rise.bcg.com':return None,'training_page'
    if re.search(r'/careers?/|/jobdetails',a['url'],re.I):return None,'recruitment_page'
    if 'news.google.com' in a['url']:
        # Reuse the existing publisher-link decoder, never publish search placeholders.
        from update_content import decode_google_news_url,resolve_direct_url_from_news_search
        session=requests.Session()
        a['url']=public_url(decode_google_news_url(session,a['url']))
        if not a['url'] or 'news.google.com' in a['url']:
            a['url']=public_url(resolve_direct_url_from_news_search(session,a))
        if not a['url'] or 'google.com' in (urllib.parse.urlsplit(a['url']).hostname or ''):return None,'unresolved_link'
    a['sourceKind']=publisher_kind(a['url']) if a.get('sourceKind') in (None,'unknown','discovery') else a['sourceKind']
    original=a.get('date',''); content=''; page={}; verified=False
    if verify:
        try:
            r=get(a['url'])
            if 'html' not in r.headers.get('Content-Type','').lower():raise ValueError('不是 HTML 正文')
            page=extract_page(r.text,a['url']); content=' '.join(page['paragraphs']); verified=len(content)>=200
            a['linkStatus']='reachable'; a['checkedAt']=now().isoformat(timespec='seconds')
            a['url']=public_url(r.url)
        except Exception:
            a['linkStatus']='unverified'; a['checkedAt']=now().isoformat(timespec='seconds')
    known_dates=[d for d in (date_value(original), date_value(a.get('discoveredDate')), page.get('published')) if d]
    a['date']=min(known_dates) if known_dates else ''
    if len(set(known_dates))>1:
        a['dateBasis']='日期冲突，采用较早发布日期'
        a['dateCandidates']=sorted(set(known_dates))
    elif page.get('published'):
        a['dateBasis']='原文发布日期'
    if not a['date']:return None,'unknown_date'
    # Only publisher page/real RSS description may be evidence; Google News snippets repeat titles.
    if not content:content=a.get('excerpt') or a.get('snippet','')
    if not related(a['title'],content):return None,'off_topic'
    points=evidence_points(content,a['title'])
    if not points and page.get('description') and len(page['description'])>=50:points=[page['description']]
    if not points:points=[a['title']]
    old_evidence=a.get('evidenceLevel')
    level='fulltext' if verified else ('abstract' if len(content)>160 and a.get('sourceKind')!='discovery' else 'headline')
    if not verify and old_evidence:level=old_evidence
    a['sourceCaveats']=[v for v in sentences(content) if re.search(r'did not (?:specify|disclose)|has not (?:disclosed|shared)|not yet available|remains unclear|未披露|尚未公开|尚未上线|仅限.*(?:试点|内测)|未提供.*(?:数据|信息)',v,re.I)][:2]
    points=short_quotes(points,45 if a['sourceCaveats'] else 60)
    a['sourceCaveats']=short_quotes(a['sourceCaveats'],15)
    a.pop('snippet',None)
    a.update(excerpt=' '.join(points),corePoint=points,evidenceLevel=level,evidenceLabel={'fulltext':'原文已提取','abstract':'仅摘要可用','headline':'仅标题线索'}[level],pipelineVersion=VERSION)
    a.setdefault('id','radar-'+hashlib.sha256(a['url'].encode()).hexdigest()[:16])
    if a['sourceKind']=='discovery':a['sourceKind']=publisher_kind(a['url'])
    a['firstSeenAt']=a.get('firstSeenAt') or now().date().isoformat()
    a.setdefault('dateBasis','历史存档日期（未复核）')
    lens=choose_lens(a);a['lensId']=lens['id']
    a['tags']=lens['keywords'];a['category']=lens['keywords'][0];a['contentType']='研究数据' if a['sourceKind']=='research' else ('产品功能' if a['sourceKind']=='official' else '行业观察')
    dimensions={'source':{'official':25,'research':23,'industry':21,'media':16,'analysis':14,'press_release':10,'unknown':8}.get(a['sourceKind'],8),'evidence':{'fulltext':30,'abstract':16,'headline':4}[level],'relevance':25 if related(a['title']) else 15,'specificity':min(20,5+len(points)*3+ (6 if re.search(r'\d', ' '.join(points)) else 0))}
    a['quality']={'dimensions':dimensions,'rubric':'来源25＋可核验信息30＋主题相关25＋事实具体度20；不是事实正确概率'}
    a['valueScore']=sum(dimensions.values())
    a['readingTier']='精选' if level=='fulltext' and a['valueScore']>=72 and a['sourceKind'] not in ('unknown','press_release') else '观察'
    a['analysis']={'question':lens['title'],'implication':lens['mechanism'],'counterpoint':lens['boundary'],'experiment':lens['experiment'],'basis':'基于证据的规则辅助推演，非原文结论；未使用大模型生成','anchor':points[0]}
    claim = claim_type(a['title'])
    a['signalType']=claim['label']
    a['analysis']['question']=f"{claim['question']} · {lens['keywords'][0]}"
    a['analysis']['counterpoint']=claim['limit']+' '+lens['boundary']
    a['analysis']['experiment']=claim['test']+' '+lens['experiment']
    a['analysis']['implication']=f"本条以“{a['title']}”为观察对象。"+lens['mechanism']
    a['insight']=a['analysis']['implication']
    a['relatedInsightIds']=['evidence-'+lens['id']]
    a['publisher']=(urllib.parse.urlsplit(a['url']).hostname or '').removeprefix('www.')
    registered=next((src for src in SOURCES if (urllib.parse.urlsplit(src['url']).hostname or '').removeprefix('www.')==a['publisher']),None)
    if registered:a['source']=registered['name']
    a['title']=re.sub(r'\s+[-–—]\s+(?:'+re.escape(a['source'])+'|'+re.escape(a['publisher'])+r')$','',a['title']).strip()
    if a['source'].startswith('发现 · '):a['source']=a['publisher']
    a['contentKinds']=content_kinds(a)
    a['contentType']=a['contentKinds'][0]
    return a,''

def diverse(items,limit,per_source=4):
    selected=[];counts=Counter();lenses=Counter();regions=Counter()
    pending=sorted(items,key=lambda a:(a['date'],a.get('valueScore',0)),reverse=True)
    while pending and len(selected)<limit:
        best=max(pending,key=lambda a:a.get('valueScore',0) - counts[a.get('publisher',a['source'])]*12 - lenses[a.get('lensId','')]*5 - regions[a.get('region','')]*3 + max(0,14-(now().date()-dt.date.fromisoformat(a['date'])).days))
        pending.remove(best);publisher=best.get('publisher',best['source'])
        if counts[publisher]>=per_source:continue
        if any(duplicate(best,b) for b in selected):continue
        selected.append(best);counts[publisher]+=1;lenses[best.get('lensId','')]+=1;regions[best.get('region','')]+=1
    return selected

def make_insights(articles,previous):
    old={i['id']:i for i in previous};output=[]
    cutoff=(now().date()-dt.timedelta(days=45)).isoformat()
    for lens in LENSES:
        group=[a for a in articles if a.get('lensId')==lens['id'] and a.get('readingTier')=='精选' and a['date']>=cutoff]
        group=diverse(group,4,2)
        if not group:continue
        iid='evidence-'+lens['id']; pubs={a.get('publisher',a['source']) for a in group}
        evidence=[dict(articleId=a['id'],title=a['title'],source=a['source'],caveats=a.get('sourceCaveatsZh') or a.get('sourceCaveats',[]),signalType=a.get('signalType','产品观察'),date=a['date'],quote=a['corePoint'][0],quoteZh=(a.get('summaryZh') or a['corePoint'])[0],url=a['url']) for a in group]
        fingerprint=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()[:16]
        prev=old.get(iid,{})
        contrast='；'.join(f"{a['source']}提供{a.get('signalType','产品观察')}线索" for a in group)
        output.append(dict(observation=contrast+'。这些证据衡量的对象不同，不能直接比较效果。',id=iid,title=lens['title'],summary=lens['mechanism'],evidence=evidence,counterpoint=lens['boundary'],experiment=lens['experiment'],takeaways=[],keywords=lens['keywords'],relatedArticleIds=[a['id'] for a in group],sourceCount=len(pubs),confidence='待验证假设',iterationNote=f'近45天 {len(group)} 篇原文、{len(pubs)} 个发布域名提供观察线索；多篇报道不等于独立验证或因果证据。',generatedAt=prev.get('generatedAt',now().date().isoformat()),updatedAt=prev.get('updatedAt') if prev.get('fingerprint')==fingerprint else now().date().isoformat(),fingerprint=fingerprint,method='规则辅助研究假设'))
    return output

MONTH_ANGLES = {
    'discovery': ('导购入口', '对话搜索、商品发现与候选推荐', '入口变化能否缩短真实购物决策'),
    'payments': ('交易授权', '智能体结账、支付接入与用户授权', '从推荐到成交时的授权和责任边界'),
    'merchant': ('商家接入', '商品数据、商家工具与协议接入', '商家接入能否带来可衡量的新增成交'),
    'visual': ('视觉试穿', '虚拟试穿、穿搭与尺码判断', '视觉体验是否降低选错和退货'),
    'memory': ('偏好记忆', '个性化推荐、偏好记忆与复购', '长期偏好是否减少重复决策'),
    'trust': ('推荐信任', '推荐证据、消费者信任与风险', '用户是否能核验推荐依据'),
    'local': ('即时购物', '本地生活、即时购物与配送履约', '推荐结果是否能在当下真正履约'),
}
MONTH_SUBJECTS = [
    ('TikTok', r'tiktok|抖音'), ('Gap', r'\bgap\b'), ('Google', r'google|谷歌'),
    ('OpenAI', r'openai|chatgpt'), ('Stripe', r'stripe'), ('Shopify', r'shopify'),
    ('Amazon', r'amazon|rufus|亚马逊'), ('Walmart', r'walmart|sparky|沃尔玛'),
    ('Constructor', r'constructor'), ('Instacart', r'instacart'), ('淘宝', r'淘宝|天猫'),
    ('京东', r'京东|京言'), ('美团', r'美团|问小团'), ('豆包', r'豆包'),
    ('Mastercard', r'mastercard'), ('Visa', r'\bvisa\b'), ('Perplexity', r'perplexity'),
]


def build_reports(articles):
    reports=[]
    for month in sorted({a['date'][:7] for a in articles},reverse=True):
        group=[a for a in articles if a['date'].startswith(month)]
        verified=[a for a in group if a.get('evidenceLevel')=='fulltext']
        preferred=[a for a in verified if a.get('readingTier')=='精选']
        # Recommendations are limited to available original evidence. No title-only filler.
        top=diverse(preferred or verified,5,2)
        summary_pool=preferred or verified
        counts=Counter(a.get('lensId','discovery') for a in summary_pool)
        themes=[key for key,_ in counts.most_common(3) if key in MONTH_ANGLES]
        if themes:
            title=' · '.join(MONTH_ANGLES[key][0] for key in themes)
            parts=[]
            for key in themes:
                related_items=[a for a in summary_pool if a.get('lensId','discovery')==key]
                subjects=[]
                for a in sorted(related_items,key=lambda a:a.get('valueScore',0),reverse=True):
                    for name,pattern in MONTH_SUBJECTS:
                        if name not in subjects and re.search(pattern,a['title'],re.I):subjects.append(name)
                prefix='、'.join(subjects[:2])+' 等相关资料' if subjects else MONTH_ANGLES[key][0]+'相关资料'
                parts.append(prefix+'聚焦'+MONTH_ANGLES[key][1])
            summary='；'.join(parts)+'。重点追踪'+MONTH_ANGLES[themes[0]][2]+'。'
        else:
            title='本月资讯回顾'
            summary='本月保留 '+str(len(group))+' 条历史线索，暂无可核验原文；暂不生成趋势总结或推荐。'
        reports.append(dict(month=month,title=title,summary=summary,articleCount=len(group),
            topArticleIds=[a['id'] for a in top],summaryArticleIds=[a['id'] for a in summary_pool],
            insight=MONTH_ANGLES[themes[0]][2] if themes else '',updatedAt=now().date().isoformat()))
    return reports

def run(days=45,limit=24,max_queries=None,recheck=False,dry_run=False):
    max_queries=len(QUERIES) if max_queries is None else max_queries
    started=now().isoformat(timespec='seconds'); cutoff=(now().date()-dt.timedelta(days=days)).isoformat()
    existing=load('articles.json',[]); previous=load('insights.json',[])
    sources=list(SOURCES)
    for region,q in QUERIES[:max_queries]:
        lang,gl,ceid=('zh-CN','CN','CN:zh-Hans') if region=='国内' else ('en-US','US','US:en')
        url='https://news.google.com/rss/search?'+urllib.parse.urlencode(dict(q=f'{q} when:{days}d',hl=lang,gl=gl,ceid=ceid))
        sources.append(dict(name='发现 · '+q,region=region,kind='discovery',url=url))
    candidates=[];health=[];rejected=Counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        for items,h in pool.map(fetch_source,sources):candidates+=items;health.append(h)
    print(f'Discovery: {len(candidates)} candidates; {sum(h["status"]=="ok" for h in health)}/{len(health)} endpoints healthy',flush=True)
    if not any(h['status']=='ok' for h in health):raise RuntimeError('全部来源失败；保留已有数据并让工作流报警')
    unique=[]
    for a in candidates:
        if a.get('date') and a['date']<cutoff:continue
        if not related(a['title'],a.get('snippet','')):continue
        if any(duplicate(a,b) or any(public_url(a['url'])==public_url(c['url']) for c in b.get('relatedCoverage',[])) for b in existing+unique):continue
        unique.append(a)
    # Cap costly original-page fetches, preserve room for direct feeds and domestic reporting.
    unique.sort(key=lambda a:(a.get('sourceKind')!='discovery',a.get('date','')),reverse=True)
    from itertools import zip_longest
    domestic=[a for a in unique if a['region']=='国内'];overseas=[a for a in unique if a['region']!='国内']
    unique=[a for pair in zip_longest(domestic,overseas) for a in pair if a]
    bucket=Counter();to_fetch=[]
    for a in unique:
        key=a['source'];
        if bucket[key]>=6:continue
        bucket[key]+=1;to_fetch.append(a)
        if len(to_fetch)>=160:break
    preserved=[]; refresh=[]
    for a in existing:
        if recheck or a.get('pipelineVersion')!=VERSION:refresh.append(a)
        elif not related(a['title'],a.get('excerpt','')):rejected['off_topic']+=1
        else:preserved.append(a)
    if not recheck:
        for a in sorted(preserved,key=lambda x:x.get('checkedAt',''))[:12]:
            if a.get('checkedAt','')[:10] < (now().date()-dt.timedelta(days=7)).isoformat():refresh.append(a);preserved.remove(a)
    results=[]
    with ThreadPoolExecutor(max_workers=10) as pool:
        for a,reason in pool.map(enrich,to_fetch+refresh):
            if a:results.append(a)
            else:rejected[reason]+=1
    old_ids={a['id'] for a in existing}
    refreshed=[a for a in results if a['id'] in old_ids]
    eligible=[a for a in results if a['id'] not in old_ids and a['date']>=cutoff and a['evidenceLevel']!='headline' and a['valueScore']>=60]
    selected=diverse(eligible,limit)
    merged=[]
    for a in sorted(preserved+refreshed+selected,key=lambda a:(a.get('readingTier')=='精选',a.get('valueScore',0),a['date']),reverse=True):
        dupe=next((b for b in merged if duplicate(a,b) or same_event(a,b)),None)
        if dupe:
            if a.get('url')!=dupe.get('url'):dupe.setdefault('relatedCoverage',[]).extend([{k:a[k] for k in ('title','url','source')}]+a.get('relatedCoverage',[]))
            dupe['relatedCoverage']=list({c['url']:c for c in dupe.get('relatedCoverage',[]) if c['url']!=dupe['url']}.values())[:10]
        else:merged.append(a)
    merged.sort(key=lambda a:(a['date'],a.get('valueScore',0)),reverse=True)
    if not merged:raise RuntimeError('质量处理后数据为空；拒绝覆盖现有内容')
    selected=[a for a in merged if a['id'] not in old_ids]
    from localize_summaries import localize_articles, localize_titles
    translation_candidates={a['id'] for a in merged}
    merged=localize_articles(merged,strict=False)
    merged=localize_titles(merged,strict=False)
    kept_ids={a['id'] for a in merged}
    merged.extend(a for a in existing if a['id'] in translation_candidates and a['id'] not in kept_ids and a.get('summaryZh'))
    merged.sort(key=lambda a:(a['date'],a.get('valueScore',0)),reverse=True)
    selected=[a for a in merged if a['id'] not in old_ids]
    from article_brief import refresh_briefs
    refresh_briefs(merged)
    insights=make_insights(merged,previous);reports=build_reports(merged)
    changed=sum(next((x.get('fingerprint') for x in previous if x['id']==i['id']),None)!=i['fingerprint'] for i in insights)
    digest_top=diverse([a for a in merged if a['date']>=(now().date()-dt.timedelta(days=14)).isoformat() and a.get('readingTier')=='精选'],5,2)
    meta=load('meta.json',{});meta.update(lastUpdated=started,lastInsightUpdated=now().date().isoformat(),latestAdded=len(selected),latestInsightChanged=changed,sourceCount=len({a.get('publisher',a['source']) for a in merged}),articleCount=len(merged),updateTime='每日北京时间 11:00 计划运行（GitHub 可能延迟）',selectionRule='原文可核验优先；分级而非凑数；事实与推演分离；按来源和主题打散。',pipelineVersion=VERSION,analysisMode='规则辅助研究：证据摘录＋因果机制＋反向解释＋验证实验',sourceHealth={'configured':len(SOURCES),'healthy':sum(h['status']=='ok' for h in health if h['kind']!='discovery'),'failed':sum(h['status']!='ok' for h in health if h['kind']!='discovery'),'discoveryQueries':max_queries},qualitySummary={'verified':sum(a.get('evidenceLevel')=='fulltext' for a in merged),'watchlist':sum(a.get('readingTier')=='观察' for a in merged),'rejected':dict(rejected)},lastRunStatus='degraded' if sum(h['status']=='ok' for h in health)<len(health)*.5 else 'ok')
    digest=dict(date=now().date().isoformat(),generatedAt=started,newCount=len(selected),title='先读这几条，再形成判断',articleIds=[a['id'] for a in digest_top],insightIds=[i['id'] for i in insights],note='近14天已提取原文的多来源精选；零新增时保留阅读入口，不制造“今日新趋势”。',analysisMode=meta['analysisMode'])
    if not dry_run:
        # Preserve old material, including attached IDs, for a reversible migration.
        if not (DATA/'legacy_insights.json').exists():write('legacy_insights.json',previous)
        if not (DATA/'legacy_articles.json').exists():write('legacy_articles.json',existing)
        for name,obj in [('articles.json',merged),('insights.json',insights),('monthly_reports.json',reports),('source_health.json',health),('daily_digest.json',digest),('meta.json',meta)]:write(name,obj)
    print(json.dumps({'added':len(selected),'articles':len(merged),'insights':len(insights),'rejected':dict(rejected),'health':meta['sourceHealth']},ensure_ascii=False),flush=True)
    return selected

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=45);p.add_argument('--limit',type=int,default=24);p.add_argument('--max-google-queries',type=int,default=len(QUERIES));p.add_argument('--recheck',action='store_true');p.add_argument('--dry-run',action='store_true');p.add_argument('--skip-wechat',action='store_true',help='Compatibility: ephemeral WeChat links are never collected')
    args=p.parse_args()
    if not 1<=args.days<=366 or not 0<=args.max_google_queries<=len(QUERIES) or not 1<=args.limit<=100:p.error('参数超出安全范围')
    run(args.days,args.limit,args.max_google_queries,args.recheck,args.dry_run)
