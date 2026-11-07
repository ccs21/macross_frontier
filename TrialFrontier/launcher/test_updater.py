import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import updater

class UpdateTests(unittest.TestCase):
    def payload(self,root):
        p=root/'.updates/test/payload';p.mkdir(parents=True)
        (p/'TrialFrontier.exe').write_bytes(b'new')
        (p/'resources').mkdir();(p/'resources/korean.json').write_text('[]')
        return p
    def test_preserve(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=self.payload(root)
            (root/'TrialFrontier.exe').write_bytes(b'old')
            for name in ('save','disc','cache','localization'):
                (root/name).mkdir();(root/name/'keep').write_bytes(b'keep')
            (root/'settings.ini').write_bytes(b'settings')
            updater.promote(root,p)
            self.assertEqual((root/'TrialFrontier.exe').read_bytes(),b'new')
            self.assertEqual((root/'settings.ini').read_bytes(),b'settings')
            for name in ('save','disc','cache','localization'):self.assertEqual((root/name/'keep').read_bytes(),b'keep')
    def test_rollback(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=self.payload(root);(root/'TrialFrontier.exe').write_bytes(b'old')
            with patch.object(updater.shutil,'copytree',side_effect=OSError('simulated disk failure')):
                with self.assertRaises(OSError):updater.promote(root,p)
            self.assertEqual((root/'TrialFrontier.exe').read_bytes(),b'old')
            self.assertFalse((root/'resources').exists())
    def test_zip_guard_and_preserve(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);archive=root/'test.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for n in ('TrialFrontier.exe','MacrossTrialFrontier.exe','resources/korean.json','save/progress.dat','settings.ini'):
                    z.writestr('TrialFrontier-0.1.4-test/'+n,b'test')
            updater.unpack(archive,root/'out')
            self.assertFalse((root/'out/save').exists());self.assertFalse((root/'out/settings.ini').exists())
            with zipfile.ZipFile(archive,'w') as z:z.writestr('../evil.exe',b'evil')
            with self.assertRaises(ValueError):updater.unpack(archive,root/'other')
    def test_release_selection(self):
        asset=dict(name='TrialFrontier-0.1.4-test.zip',digest='sha256:'+'a'*64,size=5,
                   browser_download_url='https://github.com/ccs21/macross_frontier/releases/download/v0.1.4/file.zip')
        data=[dict(draft=False,prerelease=False,assets=[asset])]
        with patch.object(updater,'request',return_value=io.BytesIO(json.dumps(data).encode())):
            self.assertEqual(updater.latest('0.1.3-test')['version'],'0.1.4')
        with patch.object(updater,'request',return_value=io.BytesIO(json.dumps(data).encode())):
            self.assertIsNone(updater.latest('0.1.4-test'))

if __name__=='__main__':unittest.main()
