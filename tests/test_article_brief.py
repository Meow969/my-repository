import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import article_brief as b
from localize_summaries import localize_titles,fingerprint
class CardTests(unittest.TestCase):
    def article(self,title='Amazon shopping assistant',**kw):
        a=dict(id='test',url='https://example.com/story',date='2026-10-12',title=title,titleZh='购物助手新闻',corePoint=['The shopping assistant helps compare products.'],summaryZh=['购物助手帮助用户比较商品。'],evidenceLevel='fulltext',sourceKind='media',contentKinds=['产品案例'],source='Test',valueScore=80)
        a.update(kw);return a
    def review(self,a):
        return dict(heading='这次取消对比入口，改变了任务起点',anchorZh='原文描述了入口从详情页改到助手。',quote='The shopping assistant helps compare products.',insight='当前入口要求先选候选，因此应核对选择前后的任务流失。',deepThought='在同一商品页直接比较与跳转后比较的用户意图不同，不能直接用后者更高的成交率证明迁移正确。',validation='对照相同商品查看行为，记录开始对比到完成对比的损失。',evidenceLimit='没有披露入口变更的实验效果。',url=a['url'],sourceHash=b.source_hash(a),reviewedAt='2026-10-13')
    def test_unreviewed_has_no_keyword_generated_insight(self):
        for title in ['Amazon shopping assistant','AI payments authorization','Gap AI try-on','Meta blocks AI shopping','AI shopping forecast 2035']:
            a=self.article(title);v=b.build_brief(a,{})
            self.assertIsNone(v['research']);self.assertEqual(v['researchStatus'],'unreviewed')
            self.assertEqual(v['summary'],a['summaryZh'])
    def test_valid_review_requires_exact_source(self):
        a=self.article();r=self.review(a);v=b.build_brief(a,{'test':r})
        self.assertEqual(v['research']['insight'],r['insight']);self.assertEqual(v['researchStatus'],'reviewed')
        a['corePoint']=['The product was discontinued.'];v=b.build_brief(a,{'test':r})
        self.assertIsNone(v['research']);self.assertEqual(v['researchStatus'],'source_changed')
    def test_changed_url_invalidates_review(self):
        a=self.article();r=self.review(a);a['url']='https://other.example/story'
        self.assertIsNone(b.build_brief(a,{'test':r})['research'])
    def test_incomplete_or_ungrounded_review_is_not_published(self):
        a=self.article();r=self.review(a);r.pop('quote')
        self.assertEqual(b.build_brief(a,{'test':r})['researchStatus'],'incomplete_review')
        r=self.review(a);a['evidenceLevel']='abstract'
        self.assertEqual(b.build_brief(a,{'test':r})['researchStatus'],'insufficient_evidence')
    def test_legacy_template_cannot_leak_through_search(self):
        a=self.article(analysis={'insight':'a generic block'},insight='another generic block')
        with patch.object(b,'read_reviews',return_value={}):b.refresh_briefs([a])
        self.assertNotIn('analysis',a);self.assertNotIn('insight',a);self.assertEqual(a['relatedInsightIds'],[])
    def test_brand_prefix_does_not_evade_duplicate_check(self):
        a=self.review(self.article());c=dict(a,heading='Google: '+a['heading'])
        self.assertTrue(b.same_research(a,c))
    def test_near_copy_is_duplicate(self):
        a=self.review(self.article());c=dict(a,heading='新标题',insight=a['insight']+'建议测试。',deepThought=a['deepThought']+'需要验证。')
        self.assertTrue(b.same_research(a,c))
    def test_only_one_copy_is_published(self):
        a=self.article();c=self.article(id='other',date='2026-10-11',title='Google shopping')
        r=self.review(a);t=self.review(c);t['heading']='Google: '+t['heading']
        with patch.object(b,'read_reviews',return_value={'test':r,'other':t}):b.refresh_briefs([a,c])
        self.assertTrue(a['brief']['research']);self.assertIsNone(c['brief']['research']);self.assertEqual(c['brief']['relatedResearchArticleId'],a['id'])
    def test_no_auto_insights_without_review(self):
        a=self.article();a['brief']=b.build_brief(a,{})
        self.assertEqual(b.reviewed_insights([a],[]),[])
    def test_reviewed_insight_uses_matching_quote(self):
        a=self.article();a['brief']=b.build_brief(a,{'test':self.review(a)})
        first=b.reviewed_insights([a],[]);second=b.reviewed_insights([a],first)
        self.assertEqual(first,second);self.assertEqual(first[0]['evidence'][0]['quote'],a['brief']['research']['quote'])
    def test_generated_keywords_do_not_create_fake_entities(self):
        a=self.article('Authvia: Gap Between Intent and Authorization',tags=['Google'])
        v=b.build_brief(a,{})
        self.assertNotIn('Gap',v['keywords']);self.assertNotIn('Google',v['keywords'])
    def test_headline_does_not_imply_verified_facts(self):
        v=b.build_brief(self.article(evidenceLevel='headline'),{})
        self.assertIn('正文尚未核实',v['summary'][0]);self.assertIsNone(v['research'])
    def test_title_and_summary_remain_available(self):
        a=self.article('京东AI购物助手升级');localize_titles([a],object())
        self.assertEqual(a['titleZh'],a['title']);self.assertTrue(b.build_brief(a,{})['summary'])
    def test_source_hash_ignores_translation_but_not_facts(self):
        a=self.article();h=b.source_hash(a);a['titleZh']='新的中文译名'
        self.assertEqual(b.source_hash(a),h)
        a['title']='Google new product';self.assertNotEqual(b.source_hash(a),h)
    def test_stock_filter_preserves_inventory(self):
        import evidence_pipeline as p
        self.assertTrue(p.related('Vinasoy Cuts Out-of-Stock Rates Using AI Retail Monitoring'))
        self.assertFalse(p.related('Agentic Commerce Senior Manager | Life Sciences'))
if __name__=='__main__':unittest.main()
