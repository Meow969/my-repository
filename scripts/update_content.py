#!/usr/bin/env python3
"""Update AI Shopping Radar content.

Default behavior is dependency-light and rule-based:
- searches WeChat/Sogou for Chinese AI shopping terms;
- reads selected official/industry RSS feeds for overseas signals;
- filters by recency, source quality, and product relevance;
- appends only high-value items to data/articles.json;
- refreshes data/meta.json.

Optional: set OPENAI_API_KEY to enrich summaries with a model in the future.
"""
from __future__ import annotations

import argparse
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

try:
    from content_quality import canonical_source, clean_display_title, clean_url, dedupe_items, is_ai_shopping_related, is_duplicate, is_temporary_wechat_url, normalized_title
except ImportError:  # pragma: no cover
    from scripts.content_quality import canonical_source, clean_display_title, clean_url, dedupe_items, is_ai_shopping_related, is_duplicate, is_temporary_wechat_url, normalized_title

try:
    import requests
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Missing dependency: requests. Install with `python3 -m pip install requests`.") from exc

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
INSIGHTS_PATH = DATA_DIR / "insights.json"
MONTHLY_REPORTS_PATH = DATA_DIR / "monthly_reports.json"
META_PATH = DATA_DIR / "meta.json"
TZ = dt.timezone(dt.timedelta(hours=8))

WECHAT_QUERIES = [
    "AI购物",
    "AI导购",
    "智能体购物",
    "购物智能体 零售",
    "AI电商闭环",
    "淘宝 千问 AI购物",
    "淘宝 AI万能搜 AI导购",
    "淘宝 AI试穿 虚拟试衣",
    "淘宝设计 AI试穿 服饰导购",
    "天猫 AI导购 天猫双11",
    "天猫 AI试穿 虚拟试穿",
    "豆包 AI购物",
    "京东AI购",
    "美团 小美 AI助手",
    "美团 AI导购 本地生活",
    "美团 小美 外卖 买菜 AI",
    "得物 AI试穿 AI试鞋",
    "得物 AI导购 球鞋",
    "虾皮 Shopee AI导购",
    "Shopee AI shopping assistant",
    "Amazon Rufus AI shopping assistant",
    "Amazon Alexa shopping assistant AI",
    "Walmart Sparky AI shopping assistant",
    "Walmart Gemini AI shopping",
    "Target AI shopping assistant",
    "Kohl's AI shopping assistant",
    "Instacart AI shopping checkout",
    "Pinterest AI shopping visual search",
    "Google virtual try on shopping AI",
    "Google AI Mode shopping virtual try on",
    "AI购物助手 电商",
    "Agentic Commerce",
    "Universal Commerce Protocol AI购物",
    "OpenClaw AI购物助手",
    "AI导购 产品设计",
    "AI购物 用户体验",
    "AI购物 交易闭环",
    "AI导购 商家",
    "AI搜索 电商",
    "AI购物 观点",
    "AI购物 案例",
]

RSS_SOURCES = [
    ("Google Shopping Blog", "海外", "https://blog.google/products-and-platforms/products/shopping/rss/"),
    ("Google Ads & Commerce Blog", "海外", "https://blog.google/products/ads-commerce/rss/"),
    ("OpenAI Blog", "海外", "https://openai.com/news/rss.xml"),
    ("Shopify Blog", "海外", "https://www.shopify.com/blog.atom"),
    ("TechCrunch", "海外", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge", "海外", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    ("Retail Dive", "海外", "https://www.retaildive.com/feeds/news/"),
    ("Practical Ecommerce", "海外", "https://www.practicalecommerce.com/feed"),
    ("Digital Commerce 360", "海外", "https://www.digitalcommerce360.com/feed/"),
    ("Modern Retail", "海外", "https://www.modernretail.co/feed/"),
    ("a16z", "海外", "https://a16z.com/feed/"),
]

GOOGLE_NEWS_QUERIES = [
    "AI shopping assistant",
    "agentic commerce",
    "AI shopping agent",
    "ChatGPT shopping",
    "Google AI shopping",
    "Amazon Rufus AI shopping",
    "Amazon Alexa AI shopping assistant",
    "Walmart Sparky AI shopping assistant",
    "Walmart Google Gemini AI assisted shopping",
    "Target AI shopping assistant holiday shopping",
    "Kohl's AI shopping assistant styling",
    "Instacart ChatGPT checkout AI shopping",
    "Pinterest AI shopping visual discovery",
    "Alibaba Aidge AI ecommerce assistant",
    "AliExpress AI shopping assistant",
    "Perplexity shopping AI",
    "Taobao AI shopping assistant",
    "Taobao AI try on virtual fitting",
    "Tmall AI shopping assistant",
    "Alibaba Qwen Taobao shopping AI",
    "Meituan Xiaomei AI assistant",
    "Meituan AI shopping local commerce",
    "Shopee AI shopping assistant",
    "Shopee AI recommendation shopping",
    "Dewu AI try on sneaker shopping",
    "Google AI virtual try on shopping",
    "Pinterest AI shopping assistant",
    "Walmart AI shopping assistant",
    "Instacart AI shopping assistant",
    "AI consumer app commerce",
    "conversational commerce AI",
    "AI retail assistant",
    "AI ecommerce assistant",
    "AI search shopping",
    "AI agent retail",
    "AI personal shopper product design",
    "AI shopping assistant case study",
    "AI shopping consumer behavior",
    "agentic commerce merchant",
    "agentic commerce checkout payment",
    "AI shopping product discovery",
    "AI shopping search recommendations",
    "AI shopping trust privacy",
    "AI shopping memory personalization",
    "retail AI agent customer experience",
    "site:aboutamazon.com/news/retail Rufus AI shopping",
    "site:aboutamazon.com/news/retail Alexa for Shopping AI assistant",
    "site:blog.google/products/shopping AI shopping",
    "site:corporate.walmart.com/news Sparky AI shopping",
    "site:corporate.target.com AI powered shopping features",
    "site:corporate.kohls.com AI shopping assistant",
    "site:company.instacart.com ChatGPT checkout Instacart",
    "site:newsroom.pinterest.com AI shopping visual search",
    "site:blog.google/products/ads-commerce agentic commerce",
    "site:shopify.com/blog AI ecommerce shopping",
    "site:stripe.com agentic commerce",
    "site:mastercard.com agentic commerce",
    "site:visa.com AI commerce",
    "site:mckinsey.com AI retail ecommerce",
    "site:a16z.com AI consumer shopping",
    "site:retaildive.com AI shopping retail",
    "site:modernretail.co AI shopping",
    "site:practicalecommerce.com AI ecommerce",
    "site:digitalcommerce360.com AI shopping",
    "site:pymnts.com agentic commerce shopping",
    "site:techcrunch.com AI shopping assistant",
    "site:theverge.com AI shopping",
    "consumer AI app",
    "ChatGPT app consumer assistant shopping search",
    "ChatGPT tasks shopping assistant consumer",
    "OpenAI operator shopping consumer",
    "OpenAI ChatGPT search shopping recommendations",
    "Gemini app shopping search consumer assistant",
    "Google Gemini AI personal assistant shopping",
    "Google AI Mode shopping try on product comparison",
    "Google Lens AI shopping visual search",
    "Claude app consumer assistant computer use shopping",
    "Anthropic Claude computer use shopping agent",
    "Perplexity AI shopping answer engine",
    "Perplexity Comet browser shopping assistant",
    "AI browser shopping assistant agent",
    "AI personal assistant shopping memory",
    "AI wearable assistant shopping recommendations",
    "Meta AI shopping assistant product discovery",
    "Copilot shopping assistant Microsoft Edge",
    "TikTok Shop AI shopping assistant",
    "eBay AI shopping assistant magical listing",
    "Etsy AI gift mode shopping assistant",
    "Zalando AI fashion assistant",
    "Klarna AI shopping assistant",
    "PayPal AI shopping agent checkout",
    "Shopify Sidekick AI merchant ecommerce",
    "Shopify agentic commerce AI shopping",
    "AI购物",
    "AI导购",
    "淘宝 AI万能搜",
    "淘宝 AI试穿",
    "淘宝设计 AI试穿",
    "淘宝设计 AI 试衣 服饰 导购",
    "天猫 AI导购",
    "天猫 AI试穿",
    "千问 淘宝 闪购 AI购物",
    "通义千问 淘宝 AI购物 助手",
    "通义千问 电商 导购",
    "夸克 AI搜索 购物 电商",
    "豆包 AI助手 购物 搜索",
    "Kimi AI助手 购物 搜索",
    "元宝 AI助手 购物 搜索",
    "阿里 悟空 电商 AI Agent",
    "阿里 Aidge AI电商 商家",
    "美团 小美 AI助手",
    "美团 AI导购",
    "美团 问小团 AI搜索 本地生活",
    "美团 小美 外卖 点餐 AI助手",
    "京东 AI导购 京言 智能购物助手",
    "京东 言犀 AI导购 购物助手",
    "京东 AI试穿 AI购物",
    "得物 AI试穿",
    "得物 AI鉴别机器人 WAIC",
    "得物 AI导购 球鞋 试穿",
    "虾皮 AI导购",
    "Shopee AI Copilot sellers shopping",
    "小红书 AI搜索 购物 种草",
    "抖音电商 AI导购 搜索",
    "快手电商 AI导购 智能客服",
    "购物智能体",
    "AI电商",
    "AI购物 产品设计",
    "AI导购 用户体验",
    "AI购物 交易闭环",
    "AI导购 商家 可见性",
    "AI购物 复购 记忆",
    "AI购物 支付 履约",
    "AI导购 观点 案例",
    "对话式购物",
    "智能体商业",
]

SOURCE_WEIGHT = {
    "灵工研习社": 14,
    "商业六和岛": 12,
    "神神叨叨的EK": 12,
    "比特拈花": 12,
    "架构师之道": 12,
    "TechWeb": 10,
    "新华网": 13,
    "新京报": 12,
    "界面新闻": 12,
    "北京商报": 11,
    "21财经": 11,
    "央广网": 11,
    "驱动之家": 10,
    "新浪财经": 10,
    "证券时报": 10,
    "天下网商": 12,
    "淘宝设计": 13,
    "三易生活": 10,
    "i黑马": 10,
    "商派": 9,
    "艾奇SEM": 8,
    "GEO优化实战派": 8,
    "Google Shopping Blog": 14,
    "Google Ads & Commerce Blog": 14,
    "Google Blog": 14,
    "OpenAI Blog": 13,
    "About Amazon": 13,
    "Walmart Corporate": 13,
    "Target Corporation": 12,
    "Kohl's Corporate": 11,
    "Instacart": 11,
    "Pinterest Newsroom": 10,
    "Shopify Blog": 10,
    "Anthropic": 13,
    "Stripe": 12,
    "Mastercard": 12,
    "Visa": 12,
    "McKinsey & Company": 12,
    "a16z": 11,
    "Digital Commerce 360": 11,
    "Retail Dive": 10,
    "Modern Retail": 10,
    "Practical Ecommerce": 10,
    "PYMNTS.com": 9,
    "The Verge": 8,
    "TechCrunch": 8,
    "36氪": 8,
    "虎嗅": 8,
    "钛媒体": 8,
    "亿邦动力网": 8,
    "人人都是产品经理": 7,
}

TAG_RULES = {
    "C端AI产品": ["consumer ai", "ai app", "ai assistant app", "personal assistant", "ai browser", "ai wearable", "chatgpt", "gemini", "claude", "perplexity", "copilot", "meta ai", "grok", "operator", "comet", "豆包", "kimi", "通义千问", "千问", "夸克", "元宝", "大模型应用", "ai助手", "ai搜索"],
    "AI搜索": ["ai search", "answer engine", "perplexity", "comet", "ai mode", "ai搜索", "答案引擎", "搜索助手", "夸克"],
    "AI购物": ["ai购物", "购物助手", "购物智能体", "ai shopping", "shopping agent", "agentic shopping", "ai commerce", "online shopping", "cart assistant"],
    "对话导购": ["导购", "对话式", "conversation", "conversational"],
    "竞品案例": ["淘宝", "天猫", "千问", "美团", "小美", "问小团", "京东", "京言", "言犀", "虾皮", "shopee", "亚马逊", "amazon", "rufus", "alexa", "得物", "小红书", "抖音电商", "快手电商", "walmart", "sparky", "target", "kohl", "instacart", "pinterest", "aidge", "aliexpress", "tiktok shop", "ebay", "etsy", "zalando", "klarna", "paypal"],
    "虚拟试穿": ["试穿", "试衣", "试鞋", "virtual try", "try-on", "try on", "virtual fitting", "fitting room", "augmented reality"],
    "Agentic Commerce": ["agentic commerce", "agentic shopping", "intelligent commerce", "智能体商业", "代理购物"],
    "交易闭环": ["闭环", "下单", "支付", "checkout", "checkouts", "交易", "购物车", "universal cart", "cart assistant"],
    "商品库": ["商品", "sku", "库存", "价格", "履约", "product data", "catalog", "metrics"],
    "即时零售": ["即时零售", "闪购", "买菜", "外卖"],
    "GEO": ["geo", "ai可见性", "可见性", "搜索"],
    "商家Agent": ["商家", "merchant", "seller", "卖家"],
    "技术架构": ["架构", "开源", "blueprint", "protocol", "ucp", "openclaw", "claude"],
}

INSIGHT_RULES = {
    "decision-os": ["决策", "意图", "约束", "比较", "推荐", "assistant", "搜索"],
    "memory-as-asset": ["记忆", "偏好", "画像", "复购", "personalization", "context", "habit"],
    "trust-ladder": ["代买", "替你购物", "授权", "助手", "购物智能体"],
    "closed-loop-first": ["闭环", "支付", "下单", "履约", "售后", "checkout", "order"],
    "answer-shelf": ["答案", "货架", "推荐位", "搜索", "可见性", "candidate"],
    "data-transaction-moat": ["商品", "库存", "价格", "履约", "淘宝", "京东", "闭环"],
    "agentic-funnel": ["agentic commerce", "checkout", "可见性", "geo", "入口"],
    "multi-agent-commerce": ["claude", "blueprint", "商家", "merchant", "openclaw", "agent"],
    "multi-agent-market": ["买方agent", "卖方agent", "商家", "merchant", "撮合", "交易网络"],
    "structured-dialogue": ["导购", "架构", "对话", "搜索", "推荐"],
    "high-frequency-entry": ["即时零售", "闪购", "买菜", "复购", "外卖"],
    "habit-before-intelligence": ["高频", "习惯", "复购", "日常", "买菜", "外卖"],
    "category-wedge": ["品类", "非标", "标品", "高客单", "家电", "服饰"],
    "risk-first-design": ["风险", "失败", "误购", "兜底", "退货", "售后"],
    "evidence-led-recommendation": ["证据", "评价", "测评", "评论", "理由", "可信"],
    "intent-cart": ["购物车", "cart", "收藏", "价格提醒", "未完成", "意图"],
    "contextual-entry": ["入口", "场景", "视觉", "内容", "种草", "图片"],
    "privacy-permission": ["隐私", "权限", "授权", "预算", "个人信息"],
    "post-purchase-agent": ["售后", "物流", "退换货", "保价", "post-purchase"],
    "merchant-incentive": ["商家激励", "归因", "广告", "供给", "seller", "merchant"],
    "ranking-governance": ["排序", "治理", "赞助", "公平", "责任", "ranking"],
    "from-comparison-to-negotiation": ["比价", "议价", "报价", "优惠", "谈条件", "动态价格"],
    "social-proof-rebuild": ["评价", "口碑", "评论", "虚假评价", "social proof"],
    "merchant-readable-store": ["geo", "商家", "卖家", "商品资料", "可见性"],
    "competitor-function-radar": ["淘宝", "天猫", "千问", "美团", "小美", "问小团", "shopee", "虾皮", "amazon", "rufus", "alexa", "walmart", "sparky", "target", "kohl", "instacart", "pinterest", "得物"],
    "visual-try-on-as-proof": ["试穿", "试衣", "试鞋", "virtual try", "try-on", "virtual fitting", "fitting room", "服饰导购", "ai试穿", "造型导购"],
    "local-life-agent-loop": ["美团", "小美", "问小团", "本地生活", "外卖", "买菜", "到店"],
}

AUTO_INSIGHT_PREFIX = "auto-"
DAILY_INSIGHT_PREFIX = "daily-reflection-"
SPARK_INSIGHT_PREFIX = "spark-"

NEGATIVE_WORDS = ["融资", "培训", "课程", "招商", "广告", "大会报名", "招聘", "破解版"]
BLOCKED_URL_HOSTS = {"ebrun.com", "ttplus.cn"}
LOW_VALUE_SOURCES = {"Stocktwits", "stocktwits.com", "体坛", "体坛网", "ttplus.cn"}
LOW_VALUE_TITLE_PATTERNS = [
    "dunkin", "chief merchant", "ad auction", "fulfillment center", "tire benefit",
    "stock gains", "pre-market", "price target", "shares rise", "shares fall", "earnings call",
    "token充值", "充值中心", "多人工作台", "measurement stack", "new ecommerce tools",
    "倒计时", "报名", "大会", "峰会", "webinar", "conference", "top 100 business trends",
    "ai tools for shopee sellers", "tools for shopee sellers",
]
HIGH_VALUE_WORDS = [
    "闭环", "智能体", "Agentic Commerce", "导购", "购物助手", "千问", "豆包", "淘宝",
    "京东", "Rufus", "Claude", "OpenClaw", "Universal Commerce Protocol", "UCP",
    "支付", "checkout", "履约", "复购", "GEO", "AI可见性", "商品库", "架构",
    "天猫", "美团", "小美", "虾皮", "Shopee", "得物", "试穿", "试衣", "试鞋",
    "virtual try", "try-on", "AI万能搜", "Alexa", "Walmart", "Sparky", "Target",
    "Kohl", "Instacart", "Pinterest", "问小团", "Aidge", "AliExpress",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def is_blocked_source_or_url(item: dict[str, Any]) -> bool:
    host = urllib.parse.urlsplit(item.get("url", "")).netloc.lower().removeprefix("www.").removeprefix("m.")
    if host in BLOCKED_URL_HOSTS or item.get("source") in LOW_VALUE_SOURCES:
        return True
    title = item.get("title", "").lower()
    if is_ai_shopping_related(item) is False and item.get("source") == "AI Shopping Radar":
        return True
    if any(word in item.get("title", "") for word in ["体育投注", "注册在线", "资料检索入口", "每日雷达"]):
        return True
    return any(pattern in title for pattern in LOW_VALUE_TITLE_PATTERNS)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(value: str) -> str:
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:10]
    ascii_part = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:42]
    return f"{ascii_part}-{digest}" if ascii_part else digest


