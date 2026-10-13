import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import echo_synthesis as e
class EchoTests(unittest.TestCase):
    def test_topic_ids_unique(self):
        self.assertEqual(len(e.TOPICS),len({t['id'] for t in e.TOPICS}))
    def test_selection_excludes_headline_only(self):
        a=dict(id='one',title='AI shopping survey',date='2026-01-01',source='Test',publisher='test',evidenceLevel='headline',corePoint=['AI shopping survey'])
        self.assertEqual(e.select_sources([a],dict(terms=['survey'])),[])
    def test_signature_tracks_evidence(self):
        a=dict(id='one',title='AI shopping',url='https://example.com/a',evidenceLevel='fulltext',corePoint=['Source one'])
        x=e.topic_signature({'id':'topic'},[a]);a['corePoint']=['Source two'];self.assertNotEqual(x,e.topic_signature({'id':'topic'},[a]))
if __name__=='__main__':unittest.main()
