#!/usr/bin/env python3
"""Month-bounded historical discovery; checkpoint outside the public data directory."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
import datetime as dt
import json
from pathlib import Path
import urllib.parse
import evidence_pipeline as p

HISTORICAL_QUERIES=[
 ('国内','"AI导购"'),('海外','"AI shopping"'),
 ('国内','"AI购物"'),('海外','"agentic commerce"'),
 ('国内','淘宝 千问 AI 导购'),('海外','Amazon Rufus shopping'),
 ('国内','京东 京言 言犀 导购'),('海外','Walmart Sparky AI shopping'),
 ('国内','美团 小美 AI购物'),('海外','Google AI shopping'),
 ('国内','抖音 豆包 电商 AI'),('海外','ChatGPT Perplexity shopping'),
 ('国内','小红书 AI搜索 购物'),('海外','Shopify Instacart shopping AI'),
 ('国内','AI电商 研究 报告'),('海外','AI shopping consumer survey research'),
 ('国内','AI导购 竞品 分析'),('海外','AI retail shopping McKinsey BCG Bain'),
 ('国内','AI零售 咨询 德勤 贝恩'),('海外','AI shopping Deloitte Accenture Capgemini'),
 ('国内','AI购物 艾瑞 艾媒 CBNData'),('海外','AI shopping Adobe Salesforce report'),
 ('国内','AI导购 试穿 得物 淘宝'),('海外','Zalando Pinterest AI shopping assistant'),
 ('国内','AI电商 阿里 Lazada Shopee'),('海外','AI shopping assistant case study review'),
 ('国内','AI导购 用户研究'),('海外','shopping agent benchmark WebShop'),
]

def months(start,end):
    date=dt.date.fromisoformat(start+'-01');last=dt.date.fromisoformat(end+'-01');result=[]
    while date<=last:
        nxt=(date.replace(day=28)+dt.timedelta(days=4)).replace(day=1)
        result.append((date.isoformat(),nxt.isoformat()));date=nxt
    return result

def source_for(start,end,region,query):
    lang,gl,ceid=('zh-CN','CN','CN:zh-Hans') if region=='国内' else ('en-US','US','US:en')
    url='https://news.google.com/rss/search?'+urllib.parse.urlencode(dict(q=f'{query} after:{start} before:{end}',hl=lang,gl=gl,ceid=ceid))
    return dict(name='历史 · '+query,region=region,kind='discovery',url=url)

def checkpoint(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2))

def discover(start,end,cache):
    path=cache/'candidates.json'
    if path.exists():return json.loads(path.read_text())
    jobs=[(a,b,source_for(a,b,r,q)) for a,b in months(start,end) for r,q in HISTORICAL_QUERIES]
    candidates=[];health=[]
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures={pool.submit(p.fetch_source,s):(a,b,s) for a,b,s in jobs}
        for i,f in enumerate(as_completed(futures),1):
            a,b,s=futures[f];items,h=f.result();health.append(h)
            candidates += [x for x in items if a<=x['date']<b and p.related(x['title'],x.get('snippet',''))]
            if i%28==0:print(f'Discovery {i}/{len(jobs)}: {len(candidates)} relevant candidates',flush=True)
    if not any(h['status']=='ok' for h in health):raise RuntimeError('All historical discovery failed')
    checkpoint(path,candidates);checkpoint(cache/'discovery_health.json',health)
    return candidates

def run(args):
    cache=Path(args.cache);cache.mkdir(parents=True,exist_ok=True)
    raw=discover(args.start,args.end,cache);discovered_count=len(raw);old=p.load('articles.json',[])
    unique=[];seen={p.public_url(a['url']) for a in old};titles={p.title_key(a['title']) for a in old};nearby={}
    for a in old:nearby.setdefault((a['date'][:7],a['region']),[]).append(a)
    for a in sorted(raw,key=lambda a:(a['date'],p.publisher_kind(a['url'])!='unknown'),reverse=True):
        key=p.public_url(a['url'])
        title=p.title_key(a['title']);bucket=(a['date'][:7],a['region'])
        if key in seen or title in titles:continue
        if any(p.duplicate(a,b) for b in nearby.get(bucket,[])):continue
        unique.append(a);seen.add(key);titles.add(title);nearby.setdefault(bucket,[]).append(a)
    # Allocate slots per month AND geography. One crowded month cannot consume the budget.
    buckets={}
    for a in unique:buckets.setdefault((a['date'][:7],a['region']),[]).append(a)
    selected=[]
    for key,items in sorted(buckets.items()):
        by_source=Counter();n=0
        for a in items:
            if by_source[a['source']]>=5:continue
            selected.append(a);by_source[a['source']]+=1;n+=1
            if n>=args.per_region:break
    print(f'Verifying {len(selected)} articles across {len(buckets)} month/region buckets',flush=True)
    result_path=cache/'verified.json';results=json.loads(result_path.read_text()) if result_path.exists() else []
    done={x['inputUrl'] for x in results};todo=[a for a in selected if a['url'] not in done]
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures={pool.submit(p.enrich,a):a for a in todo}
        for i,f in enumerate(as_completed(futures),1):
            raw=futures[f]
            try:article,reason=f.result()
            except Exception as e:article,reason=None,type(e).__name__
            if article and not (args.start<=article['date'][:7]<=args.end):article,reason=None,'outside_original_date_range'
            results.append(dict(inputUrl=raw['url'],article=article,reason=reason))
            if i%20==0:checkpoint(result_path,results);print(f'Verified {i}/{len(todo)}',flush=True)
    checkpoint(result_path,results)
    candidates=[r['article'] for r in results if r['article'] and r['article']['evidenceLevel']!='headline' and r['article']['valueScore']>=60]
    # Existing IDs and content stay; new same-event reports attach as evidence instead of padding.
    merged=list(old);added=[]
    for month in [a[:7] for a,b in months(args.start,args.end)]:
        group=[a for a in candidates if a['date'].startswith(month)]
        for a in p.diverse(group,args.per_month,3):
            duplicate=next((b for b in merged if p.duplicate(a,b) or p.same_event(a,b)),None)
            if duplicate:
                if a['url']!=duplicate['url']:
                    cover=duplicate.setdefault('relatedCoverage',[])
                    if not any(c['url']==a['url'] for c in cover):cover.append({k:a[k] for k in ('title','source','url')})
                continue
            a['historyBackfill']=True;merged.append(a);added.append(a)
    merged.sort(key=lambda a:(a['date'],a['valueScore']),reverse=True)
    checkpoint(cache/'merged_articles.json',merged)
    audit=dict(start=args.start,end=args.end,discovered=discovered_count,verified=len(results),added=len(added),before=dict(sorted(Counter(a['date'][:7] for a in old).items())),after=dict(sorted(Counter(a['date'][:7] for a in merged).items())),regions=dict(Counter(a['region'] for a in added)),rejected=dict(Counter(r['reason'] for r in results if r['reason'])))
    checkpoint(cache/'audit.json',audit);print(json.dumps(audit,ensure_ascii=False,indent=2),flush=True)
    print('Staged historical articles at '+str(cache/'merged_articles.json')+'; not yet published.',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--start',default='2025-09');parser.add_argument('--end',default=p.now().strftime('%Y-%m'));parser.add_argument('--per-region',type=int,default=32);parser.add_argument('--per-month',type=int,default=32);parser.add_argument('--cache',default='/tmp/radar-history')
    run(parser.parse_args())
