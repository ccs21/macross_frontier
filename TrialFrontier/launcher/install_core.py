"""Portable, transactional first-run preparation from a user-owned ISO/mount.

Disc keys are only held in memory. No ROM hashes, downloads or source writes.
"""
import bisect
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
from iso9660 import inventory, read_file
from external_process import native_dll_search, native_environment

TITLE_ID='BLJS93001'
KEY_HELP='https://ps3.aldostools.org/dkey.html'
NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)

class KeyRequired(ValueError):pass
class Cancelled(Exception):pass

def parse_key(value):
    value=''.join(value.split())
    if len(value)!=32 or any(c not in '0123456789abcdefABCDEF' for c in value):
        raise ValueError('디스크 키는 32자리 16진수여야 합니다.')
    return bytes.fromhex(value)

def sfo(data):
    if data[:4]!=b'\0PSF' or len(data)<20:raise ValueError('PARAM.SFO를 읽을 수 없습니다.')
    keys,values,count=struct.unpack_from('<III',data,8)
    if count>256 or 20+count*16>len(data):raise ValueError('잘못된 SFO 항목 수')
    result={}
    for i in range(count):
        key,kind,length,capacity,offset=struct.unpack_from('<HHIII',data,20+i*16)
        at=keys+key
        if at>=len(data) or values+offset+length>len(data):raise ValueError('SFO 범위 오류')
        end=data.find(b'\0',at)
        if end<0:raise ValueError('SFO 이름 오류')
        name=data[at:end].decode('utf-8')
        raw=data[values+offset:values+offset+length]
        result[name]=raw.rstrip(b'\0').decode('utf-8') if kind==0x204 else int.from_bytes(raw,'little')
    return result

class ImageReader:
    """Decrypt only selected PS3 sectors; never make a 45GB movie ISO copy."""
    def __init__(self,path,key=None):
        self.path=Path(path).resolve(strict=True)
        self.file=self.path.open('rb');self.size=self.path.stat().st_size
        self.key=key;self.position=0;self.regions=[];self.starts=[]
        if key:
            header=self.file.read(4096)
            if len(header)<4096:raise ValueError('ISO가 잘렸습니다.')
            count=struct.unpack_from('>I',header)[0]
            if not 1<=count<=511:raise ValueError('PS3 디스크 영역 표가 아닙니다.')
            previous=-1
            for i in range(count):
                begin,end=struct.unpack_from('>II',header,8+i*8)
                if begin<=previous or begin>end or (end+1)*2048>self.size:raise ValueError('ISO 영역 표가 손상됐습니다.')
                self.regions.append((begin,end));self.starts.append(begin);previous=end
            if self.regions[0][0]!=0:raise ValueError('첫 디스크 영역이 잘못됐습니다.')
    def seek(self,offset,whence=0):
        p=offset if whence==0 else self.position+offset if whence==1 else self.size+offset
        if p<0 or p>self.size:raise ValueError('ISO 읽기 범위 오류')
        self.position=p;return p
    def read(self,size=-1):
        size=self.size-self.position if size<0 else min(size,self.size-self.position)
        if not self.key:
            self.file.seek(self.position);data=self.file.read(size);self.position+=len(data);return data
        from Crypto.Cipher import AES
        first=self.position//2048;skip=self.position%2048
        total=((skip+size+2047)//2048)*2048
        self.file.seek(first*2048);data=bytearray(self.file.read(total))
        for offset in range(0,len(data),2048):
            lba=first+offset//2048;i=bisect.bisect_right(self.starts,lba)-1
            plain=i>=0 and lba<=self.regions[i][1]
            if not plain:
                if len(data)-offset<2048:raise ValueError('암호화된 ISO 섹터가 잘렸습니다.')
                data[offset:offset+2048]=AES.new(self.key,AES.MODE_CBC,iv=lba.to_bytes(16,'big')).decrypt(data[offset:offset+2048])
        self.position+=size
        return bytes(data[skip:skip+size])
    def close(self):self.key=None;self.file.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()

def safe_game_path(name):
    path=PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('ISO 내부에 안전하지 않은 경로가 있습니다.')
    return name=='PS3_DISC.SFB' or name.startswith('PS3_GAME/')

def inspect_iso(path,key=None):
    with ImageReader(path,key) as stream:
        files=inventory(stream)
        selected=[r for r in files if safe_game_path(r['path'])]
        by_name={r['path'].lower():r for r in selected}
        signatures={'ps3_game/param.sfo':(b'\0PSF',),
                    'ps3_game/usrdir/eboot.bin':(b'SCE\0',b'\x7fELF'),
                    'ps3_game/usrdir/data/pack/pack.idx':(b'PIDX',),
                    'ps3_game/usrdir/data/pack/data.dat':(b'PIDX',)}
        for name,allowed in signatures.items():
            entry=by_name.get(name)
            if entry is None:raise ValueError('ISO에 필요한 파일이 없습니다: '+name)
            if read_file(stream,entry,0,4) not in allowed:
                if key:raise ValueError('입력한 디스크 키로 게임 데이터를 읽을 수 없습니다. 키 또는 ISO를 확인하세요.')
                raise KeyRequired('암호화된 ISO이거나 손상된 데이터입니다. 디스크 키가 필요합니다.')
        entry=by_name['ps3_game/param.sfo']
        if entry['size']>65536:raise ValueError('SFO 크기 오류')
        info=sfo(read_file(stream,entry))
        if info.get('TITLE_ID')!=TITLE_ID:raise ValueError('트라이얼 프론티어 BLJS93001 ISO를 선택하세요.')
        return dict(files=selected,metadata=info,bytes=sum(r['size'] for r in selected),encrypted=key is not None)

def resolve_mount(path):
    """Accept Windows-mounted ISO only; do not claim physical BD support."""
    path=Path(path).resolve(strict=True)
    drive=path.drive
    if len(drive)!=2 or drive[1]!=':':raise ValueError('마운트된 ISO 드라이브를 선택하세요.')
    letter=drive[0].upper()
    if not 'A'<=letter<='Z':raise ValueError('드라이브 문자 오류')
    script=("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            "$c=Get-CimInstance Win32_CDROMDrive | Where-Object Drive -eq '"+letter+":'; "
            "$c | ForEach-Object { Get-DiskImage -DevicePath $_.DeviceID -ErrorAction SilentlyContinue } | "
            "Select-Object -ExpandProperty ImagePath")
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',script],capture_output=True,
                          creationflags=NO_WINDOW,timeout=20)
    if not result.stdout.strip():raise ValueError('마운트 원본 ISO를 찾지 못했습니다. ISO 파일을 직접 선택하세요. 물리 BD는 지원하지 않습니다.')
    candidates=result.stdout.decode('utf-8-sig').strip().splitlines()
    for name in candidates:
        p=Path(name.strip())
        if p.is_file() and p.suffix.lower()=='.iso':return p
    raise ValueError('마운트 원본을 찾지 못했습니다. ISO 파일을 직접 선택하세요.')