def parse_wechat_date(block: str) -> str:
    match = re.search(r"timeConvert\('?([0-9]+)'?\)", block)
    if not match:
        return ""
    return dt.datetime.fromtimestamp(int(match.group(1)), TZ).date().isoformat()


def resolve_sogou_link(session: requests.Session, link: str, referer: str) -> str:
    link = clean_url(link)
    try:
        response = session.get(link, headers={"Referer": referer}, timeout=12, allow_redirects=False)
    except requests.RequestException:
        return link
    chunks = re.findall(r"url \+= '([^']*)'", response.text)
    if chunks:
        return clean_url("".join(chunks).replace("@", ""))
    location = response.headers.get("Location", "")
    if location and "antispider" not in location:
        return clean_url(urllib.parse.urljoin(link, location))
    return link


def decode_google_news_url(session: requests.Session, url: str) -> str:
    url = clean_url(url)
    parsed = urllib.parse.urlsplit(url)
    if parsed.netloc.lower() != "news.google.com" or "/articles/" not in parsed.path and "/read/" not in parsed.path:
        return url
    article_id = parsed.path.rstrip("/").split("/")[-1]
    try:
        response = session.get(f"https://news.google.com/articles/{article_id}", timeout=12)
        signature_match = re.search(r'data-n-a-sg="([^"]+)"', response.text)
        timestamp_match = re.search(r'data-n-a-ts="([^"]+)"', response.text)
        if not signature_match or not timestamp_match:
            return url
        payload = [
            "Fbv4je",
            f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{article_id}",{timestamp_match.group(1)},"{signature_match.group(1)}"]',
        ]
        decoded = session.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute?rpcids=Fbv4je",
            data="f.req=" + urllib.parse.quote(json.dumps([[payload]])),
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            timeout=12,
        )
        parsed_rows = json.loads(decoded.text.split("\n\n", 1)[1])[:-2]
        original = json.loads(parsed_rows[0][2])[1]
        return clean_url(original) if original.startswith("http") else url
    except Exception:
        return url


def fetch_wechat(days: int) -> list[dict[str, Any]]:
    cutoff = (dt.datetime.now(TZ).date() - dt.timedelta(days=days))
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://weixin.sogou.com/",
    })
    items: list[dict[str, Any]] = []
    for query in WECHAT_QUERIES:
        try:
            response = session.get(
                "https://weixin.sogou.com/weixin",
                params={"type": "2", "query": query, "ie": "utf8", "_sug_": "n", "_sug_type_": ""},
                timeout=12,
            )
        except requests.RequestException:
            continue
        blocks = re.findall(r'<li[^>]*id="sogou_vr_.*?</li>', response.text, flags=re.S)
        for block in blocks[:10]:
            title_match = re.search(r'<h3.*?<a[^>]*href="(.*?)"[^>]*>(.*?)</a>', block, flags=re.S)
            if not title_match:
                continue
            date = parse_wechat_date(block)
            if date and dt.date.fromisoformat(date) < cutoff:
                continue
            summary_match = re.search(r'<p class="txt-info"[^>]*>(.*?)</p>', block, flags=re.S)
            source_match = re.search(r'<span class="all-time-y2">(.*?)</span>', block, flags=re.S)
            title = clean_text(title_match.group(2))
            snippet = clean_text(summary_match.group(1)) if summary_match else ""
            source = canonical_source(clean_text(source_match.group(1)) if source_match else "微信公众号")
            title = clean_display_title(title, source)
            link = urllib.parse.urljoin("https://weixin.sogou.com/weixin", clean_url(title_match.group(1)))
            items.append({
                "date": date or dt.datetime.now(TZ).date().isoformat(),
                "title": title,
                "source": source,
                "region": "国内",
                "url": link,
                "snippet": snippet,
                "query": query,
                "rawUrl": link,
                "needsResolve": True,
            })
        time.sleep(0.25)
    resolved_items = []
    for item in items:
        if item.get("needsResolve"):
            resolved_url = resolve_sogou_link(session, item["rawUrl"], "https://weixin.sogou.com/weixin")
            if "weixin.sogou.com" in resolved_url or is_temporary_wechat_url(resolved_url):
                continue
            item["url"] = resolved_url
            time.sleep(0.15)
        resolved_items.append(item)
    return resolved_items


def parse_rss_date(value: str) -> str:
    if not value:
        return dt.datetime.now(TZ).date().isoformat()
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(TZ).date().isoformat()
    except Exception:
        return dt.datetime.now(TZ).date().isoformat()


def fetch_rss(days: int) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(TZ).date() - dt.timedelta(days=days)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    items: list[dict[str, Any]] = []
    for source, region, url in RSS_SOURCES:
        source = canonical_source(source)
        try:
            response = session.get(url, timeout=15)
            root = ET.fromstring(response.content)
        except Exception:
            continue
        for node in root.findall(".//item") + root.findall("{http://www.w3.org/2005/Atom}entry"):
            title = clean_display_title(clean_text((node.findtext("title") or "")), source)
            link = node.findtext("link") or ""
            if not link:
                link_node = node.find("{http://www.w3.org/2005/Atom}link")
                link = link_node.attrib.get("href", "") if link_node is not None else ""
            description = clean_text(node.findtext("description") or node.findtext("summary") or "")
            date = parse_rss_date(node.findtext("pubDate") or node.findtext("updated") or node.findtext("published") or "")
            if dt.date.fromisoformat(date) < cutoff:
                continue
            items.append({
                "date": date,
                "title": title,
                "source": source,
                "region": region,
                "url": link,
                "snippet": description,
                "query": source,
            })
    return items


