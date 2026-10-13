"""Publication gate: fail before committing or deploying inconsistent data."""
import datetime as dt
import json
from pathlib import Path
from evidence_pipeline import public_url, now
from localize_summaries import is_chinese, fingerprint, needs_title_translation
from article_brief import input_hash
from source_thinking import source_hash, evidence, valid_cached
D=Path(__file__).resolve().parents[1]/'data'
def read(name):return json.loads((D/name).read_text())
thinking_store=read('article_thinking.json')
articles=read('articles.json');insights=read('insights.json');reports=read('monthly_reports.json');digest=read('daily_digest.json');meta=read('meta.json')
assert articles,'Empty article store'
ids={a['id'] for a in articles}
assert len(ids)==len(articles),'Duplicate IDs'
for a in articles:
    assert public_url(a['url']),a['id']
    assert dt.date.fromisoformat(a['date'])<=now().date(),a['id']
    assert 0<=a['valueScore']<=100,a['id']
    assert a['evidenceLevel'] in ['fulltext','abstract','headline'],a['id']
    assert a['corePoint'],a['id']
    assert 'analysis' not in a and 'insight' not in a,a['id']
    assert a.get('summaryZh') and all(is_chinese(x) for x in a['summaryZh']),a['id']
    assert a['summarySourceHash']==fingerprint(a['corePoint'][:2]),a['id']
    assert len(a['summaryZh'])==len(a['corePoint'][:2]),a['id']
    assert not a['source'].startswith('发现 · '),a['id']
    assert a.get('titleZh') and a['titleSourceHash']==fingerprint([a['title']]),a['id']
    if needs_title_translation(a['title']):assert is_chinese(a['titleZh']),a['id']
    brief=a['brief']
    assert brief['inputHash']==input_hash(a),a['id']
    assert 1<=len(brief['keywords'])<=5 and brief['summary'],a['id']
    assert all(is_chinese(v) for v in brief['summary']),a['id']
    research=brief['research']
    assert research and research['basisArticleId']==a['id'],a['id']
    assert research['sourceHash']==source_hash(a) and research['url']==a['url'],a['id']
    assert research['quote'] in evidence(a),a['id']
    assert research['mode'] in ('source_reasoning','evidence_question'),a['id']
    for key in ['heading','insight','deepThought','validation']:
        assert research.get(key) and is_chinese(research[key]),a['id']
    if research['mode']=='source_reasoning':
        record=thinking_store[a['id']]
        assert valid_cached(a,record),a['id']
        for key,stored in [('heading','heading'),('insight','insight'),('deepThought','boundary'),('validation','test')]:
            assert research[key]==record[stored],a['id']
reasoned=[a for a in articles if a['brief']['research']['mode']=='source_reasoning']
# Exact duplicate body is rejected; similar topics are allowed only with different reasoning.
assert len({a['brief']['research']['insight'] for a in reasoned})==len(reasoned),'Duplicate article reasoning'
for i in insights:
    assert set(i['relatedArticleIds'])<=ids,i['id']
    assert i['evidence'] and i['counterpoint'] and i['experiment'],i['id']
    if i.get('kind')=='synthesis':assert len({e['articleId'] for e in i['evidence']})>=2,i['id']
    assert all(is_chinese(i[k]) for k in ['title','summary','counterpoint','experiment']),i['id']
    for e in i['evidence']:
        a=next(a for a in articles if a['id']==e['articleId'])
        assert e['quote'] in evidence(a),i['id']
        assert e['sourceHash']==source_hash(a),i['id']
        assert a['evidenceLevel']=='fulltext',i['id']
for r in reports:
    assert r['title'] and r['summary'],r['month']
    assert set(r['topArticleIds'])<=ids,r['month']
    assert set(r.get('summaryArticleIds',[]))<=ids,r['month']
    assert len(r['topArticleIds'])<=5,r['month']
    for article_id in r['topArticleIds']+r.get('summaryArticleIds',[]):
        a=next(a for a in articles if a['id']==article_id)
        assert a['date'].startswith(r['month']),article_id
        assert a['evidenceLevel']=='fulltext',article_id
assert set(digest['articleIds'])<=ids
queue=read('research_queue.json')
assert {a['id'] for a in articles if a['brief']['research']['mode']=='evidence_question'}=={a['id'] for a in queue}
assert set(digest['insightIds'])<={i['id'] for i in insights}
assert meta['articleCount']==len(articles)
print(f'Validated {len(articles)} articles, {len(insights)} evidence-backed hypotheses, {len(reports)} monthly indexes.')
