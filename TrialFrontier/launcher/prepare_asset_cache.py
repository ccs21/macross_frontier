"""Prepare verified zlib streams before launching the guest; never alter ROMs.

The runtime matches the entire compressed stream, not a ROM/version hash.
Unrecognized streams continue through the original decoder.
"""
import argparse, hashlib, json, os, re, struct, time, zlib
from pathlib import Path
MAGIC=b'MFTZC001'
LIMIT=64*1024*1024
def prepare(pack, output, extra_files=()):
    files=sorted(pack.glob('*.dat'))+list(extra_files)
    if not files: raise ValueError('No game archives found')
    identity=[dict(name=p.name,size=p.stat().st_size,mtime=p.stat().st_mtime_ns) for p in files]
    manifest=output.with_suffix('.json')
    if output.exists() and manifest.exists():
        old=json.loads(manifest.read_text(encoding='utf8'))
        if old.get('sources')==identity and old.get('bytes')==output.stat().st_size:
            print(json.dumps(dict(status='ready',**old)),flush=True);return
    output.parent.mkdir(parents=True,exist_ok=True)
    pending=output.with_suffix('.pending');seen=set();count=0;expanded=stored=0;start=time.perf_counter()
    try:
        with pending.open('wb') as out:
            out.write(MAGIC+struct.pack('<Q',0))
            for path in files:
                data=path.read_bytes();view=memoryview(data);position=0;found=0
                pattern=re.compile(rb'\x78[\x01\x5e\x9c\xda]')
                while True:
                    match=pattern.search(data,position)
                    if not match:break
                    at=match.start();position=at+2
                    dec=zlib.decompressobj()
                    # Limit the candidate input too: bogus embedded headers must
                    # not copy the remainder of a several-hundred-MB archive.
                    chunks=[];decoded_size=0;cursor=at
                    try:
                        while not dec.eof and cursor<len(data) and cursor-at<LIMIT and decoded_size<=LIMIT:
                            end=min(cursor+65536,len(data),at+LIMIT)
                            chunk=dec.decompress(view[cursor:end],LIMIT+1-decoded_size)
                            chunks.append(chunk);decoded_size+=len(chunk);cursor=end
                    except zlib.error:continue
                    if not dec.eof or decoded_size>LIMIT:continue
                    decoded=b''.join(chunks)
                    consumed=cursor-at-len(dec.unused_data)
                    if consumed<8:continue
                    compressed=data[at:at+consumed];position=at+consumed
                    digest=hashlib.sha256(compressed).digest()
                    if digest in seen:continue
                    seen.add(digest)
                    checksum=zlib.adler32(decoded)&0xffffffff
                    if checksum!=struct.unpack('>I',compressed[-4:])[0]:raise ValueError('Checksum mismatch')
                    out.write(struct.pack('<IIII',len(compressed),len(decoded),checksum,0))
                    out.write(compressed);out.write(decoded)
                    count+=1;found+=1;expanded+=len(decoded);stored+=len(compressed)
                print(f'{path.name}: {found} unique streams, total decoded {expanded//1048576} MiB',flush=True)
            out.seek(8);out.write(struct.pack('<Q',count));out.flush();os.fsync(out.fileno())
        if identity!=[dict(name=p.name,size=p.stat().st_size,mtime=p.stat().st_mtime_ns) for p in files]:
            raise ValueError('Source archives changed during preparation')
        os.replace(pending,output)
        result=dict(sources=identity,bytes=output.stat().st_size,streams=count,decoded_bytes=expanded,
                    compressed_bytes=stored,prepare_seconds=round(time.perf_counter()-start,3))
        manifest.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result),flush=True)
    finally:
        if pending.exists():pending.unlink()
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pack',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.pack,a.output)