def fetch_google_news(days: int, max_queries: int | None = None) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(TZ).date() - dt.timedelta(days=days)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    items: list[dict[str, Any]] = []
    queries = GOOGLE_NEWS_QUERIES[:max_queries] if max_queries else GOOGLE_NEWS_QUERIES
    for query in queries:
        for lang, gl, ceid in [("en-US", "US", "US:en"), ("zh-CN", "CN", "CN:zh-Hans")]:
            try:
                response = session.get(
                    "https://news.google.com/rss/search",
                    params={"q": f"{query} when:{days}d", "hl": lang, "gl": gl, "ceid": ceid},
                    timeout=15,
                )
                root = ET.fromstring(response.content)
            except Exception:
                continue
            for node in root.findall(".//item")[:25]:
                raw_source = clean_text(node.findtext("source") or "Google News")
                source = canonical_source(raw_source)
                title = clean_display_title(clean_text(node.findtext("title") or ""), source)
                link = node.findtext("link") or ""
                description = clean_text(node.findtext("description") or "")
                date = parse_rss_date(node.findtext("pubDate") or "")
                if dt.date.fromisoformat(date) < cutoff:
                    continue
                items.append({
                    "date": date,
                    "title": title,
                    "source": source,
                    "region": "国内" if re.search(r"[\u4e00-\u9fa5]", title + source) else "海外",
                    "url": link,
                    "snippet": description,
                    "query": query,
                })
            time.sleep(0.03)
    return items


def contains_term(text: str, term: str) -> bool:
    """Match terms conservatively so short English fragments do not create false tags."""
    term = term.strip().lower()
    if not term:
        return False
    lower = text.lower()
    if re.search(r"[\u4e00-\u9fa5]", term):
        return term in lower
    escaped = re.escape(term).replace(r"\ ", r"[\s\-_]+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", lower) is not None


def contains_any(text: str, terms: list[str]) -> bool:
    return any(contains_term(text, term) for term in terms)


def infer_tags(text: str) -> list[str]:
    tags = [tag for tag, words in TAG_RULES.items() if contains_any(text, words)]
    return tags[:6]


def article_context(item: dict[str, Any], include_existing_analysis: bool = False) -> str:
    parts = [
        str(item.get("title", "")),
        str(item.get("snippet", "")),
        str(item.get("excerpt", "")),
        str(item.get("source", "")),
        " ".join(item.get("tags", []) or []),
    ]
    if include_existing_analysis:
        parts.extend([str(item.get("corePoint", "")), str(item.get("insight", ""))])
    return " ".join(parts)


def is_visual_try_on_context(text: str) -> bool:
    return contains_any(text, [
        "AI试穿", "虚拟试穿", "试穿", "试衣", "试鞋", "virtual try-on", "virtual try on",
        "try-on", "try on", "virtual fitting", "fitting room", "digital try-on",
    ])


def article_angles(item: dict[str, Any], tags: list[str]) -> list[str]:
    text = article_context({**item, "tags": tags})
    title = str(item.get("title", ""))
    lower = text.lower()
    angles: list[str] = []
    if contains_any(title, ["stock", "price target", "pre-market", "premarket", "shares", "q2", "sales decline", "earnings"]):
        angles.append("market_signal")
    if contains_any(text, ["tested", "i let", "which worked best", "perfect gift", "gift", "hands-on", "实测", "测评"]):
        angles.append("consumer_benchmark")
    if contains_any(text, ["perplexity", "ai search", "ai mode", "ai traffic", "answer engine", "search traffic", "google discover", "ai搜索", "答案引擎", "夸克"]):
        angles.append("ai_search_commerce")
    if contains_any(text, ["agentic commerce", "checkout", "checkouts", "payment", "payments", "visa", "mastercard", "stripe", "rain", "acquirer", "支付", "结算", "收单", "协议", "信任协议"]):
        angles.append("agentic_checkout")
    if is_visual_try_on_context(text):
        angles.append("visual_try_on")
    if contains_any(text, ["product data", "catalog", "商品数据", "商品库", "库存", "价格", "metrics", "可见性", "GEO", "machine readable", "机器可读"]):
        angles.append("product_data")
    if contains_any(text, ["merchant", "seller", "商家", "卖家", "google ads", "广告", "投放", "campaign", "aidge"]):
        angles.append("merchant_tools")
    if contains_any(text, ["小美", "问小团", "美团", "闪购", "即时零售", "外卖", "买菜", "本地生活", "quick-commerce", "grocery"]):
        angles.append("local_life")
    if contains_any(text, ["chatgpt", "openai", "operator", "perplexity", "comet", "gemini", "claude", "copilot", "meta ai", "rufus", "alexa for shopping", "sparky", "ai shopping assistant", "ai-powered shopping", "ai万能搜", "千问", "通义", "淘宝", "天猫", "京东", "京言", "言犀", "shopee", "虾皮", "instacart", "pinterest", "kohl", "target", "walmart", "tiktok shop", "ebay", "etsy", "zalando", "klarna", "paypal"]):
        angles.append("platform_assistant")
    if contains_any(text, ["search", "discovery", "recommendation", "recommendations", "visual search", "collage", "发现", "搜索", "推荐", "逛", "种草"]):
        angles.append("discovery_decision")
    if contains_any(text, ["trust", "privacy", "wary", "risk", "fraud", "安全", "隐私", "信任", "风险", "虚假评价"]):
        angles.append("trust_risk")
    if contains_any(text, ["memory", "personalization", "personalized", "preference", "context", "habit", "记忆", "偏好", "个性化", "上下文"]):
        angles.append("memory_personalization")
    if contains_any(text, ["voice", "image", "camera", "lens", "multimodal", "视觉", "语音", "图片", "拍照", "多模态", "识图"]):
        angles.append("multimodal_entry")
    if not angles:
        angles.append("general_signal")
    return list(dict.fromkeys(angles))[:4]


def is_relevant(item: dict[str, Any], tags: list[str]) -> bool:
    if is_blocked_source_or_url(item):
        return False
    if not tags:
        return False
    return is_grounded_ai_shopping_item(item, tags) or is_grounded_consumer_ai_item(item, tags)


def is_grounded_consumer_ai_item(item: dict[str, Any], tags: list[str]) -> bool:
    source_text = article_context({**item, "tags": []})
    has_ai_product = contains_any(source_text, [
        "ChatGPT", "OpenAI", "Gemini", "Claude", "Perplexity", "Copilot", "Meta AI", "Grok",
        "AI app", "AI assistant", "AI browser", "AI search", "answer engine", "consumer AI", "personal assistant",
        "豆包", "Kimi", "通义千问", "千问", "夸克", "元宝", "大模型应用", "AI助手", "AI搜索", "智能助手",
    ])
    has_consumer_signal = contains_any(source_text, [
        "app", "browser", "search", "assistant", "mobile", "consumer", "users", "launch", "feature",
        "应用", "助手", "搜索", "浏览器", "入口", "用户", "上线", "功能", "产品", "体验",
    ])
    commerce_bridge = contains_any(source_text, [
        "shopping", "commerce", "retail", "merchant", "seller", "checkout", "personal shopper", "product discovery", "buying", "purchase",
        "购物", "导购", "电商", "零售", "商品", "商家", "比价", "下单", "支付", "本地生活",
    ])
    product_design_signal = contains_any(source_text, [
        "memory", "personalization", "agent", "operator", "browser", "computer use", "tasks", "assistant", "entry point", "workflow",
        "记忆", "偏好", "智能体", "入口", "工作流", "多模态", "浏览器", "联网搜索", "个人助手",
    ])
    low_value = contains_any(source_text, ["training", "course", "招聘", "培训", "课程", "融资", "股价", "stock", "earnings"])
    return has_ai_product and has_consumer_signal and (commerce_bridge or product_design_signal) and not low_value


def is_grounded_ai_shopping_item(item: dict[str, Any], tags: list[str]) -> bool:
    source_text = article_context({**item, "tags": []})
    has_ai = contains_any(source_text, [
        "AI", "artificial intelligence", "generative AI", "ChatGPT", "OpenAI", "Gemini", "Claude",
        "Perplexity", "Bedrock", "AgentCore", "OpenClaw", "agentic", "intelligent commerce",
        "智能体", "人工智能", "大模型", "千问", "豆包",
    ])
    has_commerce = contains_any(source_text, [
        "shopping", "shop", "shoppers", "commerce", "ecommerce", "e-commerce", "retail", "retailer", "retailers",
        "checkout", "checkouts", "cart", "merchant", "seller", "sellers", "storefront", "sales", "gift", "gifts", "buying", "purchase", "product data", "catalog",
        "淘宝", "天猫", "京东", "美团", "闪购", "点单", "Shopee", "Instacart", "Shopify", "Walmart", "Target",
        "购物", "导购", "电商", "零售", "商品", "商家", "支付", "下单", "履约",
    ])
    has_specific_signal = contains_any(source_text, [
        "AI购物", "AI导购", "AI万能搜", "购物智能体", "agentic commerce", "agentic shopping",
        "ai shopping assistant", "shopping agent", "alexa for shopping", "cart assistant", "universal cart",
        "online shopping", "virtual try-on", "虚拟试穿", "AI试穿",
    ])
    has_real_try_on = is_visual_try_on_context(source_text) and contains_any(source_text, ["shopping", "ecommerce", "commerce", "服饰", "鞋", "美妆", "购物", "电商"])
    if has_specific_signal or has_real_try_on:
        return True
    if has_ai and has_commerce:
        return True
    if "竞品案例" in tags and not has_ai and not has_specific_signal:
        return False
    return False


def is_relevant_existing_item(item: dict[str, Any]) -> bool:
    tags = item.get("tags", []) or infer_tags(article_context({**item, "tags": []}))
    return is_grounded_ai_shopping_item(item, tags) or is_grounded_consumer_ai_item(item, tags)


def infer_category(tags: list[str], text: str) -> str:
    lower = text.lower()
    if "虚拟试穿" in tags:
        return "竞品功能"
    if "C端AI产品" in tags:
        return "C端AI产品"
    if "AI搜索" in tags:
        return "AI搜索"
    if "技术架构" in tags or any(word in lower for word in ["架构", "blueprint", "protocol", "openclaw"]):
        return "技术架构"
    if any(word in lower for word in ["周报", "动态", "趋势"]):
        return "行业动态"
    if "竞品案例" in tags or any(word in lower for word in ["淘宝", "天猫", "千问", "豆包", "京东", "美团", "小美", "问小团", "虾皮", "shopee", "得物", "rufus", "alexa", "walmart", "sparky", "target", "kohl", "instacart", "pinterest", "aidge", "aliexpress", "meta"]):
        return "平台案例"
    if "GEO" in tags or "AI可见性" in text:
        return "增长/GEO"
    return "趋势框架"


def infer_content_type(tags: list[str], category: str, text: str, source: str = "") -> str:
    lower = text.lower()
    if "竞品案例" in tags or category in {"平台案例", "竞品功能"}:
        return "竞品"
    if "C端AI产品" in tags or "AI搜索" in tags:
        return "C端产品"
    if "技术架构" in tags or any(word in lower for word in ["protocol", "blueprint", "openclaw", "ucp", "mcp", "协议", "架构"]):
        return "技术/协议"
    if "商家Agent" in tags or category == "商家/生态" or any(word in lower for word in ["merchant", "seller", "商家", "卖家", "生态"]):
        return "商家生态"
    if any(word in lower for word in ["report", "survey", "forecast", "research", "调研", "报告", "预测", "数据"]):
        return "研究数据"
    if any(word in lower for word in ["观点", "深度", "why", "how", "解析", "复盘", "拆解"]):
        return "深度观点"
    if category in {"C端AI产品", "产品功能", "AI搜索", "智能体购物"}:
        return "产品功能"
    return "行业新闻"


