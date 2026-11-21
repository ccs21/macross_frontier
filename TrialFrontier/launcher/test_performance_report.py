from pathlib import Path
import struct,tempfile,unittest
from performance_report import summarize,read_records

class ReportTests(unittest.TestCase):
    def test_missing_capture_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            result=summarize(d)
            self.assertEqual(len(result['issues']),3)

    def test_matching_clocks_and_wrapped_samples(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            def write(name,rows):
                (p/name).write_bytes(struct.pack('<Q',1000)+b''.join(struct.pack('<'+'Q'*len(r),*r) for r in rows))
            rows=[]
            for tick in [200,100]:
                row=[tick]*32;row[27]=12;row[28]=3;row[29]=2;rows.append(row)
            write('cpu.bin',rows)
            write('frames.bin',[[200]*9,[100]*9]);write('waits.bin',[[110,120,22,3]])
            result=summarize(p)
            self.assertFalse(result['issues'])
            self.assertEqual(result['matched_present_records'],2)
            self.assertEqual(result['slow_frames'][0]['wall_ms']['fetch'],100)
            rows[0][13]=0;write('cpu.bin',rows)
            self.assertTrue(any('fifo_idle' in x for x in summarize(p)['issues']))
            write('cpu.bin',[[200]*32])
            self.assertTrue(any('schema' in x for x in summarize(p)['issues']))

if __name__=='__main__':unittest.main()