def resolve_source(path):
    """Only regular ISO files and directories backed by a mounted ISO."""
    raw=str(path)
    if raw.startswith(('\\\\.\\', '\\\\?\\')):
        raise ValueError('장치 직접 읽기는 지원하지 않습니다. ISO 파일 또는 마운트된 ISO를 선택하세요.')
    source=Path(path).resolve(strict=True)
    if source.is_dir():return resolve_mount(source)
    if not source.is_file() or source.suffix.lower()!='.iso':
        raise ValueError('ISO 파일 또는 Windows에 마운트한 ISO를 선택하세요.')
    return source

def validate_elf(path):
    data=Path(path).read_bytes()
    if len(data)<64 or data[:6]!=b'\x7fELF\x02\x02' or struct.unpack_from('>H',data,18)[0]!=21:
        raise ValueError('복호화된 PS3 ELF가 아닙니다.')
    if struct.unpack_from('>Q',data,24)[0]!=0x48abd8:
        raise ValueError('현재 포팅이 지원하지 않는 실행 파일 구조입니다. 롬 해시가 아닌 실행 구조를 확인했습니다.')
    return data

def prepare_elf(eboot,destination,rpcs3):
    data=Path(eboot).read_bytes()
    if data[:4]==b'\x7fELF':Path(destination).write_bytes(data)
    else:
        if data[:4]!=b'SCE\0':raise ValueError('EBOOT.BIN을 읽을 수 없습니다.')
        if not Path(rpcs3).is_file():raise ValueError('로컬 RPCS3 복호화 도구가 없습니다.')
        with tempfile.TemporaryDirectory(prefix='self-',dir=Path(destination).parent) as temp:
            temp=Path(temp);original=temp/'EBOOT.BIN';original.write_bytes(data)
            with native_dll_search():
                result=subprocess.run([str(Path(rpcs3).resolve()),'--decrypt',str(original)],cwd=temp,
                                      input=b'',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                      env=native_environment(),creationflags=NO_WINDOW,timeout=120)
            elf=temp/'EBOOT.elf'
            if result.returncode or not elf.is_file():raise ValueError('EBOOT 복호화 도구가 ELF를 생성하지 못했습니다.')
            validate_elf(elf);shutil.copyfile(elf,destination)
    validate_elf(destination)