def score_item(item: dict[str, Any], tags: list[str]) -> int:
    text = f"{item['title']} {item.get('snippet', '')}"
    score = 45 + SOURCE_WEIGHT.get(item.get("source", ""), 0) + len(tags) * 5
    score += sum(6 for word in HIGH_VALUE_WORDS if word.lower() in text.lower())
    score -= sum(12 for word in NEGATIVE_WORDS if word in text)
    try:
        age = (dt.datetime.now(TZ).date() - dt.date.fromisoformat(item["date"])).days
        score += max(0, 10 - age // 3)
    except Exception:
        pass
    if len(item.get("snippet", "")) < 35:
        score -= 8
    return min(99, max(0, score))


def fetch_article_excerpt(url: str, session: requests.Session) -> str:
    if not url or "weixin.sogou.com" in url:
        return ""
    try:
        response = session.get(url, timeout=8, allow_redirects=True)
        content_type = response.headers.get("content-type", "")
        if response.status_code >= 400 or "html" not in content_type.lower():
            return ""
        document = response.text[:500_000]
    except Exception:
        return ""
    meta_chunks = re.findall(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\'][^>]+content=["\']([^"\']+)["\']',
        document,
        flags=re.I,
    )
    body = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<noscript[\s\S]*?</noscript>", " ", document, flags=re.I)
    paragraphs = re.findall(r"<p[^>]*>([\s\S]*?)</p>", body, flags=re.I)
    chunks = meta_chunks + paragraphs[:8]
    cleaned: list[str] = []
    for chunk in chunks:
        text = clean_text(html.unescape(re.sub(r"<[^>]+>", " ", chunk)))
        if len(text) >= 24 and not re.search(r"cookie|subscribe|sign up|©|privacy policy", text, re.I):
            cleaned.append(text)
    return clean_text(" ".join(dict.fromkeys(cleaned)))[:900]


def recompute_article_fields(item: dict[str, Any], keep_score: bool = False) -> dict[str, Any]:
    item = dict(item)
    item["source"] = canonical_source(item.get("source", ""))
    item["title"] = clean_display_title(item.get("title", ""), item["source"])
    if "excerpt" in item:
        item["excerpt"] = clean_text(item.get("excerpt", ""))[:900]
    tag_source = dict(item)
    tag_source["tags"] = []
    text = article_context(tag_source)
    tags = infer_tags(text)
    if not tags and contains_any(text, ["AI", "OpenAI", "ChatGPT", "agent", "智能体", "导购", "购物"]):
        tags = ["AI购物"]
    category = infer_category(tags, text)
    content_type = infer_content_type(tags, category, text, item["source"])
    core_points = make_core_point(item, tags)
    item["corePoint"] = core_points
    insight = personalize_insight(item, make_insight(item, tags))
    item.update({
        "contentType": content_type,
        "category": category,
        "tags": tags,
        "corePoint": core_points,
        "insight": insight,
        "relatedInsightIds": related_insights_for_item(item, tags),
    })
    if not keep_score:
        item["valueScore"] = score_item(item, tags)
    return item


def related_insights(text: str) -> list[str]:
    ids = [insight_id for insight_id, words in INSIGHT_RULES.items() if contains_any(text, words)]
    return ids[:3] or ["structured-dialogue"]


ANGLE_RELATED_INSIGHTS = {
    "market_signal": ["competitor-function-radar", "agentic-funnel"],
    "consumer_benchmark": ["evidence-led-recommendation", "trust-ladder", "decision-os"],
    "ai_search_commerce": ["answer-shelf", "merchant-readable-store", "agentic-funnel"],
    "agentic_checkout": ["closed-loop-first", "trust-ladder", "agentic-funnel"],
    "visual_try_on": ["visual-try-on-as-proof", "evidence-led-recommendation", "category-wedge"],
    "product_data": ["data-transaction-moat", "merchant-readable-store", "ranking-governance"],
    "merchant_tools": ["merchant-incentive", "merchant-readable-store", "multi-agent-market"],
    "local_life": ["local-life-agent-loop", "high-frequency-entry", "habit-before-intelligence"],
    "platform_assistant": ["competitor-function-radar", "decision-os", "closed-loop-first"],
    "discovery_decision": ["decision-os", "answer-shelf", "evidence-led-recommendation"],
    "trust_risk": ["trust-ladder", "privacy-permission", "risk-first-design"],
    "general_signal": ["structured-dialogue"],
}


def related_insights_for_item(item: dict[str, Any], tags: list[str]) -> list[str]:
    ids: list[str] = []
    for angle in article_angles(item, tags):
        ids.extend(ANGLE_RELATED_INSIGHTS.get(angle, []))
    ids.extend(related_insights(article_context({**item, "tags": tags})))
    return list(dict.fromkeys(ids))[:3]


def excerpt_points(item: dict[str, Any], max_points: int = 2) -> list[str]:
    excerpt = clean_text(item.get("excerpt", ""))
    if not excerpt:
        return []
    title_sig = normalized_title(item.get("title", ""), item.get("source", ""))
    sentences = re.split(r"(?<=[。！？.!?])\s+|[；;]", excerpt)
    points: list[str] = []
    for sentence in sentences:
        sentence = clean_text(sentence).strip(" ，,。.;；")
        if len(sentence) < 18 or len(sentence) > 120:
            continue
        sentence_sig = normalized_title(sentence, item.get("source", ""))
        if title_sig and sentence_sig and (sentence_sig in title_sig or title_sig in sentence_sig):
            continue
        if contains_any(sentence, ["AI", "agent", "shopping", "commerce", "retail", "merchant", "checkout", "购物", "导购", "电商", "零售", "商家", "支付", "商品"]):
            points.append(sentence)
        if len(points) >= max_points:
            break
    return points


def clean_core_points(points: list[str], max_points: int = 3) -> list[str]:
    cleaned: list[str] = []
    for point in points:
        point = clean_text(str(point)).strip(" ，,。.;；")
        point = re.sub(r"^《[^》]{4,120}》(?:的|显示|说明|聚焦|强调|提醒|从|更像|展示)?", "", point)
        point = re.sub(r"^围绕[“\"][^”\"]+[”\"]，?", "", point)
        point = point.strip(" ：:，,")
        if not point or len(point) < 8:
            continue
        if point not in cleaned:
            cleaned.append(point)
        if len(cleaned) >= max_points:
            break
    return cleaned or ["这条资讯提供了AI购物/导购相关信号，但公开摘要信息有限，需要打开原文进一步确认细节。"]


def core_point_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value or "")


ENTITY_RULES = [
    ("淘宝", ["淘宝", "天猫", "千问", "qwen", "alibaba", "aliexpress", "阿里"]),
    ("美团", ["美团", "小美", "问小团", "keeta"]),
    ("京东", ["京东", "京言", "言犀", "jd.com"]),
    ("Amazon", ["amazon", "rufus", "alexa"]),
    ("Walmart", ["walmart", "sparky"]),
    ("Google", ["google", "gemini"]),
    ("OpenAI/ChatGPT", ["openai", "chatgpt"]),
    ("Perplexity", ["perplexity"]),
    ("小红书", ["小红书", "xiaohongshu"]),
    ("抖音电商", ["抖音电商", "tiktok shop"]),
    ("Shopify", ["shopify"]),
    ("Instacart", ["instacart"]),
    ("Visa/Mastercard", ["visa", "mastercard"]),
    ("Stripe", ["stripe"]),
    ("PayPal", ["paypal", "honey"]),
    ("Anthropic/Claude", ["anthropic", "claude"]),
    ("Target", ["target"]),
    ("Shopee", ["shopee", "虾皮"]),
    ("得物", ["得物"]),
    ("Pinterest", ["pinterest"]),
    ("Etsy", ["etsy"]),
    ("Klarna", ["klarna"]),
]


SCENARIO_RULES = [
    ("支付/结算", ["payment", "checkout", "token", "acquirer", "支付", "收单", "结算"]),
    ("商品数据/指标", ["product data", "catalog", "metrics", "measurement", "index", "forecast", "商品数据", "指标", "预测"]),
    ("AI购物助手", ["shopping assistant", "ai assistant", "assistant", "rufus", "alexa", "sparky", "购物助手", "导购"]),
    ("外部AI入口", ["chatgpt", "perplexity", "copilot", "answer engine", "ai search", "ai搜索"]),
    ("商家/供给侧", ["merchant", "seller", "retailer", "storefront", "marketplace", "商家", "卖家", "店铺", "marketplaces"]),
    ("转化/流量", ["conversion", "traffic", "sales", "spending", "%", "转化", "流量", "销售"]),
    ("试穿/视觉体验", ["try-on", "virtual try", "试穿", "试衣", "试鞋", "visual", "视觉"]),
    ("用户测评/信任", ["tested", "wary", "trust", "risk", "permission", "mistake", "实测", "信任", "风险", "授权"]),
    ("即时零售/本地生活", ["grocery", "quick-commerce", "instant", "闪购", "外卖", "买菜", "本地生活"]),
]


def detected_labels(text: str, rules: list[tuple[str, list[str]]], limit: int = 3) -> list[str]:
    labels = [label for label, words in rules if contains_any(text, words)]
    return labels[:limit]


def title_specific_points(item: dict[str, Any]) -> list[str]:
    text = article_context({**item, "tags": []})
    title = str(item.get("title", ""))
    lower = text.lower()
    entities = detected_labels(text, ENTITY_RULES, 3)
    scenarios = detected_labels(text, SCENARIO_RULES, 3)
    points: list[str] = []
    if entities or scenarios:
        entity_text = "、".join(entities) if entities else "行业案例"
        scenario_text = "、".join(scenarios) if scenarios else "AI购物"
        points.append(f"案例主体是{entity_text}，场景落在{scenario_text}。")
    if contains_any(text, ["not just", "beyond checkout", "full consumer experience"]):
        points.append("讨论重点从单点结算效率，扩大到端到端消费体验。")
    if contains_any(text, ["product data", "trusted product data", "catalog", "metrics", "measurement"]):
        points.append("商品数据、目录质量和效果指标被提升为AI购物基础设施。")
    if contains_any(text, ["23%", "48%", "40%", "$1 trillion", "trillion", "forecast", "index", "survey"]):
        points.append("文章提供了渗透率、交易规模或转化变化等量化信号。")
    if contains_any(text, ["marketplaces", "marketplace", "protect loyalty", "loyalty"]):
        points.append("商家面临渠道迁移和用户关系被AI入口截流的压力。")
    if contains_any(text, ["sues", "permission", "trusted", "risk", "mistake", "without permission", "trust"]):
        points.append("信任、授权和责任边界成为AI代购能否继续推进的关键问题。")
    if contains_any(text, ["app in chatgpt", "inside chatgpt", "instant checkout", "openai", "chatgpt apps", "paypal"]):
        points.append("交易能力正在嵌入外部AI入口，品牌自有站和平台入口关系被重新分配。")
    if contains_any(text, ["conversion", "spending", "traffic", "sales", "conversions jump"]):
        points.append("资讯把AI能力与转化、客单或流量变化直接关联。")
    if contains_any(title, ["how", "why", "what went wrong", "guide", "research"]):
        points.append("文章更偏机制拆解或方法论，而不是单纯功能发布。")
    cleaned: list[str] = []
    for point in points:
        point = clean_text(point).strip(" ，,。.;；")
        if point and point not in cleaned:
            cleaned.append(point)
    return cleaned[:3]


