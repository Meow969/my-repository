#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests
try:
    from content_quality import canonical_source, clean_display_title, dedupe_items, is_ai_shopping_related
except ImportError:  # pragma: no cover
    from scripts.content_quality import canonical_source, clean_display_title, dedupe_items, is_ai_shopping_related

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / 'data' / 'articles.json'

QUERIES = [
    'AI shopping assistant', 'agentic commerce', 'AI shopping agent', 'ChatGPT shopping',
    'Google AI shopping', 'Amazon Rufus AI shopping', 'Perplexity shopping AI',
    'AI consumer app commerce', 'conversational commerce AI', 'AI retail assistant',
    'AI ecommerce assistant', 'AI shopping checkout', 'AI personal shopper', 'AI product discovery',
    'AI search shopping', 'AI agent retail', 'AI assistant app consumer', 'consumer AI app',
    'ChatGPT app consumer', 'Gemini app consumer', 'Claude app consumer', 'Perplexity AI search',
    'AI browser agent', 'AI wearable consumer', 'AI travel agent app', 'AI personal assistant app',
    'AI marketplace agent', 'AI recommendation ecommerce', 'retail media AI agent',
    'merchant AI agent', 'agent payment commerce', 'AI payment agent', 'AI shopping cart',
    'AI visual search shopping', 'virtual try on AI shopping',
    'AI personal shopper product design', 'AI shopping assistant case study',
    'AI shopping consumer behavior', 'agentic commerce merchant',
    'agentic commerce checkout payment', 'AI shopping product discovery',
    'AI shopping search recommendations', 'AI shopping trust privacy',
    'AI shopping memory personalization', 'retail AI agent customer experience',
    'site:aboutamazon.com/news/retail Rufus AI shopping',
    'site:blog.google/products/shopping AI shopping',
    'site:blog.google/products/ads-commerce agentic commerce',
    'site:shopify.com/blog AI ecommerce shopping',
    'site:stripe.com agentic commerce', 'site:mastercard.com agentic commerce',
    'site:visa.com AI commerce', 'site:mckinsey.com AI retail ecommerce',
    'site:a16z.com AI consumer shopping', 'site:retaildive.com AI shopping retail',
    'site:modernretail.co AI shopping', 'site:practicalecommerce.com AI ecommerce',
    'site:digitalcommerce360.com AI shopping', 'site:pymnts.com agentic commerce shopping',
    'site:techcrunch.com AI shopping assistant', 'site:theverge.com AI shopping',
    'AI购物', 'AI导购', '购物智能体', 'AI电商', '对话式购物', '智能体商业',
    'AI 搜索 电商', 'AI 购物助手', 'AI 商家 智能体', 'AI 支付 智能体',
    'AI购物 产品设计', 'AI导购 用户体验', 'AI购物 交易闭环', 'AI导购 商家 可见性',
    'AI购物 复购 记忆', 'AI购物 支付 履约', 'AI导购 观点 案例',
    'ChatGPT', 'Gemini AI', 'Claude AI', 'Perplexity AI', 'AI app', 'consumer AI',
    'AI assistant', 'AI search', 'AI browser', 'AI product launch', '人工智能 应用',
    'AI助手', '大模型应用', 'AI产品', 'ChatGPT 应用', '豆包 AI', 'Kimi AI', '通义千问'
]

SOURCE_WEIGHT = {
    'OpenAI': 24, 'Google': 22, 'Google Blog': 22, 'About Amazon': 22, 'Amazon': 22,
    'McKinsey & Company': 22, 'Harvard Business Review': 20, 'BCG': 20, 'World Economic Forum': 18,
    'The Verge': 16, 'TechCrunch': 16, 'CNBC': 15, 'Retail Dive': 15, 'PYMNTS.com': 14,
    'Digital Commerce 360': 15, 'Modern Retail': 14, 'Practical Ecommerce': 14,
    'Shopify': 16, 'Stripe': 16, 'Mastercard': 16, 'Visa': 16, 'a16z': 16,
    'Kohl\'s Corporate': 14, 'Target Corporation': 14, 'Pinterest Newsroom': 14,
    'InfoQ-CN': 12, '华尔街见闻': 12, '全天候科技': 11, '财联社': 10, '36氪': 10,
    'TechWeb': 10, '新浪新闻_手机新浪网': 8, 'QQ News': 6,
}
POSITIVE = ['shopping','commerce','retail','merchant','checkout','cart','rufus','perplexity','chatgpt','gemini','claude','assistant','consumer','agent','agentic','ecommerce','try on','visual search','购物','导购','电商','零售','商家','下单','支付','智能体','买菜','闪购','豆包','千问','京东','淘宝','商品','搜索']
NEGATIVE = ['stock','shares','lawsuit unrelated','hiring','招聘','股票','股价','培训','课程','彩票','游戏攻略','政治']


