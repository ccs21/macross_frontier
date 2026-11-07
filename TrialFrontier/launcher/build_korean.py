"""Build a separate Korean asset overlay; never modify the user's ROM or workbook."""
import json
import struct
import subprocess
import sys
from contextlib import nullcontext
import zlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from extract_trial import Pack

def restore_originals(pack, elf_path, translations):
    """Read original text from the user's files; the download only carries Korean."""
    entries={str(path):row for _,path,row in pack.entries()}
    for _,path,row in pack.bundled_entries():entries.setdefault(str(path),row)
    cache={'EBOOT.elf':Path(elf_path).read_bytes()}
    result=[]
    for item in translations:
        row=dict(item)
        if 'japanese' not in row:
            occurrence=row['occurrences'][0]
            source=occurrence['source']
            if source not in cache:cache[source]=pack.read(entries[source])
            at=occurrence['offset'];length=occurrence['source_bytes']
            raw=cache[source][at:at+length]
            if len(raw)!=length:raise ValueError('번역 대상 문자열 범위 오류: '+row['id'])
            row['japanese']=raw.decode(occurrence['encoding']).rstrip('\0')
        result.append(row)
    return result


def build(rom_pack, elf_path, translations, out, texconv):
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    pack=Pack(rom_pack)
    translations=restore_originals(pack,elf_path,translations)
    members = {str(path): pack.read(row) for group, path, row in pack.bundled_entries() if group == 'resident'}
    font_path = 'data/font/font_j24x24/font_j24x24.abf'
    abf = members[font_path]
    assert abf[:8] == b'ENDIBIGE' and abf[0x80:0x88] == b'BFNTHCMN'
    count, pages = struct.unpack_from('>IH', abf, 0x90)
    page_block = abf.index(b'BFNTPBLK')
    char_block = abf.index(b'BFNTCBLK')
    assert char_block == page_block + 16 + pages * 48
    records = [abf[char_block+16+i*32:char_block+48+i*32] for i in range(count)]
    codes = {struct.unpack_from('>I', r)[0] for r in records}
    hangul = sorted({ord(c) for r in translations for c in r['korean'] if '\uac00' <= c <= '\ud7a3'} - codes)
    font = ImageFont.truetype('C:/Windows/Fonts/malgunbd.ttf', 23)
    images = out / 'font-pages'
    images.mkdir(exist_ok=True)
    new_pages = []
    for start in range(0, len(hangul), 100):
        page = Image.new('RGBA', (256,256), (255,255,255,0))
        draw = ImageDraw.Draw(page)
        page_id = pages + len(new_pages)
        for i, code in enumerate(hangul[start:start+100]):
            x,y = (i%10)*25, (i//10)*25
            # One-pixel gutter, fixed 24px advance, matching the game's 24px line grid.
            draw.text((x+1,y+1), chr(code), font=font, fill=(255,255,255,255), anchor='lt')
            records.append(struct.pack('>I4H3hBB', code,x,y,24,24,0,0,24,page_id,15) + b'\xfd'*12)
        name = f'font_ko_{page_id:02}.dds'
        page.save(images / (Path(name).stem + '.png'))
        new_pages.append(name)
    tool = Path(texconv)
    for name in new_pages:
        if getattr(sys,'frozen',False):
            from external_process import native_dll_search, native_environment
            context=native_dll_search();environment=native_environment()
        else:context=nullcontext();environment=None
        with context:
            subprocess.run([str(tool), '-nologo','-y','-m','1','-f','BC3_UNORM','-o',str(images),str(images/(Path(name).stem+'.png'))], check=True, stdout=subprocess.DEVNULL, env=environment, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        data = (images/name).read_bytes()
        assert data[84:88] == b'DXT5'
        members['data/font/font_j24x24/'+name] = data
    prefix = bytearray(abf[:page_block])
    struct.pack_into('>IH', prefix, 0x90, len(records), pages+len(new_pages))
    page_records = abf[page_block+16:char_block]
    for name in new_pages:
        encoded = name.encode('ascii') + b'\0'
        assert len(encoded)<=32
        page_records += b'BFNTPINF' + struct.pack('>II',32,0) + encoded.ljust(32,b'\0')
    records.sort(key=lambda r:struct.unpack_from('>I',r)[0])
    new_abf = bytes(prefix)+b'BFNTPBLK'+struct.pack('>II',len(page_records),16)+page_records
    new_abf += b'BFNTCBLK'+struct.pack('>II',len(records)*32,len(records)*32+16)+b''.join(records)+abf[-16:]
    members[font_path] = new_abf
    assert len({struct.unpack_from('>I',r)[0] for r in records})==len(records)

    # FSTS uses relative member offsets and an independent UTF8/CP932 filename table.
    names = bytearray()
    entries = []
    for name, data in sorted(members.items()):
        filename = len(names)
        names.extend(name.encode('cp932')+b'\0')
        stored = zlib.compress(data,9)
        if len(stored)>=len(data):stored=data
        entries.append((filename,data,stored))
    names_at = 32 + len(entries)*16
    payload_at = (names_at+len(names)+15)&~15
    table = bytearray()
    payload = bytearray()
    for filename,data,stored in entries:
        table.extend(struct.pack('<4I',filename,payload_at+len(payload),len(data),len(stored)))
        payload.extend(stored)
        payload.extend(b'\0'*((-len(payload))%16))
    bundle = b'FSTS'+struct.pack('<4I',len(entries),32,names_at,len(names))+b'\0'*12+table+names
    bundle = bundle.ljust(payload_at,b'\0')+payload

    data_archive = bytearray((pack.folder/'data.dat').read_bytes())
    start = (len(data_archive)+2047)&~2047
    data_archive.extend(b'\0'*(start-len(data_archive)))
    data_archive.extend(bundle)
    def redirect_resident(index):
        table,_,names,_ = struct.unpack_from('<4I',index,24)
        n = struct.unpack_from('<I',index,table)[0]
        found=0
        for i in range(n):
            at=table+struct.unpack_from('<I',index,table+4+i*4)[0]
            name=struct.unpack_from('<I',index,at)[0]+names
            end=index.index(0,name)
            if index[name:end]==b'resident':
                struct.pack_into('<3I',index,at+8,start,len(bundle),len(entries));found+=1
        assert found==1
    redirect_resident(data_archive)
    index=bytearray(pack.data)
    redirect_resident(index)
    (out/'data.dat').write_bytes(data_archive)
    (out/'pack.idx').write_bytes(index)

    # Counted binary strings avoid JSON parsing and ambiguous escaping at runtime.
    dictionary=bytearray(b'MFTKO001'+struct.pack('<I',len(translations)))
    for r in translations:
        jp,ko=r['japanese'].encode('utf-8'),r['korean'].encode('utf-8')
        dictionary.extend(struct.pack('<II',len(jp),len(ko))+jp+ko)
    (out/'strings.bin').write_bytes(dictionary)
    # Patch loaded ELF data, not the ROM executable. Long translations live in a
    # dedicated host-owned guest arena; only verified data pointers are redirected.
    elf=Path(elf_path).read_bytes()
    sh=struct.unpack_from('>Q',elf,40)[0]
    stride,sections=struct.unpack_from('>2H',elf,58)
    ranges=[]
    for i in range(sections):
        r=struct.unpack_from('>IIQQQQIIQQ',elf,sh+i*stride)
        if r[2]&2 and not r[2]&4 and r[1]!=8:
            ranges.append((r[4],r[4]+r[5],r[3]-r[4]))
    patches=[]
    arena=0xf1000000
    relocated=0
    for r in translations:
        jp,ko=r['japanese'].encode(),r['korean'].encode()
        for occurrence in r['occurrences']:
            if occurrence['source']!='EBOOT.elf':continue
            at=occurrence['offset']
            assert elf[at:at+len(jp)+1]==jp+b'\0'
            section=next((s for s in ranges if s[0]<=at<s[1]),None)
            assert section
            address=at+section[2]
            if len(ko)<=len(jp):
                patches.append((address,jp+b'\0',ko+b'\0'))
                continue
            old=struct.pack('>I',address)
            hits=[(i,delta) for a,b,delta in ranges for i in range(a,b-3,4) if elf[i:i+4]==old]
            if not hits:
                # These three labels are inline fields in equal-size pilot records.
                # Other labels in the same field occupy up to 45 bytes; retain the
                # 64-byte bound and verify every extra byte is zero before writing.
                assert r['id'] in {'TF-0420','TF-0421','TF-0423'} and len(ko)<64
                assert not any(elf[at+len(jp):at+len(ko)+1])
                patches.append((address,elf[at:at+len(ko)+1],ko+b'\0'))
                continue
            assert arena+len(ko)+1<=0xf1010000
            patches.append((arena,b'',ko+b'\0'))
            for i,delta in hits:patches.append((i+delta,old,struct.pack('>I',arena)))
            arena=(arena+len(ko)+16)&~15
            relocated+=1
    binary=bytearray(b'MFTKP001'+struct.pack('<I',len(patches)))
    for address,before,after in patches:
        binary.extend(struct.pack('<III',address,len(before),len(after))+before+after)
    (out/'elf-patches.bin').write_bytes(binary)
    from asset_overlay import apply, localize_tables
    apply(rom_pack,out,localize_tables(pack,translations))
    (out/'build-report.json').write_text(json.dumps(dict(translations=len(translations),new_glyphs=len(hangul),font_pages=pages+len(new_pages),resident_members=len(members),font='Locally rasterized Windows Malgun Gothic Bold; no font file bundled',runtime_verified=False),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Built {len(hangul)} Korean glyphs, {len(translations)} strings, {len(bundle)} byte resident bundle, {relocated} relocated strings')

if __name__ == '__main__':
    root=Path(__file__).resolve().parents[2]
    work=Path(__file__).resolve().parent/'work'
    build(root/'Macross Trial Frontier BLJS93001/PS3_GAME/USRDIR/data/pack',
          root/'frontier-analysis/trial/EBOOT.elf',
          json.loads((work/'trial-korean-current.json').read_text(encoding='utf-8')),
          work/'korean-overlay',root/'tools/texture-pack/texconv.exe')
