import copy,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import source_thinking as t
class SourceThinkingTests(unittest.TestCase):
    def article(self):return dict(id='a',title='AI merchant feed',date='2026-01-01',source='Test',url='https://example.com/a',corePoint=['Merchant feeds replace web search in shopping recommendations.'],summaryZh=['购物推荐开始使用商家数据源而非网页搜索。'],evidenceLevel='fulltext')
    def record(self):return dict(id='a',evidenceIndex=0,heading='商品数据源切换需要分离曝光与成交',insight='推荐来源变成商家数据源后，应先检查商品是否接入目录，再分析内容的语义匹配，避免错误地把源头覆盖问题当作排序问题。',boundary='观察到曝光变化，仍不能直接推出用户购买变化。',test='固定同一组任务比较目录覆盖和购买行为。')
    def test_source_quote_exact(self):
        a=self.article();r=t.validate_result(a,self.record());self.assertEqual(r['quote'],a['corePoint'][0]);self.assertTrue(t.valid_cached(a,r))
    def test_source_change_invalidates(self):
        a=self.article();r=t.validate_result(a,self.record());a['corePoint']=['A different claim.'];self.assertFalse(t.valid_cached(a,r))
    def test_bad_index_and_id_fail(self):
        for change in [dict(id='wrong'),dict(evidenceIndex=4),dict(evidenceIndex=True)]:
            r=dict(self.record(),**change)
            with self.assertRaises(ValueError):t.validate_result(self.article(),r)
    def test_generic_old_phrase_fails(self):
        r=self.record();r['heading']='把模糊需求变成可修改的候选条件'
        with self.assertRaises(ValueError):t.validate_result(self.article(),r)
    def test_output_parser_only_assistant_text(self):
        data=dict(output=[dict(type='reasoning',content=[dict(text='hidden')]),dict(type='message',content=[dict(type='output_text',text='{"a":1}')])])
        self.assertEqual(t.extract_output(data),{'a':1})
    def test_missing_model_fails_without_guessing(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(RuntimeError):t.model_json('test')
    def test_offline_fallback_is_a_question_not_review(self):
        a=self.article();r=t.fallback(a)
        self.assertEqual(r['mode'],'evidence_question');self.assertIn(a['summaryZh'][0].rstrip('。'),r['insight'])
        self.assertEqual(r['quote'],a['corePoint'][0]);self.assertNotIn('reviewedAt',r)
if __name__=='__main__':unittest.main()
