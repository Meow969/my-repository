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
    from content_quality import canonical_source, clean_display_title, dedupe_items, is_ai_shopping_related, is_duplicate
except ImportError:  # pragma: no cover
    from scripts.content_quality import canonical_source, clean_display_title, dedupe_items, is_ai_shopping_related, is_duplicate

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
    "豆包 AI购物",
    "京东AI购",
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
    "Perplexity shopping AI",
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
    "site:blog.google/products/shopping AI shopping",
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
    "三易生活": 10,
    "i黑马": 10,
    "商派": 9,
    "艾奇SEM": 8,
    "GEO优化实战派": 8,
    "Google Shopping Blog": 14,
    "Google Ads & Commerce Blog": 14,
    "Google Blog": 14,
    "OpenAI Blog": 13,
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
    "AI购物": ["ai购物", "购物助手", "购物智能体", "ai shopping", "shopping agent"],
    "对话导购": ["导购", "对话式", "conversation", "conversational"],
    "Agentic Commerce": ["agentic commerce", "智能体商业", "代理购物"],
    "交易闭环": ["闭环", "下单", "支付", "checkout", "交易", "购物车"],
    "商品库": ["商品", "sku", "库存", "价格", "履约"],
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
}

AUTO_INSIGHT_PREFIX = "auto-"