def make_specific_insight(item: dict[str, Any]) -> str:
    text = article_context({**item, "tags": []})
    entities = detected_labels(text, ENTITY_RULES, 2)
    scenarios = detected_labels(text, SCENARIO_RULES, 2)
    prefix = f"针对{'、'.join(entities)}的{'、'.join(scenarios) or 'AI购物'}信号，" if entities else "针对这类信号，"
    def choose(options: list[str]) -> str:
        digest = int(hashlib.sha1((item.get("id", "") + item.get("title", "")).encode("utf-8")).hexdigest()[:8], 16)
        return options[digest % len(options)]
    if contains_any(text, ["product data", "trusted product data", "catalog", "metrics", "measurement"]):
        return prefix + choose([
            "产品侧要把商品资料完整度、可引用证据、实时价格库存和转化指标做成同一套监控，而不是只优化对话回答。",
            "更值得沉淀的是商品事实层：卖点、适用人群、禁忌、库存和履约承诺越结构化，AI推荐越能被验证。",
            "可以把“AI是否看得懂这个商品”做成商家侧评分，倒逼供给资料从营销文案升级为机器可读证据。",
        ])
    if contains_any(text, ["merchant", "merchants", "seller", "sellers", "retailer", "retailers", "marketplace", "marketplaces", "protect loyalty", "storefront", "商家", "卖家"]):
        return prefix + choose([
            "需要给商家端提供AI可读商品页、卖点证据、履约承诺和归因工具，避免用户关系被外部AI入口截流。",
            "商家后台不应只生成素材，而要告诉商家AI为什么没有推荐它、缺哪些证据、该补什么卖点。",
            "平台要把商家激励重新设计：让商家愿意提交结构化禁忌、适用场景和售后承诺，用户端导购才有可信依据。",
        ])
    if contains_any(text, ["acquirer", "visa", "mastercard", "stripe", "payment", "checkout", "token", "支付", "收单", "结算"]):
        return prefix + choose([
            "支付不应被当作链路末端按钮，而要设计成可授权、可撤回、可追责的交易能力；否则AI越主动，误购和责任风险越大。",
            "可以把交易权限拆成建议、代填、锁价、代付、代买五级，让用户逐步授权，而不是一次性把购买权交给AI。",
            "支付链路的产品重点是异常处理：价格变化、缺货、延迟、误购时AI如何解释、暂停、回滚和追责。",
            "当智能体进入结算，推荐理由必须和支付凭证连起来，用户需要看到AI依据哪些约束完成了这笔交易。",
        ])
    if contains_any(text, ["app in chatgpt", "inside chatgpt", "instant checkout", "openai", "chatgpt", "perplexity", "paypal"]):
        return prefix + choose([
            "关键是承接外部AI带来的半成型意图：进入站内后继续保留上下文，并补齐比较、证据、优惠和确认，而不是重新让用户搜索。",
            "外部AI入口会让用户带着问题和候选进站，站内导购应识别这包上下文，并继续完成取舍、核价和交易确认。",
            "真正的机会不是抢入口，而是做“意图交接层”：把AI答案里的预算、场景、禁忌和候选转成站内可操作任务。",
        ])
    if contains_any(text, ["memory", "personalization", "personalized", "preference", "context", "habit", "记忆", "偏好", "个性化", "上下文"]):
        return prefix + choose([
            "记忆能力要产品化成用户可编辑的购买规则，例如预算、尺码、品牌黑白名单、复购周期和场景偏好；黑箱画像越强，用户越难放心授权。",
            "记忆不该只用于更准推荐，还要用于解释“这次为什么这样推荐”，让用户能检查、纠正和删除单条购买偏好。",
            "适合先把记忆用在低争议场景：复购、尺码、常买品牌、禁忌成分，再逐步进入高客单决策。",
        ])
    if contains_any(text, ["voice", "image", "camera", "lens", "multimodal", "视觉", "语音", "图片", "拍照", "多模态", "识图"]):
        return prefix + choose([
            "多模态不是展示炫技，而是降低需求输入成本；AI导购应把图片/语音里的场景、风格和限制条件转成候选商品与排除理由。",
            "图片和语音入口最适合捕捉用户说不清的需求，产品应把识别结果显性化，让用户确认AI理解的场景和风格。",
            "多模态导购要从“看见了什么”走到“因此排除了什么”，否则只是把搜索框换成相机。",
        ])
    if contains_any(text, ["operator", "computer use", "browser", "agent", "tasks", "workflow", "智能体", "浏览器", "任务", "工作流"]):
        return prefix + choose([
            "通用AI助手的启发是把导购拆成可接管的小任务：查证、比价、凑单、补货、售后提醒，而不是直接承诺全自动购买。",
            "智能体能力适合先进入可验证动作，例如抓取参数、生成对比、检查优惠，而不是一上来替用户做不可逆决策。",
            "如果AI能跨页面执行任务，购物产品更需要任务日志：它看了哪些页面、依据什么筛掉候选、在哪一步等待用户确认。",
        ])
    if contains_any(text, ["conversion", "spending", "traffic", "sales", "%", "转化", "流量"]):
        return prefix + choose([
            "不要只记录功能上线，要追踪它影响了哪一段漏斗：需求表达、候选点击、加购、客单、复购或售后成本。",
            "增长信号要拆到链路指标里看：AI到底提高了需求表达效率、减少比较成本，还是只带来了短期流量噪声。",
            "可以把AI导购实验按节点归因，分别观察搜索改写、推荐解释、对比证据、加购和下单的边际贡献。",
        ])
    if contains_any(text, ["tested", "i let", "which worked best", "perfect gift", "实测", "测评"]):
        return prefix + choose([
            "可以把真实测评拆成验收清单：是否理解约束、是否核价核库存、是否给替代方案、是否说明不推荐的理由。",
            "测评内容的价值在失败样例：把用户吐槽转成测试集，比从发布稿推导功能优先级更可靠。",
            "应把测评里的“看似合理但不可买”作为红线，要求AI推荐同时通过价格、库存、配送和用户约束核验。",
        ])
    if is_visual_try_on_context(text):
        return prefix + choose([
            "视觉体验要进入决策证据链，把尺码、风格、场景和退货风险用于推荐排序，而不是停留在营销图片生成。",
            "试穿结果应转成可比较证据，例如“哪里合适/哪里不合适/适合什么场景”，而不是只展示一张好看的图。",
            "视觉导购最该服务非标品的后悔成本管理，把不确定性前置，才可能减少退货和反复比较。",
        ])
    if contains_any(text, ["grocery", "quick-commerce", "instant", "闪购", "外卖", "买菜", "本地生活"]):
        return prefix + choose([
            "更适合先做高频低风险的局部代劳，例如补货、凑单、配送时效确认，再逐步迁移到复杂高客单决策。",
            "本地生活导购要把“现在能不能满足”放在第一位，位置、时段、库存、排队和配送承诺比长篇推荐理由更关键。",
            "即时场景可以成为AI购物习惯入口，因为失败成本低、频次高、反馈快，适合训练用户授权心智。",
        ])
    if contains_any(text, ["trust", "risk", "permission", "sues", "mistake", "trusted", "风险", "授权", "信任"]):
        return prefix + choose([
            "必须把证据来源、授权边界和出错责任放在主流程里；信任机制不是合规补丁，而是AI导购能否成交的前置条件。",
            "信任设计要具体到每张推荐卡：依据来自哪里、哪些信息不确定、用户授权到哪一步、出错后谁负责。",
            "风险信息不能藏在协议里，越是主动代劳的AI，越要在关键节点主动暴露不确定性和兜底方案。",
        ])
    return ""


LOW_INFORMATION_CORE = "这条资讯提供了AI购物/导购相关信号，但公开摘要信息有限，需要打开原文进一步确认细节。"
DEFAULT_INSIGHT = "判断文章价值时，应重点看它是否能帮助产品回答三个问题：用户为什么信任AI、AI凭什么推荐、推荐后如何完成交易。"


def analysis_signature(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "", core_point_text(value).lower())


