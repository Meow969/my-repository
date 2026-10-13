"""Readable, evidence-linked article cards. Facts remain separate from product hypotheses."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
from difflib import SequenceMatcher

VERSION='article-reviewed-v2'
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

# Labels may be classified automatically. Product conclusions must never be.
TOPICS=[
 ('平台开放',r'block|restrict|ban\b|封锁|屏蔽'),
 ('商品对比',r'compar|对比|比较'),('广告推荐',r'sponsor|advertis|广告|赞助'),
 ('支付授权',r'authoriz|permission|授权'),('虚拟试穿',r'try.on|试穿|试衣'),
 ('商品数据',r'catalog|product data|商品目录|商品数据'),('交易协议',r'protocol|协议'),
 ('个性化',r'personaliz|个性化'),('履约售后',r'refund|delivery|退货|售后|配送'),
 ('用户研究',r'survey|study|research|研究|调查'),('AI购物',r'shopping|购物|导购|retail|电商'),
]
REVIEW_PATH=Path(__file__).with_name('reviewed_research.json')
REQUIRED=('heading','anchorZh','insight','deepThought','validation','evidenceLimit','quote','reviewedAt','sourceHash')


def source_hash(a):
    value={k:a.get(k) for k in ('title','url','corePoint')}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def read_reviews():
    return json.loads(REVIEW_PATH.read_text()) if REVIEW_PATH.exists() else {}


def normalized(value):
    return re.sub(r'[^\w\u4e00-\u9fff]','',value).lower()


def same_research(left,right):
    # No brand-prefix trick: inspect the analytic body as well as the heading.
    for key in ('heading','insight','deepThought'):
        x,y=normalized(left.get(key,'')),normalized(right.get(key,''))
        if x and x==y:return True
    x=normalized(left.get('insight','')+left.get('deepThought',''))
    y=normalized(right.get('insight','')+right.get('deepThought',''))
    return min(len(x),len(y))>40 and SequenceMatcher(None,x,y).ratio()>.86


def review_for(article,reviews):
    record=reviews.get(article['id'])
    if not record:return None,'unreviewed'
    if not all(record.get(key) for key in REQUIRED):return None,'incomplete_review'
    if record['sourceHash']!=source_hash(article):return None,'source_changed'
    if record.get('url')!=article['url']:return None,'source_changed'
    if article.get('evidenceLevel')!='fulltext':return None,'insufficient_evidence'
    return dict(record,basisArticleId=article['id'],method='逐篇原文核对后的产品推演'), 'reviewed'


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


def build_brief(a,reviews=None):
    reviews=read_reviews() if reviews is None else reviews
    raw=source_text(a)
    entities=[name for _,name in sorted((re.search(pattern,a['title'],re.I).start(),name) for name,pattern in ENTITIES if re.search(pattern,a['title'],re.I))]
    topics=[label for label,pattern in TOPICS if re.search(pattern,raw,re.I)]
    keywords=list(dict.fromkeys(entities[:2]+topics[:3]))[:5] or ['电商观察']
    facts=[]
    for value in a.get('summaryZh',[])[:3]:
        point=clean_sentence(value)
        if not any(SequenceMatcher(None,point,old).ratio()>.78 for old in facts):facts.append(point)
    if a.get('evidenceLevel')=='headline':
        facts=['目前仅保存标题线索：'+a['titleZh'].rstrip('。')+'。正文尚未核实，暂不能确认产品细节或实际效果。']
    elif a.get('evidenceLevel')=='abstract' and facts:facts[0]='据目前可获取的摘要，'+facts[0]
    research,status=review_for(a,reviews)
    if research and research.get('summary'):facts=research['summary']
    return dict(version=VERSION,inputHash=input_hash(a),keywords=keywords,summary=facts,
        summaryLabel='核心信息',research=research,researchStatus=status)


def refresh_briefs(articles):
    reviews=read_reviews();accepted=[]
    for article in sorted(articles,key=lambda a:(a.get('date',''),a.get('valueScore',0)),reverse=True):
        brief=build_brief(article,reviews)
        if brief['research']:
            other=next((a for a in accepted if same_research(a['brief']['research'],brief['research'])),None)
            if other:
                brief.update(research=None,researchStatus='duplicate_review',relatedResearchArticleId=other['id'])
            else:accepted.append(article)
        article['brief']=brief
        # Legacy template fields must not leak through search, notes, or other renderers.
        article.pop('analysis',None);article.pop('insight',None)
        article['relatedInsightIds']=['case-'+article['id']] if brief['research'] else []
    return articles


def reviewed_insights(articles,previous):
    old={i['id']:i for i in previous};result=[]
    for a in articles:
        r=a.get('brief',{}).get('research')
        if not r:continue
        iid='case-'+a['id'];fp=hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        result.append(dict(id=iid,title=r['heading'],summary=r['insight'],counterpoint=r['deepThought'],
            experiment=r['validation'],keywords=a['brief']['keywords'],relatedArticleIds=[a['id']],
            evidence=[dict(articleId=a['id'],title=a['title'],source=a['source'],date=a['date'],
                quote=r['quote'],quoteZh=r['anchorZh'],url=a['url'])],sourceCount=1,
            generatedAt=old.get(iid,{}).get('generatedAt',r['reviewedAt']),updatedAt=r['reviewedAt'],
            fingerprint=fp,method=r['method'],researchStatus='reviewed',takeaways=[]))
    return result
