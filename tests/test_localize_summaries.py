import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import localize_summaries as l
class Stub:
    def __init__(self):self.calls=[]
    def translate(self,values):
        self.calls+=values
        return ['这条购物新闻描述了新的产品功能。' for _ in values]
class LocalizationTests(unittest.TestCase):
    def test_chinese_detector_preserves_mixed_product_names(self):
        self.assertTrue(l.is_chinese('Amazon Rufus 推出新的购物推荐功能。'))
        self.assertFalse(l.is_chinese('Amazon Rufus adds personalized shopping recommendations.'))
    def test_translates_brief_without_modifying_source(self):
        raw='Shopping agents help customers compare products.'
        article=dict(title='Original English title',corePoint=[raw])
        translator=Stub();l.localize_articles([article],translator)
        self.assertEqual(article['corePoint'],[raw]);self.assertEqual(article['title'],'Original English title')
        self.assertTrue(l.is_chinese(article['summaryZh'][0]))
        self.assertEqual(article['summarySourceHash'],l.fingerprint([raw]))
    def test_existing_chinese_is_not_retranslated(self):
        article=dict(title='AI购物',corePoint=['京东发布新的购物助手，帮助用户对比商品。'])
        translator=Stub();l.localize_articles([article],translator)
        self.assertEqual(translator.calls,[]);self.assertEqual(article['summaryZh'],article['corePoint'])
    def test_cache_is_bound_to_evidence(self):
        article=dict(title='Shopping',corePoint=['Shopping agents help compare products.'])
        translator=Stub();l.localize_articles([article],translator)
        count=len(translator.calls);l.localize_articles([article],translator)
        self.assertEqual(len(translator.calls),count)
        article['corePoint']=['Shopping agents now require confirmation for each payment.']
        l.localize_articles([article],translator);self.assertGreater(len(translator.calls),count)
    def test_daily_quarantines_failed_new_brief(self):
        class Failing:
            def translate(self,values):raise ValueError('content translation failed')
        good=dict(id='good',title='AI购物',corePoint=['购物助手帮助用户比较商品并确认购买意图。'])
        bad=dict(id='bad',title='Shopping',corePoint=['Bad English excerpt that cannot be translated.'])
        result=l.localize_articles([good,bad],Failing(),strict=False)
        self.assertEqual([a['id'] for a in result],['good'])
    def test_missing_translated_title_defers_new_article(self):
        class Failing:
            def translate(self,values):raise ValueError('bad title')
        result=l.localize_titles([dict(id='new',title='Untranslatable fresh shopping case')],Failing(),strict=False)
        self.assertEqual(result,[])
    def test_short_translation_cardinality(self):
        self.assertNotEqual(l.fingerprint(['A','B']),l.fingerprint(['AB']))
        self.assertFalse(l.is_chinese(''))
if __name__=='__main__':unittest.main()
