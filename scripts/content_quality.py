from __future__ import annotations

import html
import re
import unicodedata
import urllib.parse
from difflib import SequenceMatcher
from typing import Any

SOURCE_ALIASES = {
    "digitalcommerce360.com": "Digital Commerce 360",
    "digital commerce 360": "Digital Commerce 360",
    "aboutamazon.com": "About Amazon",
    "amazon news": "About Amazon",
    "google blog": "Google Blog",
    "blog.google": "Google Blog",
    "practicalecommerce.com": "Practical Ecommerce",
    "practical ecommerce": "Practical Ecommerce",
    "modernretail.co": "Modern Retail",
    "modern retail": "Modern Retail",
    "pymnts": "PYMNTS.com",
    "pymnts.com": "PYMNTS.com",
    "retail dive": "Retail Dive",
    "retaildive.com": "Retail Dive",
    "theverge.com": "The Verge",
    "techcrunch.com": "TechCrunch",
    "qq news": "QQ News",
    "sohu": "Sohu",
    "36kr": "36氪",
    "36氪": "36氪",
    "huxiu": "虎嗅",
    "虎嗅": "虎嗅",
    "钛媒体": "钛媒体",
    "人人都是产品经理": "人人都是产品经理",
    "亿邦动力": "亿邦动力网",
}

SOURCE_PREFERENCE = {
    "Google Shopping Blog": 34,
    "Google Blog": 32,
    "About Amazon": 32,
    "OpenAI Blog": 30,
    "OpenAI": 30,
    "Shopify Blog": 28,
    "Shopify": 28,
    "Anthropic": 28,
    "Stripe": 26,
    "Mastercard": 26,
    "Visa": 26,
    "McKinsey & Company": 25,
    "BCG": 24,
    "a16z": 24,
    "Digital Commerce 360": 22,
    "Retail Dive": 21,
    "Modern Retail": 20,
    "Practical Ecommerce": 20,
    "PYMNTS.com": 19,
    "The Verge": 18,
    "TechCrunch": 18,
    "InfoQ-CN": 15,
    "36氪": 14,
    "虎嗅": 14,
    "钛媒体": 14,
    "亿邦动力网": 14,
    "人人都是产品经理": 12,
    "Google News Search": -20,
}

SOURCE_SUFFIXES = sorted({*SOURCE_ALIASES.keys(), *SOURCE_ALIASES.values()}, key=len, reverse=True)
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "utm_id",
    "gclid", "fbclid", "mc_cid", "mc_eid", "spm", "from", "source",
}


def clean_url(url: str) -> str:
    cleaned = str(url or "").strip().replace("\\/", "/")
    cleaned = re.sub(r"&(?:amp|#0*38|#x0*26);", "&", cleaned, flags=re.I)
    cleaned = re.sub(r"%(?:c3%97|C3%97)tamp%3[dD]", "&timestamp=", cleaned)
    cleaned = cleaned.replace("×tamp=", "&timestamp=")
    return cleaned.strip(' \"\'')


def is_temporary_wechat_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(clean_url(url))
    if parsed.netloc.lower() != "mp.weixin.qq.com":
        return False
    params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
    return parsed.path == "/s" and ("signature" in params or "timestamp" in params or params.get("src") == "11")
SHOPPING_TERMS = [
    "shopping", "commerce", "retail", "merchant", "seller", "ecommerce", "checkout", "cart",
    "product discovery", "personal shopper", "try on", "rufus", "agentic commerce", "storefront",
    "电商", "零售", "购物", "导购", "商家", "卖家", "商品", "下单", "支付", "淘宝", "京东",
    "闪购", "买菜", "货架", "履约", "售后", "比价", "试穿",
]
AI_TERMS = [
    "ai", "agent", "assistant", "chatgpt", "gemini", "claude", "perplexity", "rufus", "anthropic",
    "智能体", "大模型", "助手", "千问", "豆包", "openclaw", "对话式",
]


def canonical_source(source: str) -> str:
    cleaned = re.sub(r"\s+", " ", html.unescape(source or "")).strip()
    lowered = cleaned.lower().removeprefix("www.")
    for key, value in SOURCE_ALIASES.items():
        if key in lowered:
            return value
    return cleaned or "Unknown"


def clean_display_title(title: str, source: str = "") -> str:
    cleaned = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", title or ""))).strip()
    candidates = [source, canonical_source(source), *SOURCE_SUFFIXES]
    for suffix in candidates:
        suffix = (suffix or "").strip()
        if len(suffix) < 2:
            continue
        cleaned = re.sub(rf"\s*[-–—|｜]\s*{re.escape(suffix)}\s*$", "", cleaned, flags=re.I)
    return cleaned.strip(" -–—|｜")


def canonical_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(clean_url(url))
    except Exception:
        return clean_url(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    query = [(k, v) for k, v in query if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    path = re.sub(r"/+$", "", parsed.path)
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower().removeprefix("www."), path, urllib.parse.urlencode(query), ""))


