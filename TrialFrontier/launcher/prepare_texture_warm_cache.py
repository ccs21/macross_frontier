"""Prepare original BC textures from installed archives, without a gameplay capture."""
from pathlib import Path
import hashlib, json, os, struct, sys
try:
    from extract_trial import Pack
except ImportError:
    sys.path.insert(0,str(Path(__file__).resolve().parent/'localization'))
    from extract_trial import Pack

def textures(data):
    at=0
    while True:
        at=data.find(b'DDS ',at)
        if at<0:return
        p=at;at+=4
        if len(data)-p<128 or struct.unpack_from('<I',data,p+4)[0]!=124:continue
        h,w=struct.unpack_from('<II',data,p+12)
        levels=max(1,struct.unpack_from('<I',data,p+28)[0])
        fmt={b'DXT1':0x86,b'DXT3':0x87,b'DXT5':0x88}.get(bytes(data[p+84:p+88]))
        caps=struct.unpack_from('<I',data,p+112)[0]
        if not fmt or not 0<w<=8192 or not 0<h<=8192 or levels>14 or caps&0x200200:continue
        if levels>max(w,h).bit_length():continue
        size=sum(((max(1,w>>m)+3)//4)*((max(1,h>>m)+3)//4)*(8 if fmt==0x86 else 16) for m in range(levels))
        if size>32*1024*1024 or p+128+size>len(data):continue
        yield (fmt,w,h,levels),data[p+128:p+128+size]

def prepare(folder,output,extra_folders=()):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    pending=output.with_suffix('.pending');seen=set();count=total=0
    try:
        with pending.open('wb') as out:
            out.write(b'MFTWARM1'+struct.pack('<II',0,0))
            for directory in (folder,*extra_folders):
                archive=Pack(directory)
                for _,path,row in archive.entries():
                    if path.suffix.lower() in {'.at3','.vad','.po','.info','.anm','.cg','.cgfx'}:continue
                    for desc,raw in textures(archive.read(row)):
                        key=hashlib.sha256(struct.pack('<4I',*desc)+raw).digest()
                        if key in seen:continue
                        if count>=512 or total+len(raw)>256*1024*1024:continue
                        seen.add(key);out.write(struct.pack('<6I',*desc,len(raw),0));out.write(raw)
                        count+=1;total+=len(raw)
            out.seek(8);out.write(struct.pack('<I',count));out.flush();os.fsync(out.fileno())
        os.replace(pending,output)
    finally:
        if pending.exists():pending.unlink()
    result=dict(textures=count,raw_bytes=total,scope='Original 2D BC1/BC2/BC3; no cube, volume, or dynamic render targets')
    output.with_suffix('.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--pack',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.pack,a.output)