NEGATIVE_WORDS = ["融资", "培训", "课程", "招商", "广告", "大会报名", "招聘", "破解版"]
HIGH_VALUE_WORDS = [
    "闭环", "智能体", "Agentic Commerce", "导购", "购物助手", "千问", "豆包", "淘宝",
    "京东", "Rufus", "Claude", "OpenClaw", "Universal Commerce Protocol", "UCP",
    "支付", "checkout", "履约", "复购", "GEO", "AI可见性", "商品库", "架构",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
    try:
        response = session.get(link, headers={"Referer": referer}, timeout=12, allow_redirects=False)
    except requests.RequestException:
        return link
    chunks = re.findall(r"url \+= '([^']*)'", response.text)
    if chunks:
        return "".join(chunks).replace("@", "")
    location = response.headers.get("Location", "")
    if location and "antispider" not in location:
        return urllib.parse.urljoin(link, location)
    return link


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
            link = urllib.parse.urljoin("https://weixin.sogou.com/weixin", html.unescape(title_match.group(1)))
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
    for item in items[:16]:
        if item.get("needsResolve"):
            item["url"] = resolve_sogou_link(session, item["rawUrl"], "https://weixin.sogou.com/weixin")
            time.sleep(0.15)
    return items


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


def infer_tags(text: str) -> list[str]:
    lower = text.lower()
    tags = [tag for tag, words in TAG_RULES.items() if any(word.lower() in lower for word in words)]
    return tags[:6]


def is_relevant(item: dict[str, Any], tags: list[str]) -> bool:
    if not tags:
        return False
    return is_ai_shopping_related(item)


def infer_category(tags: list[str], text: str) -> str:
    lower = text.lower()
    if "技术架构" in tags or any(word in lower for word in ["架构", "blueprint", "protocol", "openclaw"]):
        return "技术架构"
    if any(word in lower for word in ["周报", "动态", "趋势"]):
        return "行业动态"
    if any(word in lower for word in ["淘宝", "千问", "豆包", "京东", "rufus", "meta"]):
        return "平台案例"
    if "GEO" in tags or "AI可见性" in text:
        return "增长/GEO"
    return "趋势框架"


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


def related_insights(text: str) -> list[str]:
    lower = text.lower()
    ids = [insight_id for insight_id, words in INSIGHT_RULES.items() if any(word.lower() in lower for word in words)]
    return ids[:3] or ["structured-dialogue"]


def make_core_point(item: dict[str, Any], tags: list[str]) -> str:
    title = item["title"]
    if "交易闭环" in tags:
        return "AI购物正在从推荐信息走向交易闭环，商品、价格、支付、履约等能力开始成为核心竞争点。"
    if "技术架构" in tags:
        return "购物智能体的重点从单轮问答转向任务编排，需要搜索、比较、确认、支付等工具协同。"
    if "即时零售" in tags:
        return "高频低风险的即时消费场景更容易培养用户使用AI购物的习惯。"
    if "GEO" in tags:
        return "商家竞争正在从搜索排名延伸到AI答案可见性和智能体推荐资格。"
    if "Agentic Commerce" in tags:
        return "Agentic Commerce 会把发现、比较和结算前置到AI入口，重塑传统电商漏斗。"
    return f"围绕“{title}”，文章提供了AI购物/导购从概念走向真实商业场景的最新观察。"


def make_insight(item: dict[str, Any], tags: list[str]) -> str:
    if "交易闭环" in tags or "商品库" in tags:
        return "对话导购要优先接入可信商品资料、实时价格库存、优惠和售后规则；否则只能种草，难以承担成交责任。"
    if "技术架构" in tags:
        return "可把导购流程拆成需求澄清、候选生成、证据比较、风险提示、下单确认五个稳定模块，降低幻觉和误购风险。"
    if "即时零售" in tags:
        return "先从复购、买菜、日用品等低风险场景建立偏好记忆，比从复杂大件切入更容易形成日常使用。"
    if "GEO" in tags:
        return "需要为商家建设AI可读信息资产，让商品卖点、适用场景、证据、履约承诺能被智能体稳定理解和引用。"
    return "判断文章价值时，应重点看它是否能帮助产品回答三个问题：用户为什么信任AI、AI凭什么推荐、推荐后如何完成交易。"


def normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    item = dict(item)
    item["source"] = canonical_source(item.get("source", ""))
    item["title"] = clean_display_title(item.get("title", ""), item["source"])
    text = f"{item['title']} {item.get('snippet', '')}"
    tags = infer_tags(text)
    if not is_relevant(item, tags):
        return {}
    return {
        "id": slugify(f"{item['date']}-{item['source']}-{item['title']}"),
        "date": item["date"],
        "title": item["title"],
        "source": item["source"],
        "region": item["region"],
        "category": infer_category(tags, text),
        "url": item["url"],
        "tags": tags,
        "corePoint": make_core_point(item, tags),
        "insight": make_insight(item, tags),
        "valueScore": score_item(item, tags),
        "relatedInsightIds": related_insights(text),
    }


def update(days: int, limit: int, dry_run: bool = False) -> list[dict[str, Any]]:
    existing = load_json(ARTICLES_PATH, [])
    existing = dedupe_items(existing)
    raw_items = fetch_wechat(days) + fetch_rss(days) + fetch_google_news(days)
    normalized = [normalize_item(item) for item in raw_items if item.get("title") and item.get("url")]
    normalized = [item for item in normalized if item]
    normalized = dedupe_items(normalized)
    selected = [item for item in normalized if item["valueScore"] >= 72 and not any(is_duplicate(item, old) for old in existing)]
    selected.sort(key=lambda item: (item["date"], item["valueScore"]), reverse=True)
    selected = selected[:limit]
    if not dry_run:
        before_merge_count = len(selected) + len(existing)
        merged = dedupe_items(selected + existing, limit=520)
        write_json(ARTICLES_PATH, merged)
        refresh_monthly_reports(merged)
        insight_changed = refresh_insights(merged)
        meta = load_json(META_PATH, {})
        meta["lastUpdated"] = dt.datetime.now(TZ).replace(microsecond=0).isoformat()
        meta["latestAdded"] = len(selected)
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
        article.get("corePoint", ""),
        article.get("insight", ""),
        " ".join(article.get("tags", [])),
    ]).lower()
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


def refresh_insights(articles: list[dict[str, Any]]) -> int:
    now = dt.datetime.now(TZ).date().isoformat()
    existing = load_json(INSIGHTS_PATH, [])
    base = [item for item in existing if not str(item.get("id", "")).startswith(AUTO_INSIGHT_PREFIX)]
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
    write_json(INSIGHTS_PATH, reviewed + auto)
    return len(reviewed) + len(auto)


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
