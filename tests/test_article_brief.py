import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import article_brief as b
import source_thinking as t
class CardTests(unittest.TestCase):
    def article(self):return dict(id='test',title='Amazon shopping assistant',titleZh='亚马逊购物助手',date='2026-01-01',url='https://example.com/a',corePoint=['Amazon adds personalized recommendations.'],summaryZh=['亚马逊增加个性化推荐。'],evidenceLevel='fulltext',sourceKind='media',source='Test',contentKinds=['产品案例'],valueScore=80,lensId='discovery')
    def record(self,a):return t.validate_result(a,dict(id=a['id'],evidenceIndex=0,heading='个性化推荐要允许当前任务覆盖旧偏好',insight='个性化推荐会提高复用效率，但送礼场景不能套用本人偏好，产品应允许当前任务覆盖记忆。',boundary='发布功能不代表实际推荐效果已经提升。',test='分别检查自购与送礼任务的推荐结果。'))
    def test_every_card_has_source_bound_thought(self):
        a=self.article();r=self.record(a);v=b.build_brief(a,{}, {'test':r})
        self.assertEqual(v['research']['insight'],r['insight']);self.assertEqual(v['research']['mode'],'source_reasoning')
        self.assertEqual(v['summary'],a['summaryZh'])
    def test_absent_generation_still_shows_limited_question(self):
        a=self.article();v=b.build_brief(a,{},{});self.assertTrue(v['research']);self.assertEqual(v['researchStatus'],'evidence_question')
    def test_changed_source_never_reuses_old_conclusion(self):
        a=self.article();r=self.record(a);a['corePoint']=['New evidence.'];v=b.build_brief(a,{}, {'test':r})
        self.assertEqual(v['researchStatus'],'evidence_question');self.assertNotEqual(v['research']['insight'],r['insight'])
    def test_headline_is_not_a_verified_product_claim(self):
        a=self.article();a['evidenceLevel']='headline';v=b.build_brief(a,{},{});self.assertIn('正文尚未核实',v['summary'][0])
    def test_input_hash_changes_with_facts(self):
        a=self.article();h=b.input_hash(a);a['summaryZh']=['不同内容。'];self.assertNotEqual(h,b.input_hash(a))
    def test_no_fake_entities_from_old_tags(self):
        a=self.article();a['tags']=['Google'];self.assertNotIn('Google',b.build_brief(a,{}, {})['keywords'])
if __name__=='__main__':unittest.main()
