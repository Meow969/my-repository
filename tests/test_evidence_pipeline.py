import datetime as dt
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evidence_pipeline as p

class ParsingTests(unittest.TestCase):
    def test_dates_do_not_invent_recency(self):
        for value in ['',None,'broken','2099-01-01']:
            self.assertEqual(p.date_value(value),'')
        self.assertEqual(p.date_value('2026-01-01T20:00:00Z'),'2026-01-02')
    def test_namespaced_atom(self):
        xml='''<feed xmlns="http://www.w3.org/2005/Atom"><title>Test</title><entry><title>AI shopping experiment</title><link href="https://example.com/news"/><published>2026-01-03T00:00:00Z</published><summary>Real evidence on retail conversion</summary></entry></feed>'''
        items=p.parse_feed(xml,dict(name='Test',kind='research',region='海外'))
        self.assertEqual(len(items),1);self.assertEqual(items[0]['date'],'2026-01-03')
        self.assertIn('Real evidence',items[0]['snippet'])
    def test_missing_date_skipped(self):
        self.assertEqual(p.parse_feed('<rss version="2.0"><channel><item><title>AI shopping</title><link>https://example.com/x</link></item></channel></rss>',dict(name='Test',kind='media',region='国内')),[])
    def test_google_publisher_not_query(self):
        xml='<rss version="2.0"><channel><item><title>AI shopping - Original News</title><link>https://example.com/a</link><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate><source>Original News</source></item></channel></rss>'
        item=p.parse_feed(xml,dict(name='发现 · AI',kind='discovery',region='海外'))[0]
        self.assertEqual(item['source'],'Original News');self.assertEqual(item['title'],'AI shopping')
    def test_publication_not_modification(self):
        html='<script type="application/ld+json">{"@type":"NewsArticle","datePublished":"2025-06-01","dateModified":"2026-10-01"}</script><article><p>'+'AI shopping affects discovery and checkout. '*10+'</p></article>'
        self.assertEqual(p.extract_page(html,'https://example.com/a')['published'],'2025-06-01')
    def test_sitemap_not_publication(self):
        xml='<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.com/ai-shopping</loc><lastmod>2026-10-01</lastmod></url></urlset>'
        item=p.sitemap_candidates(xml,dict(name='Test',kind='official',region='海外'))[0]
        self.assertEqual(item['date'],'')
    def test_safe_urls_and_slashes(self):
        for url in ['javascript:alert(1)','http://127.0.0.1/a','http://localhost/a','https://u:p@example.com','https://x.jd.com/a','file:///tmp/x']:
            self.assertEqual(p.public_url(url),'')
        self.assertEqual(p.public_url('https://example.com/feed/?utm_source=x'),'https://example.com/feed/')
    def test_same_platform_different_news_kept(self):
        a={'date':'2026-01-01','title':'Amazon launches new AI shopping checkout authorization','url':'https://example.com/a'}
        b={'date':'2026-01-01','title':'Amazon announces virtual try on and size comparison','url':'https://example.com/b'}
        self.assertFalse(p.duplicate(a,b));self.assertTrue(p.duplicate(a,dict(a,url=a['url']+'?utm_source=x')))
    def test_deduplicate_facts(self):
        phrase='AI shopping allows shoppers to compare verified prices across merchants.'
        self.assertEqual(p.evidence_points(phrase+' '+phrase,'AI shopping'),[phrase])
    def test_topic_noise(self):
        for title in ['比亚迪首次 OTA 新增生态智能体服务','世界模型赛道谁在突围','AI 催收公司融资','智能座舱深度体验导购报告','Token用不完很焦虑','Shopify shares climb as AI-commerce optimism grows']:
            self.assertFalse(p.related(title,'AI shopping ecommerce retail'),title)
        for title in ['Google AI shopping adds virtual try-on','京东AI购升级购物推荐','Visa agentic payment authorization']:
            self.assertTrue(p.related(title),title)
    def test_redirect_validation(self):
        response=Mock(is_redirect=True,headers={'Location':'http://127.0.0.1/private'})
        with patch.object(p.requests,'get',return_value=response) as mock:
            with self.assertRaises(ValueError):p.get('https://example.com/feed/')
            self.assertEqual(mock.call_count,1)
    def test_source_diversity(self):
        today=p.now().date().isoformat()
        items=[dict(id=str(i),title='Different article '+str(i),url=f'https://site{i%3}.com/{i}',source=str(i%3),publisher=str(i%3),date=today,valueScore=90-i,lensId='discovery') for i in range(12)]
        selected=p.diverse(items,8,2)
        self.assertEqual(len(selected),6)
    def test_failed_fetch_not_verified(self):
        raw=dict(title='AI shopping adds checkout',date='2026-01-01',source='Test',sourceKind='official',region='海外',url='https://example.com/a',snippet='AI shopping adds a checkout flow for consumers to approve orders and choose merchants. '*4)
        with patch.object(p,'get',side_effect=ValueError('unavailable')):
            a,_=p.enrich(raw)
        self.assertNotEqual(a['evidenceLevel'],'fulltext');self.assertEqual(a['readingTier'],'观察')
    def test_insights_change_only_with_evidence(self):
        a=dict(id='one',title='AI shopping: a new checkout flow',source='Test',publisher='example.com',date=p.now().date().isoformat(),url='https://example.com/a',valueScore=90,lensId='payments',readingTier='精选',evidenceLevel='fulltext',corePoint=['AI shopping checkout requires the customer to approve each order.'])
        first=p.make_insights([a],[]);second=p.make_insights([a],first)
        self.assertEqual(first,second);self.assertEqual(first[0]['confidence'],'待验证假设')
    def test_event_bundling_does_not_mix_capabilities(self):
        a=dict(title='TikTok launches AI shopping assistant and one-click checkout',date='2026-10-01')
        b=dict(title='TikTok rolls out one-click checkout',date='2026-10-02')
        self.assertTrue(p.same_event(a,b))
        self.assertFalse(p.same_event(a,dict(b,title='TikTok adds virtual try-on to shopping')))
        self.assertFalse(p.same_event(a,dict(b,date='2026-10-07')))
    def test_bad_publisher_date_cannot_promote_old_news(self):
        raw=dict(title='AI shopping launches checkout',date='2026-01-01',url='https://example.com/article',source='Test',region='海外')
        page=dict(published=p.now().date().isoformat(),description='',paragraphs=['AI shopping has launched a new checkout that verifies authorization. '*8])
        with patch.object(p,'get',return_value=Mock(headers={'Content-Type':'text/html'},text='',url=raw['url'])),patch.object(p,'extract_page',return_value=page):
            a,_=p.enrich(raw)
        self.assertEqual(a['date'],'2026-01-01')
        self.assertIn('冲突',a['dateBasis'])
    def test_cached_fulltext_is_not_replaced_by_rss_snippet(self):
        excerpt='Gap Inc. introduces a new AI shopping experience with verified product recommendations. '*6
        raw=dict(title='Gap AI shopping',date='2026-01-01',url='https://example.com/article',source='Test',region='海外',excerpt=excerpt,snippet='Short feed teaser',evidenceLevel='fulltext')
        a,_=p.enrich(raw,verify=False)
        self.assertIn('Gap Inc.',a['excerpt'])
        self.assertNotIn('Short feed teaser',a['excerpt'])
        self.assertIn('Gap Inc.',a['corePoint'][0])
    def test_monthly_reports_stay_in_month_and_prefer_evidence(self):
        def article(i,date,level='fulltext',tier='精选'):
            return dict(id=i,date=date,title='Stripe agentic checkout '+i,url='https://example.com/'+i,source='Stripe',publisher='example.com',valueScore=90,lensId='payments',evidenceLevel=level,readingTier=tier)
        items=[article('a','2026-01-01'),article('b','2026-02-01'),article('c','2026-01-02','headline','观察')]
        reports=p.build_reports(items)
        self.assertEqual(reports[0]['month'],'2026-02')
        self.assertEqual(reports[1]['topArticleIds'],['a'])
        self.assertEqual(reports[1]['articleCount'],2)
        self.assertIn('Stripe',reports[1]['summary'])
        self.assertIn('授权',reports[1]['summary'])
        self.assertEqual(reports[1]['summaryArticleIds'],['a'])
    def test_month_with_only_headlines_does_not_invent_summary(self):
        item=dict(id='h',title='AI shopping',date='2026-01-01',evidenceLevel='headline',readingTier='观察')
        report=p.build_reports([item])[0]
        self.assertEqual(report['topArticleIds'],[])
        self.assertIn('暂无可核验原文',report['summary'])

    def test_source_registry_unique(self):
        self.assertEqual(len(p.SOURCES),len({s['url'] for s in p.SOURCES}))
        self.assertTrue(all(p.public_url(s['url']) for s in p.SOURCES))

if __name__=='__main__':unittest.main()