def clean(value: str) -> str:
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<.*?>', '', value or ''))).strip()


def parse_date(value: str) -> str | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.date().isoformat()
    except Exception:
        return None


def slug(value: str) -> str:
    return hashlib.sha1(value.encode('utf-8')).hexdigest()[:14]


def tags_for(text: str) -> list[str]:
    lower = text.lower()
    tags = []
    rules = {
        'AI购物': ['shopping','购物','导购','电商'],
        '购物智能体': ['agentic','agent','智能体','代买'],
        'C端AI产品': ['consumer','app','assistant','chatgpt','gemini','claude','豆包','千问','kimi'],
        '交易闭环': ['checkout','payment','cart','支付','下单','购物车'],
        '商家接入': ['merchant','seller','retailer','商家','卖家','零售商'],
        '视觉购物': ['visual','try on','image','circle','试穿','视觉','图片'],
        'AI搜索': ['search','perplexity','搜索'],
        '即时零售': ['instant','grocery','闪购','买菜','外卖'],
    }
    for tag, words in rules.items():
        if any(w in lower for w in words): tags.append(tag)
    return tags[:5] or ['C端AI产品']


def category_for(tags: list[str], title: str) -> str:
    lower = title.lower()
    if '交易闭环' in tags: return '交易闭环'
    if '视觉购物' in tags: return '产品功能'
    if '商家接入' in tags: return '商家/生态'
    if 'AI搜索' in tags: return 'AI搜索'
    if '购物智能体' in tags: return '智能体购物'
    if any(w in lower for w in ['report','研究','麦肯锡','hbr','bcg']): return '报告/研究'
    return 'C端AI产品'


def related_for(tags: list[str], title: str) -> list[str]:
    lower = title.lower()
    ids = []
    if '交易闭环' in tags: ids += ['closed-loop-first','trust-ladder']
    if '商家接入' in tags: ids += ['merchant-readable-store','multi-agent-market']
    if 'AI搜索' in tags or '购物智能体' in tags: ids += ['agentic-funnel','answer-shelf']
    if '即时零售' in tags: ids += ['habit-before-intelligence','preference-memory']
    if '视觉购物' in tags: ids += ['category-wedge','structured-dialogue']
    if 'C端AI产品' in tags: ids += ['decision-os']
    return list(dict.fromkeys(ids))[:3] or ['decision-os']


def score(item: dict[str, Any]) -> int:
    text = f"{item['title']} {item.get('snippet','')} {item.get('query','')}".lower()
    s = 55 + SOURCE_WEIGHT.get(item.get('source',''), 0)
    s += sum(4 for w in POSITIVE if w.lower() in text)
    s -= sum(10 for w in NEGATIVE if w.lower() in text)
    if any(w in text for w in ['shopping','commerce','购物','导购','电商','零售']): s += 10
    return max(60, min(96, s))


def core_and_insight(item: dict[str, Any], tags: list[str]) -> tuple[str, str]:
    title = item['title']
    if '交易闭环' in tags:
        return ('这条信息指向AI购物从“推荐答案”进入“交易执行”：购物车、支付、下单和履约正在成为AI入口竞争的一部分。', '产品上要把交易确认做成独立能力：预算、库存、优惠、到达时间和售后责任必须在AI建议前后被核验，否则推荐越强，误购风险越高。')
    if '商家接入' in tags:
        return ('这条信息说明AI购物不是单边C端体验，商家侧能否被AI读取、比较和调用，会决定商品是否进入候选答案。', '需要建设“给机器看的店”：结构化卖点、适用场景、评价证据、价格库存和售后承诺。商家运营后台会成为AI导购供给质量的关键。')
    if '视觉购物' in tags:
        return ('视觉、试穿和图片搜索正在把购物入口前移到“看到即询问”的瞬间，尤其适合非标和审美型品类。', '非标品导购不要照搬参数比较，应该强化风格翻译、相似款发现、适配模拟和后悔风险降低。')
    if 'AI搜索' in tags:
        return ('AI搜索正在把答案、证据、商品卡和购买动作合并，搜索结果页与购物入口的边界变得模糊。', '导购产品要提供可追溯证据链：为什么推荐、来源是什么、替代项有哪些、哪些条件下不推荐。')
    if '即时零售' in tags:
        return ('高频低风险消费正在成为AI购物习惯养成的更优入口，用户更容易授权AI处理重复选择。', '先用买菜、日用品、外卖等场景训练偏好记忆和授权边界，再迁移到复杂高客单决策。')
    if '购物智能体' in tags:
        return ('购物智能体正在从信息助手走向任务代理，用户会逐步把筛选、比较、提醒和部分购买动作交给AI。', '导购体验要分层授权：先解释，再筛选，再加购，最后代买。越接近支付，越需要确认、可撤回和责任说明。')
    return (f'这条信息反映C端AI产品正在改变用户完成任务和消费决策的方式：{title}', '把它用于AI导购时，重点看它能否缩短用户表达需求、形成判断、完成动作的链路，而不是只看功能是否新奇。')


