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
    from content_quality import canonical_source, clean_display_title, clean_url, dedupe_items, is_ai_shopping_related, is_duplicate, is_temporary_wechat_url
except ImportError:  # pragma: no cover
    from scripts.content_quality import canonical_source, clean_display_title, clean_url, dedupe_items, is_ai_shopping_related, is_duplicate, is_temporary_wechat_url

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
    "AI购物",
    "AI导购",
    "淘宝 AI万能搜",
    "淘宝 AI试穿",
    "淘宝设计 AI试穿",
    "天猫 AI导购",
    "天猫 AI试穿",
    "千问 淘宝 闪购 AI购物",
    "阿里 悟空 电商 AI Agent",
    "阿里 Aidge AI电商 商家",
    "美团 小美 AI助手",
    "美团 AI导购",
    "美团 问小团 AI搜索 本地生活",
    "得物 AI试穿",
    "得物 AI鉴别机器人 WAIC",
    "虾皮 AI导购",
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
    "AI购物": ["ai购物", "购物助手", "购物智能体", "ai shopping", "shopping agent", "agentic shopping", "ai commerce", "online shopping", "cart assistant"],
    "对话导购": ["导购", "对话式", "conversation", "conversational"],
    "竞品案例": ["淘宝", "天猫", "千问", "美团", "小美", "问小团", "虾皮", "shopee", "亚马逊", "amazon", "rufus", "alexa", "得物", "walmart", "sparky", "target", "kohl", "instacart", "pinterest", "aidge", "aliexpress"],
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

