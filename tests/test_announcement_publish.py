"""The publisher accepts only audited Markdown and JSON, without a PDF."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).parent
SCRIPT=ROOT/'scripts/publish-a-share-announcements.sh'
if not SCRIPT.exists():SCRIPT=ROOT.parent/'scripts/publish-a-share-announcements.sh'
GATE=SCRIPT.read_text().split("<<'PY'\n",1)[1].split('\nPY\n',1)[0]
DATE='2026-10-16'

class MarkdownPublishGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.root=self.base/'repo';self.root.mkdir()
        self.out=self.root/'published/a-share-announcements';self.out.mkdir(parents=True)
        md=b'# A-share major announcements\n';js=b'{"items": []}\n'
        for name,data in [(DATE+'.md',md),('latest.md',md),(DATE+'.json',js)]:
            (self.out/name).write_bytes(data)
        self.status={'date':DATE,'output_format':'markdown','publishable':True,'diagnostic':False,
            'fact_review':{'passed':True},'markdown_review':{'passed':True},
            'output_path':str(self.out/(DATE+'.md')),'markdown_path':str(self.out/(DATE+'.md')),
            'json_path':str(self.out/(DATE+'.json')),'report_filename':DATE+'.md',
            'report_sha256':hashlib.sha256(md).hexdigest(),
            'markdown_sha256':hashlib.sha256(md).hexdigest(),'json_sha256':hashlib.sha256(js).hexdigest()}

    def gate(self,root=None):
        path=self.root/'status.json';path.write_text(json.dumps(self.status))
        return subprocess.run([sys.executable,'-',str(path),str(root or self.root)],input=GATE,text=True,capture_output=True)

    def test_markdown_and_json_pass_without_pdf_and_only_expected_paths_are_returned(self):
        result=self.gate()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),[
            'published/a-share-announcements/'+DATE+'.md','published/a-share-announcements/latest.md',
            'published/a-share-announcements/'+DATE+'.json',DATE])
        self.assertFalse(list(self.root.rglob('*.pdf')))

    def test_project_symlink_is_supported(self):
        alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
        self.assertEqual(self.gate(alias).returncode,0)

    def test_tampered_markdown_json_and_latest_are_rejected(self):
        for name in [DATE+'.md',DATE+'.json','latest.md']:
            path=self.out/name;original=path.read_bytes();path.write_bytes(b'tampered')
            with self.subTest(name=name):self.assertNotEqual(self.gate().returncode,0)
            path.write_bytes(original)

    def test_diagnostic_failed_review_and_legacy_pdf_status_cannot_publish(self):
        cases=[{'diagnostic':True},{'publishable':False},{'error':'failed'},
               {'markdown_review':{'passed':False}},
               {'markdown_review':{},'layout_review':{'passed':True},'output_format':'pdf'}]
        original=dict(self.status)
        for patch in cases:
            self.status={**original,**patch}
            with self.subTest(patch=patch):self.assertNotEqual(self.gate().returncode,0)
        self.status=original

    def test_wrong_output_path_or_report_hash_cannot_publish(self):
        for patch in [{'output_path':str(self.out/'latest.md')},{'report_sha256':'bad'},
                      {'markdown_path':str(self.root/'outside.md')},
                      {'json_path':str(self.root/'outside.json')}]:
            original=dict(self.status);self.status.update(patch)
            with self.subTest(patch=patch):self.assertNotEqual(self.gate().returncode,0)
            self.status=original

if __name__=='__main__':unittest.main()
