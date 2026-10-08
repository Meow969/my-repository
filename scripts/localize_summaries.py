#!/usr/bin/env python3
"""Local neural translation of short source excerpts; no API key or per-run quota."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import requests

MODEL_URL='https://argos-net.com/v1/translate-en_zh-1_9.argosmodel'
MODEL_ARCHIVE_HASH='433e7c4f034d87fbe2353161e05f18646d7999452f801a4e1f0378522b9850ab'
MODEL_VERSION='opus-en-zh-1.9-domain-v1'
MODEL_DIR=Path(os.environ.get('RADAR_TRANSLATION_MODEL',str(Path.home()/'.cache/ai-shopping-radar/opus-en-zh-1.9')))
MODEL_FILES={'model/model.bin': '1a039114d9456b6528fabb65b455b6f156319634a0f984b1f6018f7737d67598', 'model/config.json': '3a8660f12559a223969532ff191e5e6f50d4ff24164517edbd6a5090dc5144c6', 'model/shared_vocabulary.json': 'c0b6e24705ec0489d5b810de365959c1013aecd644cfeca161b54ea1df6a7dc0', 'sentencepiece.model': '872224b85a11edc9d769a94949fd387b67ea85b50708db9f91f32f5b497a9af3', 'README.md': '050e546664f0e70d80b6f83aa1da5f04ee85335f4a1b62d1c89184f76100b5dc'}
ROOT=Path(__file__).resolve().parents[1]


def is_chinese(value):
    han=len(re.findall(r'[\u4e00-\u9fff]',value));latin=len(re.findall(r'[a-zA-Z]',value))
    return han>=12 or (han>=4 and han/(han+latin or 1)>.18)


def fingerprint(points):
    return hashlib.sha256(json.dumps(points,ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def prepare_model():
    import zipfile
    MODEL_DIR.mkdir(parents=True,exist_ok=True)
    if all((MODEL_DIR/name).exists() and file_hash(MODEL_DIR/name)==digest for name,digest in MODEL_FILES.items()):return MODEL_DIR
    with requests.get(MODEL_URL,timeout=(10,180),stream=True) as r:
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(dir=MODEL_DIR,delete=False) as f:
            archive=Path(f.name)
            for chunk in r.iter_content(1024*1024):f.write(chunk)
    try:
        if file_hash(archive)!=MODEL_ARCHIVE_HASH:raise RuntimeError('Translation model archive checksum mismatch')
        with zipfile.ZipFile(archive) as z:
            for name,digest in MODEL_FILES.items():
                content=z.read('translate-en_zh-1_9/'+name)
                if hashlib.sha256(content).hexdigest()!=digest:raise RuntimeError('Translation model file checksum mismatch: '+name)
                path=MODEL_DIR/name;path.parent.mkdir(parents=True,exist_ok=True)
                tmp=path.with_suffix('.tmp');tmp.write_bytes(content);tmp.replace(path)
    finally:archive.unlink(missing_ok=True)
    return MODEL_DIR


def normalize_terms(source,value):
    value=value.replace('▁',' ').strip()
    if any(c in source for c in '‑–—'):value=value.replace(' ⁇ ','-')
    glossary={
      r'Cart Assistant':{'纸牌助理':'Cart Assistant','漫画助理':'Cart Assistant'},
      r'\bInstacart\b':{'Instacert':'Instacart'},
      r'whitelabel':{'白色标签':'白标'},
      r'grocery-native':{'杂货本地化':'面向生鲜杂货业务的'},
      r'\bGap\b':{'空白':'Gap','差距公司':'Gap'},
      r'\bMars\b':{'火星':'Mars'},
      r'\bConstructor\b':{'施工公司':'Constructor','建筑商':'Constructor','构造器':'Constructor'},
      r'\bNewegg\b':{'一个新人':'Newegg','新蛋':'Newegg'},
      r'\bMyprotein\b':{'我的蛋白质':'Myprotein'},
      r'\bcheckout\b':{'现金存款':'结账','退房':'结账','签出':'结账','代理清单':'智能体结账'},
      r'\bgrocery runs\b':{'杂货运营':'日常食品采购'},
      r'\bhesitant\b':{'犹 ⁇ ':'犹豫','犹⁇':'犹豫'},
    }
    for term,replacements in glossary.items():
        if re.search(term,source):
            for old,new in replacements.items():value=value.replace(old,new)
    return value


class Translator:
    def __init__(self):
        import ctranslate2
        import sentencepiece
        root=prepare_model()
        self.tokenizer=sentencepiece.SentencePieceProcessor(model_file=str(root/'sentencepiece.model'))
        self.model=ctranslate2.Translator(str(root/'model'),device='cpu',compute_type='int8',inter_threads=1,intra_threads=min(4,os.cpu_count() or 2))

    def translate(self,texts):
        batches=[self.tokenizer.encode(text.replace('‑','-').replace('–','-').replace('—','-'),out_type=str) for text in texts]
        results=self.model.translate_batch(batches,beam_size=4,max_decoding_length=256,max_batch_size=16,no_repeat_ngram_size=4)
        output=[]
        for source,result in zip(texts,results):
            value=self.tokenizer.decode(result.hypotheses[0]).strip()
            value=re.sub(r'([\u4e00-\u9fff]) +(?=[\u4e00-\u9fff])',r'\1',value)
            if re.search(r'generative (?:AI|artificial intelligence)',source,re.I):
                value=value.replace('基因化','生成式').replace('生成性','生成式').replace('AI动力','AI驱动')
            if re.search(r'\bshoppers\b',source,re.I) and not re.search(r'shop.?owners',source,re.I):value=value.replace('店主','购物者')
            if 'Rufus' in source:value=value.replace('鲁弗斯','Rufus').replace('鲁夫斯','Rufus')
            if re.search(r'\bpiloting\b',source,re.I):value=value.replace('驾驶','试点')
            value=normalize_terms(source,value)
            if not is_chinese(value):raise ValueError('Non-Chinese translation: '+repr((source,value)))
            output.append(value)
        return output


def localize_articles(articles,translator=None,strict=True):
    """Reuse hash-bound translations; missing/failed translations block publication."""
    cache={};pending={};persist=translator is None
    override_path=Path(__file__).with_name('editorial_summaries.json')
    overrides=json.loads(override_path.read_text()) if override_path.exists() else {}
    cache_path=MODEL_DIR/(MODEL_VERSION+'-cache.json')
    if persist and cache_path.exists():
        try:cache=json.loads(cache_path.read_text())
        except (ValueError,OSError):cache={}
        cache={k:v for k,v in cache.items() if isinstance(v,str) and is_chinese(v)}
    for a in articles:
        points=(a.get('corePoint') or [a['title']])[:2]
        key=fingerprint(points)
        if key in overrides:
            for src,zh in zip(points,overrides[key]['summaryZh']):cache[src]=zh
        elif a.get('summaryVersion')==MODEL_VERSION and a.get('summarySourceHash')==key and a.get('summaryZh') and all(is_chinese(v) for v in a['summaryZh']):
            for src,zh in zip(points,a['summaryZh']):cache[src]=zh
        caveats=a.get('sourceCaveats',[])
        if a.get('caveatsSourceHash')==fingerprint(caveats) and a.get('sourceCaveatsZh'):
            for src,zh in zip(caveats,a['sourceCaveatsZh']):cache[src]=zh
        for value in points+caveats:
            if is_chinese(value):cache.setdefault(value,value)
            elif value not in cache:pending[value]=None
    todo=[v for v in pending if v not in cache]
    if todo:
        translator=translator or Translator()
        for start in range(0,len(todo),16):
            chunk=todo[start:start+16]
            try:
                translations=translator.translate(chunk)
            except ValueError:
                if strict:raise
                translations=[]
                for value in chunk:
                    try:translations.append(translator.translate([value])[0])
                    except ValueError:translations.append(None)
            if len(translations)!=len(chunk):raise ValueError('Incomplete translation batch')
            for source,zh in zip(chunk,translations):
                if zh is None and not strict:continue
                if not is_chinese(zh):raise ValueError('Invalid Chinese brief')
                cache[source]=zh
            if persist:
                cache_path.parent.mkdir(parents=True,exist_ok=True)
                tmp=cache_path.with_suffix('.tmp');tmp.write_text(json.dumps(cache,ensure_ascii=False));tmp.replace(cache_path)
            if start%160==0:print(f'Chinese briefs: {min(start+16,len(todo))}/{len(todo)} excerpts',flush=True)
    retained=[]
    for a in articles:
        points=(a.get('corePoint') or [a['title']])[:2]
        if any(v not in cache for v in points):
            if strict:raise ValueError('Missing translated brief')
            print('Quarantine article without a Chinese brief: '+a['id'],flush=True);continue
        a['summaryZh']=[normalize_terms(v,cache[v]) for v in points]
        a['sourceCaveatsZh']=[normalize_terms(v,cache[v]) if v in cache else '此段限制的译文暂缺，请查阅原文。' for v in a.get('sourceCaveats',[])]
        a['caveatsSourceHash']=fingerprint(a.get('sourceCaveats',[]))
        a['summarySourceHash']=fingerprint(points)
        a['summaryMethod']='人工校订中文简介' if fingerprint(points) in overrides else '中文原文摘录' if all(is_chinese(v) for v in points) else 'OPUS-MT本地机器翻译；原文为准'
        a['summaryVersion']=MODEL_VERSION
        retained.append(a)
    return retained


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-model',action='store_true');parser.add_argument('--input',default=str(ROOT/'data/articles.json'));parser.add_argument('--output')
    args=parser.parse_args()
    if args.prepare_model:print(prepare_model())
    else:
        path=Path(args.input);articles=localize_articles(json.loads(path.read_text()))
        output=Path(args.output or args.input);output.write_text(json.dumps(articles,ensure_ascii=False,indent=2)+'\n')
        print(f'Chinese briefs ready: {len(articles)} articles')