def normalized_title(title: str, source: str = "") -> str:
    text = unicodedata.normalize("NFKC", clean_display_title(title, source)).lower()
    text = re.sub(r"\b(全文|深度|独家|原创|万字长文分享)\b", "", text)
    text = re.sub(r"\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?", "", text)
    text = re.sub(r"\b20\d{2}\b", "", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fa5]+", "", text)
    return text


def normalized_article_text(item: dict[str, Any]) -> str:
    return " ".join([
        str(item.get("title", "")),
        str(item.get("corePoint", "")),
        str(item.get("insight", "")),
        str(item.get("snippet", "")),
        " ".join(item.get("tags", []) or []),
    ]).lower()


def event_signature(item: dict[str, Any]) -> str:
    text = normalized_article_text(item)
    date = str(item.get("date", ""))[:7]
    if ("anthropic" in text or "claude" in text) and any(term in text for term in [
        "merchant blueprint", "商家 agent", "商业智能体", "购物助手", "shopping agents",
        "agentic commerce", "commerce blueprint", "商家运营助手",
    ]):
        return f"{date}:anthropic-commerce-blueprint"
    if ("支付宝" in text or "alipay" in text) and any(term in text for term in ["ju1111", "网站协议", "智能体商业底座"]):
        return f"{date}:alipay-ju1111-protocol"
    return ""


def is_search_placeholder(item: dict[str, Any]) -> bool:
    item_id = str(item.get("id", ""))
    return item_id.startswith("daily-index-") or item.get("category") == "每日检索入口"


def is_ai_shopping_related(item: dict[str, Any]) -> bool:
    if is_search_placeholder(item):
        return False
    text = " ".join([
        str(item.get("title", "")),
        str(item.get("snippet", "")),
        str(item.get("source", "")),
        " ".join(item.get("tags", []) or []),
    ]).lower()
    return any(term.lower() in text for term in SHOPPING_TERMS) and any(term.lower() in text for term in AI_TERMS)


def title_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    a = normalized_title(left.get("title", ""), left.get("source", ""))
    b = normalized_title(right.get("title", ""), right.get("source", ""))
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if min(len(a), len(b)) >= 18 and (a in b or b in a):
        return 0.98
    return SequenceMatcher(None, a, b).ratio()


def is_duplicate(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if is_search_placeholder(left) and is_search_placeholder(right) and left.get("date") != right.get("date"):
        return False
    left_url = canonical_url(left.get("url", ""))
    right_url = canonical_url(right.get("url", ""))
    if left_url and right_url and left_url == right_url:
        return True
    left_event = event_signature(left)
    if left_event and left_event == event_signature(right):
        return True
    left_title = normalized_title(left.get("title", ""), left.get("source", ""))
    right_title = normalized_title(right.get("title", ""), right.get("source", ""))
    if not left_title or not right_title:
        return False
    if left_title == right_title:
        return True
    if min(len(left_title), len(right_title)) >= 18 and (left_title in right_title or right_title in left_title):
        return True
    return min(len(left_title), len(right_title)) >= 24 and title_similarity(left, right) >= 0.92


def item_quality(item: dict[str, Any]) -> tuple[int, int, str]:
    source = canonical_source(item.get("source", ""))
    url = canonical_url(item.get("url", ""))
    score = int(item.get("valueScore", 0) or 0)
    score += SOURCE_PREFERENCE.get(source, 0)
    if is_search_placeholder(item):
        score -= 60
    if "news.google.com/search" in url:
        score -= 25
    if "news.google.com/rss/articles" in url:
        score -= 6
    if url.startswith("https://mp.weixin.qq.com/") or "mp.weixin.qq.com" in url:
        score += 8
    score += min(len(item.get("snippet", "") or item.get("corePoint", "")), 240) // 60
    try:
        date_rank = int(str(item.get("date", "")).replace("-", ""))
    except ValueError:
        date_rank = 0
    return (score, date_rank, source)


def normalize_item_identity(item: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(item)
    normalized["source"] = canonical_source(str(normalized.get("source", "")))
    normalized["title"] = clean_display_title(str(normalized.get("title", "")), normalized["source"])
    normalized["url"] = canonical_url(str(normalized.get("url", ""))) or str(normalized.get("url", ""))
    return normalized


def dedupe_items(items: list[dict[str, Any]], limit: int | None = None) -> list[dict[str, Any]]:
    normalized = [normalize_item_identity(item) for item in items if item.get("title") and not is_search_placeholder(item)]
    ordered = sorted(normalized, key=item_quality, reverse=True)
    kept: list[dict[str, Any]] = []
    for item in ordered:
        if any(is_duplicate(item, existing) for existing in kept):
            continue
        kept.append(item)
    kept.sort(key=lambda item: (item.get("date", ""), int(item.get("valueScore", 0) or 0)), reverse=True)
    return kept[:limit] if limit else kept