NEGATIVE_WORDS = ["融资", "培训", "课程", "招商", "广告", "大会报名", "招聘", "破解版"]
BLOCKED_URL_HOSTS = {"ebrun.com", "ttplus.cn"}
LOW_VALUE_SOURCES = {"Stocktwits", "体坛"}
LOW_VALUE_TITLE_PATTERNS = [
    "dunkin", "chief merchant", "ad auction", "fulfillment center", "tire benefit",
    "token充值", "充值中心", "多人工作台", "measurement stack", "new ecommerce tools",
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
    if any(word in item.get("title", "") for word in ["体育投注", "注册在线"]):
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


def fetch_google_news(days: int) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(TZ).date() - dt.timedelta(days=days)
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    items: list[dict[str, Any]] = []
    for query in GOOGLE_NEWS_QUERIES:
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
    if contains_any(text, ["perplexity", "ai search", "ai traffic", "answer engine", "search traffic", "google discover", "ai搜索"]):
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
    if contains_any(text, ["chatgpt", "perplexity", "gemini", "rufus", "alexa for shopping", "sparky", "ai shopping assistant", "ai-powered shopping", "ai万能搜", "千问", "淘宝", "天猫", "shopee", "虾皮", "instacart", "pinterest", "kohl", "target", "walmart"]):
        angles.append("platform_assistant")
    if contains_any(text, ["search", "discovery", "recommendation", "recommendations", "visual search", "collage", "发现", "搜索", "推荐", "逛", "种草"]):
        angles.append("discovery_decision")
    if contains_any(text, ["trust", "privacy", "wary", "risk", "fraud", "安全", "隐私", "信任", "风险", "虚假评价"]):
        angles.append("trust_risk")
    if not angles:
        angles.append("general_signal")
    return list(dict.fromkeys(angles))[:4]


def is_relevant(item: dict[str, Any], tags: list[str]) -> bool:
    if is_blocked_source_or_url(item):
        return False
    if not tags:
        return False
    return is_grounded_ai_shopping_item(item, tags)


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


def infer_category(tags: list[str], text: str) -> str:
    lower = text.lower()
    if "虚拟试穿" in tags:
        return "竞品功能"
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
    item.update({
        "contentType": content_type,
        "category": category,
        "tags": tags,
        "corePoint": make_core_point(item, tags),
        "insight": make_insight(item, tags),
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
    sentences = re.split(r"(?<=[。！？.!?])\s+|[；;]", excerpt)
    points: list[str] = []
    for sentence in sentences:
        sentence = clean_text(sentence).strip(" ，,。.;；")
        if len(sentence) < 18 or len(sentence) > 120:
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


def make_core_point(item: dict[str, Any], tags: list[str]) -> list[str]:
    title = item["title"]
    lower = title.lower()
    angles = article_angles(item, tags)
    points: list[str] = []
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
    if any(word in lower for word in ["sparky", "alexa for shopping", "rufus", "ai shopping assistant", "ai-powered shopping"]):
        points.extend(["海外平台正在把AI导购做成可执行助手。", "能力从理解意图、比较商品，延伸到价格提醒、补货和订单验证。"])
    if any(word in title for word in ["问小团", "小美"]):
        points.extend(["本地生活AI的关键不在“会聊天”。", "更关键的是合并位置、时间、排队、配送、优惠和服务约束。"])
    if any(word in title for word in ["千问", "淘宝", "天猫", "AI万能搜"]):
        points.extend(["阿里系AI能力正在回到电商交易链路内部。", "搜索、清单、凑单、下单等能力开始被统一编排。"])
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
    points = excerpt_points(item) + points
    if not points:
        points.append("公开信息显示，这是一条与AI购物/导购相关的行业信号。")
    return clean_core_points(points)


def make_insight(item: dict[str, Any], tags: list[str]) -> str:
    title = item["title"]
    lower = title.lower()
    subject = f"围绕《{title}》"
    angles = article_angles(item, tags)
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
    return "判断文章价值时，应重点看它是否能帮助产品回答三个问题：用户为什么信任AI、AI凭什么推荐、推荐后如何完成交易。"


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


def update(days: int, limit: int, dry_run: bool = False) -> list[dict[str, Any]]:
    existing = load_json(ARTICLES_PATH, [])
    existing = dedupe_items([
        item for item in (recompute_article_fields(item, keep_score=True) for item in existing)
        if is_grounded_ai_shopping_item(item, item.get("tags", []))
    ])
    raw_items = fetch_wechat(days) + fetch_rss(days) + fetch_google_news(days)
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
        merged = dedupe_items(selected + existing, limit=520)
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


def refresh_monthly_reports(articles: list[dict[str, Any]]) -> None:
    existing_reports = load_json(MONTHLY_REPORTS_PATH, [])
    by_month = {report.get("month"): report for report in existing_reports}
    months = sorted({item["date"][:7] for item in articles}, reverse=True)
    reports = []
    for month in months:
        month_articles = [item for item in articles if item["date"].startswith(month)]
        month_articles.sort(key=lambda item: item.get("valueScore", 0), reverse=True)
        top_ids = [item["id"] for item in month_articles[:5]]
        report = dict(by_month.get(month, {}))
        if not report:
            top_tags = []
            for item in month_articles[:5]:
                top_tags.extend(item.get("tags", []))
            focus = "、".join(list(dict.fromkeys(top_tags))[:4]) or "AI购物"
            report = {
                "month": month,
                "title": f"{focus}成为本月主线",
                "summary": f"本月高价值信息集中在{focus}，重点观察其对AI导购入口、交易闭环和商家接入的影响。",
                "productImplication": "产品团队应把当月新信号翻译成可验证假设，并进入需求澄清、推荐解释、交易确认或商家接入模块。",
            }
        report["month"] = month
        report["topArticleIds"] = top_ids
        reports.append(report)
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
        return "最新复盘：这个方向暂时缺少足够信息源，适合作为观察项，不宜过早变成主功能投入。"
    recent_related = [item for item in recent if item in related] or related[:5]
    tags = [tag for tag, _ in tag_counts(recent_related)[:3]]
    focus = "、".join(tags) or "AI购物"
    title = insight.get("title", "")
    if "记忆" in title:
        return f"最新复盘：相关资料继续指向{focus}，记忆能力要从聊天上下文升级为可编辑的购买约束，否则很难支撑长期授权。"
    if "信任" in title or "风险" in title:
        return f"最新复盘：{focus}信号变强，说明用户不是不接受AI代劳，而是需要看到证据、边界和出错后的责任归属。"
    if "商家" in title or "机器" in title:
        return f"最新复盘：{focus}正在把竞争前移到供给侧，谁能把商品、库存、评价和履约做成机器可读资料，谁更容易被AI选中。"
    if "闭环" in title or "购物车" in title or "漏斗" in title:
        return f"最新复盘：{focus}显示导购正在逼近交易基础设施，产品重点要从推荐准确率转到确认、支付、履约和售后的连续可靠性。"
    return f"最新复盘：近一批高价值信息集中在{focus}，更值得关注它如何改变用户决策步骤，而不只是把原搜索结果改写成聊天答案。"


def build_auto_insights(articles: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    latest_month = max({item["date"][:7] for item in articles}) if articles else dt.datetime.now(TZ).strftime("%Y-%m")
    month_articles = [item for item in articles if item["date"].startswith(latest_month)]
    recent_articles = sorted(month_articles or articles, key=lambda item: (item.get("date", ""), item.get("valueScore", 0)), reverse=True)[:24]
    top_tags = [tag for tag, _ in tag_counts(recent_articles)[:5]] or ["AI购物"]
    top_ids = [item["id"] for item in sorted(recent_articles, key=lambda item: item.get("valueScore", 0), reverse=True)[:8]]
    focus = "、".join(top_tags[:3])
    return [
        {
            "id": "auto-current-signal",
            "title": f"最新复盘：{focus}正在收敛成产品主线",
            "summary": f"{latest_month} 的信息密度显示，AI购物的竞争点不是单一助手入口，而是{focus}这些能力之间能否互相闭环。",
            "trendNote": "产品上更该把新增资讯拆成可验证模块：入口是否更自然、证据是否更可信、商家供给是否可读、交易是否可执行。",
            "takeaways": ["用月度高频信号更新路线图优先级", "把新闻动态转成可实验的产品假设", "避免只追热点发布而忽略交易链路"],
            "keywords": top_tags[:5] + ["最新复盘", "产品路线"],
            "relatedArticleIds": top_ids,
            "updatedAt": now,
        },
        {
            "id": "auto-evidence-gap",
            "title": "每天新增资料最该沉淀成“证据库”",
            "summary": "资讯越多，AI导购越不能只做摘要；真正可复用的是场景、约束、失败案例、官方能力和交易规则这些可被产品调用的证据。",
            "trendNote": "建议把每日信息拆成观点、证据、适用品类、风险边界四类资产，让灵感集成为产品判断的知识底座。",
            "takeaways": ["每条资料至少沉淀一个产品判断", "把来源链接挂到对应灵感而不是孤立收藏", "优先保留能影响决策链路的证据"],
            "keywords": ["证据库", "信息复盘", "产品判断", "资料结构化", "灵感沉淀"],
            "relatedArticleIds": top_ids,
            "updatedAt": now,
        },
        {
            "id": "auto-next-experiment",
            "title": "下一步应围绕“低风险授权”设计实验",
            "summary": "从近一年资料看，AI导购最容易启动的不是万能代买，而是低风险、高频、可撤回的局部授权。",
            "trendNote": "可以优先验证三类入口：复购补货、预算内比选、售后/保价提醒；这些场景失败成本低，更容易积累用户信任。",
            "takeaways": ["用小授权替代一步到位的全自动", "用复购和售后提升留存频次", "用可撤回机制降低心理门槛"],
            "keywords": ["低风险授权", "复购", "信任阶梯", "售后", "实验设计"],
            "relatedArticleIds": top_ids,
            "updatedAt": now,
        },
    ]


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
    daily_reflections = build_daily_reflections(articles, now)
    auto = build_auto_insights(articles, now)
    write_json(INSIGHTS_PATH, reviewed + daily_reflections + auto)
    return len(reviewed) + len(daily_reflections) + len(auto)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    selected = update(args.days, args.limit, args.dry_run)
    print(f"Selected {len(selected)} new items")
    for item in selected:
        print(f"- {item['date']} {item['title']} | {item['source']} | {item['valueScore']}")


if __name__ == "__main__":
    main()
