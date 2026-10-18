import datetime as dt
import importlib.util
import json
from pathlib import Path
import unittest
import tempfile

P = Path(__file__).parent / 'scripts' / 'a_share_announcements.py'
if not P.exists():
    P = Path(__file__).parent.parent / 'scripts' / 'a_share_announcements.py'
spec = importlib.util.spec_from_file_location('daily', P) if P.exists() else None
m = importlib.util.module_from_spec(spec) if spec else None
if m: spec.loader.exec_module(m)

class ReportPolicyTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(m, 'daily report pipeline must exist')
    def test_five_am_uses_previous_calendar_date_not_last_trading_day(self):
        self.assertEqual(m.report_date(dt.datetime(2026,10,19,5,tzinfo=dt.timezone(dt.timedelta(hours=8)))), dt.date(2026,10,18))
    def test_ai_cannot_reference_unknown_announcements(self):
        with self.assertRaises(ValueError):
            m.validate_selection([{'code':'600000','important':True,'announcement_ids':['made-up']}], {'600000':[{'id':'known','title':'重大合同','text':'金额100亿元'}]})
    def test_ai_must_cover_each_candidate_company(self):
        with self.assertRaises(ValueError):
            m.validate_selection([], {'600000':[{'id':'known'}]})
    def test_scores_and_sources_are_validated(self):
        raw={'code':'600000','important':True,'announcement_ids':['known'],'categories':['合同中标'],'direction':'利好','score':5,'event':'签订合同','conclusion':'订单增加','analysis':['合同金额100亿元。','收入确认以履约为准。'],'key_data':[{'label':'合同金额','value':'100亿元','evidence':'合同金额100亿元'}],'focus':['关注履约']}
        source={'600000':[{'id':'known','name':'浦发银行','title':'重大合同','text':'公司签署合同金额100亿元','url':'https://example.org/a.pdf','date':'2026-10-16'}]}
        items=m.validate_selection([raw],source)
        self.assertEqual(items[0]['announcements'][0]['title'],'重大合同')
        raw['key_data'][0]['evidence']='合同金额200亿元'
        with self.assertRaises(ValueError): m.validate_selection([raw],source)
    def test_narrative_cannot_change_monetary_units(self):
        raw={'code':'600000','important':True,'announcement_ids':['known'],'categories':['合同中标'],'direction':'利好','score':5,'event':'合同金额100亿元','conclusion':'订单增加','analysis':['合同金额100亿元。','收入确认以履约为准。'],'key_data':[{'label':'合同金额','value':'100万元','evidence':'合同金额100万元'}],'focus':['关注履约']}
        source={'600000':[{'id':'known','name':'浦发银行','title':'重大合同','text':'公司签署合同金额100万元','url':'https://example.org/a.pdf','date':'2026-10-16'}]}
        with self.assertRaises(ValueError): m.validate_selection([raw],source)
    def test_table_amount_unit_can_be_verified_separately(self):
        raw={'code':'600000','important':True,'announcement_ids':['known'],'categories':['业绩'],'direction':'利空','score':-4,'expectation':'无一致预期（未提供）','event':'利润下降','conclusion':'盈利承压','analysis':['净利润预计29,282.26万元。','具体数据以定期报告为准。'],'key_data':[{'label':'归母净利润','value':'21,473.66 ～ 29,282.26','evidence':'净利润\n21,473.66 ～ 29,282.26','unit':'万元','unit_evidence':'单位：万元\n净利润\n21,473.66 ～ 29,282.26'}],'focus':['关注定期报告']}
        source={'600000':[{'id':'known','name':'示例','title':'业绩预告','text':'单位：万元\n净利润\n21,473.66 ～ 29,282.26','url':'https://example.org/a.pdf','date':'2026-10-16'}]}
        item=m.validate_selection([raw],source)[0]
        self.assertIn('万元',item['key_data'][0]['label'])
        self.assertEqual(item['expectation'],'无一致预期')
        raw['key_data'][0]['unit']='亿元'
        with self.assertRaises(ValueError): m.validate_selection([raw],source)
    def test_compound_table_units_cannot_be_rebound_as_plain_currency(self):
        for header in ['万元/股','万元、万股']:
            value='100'; quote='单位：'+header+'\n净利润100'
            raw={'code':'600000','important':True,'announcement_ids':['known'],'categories':['业绩'],'direction':'利空','score':-4,'event':'利润下降','conclusion':'盈利承压','analysis':['净利润100万元。','具体数据以定期报告为准。'],'key_data':[{'label':'净利润','value':value,'evidence':'净利润100','unit':'万元','unit_evidence':quote}],'focus':['关注报告']}
            source={'600000':[{'id':'known','name':'示例','title':'业绩预告','text':quote,'url':'https://example.org/a.pdf','date':'2026-10-16'}]}
            with self.assertRaises(ValueError): m.validate_selection([raw],source)
    def test_explicit_value_unit_cannot_get_conflicting_label(self):
        quote='单位：亿元\n净利润100万元'
        raw={'code':'600000','important':True,'announcement_ids':['known'],'categories':['业绩'],'direction':'利空','score':-4,'event':'利润下降','conclusion':'盈利承压','analysis':['净利润100万元。','具体数据以定期报告为准。'],'key_data':[{'label':'净利润','value':'100万元','evidence':'净利润100万元','unit':'亿元','unit_evidence':quote}],'focus':['关注报告']}
        source={'600000':[{'id':'known','name':'示例','title':'业绩预告','text':quote,'url':'https://example.org/a.pdf','date':'2026-10-16'}]}
        with self.assertRaises(ValueError): m.validate_selection([raw],source)
    def test_unit_evidence_must_belong_to_same_announcement_as_amount(self):
        raw={'code':'600000','important':True,'announcement_ids':['known','other'],'categories':['业绩'],'direction':'利空','score':-4,'event':'利润下降','conclusion':'盈利承压','analysis':['净利润预计100亿元。','具体数据以定期报告为准。'],'key_data':[{'label':'归母净利润','value':'100','evidence':'净利润100','unit':'亿元','unit_evidence':'单位：亿元'}],'focus':['关注定期报告']}
        source={'600000':[{'id':'known','name':'示例','title':'业绩预告','text':'单位：万元，净利润100','url':'https://example.org/a.pdf','date':'2026-10-16'},{'id':'other','name':'示例','title':'其他公告','text':'单位：亿元，合同200','url':'https://example.org/b.pdf','date':'2026-10-16'}]}
        with self.assertRaises(ValueError): m.validate_selection([raw],source)
    def test_direction_then_absolute_score_sort(self):
        items=[{'direction':'利空','score':-5,'code':'3'},{'direction':'利好','score':2,'code':'2'},{'direction':'中性','score':0,'code':'0'},{'direction':'利好','score':5,'code':'1'}]
        self.assertEqual([x['code'] for x in m.sort_items(items)],['1','2','0','3'])
    def test_chinese_batches_split_on_utf8_budget_without_losing_sources(self):
        groups={str(600001+number):[{'id':str(number),'title':'重大合同','text':'中'*12000}]
                for number in range(3)}
        self.assertLess(sum(len(row['text'])+len(row['title']) for rows in groups.values() for row in rows),45000)
        result=list(m.batches(groups))
        self.assertEqual(len(result),2)
        self.assertTrue(all(len(json.dumps(batch,ensure_ascii=False).encode('utf-8'))<=100000 for batch in result))
        self.assertEqual({code:rows for batch in result for code,rows in batch.items()},groups)
    def test_company_over_utf8_budget_remains_complete_in_its_own_batch(self):
        groups={'600001':[{'id':'large','title':'重大合同','text':'中'*34000}],
                '600002':[{'id':'small','title':'重大合同','text':'完整原文'}]}
        result=list(m.batches(groups))
        self.assertEqual(len(result),2)
        self.assertEqual(result[0],{'600001':groups['600001']})
        self.assertEqual({code:rows for batch in result for code,rows in batch.items()},groups)
    def test_diagnostic_default_output_cannot_touch_published_or_live_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            result=m.main(['--project-root',folder,'--date','2026-10-17','--limit','1'])
            self.assertEqual(result,0)
            self.assertFalse((root/'published').exists())
            self.assertFalse((root/'var/a-share-announcements-status').exists())
            self.assertTrue((root/'var/a-share-announcements-diagnostic-status/latest-run.json').is_file())
    def test_publish_gate_supports_memini_symlinked_project_root(self):
        import hashlib,subprocess,sys
        gate=(P.parent/'publish-a-share-announcements.sh').read_text().split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder); root=base/'real'; root.mkdir(); alias=base/'alias'; alias.symlink_to(root,target_is_directory=True)
            out=root/'published/a-share-announcements'; out.mkdir(parents=True)
            contents={'report.pdf':b'%PDF test','latest.pdf':b'%PDF test','2026-10-16.md':b'report','latest.md':b'report','2026-10-16.json':b'{}'}
            for name,value in contents.items(): (out/name).write_bytes(value)
            status={'date':'2026-10-16','publishable':True,'fact_review':{'passed':True},'layout_review':{'passed':True},'output_path':str(out/'report.pdf'),'report_sha256':hashlib.sha256(b'%PDF test').hexdigest(),'markdown_sha256':hashlib.sha256(b'report').hexdigest(),'json_sha256':hashlib.sha256(b'{}').hexdigest()}
            status_path=root/'status.json'; status_path.write_text(json.dumps(status))
            result=subprocess.run([sys.executable,'-',str(status_path),str(alias)],input=gate,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(result.stdout.splitlines()[-1],'2026-10-16')
            self.assertEqual(len(result.stdout.splitlines()),6)
    def test_parser_accepts_fenced_json_but_rejects_prose(self):
        self.assertEqual(m.parse_model_json('```json\n{"items": []}\n```'), {'items':[]})
        with self.assertRaises(ValueError): m.parse_model_json('今天市场很好')

if __name__ == '__main__': unittest.main()
