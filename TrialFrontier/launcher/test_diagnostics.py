import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from diagnostics import run_and_record

class CaptureTests(unittest.TestCase):
    def test_capture_rotation_and_environment(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/'settings.ini').write_text('[Graphics]\nRenderer=0')
            old=os.environ.get('PS3RECOMP_VK_WAIT_TRACE')
            class Process:
                pid=123
                def wait(self):return 0
            def launch(root):
                Path(os.environ['PS3RECOMP_VK_WAIT_TRACE']).write_bytes(b'wait-data')
                Path(os.environ['PS3RECOMP_VK_FRAME_TRACE']).write_bytes(b'frame-data')
                (root/'launcher.log').write_bytes(b'A'*400000)
                return Process()
            for _ in range(3):run_and_record(root,'1.0.5',launch)
            self.assertEqual(os.environ.get('PS3RECOMP_VK_WAIT_TRACE'),old)
            self.assertEqual(len(list((root/'diagnostics').glob('performance-*.zip'))),2)
            with zipfile.ZipFile(root/'diagnostics/performance-latest.zip') as z:
                self.assertEqual(z.read('waits.bin'),b'wait-data')
                self.assertLess(len(z.read('launcher-excerpt.log')),328000)
                self.assertNotIn('save',z.namelist())

    def test_failure_restores_environment(self):
        with tempfile.TemporaryDirectory() as name:
            old=os.environ.get('PS3RECOMP_VK_FRAME_TRACE')
            def fail(root):raise RuntimeError('launch failed')
            with self.assertRaises(RuntimeError):run_and_record(Path(name),'1.0.5',fail)
            self.assertEqual(os.environ.get('PS3RECOMP_VK_FRAME_TRACE'),old)

if __name__=='__main__':unittest.main()
