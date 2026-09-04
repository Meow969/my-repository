#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
from html import unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
QUALITY_DOMAINS = [
    'openai.com', 'blog.google', 'aboutamazon.com', 'shopify.com', 'mckinsey.com',
    'stripe.com', 'mastercard.com', 'visa.com', 'perplexity.ai', 'a16z.com',
    '36kr.com', 'huxiu.com', 'iyiou.com', 'geekpark.net', 'leiphone.com', 'mp.weixin.qq.com'
]


def strip_tags(value: str) -> str:
    value = re.sub(r'<script[\s\S]*?</script>', ' ', value, flags=re.I)
    value = re.sub(r'<style[\s\S]*?</style>', ' ', value, flags=re.I)
    value = re.sub(r'<[^>]+>', ' ', value)
    return re.sub(r'\s+', ' ', unescape(value)).strip()


def tokenize(text: str) -> list[str]:
    cn = re.findall(r'[\u4e00-\u9fa5]{2,}', text)
    chunks = []
    for chunk in cn:
        chunks.extend(chunk[i:i + 4] for i in range(0, max(1, len(chunk) - 1), 2))
    en = re.findall(r'[a-zA-Z][a-zA-Z\-]{2,}', text)
    seen = []
    for token in chunks + en:
        if token not in seen:
            seen.append(token)
    return seen[:16]


def extract_bing_results(markup: str) -> list[dict]:
    blocks = re.findall(r'<li class="b_algo"[\s\S]*?</li>', markup)
    results = []
    for block in blocks:
        match = re.search(r'<h2[\s\S]*?<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', block, flags=re.I)
        snippet = re.search(r'<p[^>]*>([\s\S]*?)</p>', block, flags=re.I)
        if not match:
            continue
        url = unescape(match.group(1))
        if not url.startswith('http'):
            continue
        results.append({
            'title': strip_tags(match.group(2)),
            'url': urllib.parse.unquote(url),
            'snippet': strip_tags(snippet.group(1)) if snippet else '',
        })
    return results


def score_result(result: dict, note: str) -> int:
    haystack = f"{result.get('title','')} {result.get('snippet','')} {result.get('url','')}".lower()
    score = sum(2 for token in tokenize(note) if token.lower() in haystack)
    score += 8 if any(domain in result.get('url', '') for domain in QUALITY_DOMAINS) else 0
    score += 6 if re.search(r'ai|agent|shopping|commerce|retail|导购|购物|电商|智能体|零售|支付|履约', haystack, re.I) else 0
    score -= 10 if re.search(r'招聘|培训|下载|破解|广告|招商|课程', haystack) else 0
    return score


def search_web(note: str) -> list[dict]:
    queries = [
        f'{note} AI购物 导购 智能体 案例',
        f'{note} Agentic Commerce shopping agent retail case',
        f'{note} site:mp.weixin.qq.com AI购物 OR AI导购',
        f'{note} site:blog.google OR site:aboutamazon.com OR site:shopify.com AI shopping',
    ]
    session = requests.Session()
    session.headers.update({'user-agent': 'Mozilla/5.0', 'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8'})
    results = []
    for query in queries:
        try:
            response = session.get('https://www.bing.com/search', params={'q': query, 'count': 10}, timeout=12)
            results.extend(extract_bing_results(response.text))
        except requests.RequestException:
            pass
    deduped = []
    seen = set()
    for result in results:
        key = re.sub(r'[#?].*$', '', result['url'])
        if key not in seen:
            seen.add(key)
            result['score'] = score_result(result, note)
            if result['score'] > 3:
                deduped.append(result)
    deduped.sort(key=lambda item: item['score'], reverse=True)
    return deduped[:6]


def synthesize(note: str, results: list[dict]) -> str:
    names = '、'.join(f"《{item['title']}》" for item in results[:3]) or '搜索结果'
    lower = note.lower()
    angle = '这个想法的关键不是单点功能，而是要验证它能否改变用户决策链路。'
    if re.search(r'复购|日常|买菜|低风险|高频', note):
        angle = '这个方向适合先做高频低风险场景，用偏好记忆和履约稳定性建立授权习惯，再逐步迁移到更复杂品类。'
    if re.search(r'信任|授权|代买|自动', note):
        angle = '这个方向的核心是信任阶梯：先解释、再筛选、再加购、最后授权下单，自动化必须建立在可撤回和可追责之上。'
    if re.search(r'商家|品牌|geo|可见性|商品', lower):
        angle = '这个方向本质是商家信息资产问题：商品卖点、证据、库存、价格和售后必须机器可读，AI才敢把候选资格交给品牌。'
    if re.search(r'支付|checkout|闭环|履约', lower):
        angle = '这个方向会进入交易基础设施层，重点不再是推荐多准，而是价格、库存、支付、售后和责任边界是否可靠。'
    return f'基于你的观点和{names}，可延展出一个产品判断：{angle} 下一步可以把它拆成三个验证问题：用户是否愿意交出这类决策权、AI是否有足够证据做判断、推荐之后能否稳定完成交易或后续服务。'


class Handler(SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/api/search-note':
            self.send_error(404)
            return
        length = int(self.headers.get('content-length', '0'))
        body = self.rfile.read(length).decode('utf-8')
        try:
            payload = json.loads(body or '{}')
        except json.JSONDecodeError:
            payload = {}
        note = str(payload.get('note', '')).strip()
        results = search_web(note) if note else []
        if len(results) < 3 and note:
            q = urllib.parse.quote(note[:80])
            results.extend([
                {'title': '微信文章搜索：相关中文案例', 'url': f'https://weixin.sogou.com/weixin?type=2&query={q}', 'snippet': '用于继续查找中文公众号案例和分析。', 'score': 4},
                {'title': 'Google 搜索：海外 AI shopping agent 案例', 'url': f'https://www.google.com/search?q={q}+AI+shopping+agent+case', 'snippet': '用于继续查找海外产品案例。', 'score': 4},
                {'title': 'Google 搜索：Agentic Commerce report', 'url': f'https://www.google.com/search?q={q}+Agentic+Commerce+retail+report', 'snippet': '用于继续查找行业报告和协议动态。', 'score': 4},
            ])
        response = {'keywords': tokenize(note)[:8], 'results': results[:6], 'insight': synthesize(note, results)}
        data = json.dumps(response, ensure_ascii=False).encode('utf-8')
        self.send_response(200)
        self.send_header('content-type', 'application/json; charset=utf-8')
        self.send_header('content-length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    import os
    os.chdir(ROOT)
    ThreadingHTTPServer(('', args.port), Handler).serve_forever()