def file_digest(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def installation_issue(root,verify_integrity=True):
    root=Path(root)
    try:
        state=json.loads((root/'install-state.json').read_text(encoding='utf-8'))
        if state.get('schema')!=2 or state.get('title_id')!=TITLE_ID:
            return '설치 기록의 형식 또는 게임 ID가 맞지 않습니다.'
        mandatory={'EBOOT.elf','disc/PS3_GAME/PARAM.SFO','disc/PS3_GAME/USRDIR/EBOOT.BIN',
                   'localization/ko/strings.bin','localization/ko/elf-patches.bin','localization/ko/pack.idx',
                   'localization/ko/data.dat','cache/assets/predecoded-v1.bin'}
        mandatory.update('disc/PS3_GAME/USRDIR/data/pack/'+name for name in ('pack.idx','data.dat','init.dat','fileset.dat'))
        required=state['required']
        # ISO9660 exposes uppercase filenames; Windows resolves them without case.
        names={name.casefold() for name in required}
        missing=sorted(name for name in mandatory if name.casefold() not in names)
        if missing:return '설치 기록에서 필수 파일이 빠졌습니다: '+', '.join(missing)
        essential={name.casefold() for name in mandatory}
        for name,size in required.items():
            if Path(name).is_absolute() or '..' in Path(name).parts or ':' in name:
                return '잘못된 설치 경로: '+name
            path=root/name
            if not path.is_file():return '파일이 없습니다: '+name
            actual=path.stat().st_size
            if actual!=size or size<0 or (size==0 and name.casefold() in essential):
                return f'파일 크기가 다릅니다: {name} (기록 {size}, 실제 {actual})'
            if verify_integrity and file_digest(path)!=state['integrity'][name]:
                return '파일 무결성 검사 실패: '+name
        validate_elf(root/'EBOOT.elf')
        if sfo((root/'disc/PS3_GAME/PARAM.SFO').read_bytes()).get('TITLE_ID')!=TITLE_ID:
            return 'PARAM.SFO의 게임 ID가 맞지 않습니다.'
        for name,magic in [('localization/ko/strings.bin',b'MFTKO001'),('localization/ko/elf-patches.bin',b'MFTKP001'),
                           ('localization/ko/data.dat',b'PIDX'),('disc/PS3_GAME/USRDIR/data/pack/pack.idx',b'PIDX'),
                           ('cache/assets/predecoded-v1.bin',b'MFTZC001')]:
            with (root/name).open('rb') as f:
                if f.read(len(magic))!=magic:return '파일 헤더가 올바르지 않습니다: '+name
        return None
    except (OSError,ValueError,KeyError,TypeError,AttributeError,struct.error) as error:
        return '설치 파일 확인 오류: '+str(error)

def ready(root,verify_integrity=True):
    return installation_issue(root,verify_integrity) is None

def install(source,root,resources,key=None,progress=lambda text,pct:None,cancel=None):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    source=resolve_source(source)
    checked=inspect_iso(source,key)
    required_space=checked['bytes']*3+256*1024*1024
    if shutil.disk_usage(root).free<required_space:raise ValueError('게임 설치와 캐시를 위한 여유 공간이 부족합니다.')
    cancel=cancel or threading.Event()
    def check():
        if cancel.is_set():raise Cancelled('설치를 취소했습니다.')
    with tempfile.TemporaryDirectory(prefix='.first-run-',dir=root) as temp:
        stage=Path(temp);disc=stage/'disc';done=0;integrity={}
        with ImageReader(source,key) as image:
            for entry in checked['files']:
                check();target=disc/entry['path'];target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('wb') as output:
                    digest=hashlib.sha256()
                    offset=0
                    while offset<entry['size']:
                        check();data=read_file(image,entry,offset,min(1024*1024,entry['size']-offset))
                        if not data:raise ValueError('ISO 파일이 잘렸습니다.')
                        output.write(data);digest.update(data);offset+=len(data);done+=len(data)
                        progress('게임 파일 추출: '+entry['path'],int(done*40/checked['bytes']))
                integrity['disc/'+entry['path']]=digest.hexdigest()
        key=None;check();progress('실행 파일 준비',43)
        prepare_elf(disc/'PS3_GAME/USRDIR/EBOOT.BIN',stage/'EBOOT.elf',resources['rpcs3'])
        check();progress('한글 폰트와 번역 적용',50)
        from build_korean import build
        translations=json.loads(Path(resources['translations']).read_text(encoding='utf-8'))
        overlay=stage/'localization/ko'
        build(disc/'PS3_GAME/USRDIR/data/pack',stage/'EBOOT.elf',translations,overlay,resources['texconv'])
        check();progress('다음 실행을 위한 압축 해제 캐시 준비',65)
        from prepare_asset_cache import prepare
        cache=stage/'cache/assets/predecoded-v1.bin'
        prepare(disc/'PS3_GAME/USRDIR/data/pack',cache,extra_files=[overlay/'data.dat'])
        check();progress('설치 파일 확인',95)
        required={str(p.relative_to(stage)).replace('\\','/'):p.stat().st_size for p in disc.rglob('*') if p.is_file()}
        for name in ['EBOOT.elf','localization/ko/strings.bin','localization/ko/elf-patches.bin',
                     'localization/ko/data.dat','localization/ko/pack.idx','cache/assets/predecoded-v1.bin']:
            required[name]=(stage/name).stat().st_size
            integrity[name]=file_digest(stage/name)
        # These hashes describe this user's completed installation, never a fixed
        # reference ROM. They detect later corruption without rejecting variants.
        state=dict(schema=2,title_id=TITLE_ID,metadata=checked['metadata'],required=required,integrity=integrity)
        (stage/'install-state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        issue=installation_issue(stage,False)
        if issue:raise ValueError('설치 결과 확인 실패: '+issue)
        # Only generated resources are promoted. Saves and settings never move.
        promoted=[];saved=[]
        try:
            for name in ['disc','localization','cache','EBOOT.elf','install-state.json']:
                target=root/name;backup=stage/('old-'+name)
                if target.exists():target.rename(backup);saved.append((backup,target))
                (stage/name).rename(target);promoted.append(target)
            issue=installation_issue(root,False)
            if issue:raise ValueError('최종 설치 확인 실패: '+issue)
        except Exception:
            for target in reversed(promoted):target.rename(stage/('failed-'+target.name))
            for backup,target in reversed(saved):backup.rename(target)
            raise
        progress('준비 완료',100)
    return state

def launch(root):
    root=Path(root).resolve()
    if not ready(root,False):raise ValueError('필수 설치 파일이 없습니다. 먼저 설치를 완료하세요.')
    exe=root/'MacrossTrialFrontier.exe'
    if not exe.is_file():raise ValueError('포팅 실행 파일이 없습니다.')
    env=native_environment()
    for key in list(env):
        if key.startswith(('PAD_','FRONTIER_TEXT_TRACE','RSX_CAP','PS3_FTRACE','TRIAL_MAIN_STACK')):env.pop(key,None)
    for key in ('FRONTIER_PAD_TRACE','SPU_DUMP_MISS','TRIAL_PREDECODE_TRACE','SJP_NO_SPIN','TRIAL_ASYNC_VBLANK',
                'AUDIO_TIMING','FRONTIER_AUDIO_TRACE','VTX_STATS','VTX_CACHE_CHECK','VTX_FETCH_ALL','VTX_RAW28',
                'TRIAL_FIFO_IDLE_MS','RSX_PSO_WARMUP','PERF','D3D12_DBG','D3D12_IQ','RSX_FRAME_TIMES',
                'AUDIO_RATE','AUDIO_WAV','VBFULL','TEX_DRAW_SNAP','GCM_M2MF_TRACE','GCM_SUBCH_GATE',
                'GCM_VAL_WATCH','GCM2D_TRACE','GCM_OBJDBG','PS3_ASSET_OVERLAY'):
        env.pop(key,None)
    env.update(PS3_VFS_ROOT='disc',PS3_HDD0_ROOT='hdd0',PS3_GAMEDATA_ROOT='gamedata',
               PS3_TITLE='Macross Trial Frontier',PS3_VERBOSE='0',SPURS_JOB_LS_MAILBOX_ONLY='1',SPU_JOB_FP_CACHE='1',
               TRIAL_JOB_PARALLEL='1',SPURS_CHAIN_OWNER_POOL='0',RSX_FRAME_LIMIT='30',GCM_STRICT_FLIP='1',
               RSX_ACCUM_FRAME='1',D3D12_VSYNC='0',TRIAL_PREDECODE_CACHE='1',GCM_PUT_KICK='0',
               TRIAL_INFLATE_LOCALS='0',TRIAL_VMX_FMA='0',GCM_PARK_GRACE_MS='10000',TEMP=str(root/'temp'),TMP=str(root/'temp'))
    for name in ('temp','hdd0','gamedata'):(root/name).mkdir(exist_ok=True)
    with (root/'launcher.log').open('wb') as log:
        with native_dll_search():
            return subprocess.Popen([str(exe),'EBOOT.elf'],cwd=root,env=env,stdout=log,stderr=log,creationflags=NO_WINDOW)
