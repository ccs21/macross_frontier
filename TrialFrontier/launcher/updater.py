"""Full-package updates; all working files remain inside the portable folder."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

REPO='ccs21/macross_frontier'
API=f'https://api.github.com/repos/{REPO}/releases?per_page=100'
PACKAGE=re.compile(r'TrialFrontier-(\d+\.\d+\.\d+)-test\.zip$')
DIRS={'_internal','tools','resources','source','licenses'}
FILES={'trialfrontier.exe','macrosstrialfrontier.exe','사용방법.txt','third-party.txt','icon.ico',
       'readme.md','release_notes.md','status.md','build.md'}

def version(text):
    match=re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)(?:-test)?',text)
    if not match:raise ValueError('지원하지 않는 버전: '+text)
    return tuple(map(int,match.groups()))

def request(url):
    return urllib.request.urlopen(urllib.request.Request(url,headers={
        'User-Agent':'Macross-Trial-Frontier-Updater', 'Accept':'application/vnd.github+json'}),timeout=8)

def latest(current):
    with request(API) as response:releases=json.load(response)
    choices=[]
    for release in releases:
        if release.get('draft') or release.get('prerelease'):continue
        for asset in release.get('assets',[]):
            match=PACKAGE.fullmatch(asset['name'])
            if not match or version(match[1])<=version(current):continue
            digest=asset.get('digest','') or ''
            if not re.fullmatch(r'sha256:[0-9a-fA-F]{64}',digest):continue
            url=asset['browser_download_url']
            if not url.startswith(f'https://github.com/{REPO}/releases/download/'):continue
            choices.append(dict(version=match[1],url=url,sha256=digest[7:].lower(),size=asset['size']))
    return max(choices,key=lambda x:version(x['version'])) if choices else None

def allowed(path):
    return path.parts[0].casefold() in DIRS or (len(path.parts)==1 and path.name.casefold() in FILES)

def unpack(archive,destination):
    """Strict allowlist prevents a package replacing ROM, save, settings or cache."""
    destination=Path(destination);seen=set();total=0
    with zipfile.ZipFile(archive) as z:
        entries=[]
        for item in z.infolist():
            name=item.filename
            p=PurePosixPath(name)
            if '\\' in name or ':' in name or p.is_absolute() or '..' in p.parts:
                raise ValueError('잘못된 업데이트 경로')
            if len(p.parts)<2:continue
            if not re.fullmatch(r'TrialFrontier-\d+\.\d+\.\d+-test',p.parts[0]):
                raise ValueError('잘못된 배포 폴더')
            relative=PurePosixPath(*p.parts[1:])
            if (item.external_attr>>16)&0o170000==0o120000:raise ValueError('링크 파일은 허용되지 않습니다')
            if item.is_dir() or not allowed(relative):continue
            key=str(relative).casefold()
            if key in seen:raise ValueError('중복된 업데이트 경로')
            seen.add(key);total+=item.file_size
            if total>8*1024**3:raise ValueError('업데이트 압축 해제 용량 초과')
            entries.append((item,relative))
        if not {'trialfrontier.exe','macrosstrialfrontier.exe','resources/korean.json'}<=seen:
            raise ValueError('전체 배포본의 필수 파일이 없습니다')
        for item,relative in entries:
            target=destination/str(relative);target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(item) as source,target.open('wb') as out:shutil.copyfileobj(source,out)

def download(root,release,progress):
    (Path(root)/'.updates').mkdir(exist_ok=True)
    work=Path(tempfile.mkdtemp(prefix='update-',dir=Path(root)/'.updates'))
    archive=work/'package.zip';digest=hashlib.sha256();count=0
    with request(release['url']) as response,archive.open('wb') as out:
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            count+=len(chunk)
            if count>release['size']:raise ValueError('업데이트 크기 불일치')
            out.write(chunk);digest.update(chunk)
            progress('새 전체 배포본 다운로드 중…',count*90/max(1,release['size']))
    if count!=release['size'] or digest.hexdigest()!=release['sha256']:
        raise ValueError('업데이트 무결성 검사 실패')
    payload=work/'payload';unpack(archive,payload)
    progress('업데이트 준비 완료',100)
    return payload

def promote(root,payload):
    root=Path(root).resolve();payload=Path(payload).resolve()
    if not payload.is_relative_to(root/'.updates'):raise ValueError('업데이트 작업 경로 오류')
    backup=payload.parent/'backup';backup.mkdir(exist_ok=False)
    replaced=[];saved=[]
    try:
        # Replace packaged directories as units: no obsolete DLLs left mixed in.
        for source in sorted(payload.iterdir()):
            if not allowed(PurePosixPath(source.name)):raise ValueError('업데이트 대상 오류')
            target=root/source.name
            if target.is_symlink() or (target.exists() and target.resolve()!=target):
                raise ValueError('업데이트 대상이 외부 경로를 가리킵니다')
            if target.exists():target.rename(backup/source.name);saved.append(target)
            replaced.append(target)
            # Copy so the helper can keep running from its staged executable.
            if source.is_dir():shutil.copytree(source,target)
            else:shutil.copy2(source,target)
    except Exception:
        for target in reversed(replaced):
            if not target.exists():continue
            if target.is_dir():shutil.rmtree(target)
            else:target.unlink()
        for target in reversed(saved):
            if target.exists():
                if target.is_dir():shutil.rmtree(target)
                else:target.unlink()
            (backup/target.name).rename(target)
        raise

def handoff(root,payload):
    from external_process import native_dll_search,native_environment
    with native_dll_search():
        subprocess.Popen([str(payload/'TrialFrontier.exe'),'--apply-update',str(root),str(os.getpid())],
                         cwd=payload,env=native_environment(),creationflags=subprocess.CREATE_NO_WINDOW)

def apply_pending(root,parent_pid):
    import ctypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x100000,False,int(parent_pid))
    if handle:
        try:
            if kernel.WaitForSingleObject(handle,60000)!=0:raise RuntimeError('이전 런처 종료 대기 시간 초과')
        finally:kernel.CloseHandle(handle)
    payload=Path(sys.executable).resolve().parent
    time.sleep(1) # PyInstaller's parent bootloader releases its image after the child.
    import msvcrt
    with (Path(root)/'.launcher.lock').open('r+b') as lock:
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        promote(root,payload)
    from external_process import native_dll_search,native_environment
    with native_dll_search():
        subprocess.Popen([str(Path(root)/'TrialFrontier.exe'),'--skip-update-once'],cwd=root,
                         env=native_environment(),creationflags=subprocess.CREATE_NO_WINDOW)
