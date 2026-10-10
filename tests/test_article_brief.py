import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import article_brief as b
from localize_summaries import needs_title_translation,localize_titles,fingerprint
class CardTests(unittest.TestCase):
    def article(self,title,**kw):
        a=dict(id='test',title=title,titleZh='中文标题说明',corePoint=['The shopping assistant helps compare products.'],summaryZh=['购物助手帮助用户比较商品。','它保留用户修改购物条件的能力。'],evidenceLevel='fulltext',sourceKind='media',contentKinds=['产品案例'])
        a.update(kw);return a
    def test_gap_between_does_not_invent_gap_brand(self):
        v=b.build_brief(self.article("Authvia Patent Targets the Gap Between Intent and Payment"))
        self.assertNotIn('Gap',v['keywords'])
    def test_access_is_not_generic_shopping(self):
        a=self.article('Amazon blocks Meta shopping agent');v=b.build_brief(a)
        self.assertEqual(v['research']['topic'],'access')
        self.assertIn('Amazon',v['keywords']);self.assertIn('平台开放',v['keywords'])
        self.assertIn('允许',v['research']['insight'])
    def test_identity_vs_authorization(self):
        a=b.build_brief(self.article('Who is behind the AI agent? Identity challenge'))
        c=b.build_brief(self.article('Authvia payment authorization patent'))
        self.assertEqual(a['research']['topic'],'identity');self.assertEqual(c['research']['topic'],'authorization')
        self.assertNotEqual(a['research']['deepThought'],c['research']['deepThought'])
    def test_visual_profile_from_title(self):
        a=self.article('Gap launches AI try-on with Alta Daily',corePoint=['The merchant can support checkout and payment.'])
        self.assertEqual(b.case_profile(a)['id'],'visual')
    def test_generated_analysis_does_not_contaminate_classification(self):
        a=self.article('Amazon AI shopping assistant',analysis={'insight':'authorization fraud identity'},tags=['虚拟试穿'])
        self.assertEqual(b.case_profile(a)['id'],'discovery')
    def test_facts_do_not_include_hypotheses(self):
        a=self.article('AI shopping assistant');v=b.build_brief(a)
        self.assertEqual(v['summary'],a['summaryZh'])
        self.assertEqual(v['research']['basisArticleId'],'test')
    def test_dedupe_repeated_summary(self):
        a=self.article('AI shopping',summaryZh=['助手帮助用户比较价格。','助手帮助用户比较价格。'])
        self.assertEqual(len(b.build_brief(a)['summary']),1)
    def test_prediction_caveat(self):
        v=b.build_brief(self.article('AI shopping forecast by 2035'))
        self.assertEqual(v['summaryLabel'],'趋势预测');self.assertIn('不是已实现',v['research']['evidenceLimit'])
    def test_headline_does_not_imply_verified_facts(self):
        v=b.build_brief(self.article('AI shopping',evidenceLevel='headline'))
        self.assertIn('正文尚未核实',v['summary'][0]);self.assertIn('待验证',v['research']['deepThought'])
    def test_hash_changes_with_fact_translation(self):
        a=self.article('AI shopping');first=b.input_hash(a);a['summaryZh']=['改变后的中文要点。'];self.assertNotEqual(first,b.input_hash(a))
    def test_title_original_is_preserved(self):
        class Stub:
            def translate(self,values):return ['这是人工智能购物功能' for _ in values]
        a=self.article('Unique shopping news example')
        original=a['title'];localize_titles([a],Stub())
        self.assertEqual(a['title'],original);self.assertEqual(a['titleSourceHash'],fingerprint([original]));self.assertIn('购物',a['titleZh'])
    def test_chinese_title_does_not_invent_english(self):
        a=self.article('京东AI购物助手升级');localize_titles([a],object());self.assertEqual(a['titleZh'],a['title'])
        self.assertFalse(needs_title_translation(a['title']))
    def test_editorial_title_uses_exact_original(self):
        a=self.article('Gap expands AI shopping with Alta Daily and new discovery tools');localize_titles([a],object());self.assertEqual(a['titleZh'],'Gap 通过 Alta Daily 和新的商品发现工具拓展 AI 购物')
    def test_stock_filter_does_not_exclude_inventory_cases(self):
        import evidence_pipeline as p
        self.assertTrue(p.related('Vinasoy Cuts Out-of-Stock Rates Using AI Retail Monitoring'))
        self.assertFalse(p.related('Shopify stock trades at USD 163 as AI commerce grows'))
    def test_recruitment_filtered(self):
        import evidence_pipeline as p
        self.assertFalse(p.related('Agentic Commerce Senior Manager | Life Sciences'))
    def test_summary_sentences_clean(self):
        self.assertEqual(b.clean_sentence('一句中文 , 并带有说明'), '一句中文，并带有说明。')
if __name__=='__main__':unittest.main()
