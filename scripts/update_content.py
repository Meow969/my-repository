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
]

RSS_SOURCES = [
    ("Google Shopping Blog", "海外", "https://blog.google/products-and-platforms/products/shopping/rss/"),
    ("OpenAI Blog", "海外", "https://openai.com/news/rss.xml"),
    ("Shopify Blog", "海外", "https://www.shopify.com/blog.atom"),
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
    "consumer AI app",
    "AI购物",
    "AI导购",
    "购物智能体",
    "AI电商",
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
    "OpenAI Blog": 13,
    "Shopify Blog": 10,
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
    "trust-ladder": ["代买", "替你购物", "授权", "助手", "购物智能体"],
    "data-transaction-moat": ["商品", "库存", "价格", "履约", "淘宝", "京东", "闭环"],
    "agentic-funnel": ["agentic commerce", "checkout", "可见性", "geo", "入口"],
    "multi-agent-commerce": ["claude", "blueprint", "商家", "merchant", "openclaw", "agent"],
    "structured-dialogue": ["导购", "架构", "对话", "搜索", "推荐"],
    "high-frequency-entry": ["即时零售", "闪购", "买菜", "复购", "外卖"],
    "merchant-readable-store": ["geo", "商家", "卖家", "商品资料", "可见性"],
}

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
            source = clean_text(source_match.group(1)) if source_match else "微信公众号"
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
        try:
            response = session.get(url, timeout=15)
            root = ET.fromstring(response.content)
        except Exception:
            continue
        for node in root.findall(".//item") + root.findall("{http://www.w3.org/2005/Atom}entry"):
            title = clean_text((node.findtext("title") or ""))
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
                title = clean_text(node.findtext("title") or "")
                link = node.findtext("link") or ""
                source = clean_text(node.findtext("source") or "Google News")
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
    text = f"{item['title']} {item.get('snippet', '')}".lower()
    relevance_terms = [word.lower() for word in HIGH_VALUE_WORDS] + [
        "shopping", "commerce", "retail", "merchant", "consumer", "ecommerce",
        "电商", "零售", "购物", "导购", "商家", "商品", "下单", "支付",
    ]
    if not tags:
        return False
    if any(term in text for term in relevance_terms):
        return True
    return False


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
    existing_keys = {(item.get("title"), item.get("source")) for item in existing}
    raw_items = fetch_wechat(days) + fetch_rss(days) + fetch_google_news(days)
    normalized = [normalize_item(item) for item in raw_items if item.get("title") and item.get("url")]
    normalized = [item for item in normalized if item]
    selected = [item for item in normalized if item["valueScore"] >= 72 and (item["title"], item["source"]) not in existing_keys]
    unique_selected: list[dict[str, Any]] = []
    seen_selected: set[tuple[str, str]] = set()
    for item in selected:
        key = (item["title"], item["source"])
        if key in seen_selected:
            continue
        seen_selected.add(key)
        unique_selected.append(item)
    selected = unique_selected
    selected.sort(key=lambda item: (item["date"], item["valueScore"]), reverse=True)
    selected = selected[:limit]
    if not dry_run:
        merged = selected + existing
        merged.sort(key=lambda item: (item["date"], item["valueScore"]), reverse=True)
        merged = merged[:520]
        write_json(ARTICLES_PATH, merged)
        refresh_monthly_reports(merged)
        meta = load_json(META_PATH, {})
        meta["lastUpdated"] = dt.datetime.now(TZ).replace(microsecond=0).isoformat()
        meta["latestAdded"] = len(selected)
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
