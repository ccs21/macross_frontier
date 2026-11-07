"""Place selected replacements in the portable overlay, preserving other members."""
from collections import defaultdict
import json
from pathlib import Path
import struct
import zlib
from extract_trial import Pack

def stored(pack,row):
    size=row[5] if 0<row[5]<row[4] else row[4]
    with (pack.folder/Path(pack.name(row[2])).name).open('rb') as f:
        f.seek(row[3]);data=f.read(size)
    if len(data)!=size:raise ValueError('Truncated archive member')
    return row[4],row[5],data

def encode(data):
    compressed=zlib.compress(data,9)
    return (len(data),len(compressed),compressed) if len(compressed)<len(data) else (len(data),len(data),data)

def bundle(items):
    names=bytearray();records=[]
    for name,entry in sorted(items.items()):
        records.append((len(names),entry));names.extend(name.encode('cp932')+b'\0')
    names_at=32+len(records)*16;payload_at=(names_at+len(names)+15)&~15
    table=bytearray();payload=bytearray()
    for name,(expanded,compressed,data) in records:
        table.extend(struct.pack('<4I',name,payload_at+len(payload),expanded,compressed))
        payload.extend(data);payload.extend(b'\0'*((-len(payload))%16))
    header=b'FSTS'+struct.pack('<4I',len(records),32,names_at,len(names))+b'\0'*12
    return (header+table+names).ljust(payload_at,b'\0')+payload

def localize_tables(pack,translations):
    rows={str(path):row for _,path,row in pack.entries()}
    for _,path,row in pack.bundled_entries():rows.setdefault(str(path),row)
    patches=defaultdict(dict)
    for r in translations:
        for o in r['occurrences']:
            if not o['source'].endswith('.lct'):continue
            old=r['japanese'].encode(o['encoding']);new=r['korean'].encode(o['encoding'])
            patches[o['source']][o['offset']]=(old,new)
    result={}
    for name,changes in patches.items():
        original=pack.read(rows[name]);data=bytearray(original)
        for at,(before,after) in sorted(changes.items(),reverse=True):
            if original[at:at+len(before)]!=before:raise ValueError('Table original mismatch: '+name)
            if any(x in after for x in (b',',b'\n',b'\r',b'"')):raise ValueError('Unescaped CSV translation')
            data[at:at+len(before)]=after
        result[name]=bytes(data)
    return result

def apply(pack_folder,overlay_folder,replacements):
    if not replacements:return
    source=Pack(pack_folder);out=Path(overlay_folder)
    index=bytearray((out/'pack.idx').read_bytes());data=bytearray((out/'data.dat').read_bytes())
    lookup={};groups=defaultdict(list)
    for group,path,row in source.bundled_entries():groups[group].append((str(path),row))
    data_name=next(row[2] for _,_,row in source.entries() if Path(source.name(row[2]).replace('\\','/')).name=='data.dat')
    fileset_table,fileset_size=struct.unpack_from('<II',source.data,24)
    count=struct.unpack_from('<I',source.data,fileset_table)[0]
    for i in range(count):
        at=fileset_table+struct.unpack_from('<I',source.data,fileset_table+4+4*i)[0]
        lookup[source.name(struct.unpack_from('<I',source.data,at)[0])]=at
    def append(payload):
        data.extend(b'\0'*((-len(data))%2048));at=len(data);data.extend(payload);return at
    def patch(at,payload):
        index[at:at+len(payload)]=payload;data[at:at+len(payload)]=payload
    changed_groups=[];seen=set()
    for group,members in groups.items():
        affected=set(name for name,_ in members)&replacements.keys()
        if not affected:continue
        active=source
        if group=='resident':
            active=Pack(out)
            members=[(str(path),row) for _,path,row in active.bundled_entries('resident')]
        items={name:encode(replacements[name]) if name in replacements else stored(active,row) for name,row in members}
        payload=bundle(items);start=append(payload)
        patch(lookup[group]+4,struct.pack('<4I',data_name,start,len(payload),len(items)))
        changed_groups.append(group);seen.update(affected)
    changed_loose=[]
    for entry,path,row in source.entries():
        name=str(path)
        if name not in replacements:continue
        expanded,compressed,payload=encode(replacements[name]);start=append(payload)
        patch(source.table+entry*24+8,struct.pack('<4I',data_name,start,expanded,compressed))
        seen.add(name);changed_loose.append(name)
    if seen!=set(replacements):raise ValueError('Replacement not indexed: '+repr(set(replacements)-seen))
    (out/'data.dat').write_bytes(data);(out/'pack.idx').write_bytes(index)
    # Verify every replacement through each modified lookup path.
    check=Pack(out)
    for group in changed_groups:
        for _,path,row in check.bundled_entries(group):
            if str(path) in replacements and check.read(row)!=replacements[str(path)]:raise ValueError('Overlay verification failed: '+str(path))
    for _,path,row in check.entries():
        if str(path) in replacements and check.read(row)!=replacements[str(path)]:raise ValueError('Loose overlay verification failed: '+str(path))
    (out/'asset-overlay-report.json').write_text(json.dumps(dict(replaced_files=sorted(seen),groups=changed_groups,loose=changed_loose),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Applied {len(seen)} files across {len(changed_groups)} filesets and {len(changed_loose)} loose entries')