def fetch_news() -> list[dict[str, Any]]:
    session = requests.Session(); session.headers.update({'User-Agent':'Mozilla/5.0'})
    out = []
    for q in QUERIES:
        for lang, gl, ceid in [('en-US','US','US:en'), ('zh-CN','CN','CN:zh-Hans')]:
            try:
                res = session.get('https://news.google.com/rss/search', params={'q': q + ' when:365d', 'hl': lang, 'gl': gl, 'ceid': ceid}, timeout=15)
                root = ET.fromstring(res.content)
            except Exception:
                continue
            for node in root.findall('.//item'):
                date = parse_date(node.findtext('pubDate') or '')
                if not date or not ('2025-09-04' <= date <= '2026-09-04'): continue
                source = canonical_source(clean(node.findtext('source') or 'Google News'))
                title = clean_display_title(clean(node.findtext('title') or ''), source)
                if not title: continue
                out.append({'date': date, 'title': title, 'source': source, 'url': node.findtext('link') or '', 'snippet': clean(node.findtext('description') or ''), 'query': q})
            time.sleep(0.03)
    return dedupe_items(out)


def normalize(item: dict[str, Any]) -> dict[str, Any]:
    item = dict(item)
    item['source'] = canonical_source(item.get('source') or 'Google News')
    item['title'] = clean_display_title(item.get('title') or '', item['source'])
    text = f"{item['title']} {item.get('snippet','')} {item.get('query','')}"
    tags = tags_for(text)
    core, insight = core_and_insight(item, tags)
    return {
        'id': 'daily-' + item['date'] + '-' + slug(item['title'] + item.get('source','')),
        'date': item['date'], 'title': item['title'], 'source': item.get('source') or 'Google News',
        'region': '国内' if re.search(r'[\u4e00-\u9fa5]', item['title'] + item.get('source','')) else '海外',
        'category': category_for(tags, item['title']), 'url': item['url'], 'tags': tags,
        'corePoint': core, 'insight': insight, 'valueScore': score(item), 'relatedInsightIds': related_for(tags, item['title'])
    }


def fallback_day(date: str) -> dict[str, Any]:
    next_day = (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()
    query = urllib.parse.quote(f'(AI shopping OR AI导购 OR agentic commerce OR consumer AI) after:{date} before:{next_day}')
    return {
        'id': 'daily-index-' + date,
        'date': date,
        'title': f'{date}｜AI购物/消费AI当日资料检索入口',
        'source': 'Google News Search',
        'region': '全球',
        'category': '每日检索入口',
        'url': f'https://news.google.com/search?q={query}',
        'tags': ['每日追踪', '全网检索', 'C端AI产品'],
        'corePoint': '当日未检索到足够明确的AI购物单篇高价值文章，因此保留一个按日期限定的全网检索入口，避免资料库日期断档。',
        'insight': '这类日期不应强行编造观点。产品资料库需要区分“已精选文章”和“待人工复核检索入口”，后续自动更新或人工复核时可替换为真实高价值文章。',
        'valueScore': 60,
        'relatedInsightIds': ['decision-os']
    }


def main():
    existing = json.loads(ARTICLES.read_text(encoding='utf-8'))
    manual = {item['id']: item for item in existing if not item['id'].startswith('daily-') and not item['id'].startswith('daily-index-')}
    raw = fetch_news()
    normalized = dedupe_items([item for item in (normalize(item) for item in raw) if is_ai_shopping_related(item)])
    by_day = {}
    for item in normalized:
        current = by_day.get(item['date'])
        if not current or item['valueScore'] > current['valueScore']:
            by_day[item['date']] = item
    start = dt.date(2025,9,4); end = dt.date(2026,9,4)
    cur = start
    daily = []
    while cur <= end:
        date = cur.isoformat()
        daily.append(by_day.get(date) or fallback_day(date))
        cur += dt.timedelta(days=1)
    merged = list(manual.values()) + daily
    final = dedupe_items(merged)
    ARTICLES.write_text(json.dumps(final, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('written', len(final), 'daily', len(daily), 'fallback', sum(1 for x in daily if x['id'].startswith('daily-index-')))

if __name__ == '__main__':
    main()