def disambiguate_duplicate_core_points(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in articles:
        sig = analysis_signature(item.get("corePoint", []))
        counts[sig] = counts.get(sig, 0) + 1
    updated = []
    for item in articles:
        item = dict(item)
        core_points = list(item.get("corePoint") or [])
        sig = analysis_signature(core_points)
        if counts.get(sig, 0) > 1:
            differentiator = f"这条资料可作为{item.get('source', '该来源')}在{item.get('date', '')}关于{item.get('category', 'AI购物')}/{item.get('contentType', '资讯')}的侧面证据，适合与同月同主题信息交叉验证。"
            if len(core_points) >= 3:
                core_points[-1] = differentiator
            else:
                core_points.append(differentiator)
            item["corePoint"] = clean_core_points(core_points, max_points=3)
        updated.append(item)
    return updated


def disambiguate_duplicate_insights(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for item in articles:
        sig = analysis_signature(item.get("insight", ""))
        counts[sig] = counts.get(sig, 0) + 1
    updated = []
    for item in articles:
        item = dict(item)
        sig = analysis_signature(item.get("insight", ""))
        if counts.get(sig, 0) > 1:
            item["insight"] = clean_text(
                f"{item.get('insight', '').rstrip('。')}。这条资料更适合补足{item.get('source', '该来源')}在{item.get('date', '')}的{item.get('category', 'AI购物')}视角，而不是和同主题资讯合并成泛泛结论。"
            )
        updated.append(item)
    return updated


def prune_redundant_analysis(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    articles = disambiguate_duplicate_insights(disambiguate_duplicate_core_points(articles))
    ranked = sorted(articles, key=lambda item: (item.get("valueScore", 0), item.get("date", "")), reverse=True)
    kept: list[dict[str, Any]] = []
    seen_pair: set[tuple[str, str]] = set()
    seen_insight: set[str] = set()
    for item in ranked:
        core_points = item.get("corePoint", [])
        insight = str(item.get("insight", ""))
        if core_points == [LOW_INFORMATION_CORE] and insight == DEFAULT_INSIGHT:
            continue
        core_sig = analysis_signature(core_points)
        insight_sig = analysis_signature(insight)
        pair_sig = (core_sig, insight_sig)
        if pair_sig in seen_pair:
            continue
        if insight_sig in {analysis_signature(DEFAULT_INSIGHT), ""} or insight_sig in seen_insight:
            continue
        seen_insight.add(insight_sig)
        seen_pair.add(pair_sig)
        kept.append(item)
    return sorted(kept, key=lambda item: (item.get("date", ""), item.get("valueScore", 0)), reverse=True)


def personalize_insight(item: dict[str, Any], insight: str) -> str:
    points = item.get("corePoint") or []
    anchor = ""
    if isinstance(points, list):
        anchor = next((str(point).strip("。") for point in points if point and not str(point).startswith("公开信息显示")), "")
    if not anchor:
        return insight
    if anchor in insight:
        return insight
    return f"基于“{anchor}”这个信号，{insight}"


def make_core_point(item: dict[str, Any], tags: list[str]) -> list[str]:
    title = item["title"]
    lower = title.lower()
    angles = article_angles(item, tags)
    points: list[str] = title_specific_points(item)
    if "market_signal" in angles:
        points.extend(["资本或经营数据开始把AI购物能力计入增长预期。", "这类信息更偏赛道热度信号，不等同于具体产品能力发布。"])
    if "consumer_benchmark" in angles:
        points.extend(["真实用户测评暴露了通用AI参与购物决策的可用性边界。", "AI能给出建议，但常在预算、收货、偏好、可购买性核对上不稳定。"])
    if "ai_search_commerce" in angles:
        points.extend(["AI搜索和答案引擎正在成为购物上游入口。", "零售商开始关注如何把外部AI流量接回商品证据、站内体验和结算链路。"])
    if "agentic_checkout" in angles:
        points.extend(["智能体商业不只是更聪明的结算。", "核心变化是把发现、比较、授权、支付和售后责任连成完整体验。"])
    if "visual_try_on" in angles:
        points.extend(["视觉/试穿能力把风格、尺码、上身效果转成可感知证据。", "它主要解决服饰、美妆、鞋履等非标品的决策不确定性。"])
    if "product_data" in angles:
        points.extend(["AI购物的底座是可信、结构化、可度量的商品与供给数据。", "没有商品数据层，导购很难稳定完成推荐、比较和成交。"])
    if "merchant_tools" in angles:
        points.extend(["AI正在进入商家侧的选品、投放、内容生成和商品表达。", "供给侧资料质量会反过来影响用户端推荐质量。"])
    if "local_life" in angles:
        points.extend(["本地生活/即时零售更强调当下可执行选择。", "AI需要同时处理位置、时间、库存、配送、优惠和服务约束。"])
    if "platform_assistant" in angles:
        points.extend(["平台正在把AI能力放进购物入口或交易资产。", "判断重点不是聊天外壳，而是是否改变搜索、选品、比较和下单流程。"])
    if "discovery_decision" in angles:
        points.extend(["AI购物正在从改写搜索结果转向理解用户意图。", "更重要的能力是组织候选商品，并给出可比较的推荐理由。"])
    if "trust_risk" in angles:
        points.extend(["AI购物的瓶颈在信任与风险控制。", "用户需要知道推荐依据、授权边界和出错后的责任归属。"])
    if "memory_personalization" in angles:
        points.extend(["记忆/个性化能力正在从聊天上下文变成可复用的消费约束。", "真正有价值的不是记住用户说过什么，而是沉淀预算、尺码、品牌禁忌、补货周期和场景偏好。"])
    if "multimodal_entry" in angles:
        points.extend(["多模态入口把购物需求从文字搜索扩展到图片、语音和场景识别。", "这类能力的价值在于降低用户表达成本，并把模糊灵感转成可比较商品集合。"])
    if any(word in lower for word in ["sparky", "alexa for shopping", "rufus", "ai shopping assistant", "ai-powered shopping"]):
        points.extend(["海外平台正在把AI导购做成可执行助手。", "能力从理解意图、比较商品，延伸到价格提醒、补货和订单验证。"])
    if any(word in title for word in ["问小团", "小美"]):
        points.extend(["本地生活AI的关键不在“会聊天”。", "更关键的是合并位置、时间、排队、配送、优惠和服务约束。"])
    if any(word in title for word in ["千问", "淘宝", "天猫", "AI万能搜"]):
        points.extend(["阿里系AI能力正在回到电商交易链路内部。", "搜索、清单、凑单、下单等能力开始被统一编排。"])
    if any(word in title for word in ["京东", "京言", "言犀"]):
        points.extend(["京东系AI信号更值得看履约、售后和商品知识资产如何被导购调用。", "这类平台的优势不在会聊天，而在能否把正品、库存、物流和服务承诺变成推荐证据。"])
    if "虚拟试穿" in tags:
        points.extend(["试穿/试衣类AI把导购从问答推荐推进到低成本预体验。", "核心价值是降低非标品的适配不确定性。"])
    if "竞品案例" in tags:
        points.extend(["头部平台正在把AI能力嵌入具体购物链路。", "竞品差异不只在模型，也在入口位置、数据资产、履约深度和交易责任。"])
    if "交易闭环" in tags:
        points.extend(["AI购物正在从推荐信息走向交易闭环。", "商品、价格、支付、履约等基础能力开始成为核心竞争点。"])
    if "技术架构" in tags:
        points.extend(["购物智能体的重点从单轮问答转向任务编排。", "搜索、比较、确认、支付等工具需要协同工作。"])
    if "即时零售" in tags:
        points.append("高频、低风险的即时消费场景更容易培养用户使用AI购物的习惯。")
    if "GEO" in tags:
        points.extend(["商家竞争正在从搜索排名延伸到AI答案可见性。", "能否被智能体理解和推荐，会成为新的流量门槛。"])
    if "Agentic Commerce" in tags:
        points.extend(["Agentic Commerce会把发现、比较和结算前置到AI入口。", "传统电商漏斗会被重组为意图表达、候选验证和授权交易。"])
    if "C端AI产品" in tags and "AI购物" not in tags:
        points.extend(["这类C端AI产品不一定直接做购物，但会改变用户表达需求、保存偏好和执行任务的方式。", "对AI导购的参考价值在于入口、记忆、工具调用和跨场景上下文迁移。"])
    points = excerpt_points(item) + points
    if not points:
        tag_focus = "、".join(tags[:2]) or "AI购物/导购"
        points.append(f"这条资料提供了来自{item.get('source', '行业来源')}的{tag_focus}信号，需要重点判断它影响的是入口、证据、授权还是交易。")
    return clean_core_points(points)


def make_insight(item: dict[str, Any], tags: list[str]) -> str:
    title = item["title"]
    lower = title.lower()
    subject = f"围绕《{title}》"
    angles = article_angles(item, tags)
    specific = make_specific_insight(item)
    if specific:
        return specific
    if "market_signal" in angles:
        return "这类资讯适合用来判断赛道热度和竞品优先级，不适合作为功能结论；产品侧应继续追到官方发布、体验截图或用户反馈后，再沉淀具体设计假设。"
    if "consumer_benchmark" in angles:
        return "这类测评最适合转成产品验收标准：AI导购不能只给“看似合理”的推荐，还要核对库存、价格、配送、替代品和用户约束，并解释为什么放弃其他选项。"
    if "ai_search_commerce" in angles:
        return "机会点在“AI入口后的承接”：当用户从ChatGPT/Perplexity/Google答案页进入购物，站内导购要接住上下文，继续完成比较、证据展示和购买确认。"
    if "agentic_checkout" in angles:
        return "AI导购不能只在付款页做效率优化，真正机会在于把逛、选、比、确认、支付、售后做成连续责任链；每一步都要有解释、撤回和兜底。"
    if "visual_try_on" in angles:
        return "视觉能力应服务“适不适合我”的判断，而不是单纯生成好看图片；可把尺码、风格、场景、退货风险变成推荐排序和对比卡片里的证据。"
    if "product_data" in angles:
        return "产品机会在商家端和数据层：让商品卖点、适用人群、禁忌、库存、价格和履约承诺机器可读，用户端导购才有可验证的推荐依据。"
    if "merchant_tools" in angles:
        return "AI导购要同时设计商家端体验：帮助商家把商品表达、素材、投放和服务承诺转成AI能理解的供给资产，而不只是优化用户聊天框。"
    if "local_life" in angles:
        return "本地生活更适合先做高频、低风险、强时效的导购：用户要的不是参数大全，而是“现在附近、预算内、能准时送达/可到店”的确定性。"
    if "platform_assistant" in angles:
        return "竞品拆解要落到链路颗粒度：入口在哪里、承接什么意图、调用哪些交易资产、推进到哪一步、失败如何回退；不要只记录“上线AI助手”。"
    if "discovery_decision" in angles:
        return "逛和选品的核心不是给更多商品，而是把用户模糊需求翻译成可比较的候选集合；导购应输出取舍理由、场景匹配和反例提醒。"
    if "trust_risk" in angles:
        return "信任设计要前置到推荐过程：展示证据来源、排序理由、可撤回授权和售后责任，比单纯提升回答流畅度更能推动交易闭环。"
    if any(word in lower for word in ["sparky", "alexa for shopping", "rufus", "ai shopping assistant", "ai-powered shopping"]):
        return f"{subject}，产品拆解要关注四个阈值：AI是否有平台级商品/库存/评价资产，是否能记住预算和偏好，是否能解释排序理由，是否敢进入价格提醒、自动购买等低风险授权。"
    if any(word in title for word in ["问小团", "小美"]):
        return f"{subject}，本地生活导购适合从“帮我安排今晚/附近/预算内”切入，把服务供给实时性做成差异化；比起商品参数，用户更在意确定性和省心程度。"
    if any(word in title for word in ["千问", "淘宝", "天猫", "AI万能搜"]):
        return f"{subject}，AI购物入口不能只做一个聊天框，必须嵌进原有交易资产：历史订单、收藏、购物车、优惠、售后和商家工具，才能形成比搜索更强的闭环。"
    if "虚拟试穿" in tags:
        return f"{subject}，服饰、美妆、球鞋等非标品导购应把“看起来适不适合我”前置成决策证据，并沉淀尺码、风格、场景偏好。"
    if "竞品案例" in tags:
        return "竞品监测要拆到功能颗粒度：入口位置、可理解的用户意图、调用的商品/内容资产、是否能闭环下单，以及失败时如何回退。"
    if "交易闭环" in tags or "商品库" in tags:
        return "对话导购要优先接入可信商品资料、实时价格库存、优惠和售后规则；否则只能种草，难以承担成交责任。"
    if "技术架构" in tags:
        return "可把导购流程拆成需求澄清、候选生成、证据比较、风险提示、下单确认五个稳定模块，降低幻觉和误购风险。"
    if "即时零售" in tags:
        return "先从复购、买菜、日用品等低风险场景建立偏好记忆，比从复杂大件切入更容易形成日常使用。"
    if "GEO" in tags:
        return f"{subject}，需要为商家建设AI可读信息资产，让商品卖点、适用场景、证据、履约承诺能被智能体稳定理解和引用。"
    if "Agentic Commerce" in tags:
        return f"{subject}，不要只看它是不是又一个AI入口，而要看它是否改变了发现、比较、确认和支付之间的责任分工。"
    scenario = "、".join(detected_labels(article_context({**item, "tags": []}), SCENARIO_RULES, 2)) or "购物决策链路"
    tag_focus = "、".join(tags[:2]) or "AI导购"
    return f"这条更适合沉淀成{scenario}的小实验：围绕{tag_focus}观察它是否能减少用户表达成本、提高候选比较质量，或让推荐后的确认/履约更可靠。"


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    item = dict(item)
    item["source"] = canonical_source(item.get("source", ""))
    item["title"] = clean_display_title(item.get("title", ""), item["source"])
    item["excerpt"] = clean_text(item.get("snippet", ""))[:420]
    tags = infer_tags(article_context(item))
    if not is_relevant(item, tags):
        return {}
    normalized = {
        "id": slugify(f"{item['date']}-{item['source']}-{item['title']}"),
        "date": item["date"],
        "title": item["title"],
        "source": item["source"],
        "region": item["region"],
        "url": item["url"],
        "excerpt": item.get("excerpt", ""),
    }
    return recompute_article_fields(normalized)


def update(days: int, limit: int, dry_run: bool = False, skip_wechat: bool = False, max_google_queries: int | None = None) -> list[dict[str, Any]]:
    existing = load_json(ARTICLES_PATH, [])
    existing = prune_redundant_analysis(dedupe_items([
        item for item in (recompute_article_fields(item, keep_score=True) for item in existing)
        if is_relevant_existing_item(item)
    ]))
    raw_items = ([] if skip_wechat else fetch_wechat(days)) + fetch_rss(days) + fetch_google_news(days, max_google_queries)
    normalized = [normalize_item(item) for item in raw_items if item.get("title") and item.get("url")]
    normalized = [item for item in normalized if item]
    normalized = dedupe_items(normalized)
    selected = [item for item in normalized if item["valueScore"] >= 72 and not any(is_duplicate(item, old) for old in existing)]
    selected.sort(key=lambda item: (item["date"], item["valueScore"]), reverse=True)
    selected = selected[:limit]
    link_session = requests.Session()
    link_session.headers.update({"User-Agent": "Mozilla/5.0"})
    resolved_selected = []
    for item in selected:
        item["url"] = decode_google_news_url(link_session, item["url"])
        if urllib.parse.urlsplit(item["url"]).netloc.lower() == "news.google.com" or is_blocked_source_or_url(item):
            continue
        page_excerpt = fetch_article_excerpt(item["url"], link_session)
        if page_excerpt:
            item["excerpt"] = page_excerpt
        resolved_selected.append(recompute_article_fields(item))
    selected = resolved_selected
    if not dry_run:
        before_merge_count = len(selected) + len(existing)
        merged = prune_redundant_analysis(dedupe_items(selected + existing, limit=620))
        write_json(ARTICLES_PATH, merged)
        refresh_monthly_reports(merged)
        insight_changed = refresh_insights(merged)
        meta = load_json(META_PATH, {})
        meta["lastUpdated"] = dt.datetime.now(TZ).replace(microsecond=0).isoformat()
        meta["latestAdded"] = len(selected)
        meta.pop("dailyCoverageAdded", None)
        meta["duplicatesRemoved"] = max(0, before_merge_count - len(merged))
        meta["sourceCount"] = len({item.get("source") for item in merged})
        meta["lastInsightUpdated"] = dt.datetime.now(TZ).date().isoformat()
        meta["latestInsightChanged"] = insight_changed
        write_json(META_PATH, meta)
    return selected


def monthly_report_text(month: str, month_articles: list[dict[str, Any]]) -> tuple[str, str, str]:
    top_tags = [tag for tag, _ in tag_counts(month_articles)[:5]]
    focus = "、".join(top_tags[:3]) or "AI购物"
    titles = " ".join(item.get("title", "") for item in month_articles[:12]).lower()
    competitor_names = []
    for label, terms in ENTITY_RULES:
        if contains_any(titles, terms):
            competitor_names.append(label)
    competitors = "、".join(competitor_names[:4]) or "头部平台"
    count = len(month_articles)
    if any(tag in top_tags for tag in ["Agentic Commerce", "交易闭环"]):
        return (
            f"{focus}进入交易责任竞争",
            f"{month} 共收录 {count} 条高价值信息，主线集中在{focus}。值得注意的是，讨论不再停留在“AI能推荐什么”，而是进入授权、支付、结算、履约和异常处理；{competitors}等信号说明购物智能体正在逼近真实交易基础设施。",
            "产品侧应把导购链路拆成建议、比较、确认、授权、支付、履约、售后七个节点分别设计兜底机制；短期优先验证低风险授权和可撤回动作，而不是一步到位做全自动代买。",
        )
    if any(tag in top_tags for tag in ["竞品案例", "C端AI产品", "AI搜索"]):
        return (
            f"{focus}重塑购物入口",
            f"{month} 共收录 {count} 条高价值信息，核心变化是{competitors}等平台把AI能力放进搜索、应用、浏览器或购物场景入口。它们的共同点不是“多了聊天框”，而是试图把用户的模糊需求、上下文和候选商品提前组织好。",
            "产品侧应重点拆解竞品的入口位置、上下文继承、商品证据调用和交易推进深度；真正可迁移的不是UI形态，而是它减少了用户哪一步决策成本。",
        )
    if "虚拟试穿" in top_tags:
        return (
            "视觉导购开始从营销玩法变成决策证据",
            f"{month} 共收录 {count} 条高价值信息，视觉/试穿相关信号更密集。它们说明非标品导购的关键不是生成更好看的图，而是把尺码、风格、搭配场景和后悔成本提前显性化。",
            "产品侧应把试穿结果纳入推荐排序和对比逻辑：解释为什么适合、哪里不适合、替代款是什么，并把退货风险作为推荐证据的一部分。",
        )
    if any(tag in top_tags for tag in ["商家Agent", "商品库", "GEO"]):
        return (
            f"{focus}把竞争推向供给侧",
            f"{month} 共收录 {count} 条高价值信息，主线是商品、商家和AI可见性。AI导购质量越来越取决于供给侧资料是否可读、可信、实时，而不是单纯模型表达能力。",
            "产品侧应建设商家AI工作台：让商家补齐卖点证据、禁忌、适用场景、库存履约和服务承诺，并把AI推荐/未推荐原因反馈给商家。",
        )
    if "即时零售" in top_tags:
        return (
            "本地生活成为AI导购习惯入口",
            f"{month} 共收录 {count} 条高价值信息，即时零售/本地生活信号更突出。高频、低风险、强时效场景更容易让用户接受AI代劳，也能更快产生反馈数据。",
            "产品侧应优先做附近、现在、预算内、可履约的确定性推荐，并从补货、凑单、配送确认等小任务建立信任。",
        )
    return (
        f"{focus}提供新的产品假设",
        f"{month} 共收录 {count} 条高价值信息，信号分布在{focus}。这些资料更适合被当作产品假设库：判断每条信息改变的是入口、理解、证据、授权、交易还是购后。",
        "产品侧应把每月资料转成可验证问题：用户是否更快表达需求、是否更信任推荐依据、是否更愿意授权AI推进下一步，以及履约失败时是否可兜底。",
    )


def refresh_monthly_reports(articles: list[dict[str, Any]]) -> None:
    months = sorted({item["date"][:7] for item in articles}, reverse=True)
    reports = []
    for month in months:
        month_articles = [item for item in articles if item["date"].startswith(month)]
        month_articles.sort(key=lambda item: item.get("valueScore", 0), reverse=True)
        top_ids = [item["id"] for item in month_articles[:5]]
        title, summary, implication = monthly_report_text(month, month_articles)
        reports.append({
            "month": month,
            "title": title,
            "summary": summary,
            "productImplication": implication,
            "articleCount": len(month_articles),
            "topArticleIds": top_ids,
        })
    write_json(MONTHLY_REPORTS_PATH, reports)


def article_matches_insight(article: dict[str, Any], insight: dict[str, Any]) -> bool:
    text = " ".join([
        article.get("title", ""),
        core_point_text(article.get("corePoint", "")),
        article.get("insight", ""),
        " ".join(article.get("tags", [])),
    ]).lower()
    if insight.get("id") == "visual-try-on-as-proof":
        return any(term in text for term in [
            "虚拟试穿", "试穿", "试衣", "试鞋", "visual shopping", "virtual try", "try-on", "try on",
            "personal fit", "virtual fitting", "服饰导购", "美妆试", "球鞋试", "ai试穿", "造型导购",
        ])
    if insight.get("id") == "local-life-agent-loop":
        return any(term in text for term in ["美团", "小美", "问小团", "本地生活", "外卖", "买菜", "到店", "即时零售", "grocery"])
    if insight.get("id") in article.get("relatedInsightIds", []):
        return True
    return any(str(word).lower() in text for word in insight.get("keywords", []) if len(str(word)) > 1)


def tag_counts(articles: list[dict[str, Any]]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for item in articles:
        for tag in item.get("tags", []):
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda pair: pair[1], reverse=True)


def trend_note_for(insight: dict[str, Any], related: list[dict[str, Any]], recent: list[dict[str, Any]]) -> str:
    if not related:
        return "来源提示：这个方向暂时缺少足够信息源，适合作为观察项，不宜过早变成主功能投入。"
    recent_related = [item for item in recent if item in related] or related[:5]
    tags = [tag for tag, _ in tag_counts(recent_related)[:3]]
    focus = "、".join(tags) or "AI购物"
    title = insight.get("title", "")
    if "记忆" in title:
        return f"来源提示：相关资料继续指向{focus}，记忆能力要从聊天上下文升级为可编辑的购买约束，否则很难支撑长期授权。"
    if "信任" in title or "风险" in title:
        return f"来源提示：{focus}信号变强，说明用户不是不接受AI代劳，而是需要看到证据、边界和出错后的责任归属。"
    if "商家" in title or "机器" in title:
        return f"来源提示：{focus}正在把竞争前移到供给侧，谁能把商品、库存、评价和履约做成机器可读资料，谁更容易被AI选中。"
    if "闭环" in title or "购物车" in title or "漏斗" in title:
        return f"来源提示：{focus}显示导购正在逼近交易基础设施，产品重点要从推荐准确率转到确认、支付、履约和售后的连续可靠性。"
    return f"来源提示：近一批高价值信息集中在{focus}，更值得关注它如何改变用户决策步骤，而不只是把原搜索结果改写成聊天答案。"


PRODUCT_IDEA_BLUEPRINTS = [
    {
        "id": "auto-constraint-collector",
        "title": "搜索框要升级成“约束收集器”",
        "summary": "AI导购最先改变的不是结果页，而是需求表达：把预算、用途、禁忌、时间、履约和偏好一次性收齐，推荐才有判断基础。",
        "takeaways": ["把模糊需求拆成可确认约束", "用追问补足风险信息，而不是急着出商品", "让用户能随时修改约束并刷新候选集"],
        "keywords": ["需求澄清", "约束", "搜索", "决策", "可编辑偏好"],
        "terms": ["search", "recommendation", "discovery", "搜索", "推荐", "意图", "约束", "导购"],
    },
    {
        "id": "auto-reason-not-to-buy",
        "title": "AI必须说清“为什么不推荐”",
        "summary": "导购的可信度来自排除逻辑：比起只解释推荐理由，更要展示哪些商品因尺码、预算、评价、履约或售后风险被淘汰。",
        "takeaways": ["把反例做进对比卡片", "把退货/差评风险前置到推荐理由", "让用户能纠正AI排除标准"],
        "keywords": ["不推荐理由", "证据", "风险前置", "信任", "评价"],
        "terms": ["trust", "risk", "review", "evidence", "评价", "证据", "风险", "信任", "测评"],
    },
    {
        "id": "auto-memory-rules-panel",
        "title": "记忆应该是一张“我的购买规则”",
        "summary": "购物记忆不是聊天记录，而是用户可看见、可编辑、可冻结的购买约束；只有透明记忆才可能支撑长期授权。",
        "takeaways": ["沉淀预算、尺码、品牌禁忌和复购周期", "把记忆修改做成主入口", "让AI说明本次推荐调用了哪些记忆"],
        "keywords": ["记忆", "购买规则", "偏好", "复购", "授权"],
        "terms": ["memory", "personalization", "preference", "context", "habit", "记忆", "偏好", "个性化", "复购"],
    },
    {
        "id": "auto-low-risk-permission",
        "title": "先做低风险授权，再谈全自动代买",
        "summary": "用户不会一开始就把高客单决策交给AI；更现实的阶梯是提醒、比价、凑单、补货、售后这类可撤回的小任务。",
        "takeaways": ["从提醒和补货建立信任", "每次授权都给撤回和确认", "把错误成本作为场景优先级标准"],
        "keywords": ["低风险授权", "复购", "售后", "信任阶梯", "代劳"],
        "terms": ["permission", "checkout", "order", "payment", "复购", "补货", "售后", "授权", "下单", "支付"],
    },
    {
        "id": "auto-product-evidence-layer",
        "title": "商品详情页要有一层“机器可读证据”",
        "summary": "AI能否稳定推荐，取决于商品卖点、适用人群、禁忌、库存、价格、评价和履约承诺是否被结构化。",
        "takeaways": ["让商家补齐可被AI引用的证据", "把证据完整度纳入商品质量分", "推荐理由必须能回链到商品事实"],
        "keywords": ["商品库", "机器可读", "商家", "证据层", "供给侧"],
        "terms": ["product data", "catalog", "merchant", "seller", "storefront", "商品", "商品库", "商家", "库存", "履约"],
    },
    {
        "id": "auto-visual-proof",
        "title": "试穿不是生成图，而是把后悔成本前置",
        "summary": "视觉导购的价值是证明“适不适合我”：尺码、风格、场景和搭配证据要进入排序与对比，而不是只做营销图。",
        "takeaways": ["把试穿结果转成推荐排序因子", "补充尺码和场景适配解释", "用视觉证据降低非标品退货风险"],
        "keywords": ["试穿", "视觉导购", "非标品", "适配证据", "风险前置"],
        "terms": ["try-on", "virtual try", "visual", "style", "fashion", "试穿", "试衣", "试鞋", "视觉", "风格"],
    },
    {
        "id": "auto-external-ai-handoff",
        "title": "外部AI入口进站后不能丢上下文",
        "summary": "ChatGPT、Perplexity、Google等入口会带来半成型购物意图；站内体验要继承问题、约束和候选，而不是让用户重新搜索。",
        "takeaways": ["识别外部入口带来的意图包", "落地页继续比较和证据展示", "把优惠、库存和售后补成交易确认"],
        "keywords": ["外部AI入口", "上下文继承", "AI搜索", "承接", "转化"],
        "terms": ["chatgpt", "perplexity", "google", "ai search", "answer engine", "流量", "入口", "上下文", "AI搜索"],
    },
    {
        "id": "auto-local-certainty",
        "title": "本地生活AI导购卖的是“此刻确定性”",
        "summary": "外卖、买菜、到店场景里，用户要的是附近、现在、预算内、能准时履约；AI应该先解决确定性，再追求复杂推荐。",
        "takeaways": ["把位置、时间、库存、配送和优惠合并判断", "优先做高频低风险任务", "用履约状态反哺下一次推荐"],
        "keywords": ["本地生活", "即时零售", "履约确定性", "高频", "小美"],
        "terms": ["grocery", "quick-commerce", "instant", "local", "美团", "小美", "问小团", "外卖", "买菜", "即时零售", "本地生活"],
    },
    {
        "id": "auto-agentic-checkout-contract",
        "title": "Agentic Commerce本质是一份“交易责任合约”",
        "summary": "智能体替用户推进交易时，关键不是下单速度，而是授权、支付、撤回、异常处理和责任归属是否被产品化。",
        "takeaways": ["把确认/撤回做成默认路径", "区分建议、代填、代付、代买的权限等级", "让每次动作都有日志和追责依据"],
        "keywords": ["Agentic Commerce", "支付", "授权", "交易责任", "闭环"],
        "terms": ["agentic commerce", "checkout", "payment", "visa", "mastercard", "stripe", "paypal", "支付", "结算", "授权", "闭环"],
    },
    {
        "id": "auto-merchant-training-console",
        "title": "商家后台要从“填资料”变成“训练AI怎么卖”",
        "summary": "当AI成为导购入口，商家需要管理的不只是商品字段，而是卖点证据、适用人群、禁忌、替代品和服务承诺。",
        "takeaways": ["给商家展示AI如何理解商品", "提供卖点/禁忌/场景的结构化补全", "把AI推荐归因反馈给商家优化供给"],
        "keywords": ["商家Agent", "供给侧", "AI可见性", "商品表达", "归因"],
        "terms": ["merchant", "seller", "aidge", "storefront", "商家", "卖家", "店铺", "投放", "AI可见性", "GEO"],
    },
    {
        "id": "auto-intent-cart",
        "title": "购物车会变成“未完成意图”的容器",
        "summary": "未来购物车不只是商品暂存，而是预算、候选、纠结点、价格提醒、凑单和售后承诺的任务看板。",
        "takeaways": ["保留用户为什么犹豫", "让AI持续追踪价格和库存变化", "把购物车变成可恢复的决策现场"],
        "keywords": ["购物车", "意图容器", "价格提醒", "凑单", "决策恢复"],
        "terms": ["cart", "shopping cart", "price", "wishlist", "购物车", "收藏", "价格", "凑单", "比价"],
    },
    {
        "id": "auto-post-purchase-retention",
        "title": "购后才是AI导购建立长期关系的低成本入口",
        "summary": "售后、保价、耗材补货、使用提醒和退换货建议，比一次性推荐更容易让用户感知AI在替自己负责。",
        "takeaways": ["把订单生命周期纳入导购记忆", "用保价/售后提醒建立可信代劳", "从购后数据反推下一次推荐"],
        "keywords": ["购后", "售后", "保价", "复购", "留存"],
        "terms": ["post-purchase", "after-sales", "order", "return", "售后", "退货", "保价", "复购", "订单"],
    },
]


def related_articles_by_terms(articles: list[dict[str, Any]], terms: list[str], limit: int = 10) -> list[dict[str, Any]]:
    matched = []
    for item in articles:
        text = article_context(item, include_existing_analysis=True)
        if contains_any(text, terms):
            matched.append(item)
    matched.sort(key=lambda item: (item.get("valueScore", 0), item.get("date", "")), reverse=True)
    return matched[:limit]


def build_auto_insights(articles: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    insights = []
    for blueprint in PRODUCT_IDEA_BLUEPRINTS:
        related = related_articles_by_terms(articles, blueprint["terms"], 12)
        if not related:
            continue
        insights.append({
            "id": blueprint["id"],
            "title": blueprint["title"],
            "summary": blueprint["summary"],
            "takeaways": blueprint["takeaways"],
            "keywords": blueprint["keywords"],
            "relatedArticleIds": [item["id"] for item in related],
            "sourceCount": len(related),
            "updatedAt": now,
        })
    return insights


def spark_angle(item: dict[str, Any]) -> tuple[str, str, list[str], list[str]]:
    text = article_context(item, include_existing_analysis=True)
    entities = detected_labels(text, ENTITY_RULES, 2)
    entity = "、".join(entities) if entities else item.get("source", "这条信号")
    if contains_any(text, ["try-on", "virtual try", "试穿", "试衣", "试鞋", "visual", "视觉", "图片", "多模态"]):
        return (
            f"把{entity}的视觉能力拆成“适配证据”",
            "这条信号启发的是：视觉导购不要只做生成效果图，而要把尺码、风格、场景和退货风险变成可比较、可追责的推荐证据。",
            ["把视觉结果接入推荐排序", "在对比卡里展示适配/不适配证据", "用失败样例训练用户预期"],
            ["视觉导购", "适配证据", "试穿", "非标品"],
        )
    if contains_any(text, ["memory", "personalization", "preference", "context", "habit", "记忆", "偏好", "个性化", "复购"]):
        return (
            f"把{entity}的个性化能力做成可编辑购买规则",
            "这条信号启发的是：用户愿意让AI记住的不是隐形画像，而是能被检查和修改的购买规则；记忆越透明，越适合承接长期导购。",
            ["展示本次推荐调用了哪些记忆", "允许用户冻结/删除单条偏好", "把复购周期和品牌禁忌沉淀为规则"],
            ["记忆", "偏好", "购买规则", "复购"],
        )
    if contains_any(text, ["checkout", "payment", "agentic commerce", "visa", "mastercard", "stripe", "paypal", "支付", "结算", "下单", "闭环"]):
        return (
            f"把{entity}的交易动作拆成分级授权",
            "这条信号启发的是：AI越接近下单，越需要把建议、代填、代付、代买拆成不同权限，并在每一步提供确认、撤回和责任记录。",
            ["先做提醒/代填等低风险动作", "为支付和下单提供二次确认", "把异常处理写进导购主流程"],
            ["交易闭环", "授权", "支付", "责任"],
        )
    if contains_any(text, ["merchant", "seller", "catalog", "product data", "storefront", "商家", "卖家", "商品库", "库存", "履约", "GEO", "可见性"]):
        return (
            f"把{entity}的供给侧动作转成AI可读资产",
            "这条信号启发的是：用户端导购质量会被商家端资料质量限制；卖点、禁忌、库存、履约和评价需要先结构化，AI才有稳定推荐依据。",
            ["建立商品证据完整度评分", "给商家反馈AI看不懂的字段", "让推荐理由回链到结构化事实"],
            ["商家", "商品库", "机器可读", "供给侧"],
        )
    if contains_any(text, ["search", "answer engine", "ai search", "perplexity", "google", "夸克", "AI搜索", "搜索", "答案"]):
        return (
            f"把{entity}的搜索入口当成需求澄清入口",
            "这条信号启发的是：AI搜索带来的不是一个新流量位，而是更完整的意图包；站内应承接约束、候选和疑问，继续推进比较与确认。",
            ["落地页继承外部AI上下文", "把搜索问题转为预算/场景/禁忌", "用证据和优惠完成临门一脚"],
            ["AI搜索", "入口", "需求澄清", "承接"],
        )
    if contains_any(text, ["grocery", "quick-commerce", "instant", "美团", "小美", "问小团", "外卖", "买菜", "即时零售", "本地生活"]):
        return (
            f"把{entity}的本地生活信号理解为确定性导购",
            "这条信号启发的是：即时场景里AI不需要给最丰富的推荐，而要最快合并位置、时间、库存、配送和优惠，给出现在就可执行的选择。",
            ["用履约确定性做排序主因子", "优先覆盖高频低风险任务", "让异常和替代方案自动浮出"],
            ["本地生活", "即时零售", "履约确定性", "高频"],
        )
    if contains_any(text, ["review", "tested", "trust", "risk", "实测", "测评", "评价", "信任", "风险"]):
        return (
            f"把{entity}的测评/风险信号变成验收清单",
            "这条信号启发的是：真实用户测评比发布稿更适合转成产品验收标准，检查AI是否核价、核库存、解释取舍并给替代方案。",
            ["沉淀推荐失败样例", "把用户质疑点变成测试用例", "在结果页展示AI如何排除候选"],
            ["测评", "信任", "验收清单", "风险"],
        )
    return (
        f"把{entity}的AI能力拆成可验证产品假设",
        "这条信号启发的是：不要只记录谁上线了AI，而要拆出它改变了购物链路的哪一步，以及能否用小实验验证入口、证据、授权或履约效果。",
        ["标注它影响的购物节点", "提出一个可验证指标", "把相关来源挂到同一灵感下持续复盘"],
        ["产品假设", "竞品拆解", "实验设计", "决策链路"],
    )


def build_spark_insights(articles: list[dict[str, Any]], now: str, limit: int = 140) -> list[dict[str, Any]]:
    ranked = sorted(articles, key=lambda item: (item.get("valueScore", 0), item.get("date", "")), reverse=True)
    sparks = []
    seen_titles: set[str] = set()
    per_month: dict[str, int] = {}
    for item in ranked:
        month = item.get("date", "")[:7]
        if per_month.get(month, 0) >= 14:
            continue
        title, summary, takeaways, keywords = spark_angle(item)
        title_sig = analysis_signature(title)
        if title_sig in seen_titles:
            continue
        related_terms = list(dict.fromkeys(keywords + (item.get("tags") or [])))
        related = [item]
        for candidate in related_articles_by_terms(articles, related_terms, 6):
            if candidate["id"] != item["id"]:
                related.append(candidate)
            if len(related) >= 5:
                break
        sparks.append({
            "id": f"{SPARK_INSIGHT_PREFIX}{item['id']}",
            "title": title,
            "summary": summary,
            "takeaways": takeaways,
            "keywords": list(dict.fromkeys(keywords + (item.get("tags") or [])))[:8],
            "relatedArticleIds": [article["id"] for article in related],
            "sourceCount": len(related),
            "updatedAt": now,
        })
        seen_titles.add(title_sig)
        per_month[month] = per_month.get(month, 0) + 1
        if len(sparks) >= limit:
            break
    return sparks


def daily_reflection_angle(articles: list[dict[str, Any]]) -> tuple[str, str, str, list[str]]:
    text = " ".join([
        " ".join(item.get("tags", [])) + " " + item.get("title", "") + " " + core_point_text(item.get("corePoint", ""))
        for item in articles
    ]).lower()
    if any(term in text for term in ["淘宝", "天猫", "千问", "美团", "小美", "问小团", "amazon", "alexa", "rufus", "walmart", "target", "pinterest", "instacart", "shopee", "得物"]):
        return (
            "竞品能力要拆成可复用模块，而不是停留在谁发布了什么功能",
            "当天资料更适合被沉淀为竞品功能拆解：入口在哪里、调用什么数据、推进到哪一步交易、失败时如何回退。",
            "把每个竞品动作转成可验证假设，例如是否能提升需求表达效率、降低决策不确定性、或把推荐推进到可确认交易。",
            ["竞品拆解", "功能模块", "交易闭环", "产品假设"],
        )
    if any(term in text for term in ["试穿", "试衣", "visual", "fashion", "style", "图片", "视觉"]):
        return (
            "视觉能力的价值不是生成图片，而是把购买风险提前显性化",
            "当天资料指向非标品导购的关键：用户真正缺的不是更多商品，而是对尺码、风格、场景适配和后悔成本的判断证据。",
            "试穿、相似款和风格翻译应进入推荐排序，让AI从“描述商品”升级为“证明它适合我”。",
            ["视觉导购", "适配证据", "非标品", "风险前置"],
        )
    if any(term in text for term in ["agentic commerce", "checkout", "支付", "下单", "购物车", "闭环"]):
        return (
            "AI导购的分水岭是能否承担交易责任",
            "当天资料说明行业正在从“答案更好”转向“动作更可靠”：库存、价格、支付、售后和授权边界会决定用户是否敢让AI继续往前走。",
            "产品上要把确认、撤回、保价、售后责任做成主流程，而不是把它们藏在推荐结果之后。",
            ["交易责任", "授权边界", "支付闭环", "可靠执行"],
        )
    if any(term in text for term in ["商家", "merchant", "seller", "商品库", "可见性", "geo"]):
        return (
            "下一代导购竞争会先发生在供给侧",
            "当天资料提醒我们，AI能否推荐好商品，取决于商家是否把卖点、库存、评价、履约和禁忌规则变成机器可读资产。",
            "可以把商家后台从“填商品信息”升级为“训练AI如何理解和推荐我的商品”的工作台。",
            ["供给侧", "机器可读", "商家Agent", "AI可见性"],
        )
    if any(term in text for term in ["记忆", "personal", "偏好", "复购", "habit"]):
        return (
            "记忆不是用户画像，而是可编辑的购买约束",
            "当天资料显示，长期偏好只有在预算、品牌禁忌、尺码、补货周期和场景里被用户看见并可修改，才会变成信任资产。",
            "AI导购应提供“我的购买规则”面板，让用户能纠正、冻结或删除记忆，而不是被动接受黑箱个性化。",
            ["记忆", "购买约束", "复购", "可编辑偏好"],
        )
    return (
        "把新闻变成产品资产，关键是沉淀可实验假设",
        "当天资料的价值不在信息本身，而在能否被拆成入口、数据、证据、授权、交易和复盘这些可落地模块。",
        "每条资讯都应回答一个产品问题：它改变用户决策链路的哪一步，能否被做成小实验验证。",
        ["产品假设", "信息复盘", "实验设计", "决策链路"],
    )


def build_daily_reflections(articles: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for item in articles:
        by_date.setdefault(item["date"], []).append(item)
    reflections = []
    for date in sorted(by_date.keys(), reverse=True):
        day_articles = sorted(by_date[date], key=lambda item: item.get("valueScore", 0), reverse=True)
        top = day_articles[:4]
        title, summary, trend_note, keywords = daily_reflection_angle(top)
        tags = [tag for tag, _ in tag_counts(top)[:5]]
        reflections.append({
            "id": f"{DAILY_INSIGHT_PREFIX}{date}",
            "title": f"{date[5:]} 反思：{title}",
            "summary": summary,
            "trendNote": trend_note,
            "takeaways": [
                "把当天信号改写成一个可验证产品假设",
                "优先记录它影响的是入口、证据、授权还是交易",
                "把相关资料挂回灵感，避免资讯只被收藏不被复用",
            ],
            "keywords": list(dict.fromkeys(keywords + tags))[:8],
            "relatedArticleIds": [item["id"] for item in top],
            "sourceCount": len(day_articles),
            "updatedAt": now,
        })
    return reflections


def refresh_insights(articles: list[dict[str, Any]]) -> int:
    now = dt.datetime.now(TZ).date().isoformat()
    existing = load_json(INSIGHTS_PATH, [])
    base = [
        item for item in existing
        if not str(item.get("id", "")).startswith(AUTO_INSIGHT_PREFIX)
        and not str(item.get("id", "")).startswith(DAILY_INSIGHT_PREFIX)
        and not str(item.get("id", "")).startswith(SPARK_INSIGHT_PREFIX)
    ]
    recent_cutoff = dt.datetime.now(TZ).date() - dt.timedelta(days=30)
    recent = [item for item in articles if dt.date.fromisoformat(item["date"]) >= recent_cutoff]
    reviewed = []
    for insight in base:
        related = [item for item in articles if article_matches_insight(item, insight)]
        related.sort(key=lambda item: (item.get("date", ""), item.get("valueScore", 0)), reverse=True)
        updated = dict(insight)
        updated["sourceCount"] = len(related)
        updated["relatedArticleIds"] = [item["id"] for item in related[:10]]
        updated["trendNote"] = trend_note_for(insight, related, recent)
        updated["updatedAt"] = now
        reviewed.append(updated)
    auto = build_auto_insights(articles, now)
    sparks = build_spark_insights(articles, now)
    write_json(INSIGHTS_PATH, reviewed + auto + sparks)
    return len(reviewed) + len(auto) + len(sparks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--skip-wechat", action="store_true")
    parser.add_argument("--max-google-queries", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    selected = update(args.days, args.limit, args.dry_run, args.skip_wechat, args.max_google_queries)
    print(f"Selected {len(selected)} new items")
    for item in selected:
        print(f"- {item['date']} {item['title']} | {item['source']} | {item['valueScore']}")


if __name__ == "__main__":
    main()
