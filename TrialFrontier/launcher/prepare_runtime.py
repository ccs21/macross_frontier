"""Portable runtime migration for fresh installs and full-package updates."""
from pathlib import Path
import hashlib
import os
import shutil
from prepare_spu import prepare, ready

def ensure(root, progress=lambda text,pct:None):
    root=Path(root)
    bundle=root/'resources/spu-build'
    if not (bundle/'recipes.json').is_file():
        raise ValueError('SPU 설치 도구가 없습니다. 전체 배포본을 다시 압축 해제하세요.')
    # Old updaters allow resources/ but not newly introduced root DLLs.
    # Ship the libraries inside resources and stage beside the native EXE.
    libs=root/'resources/native-runtime'
    for name in ('SDL2.dll','llvmlite.dll','msvcp140-8f141b4454fa78db34bc1f28c571b4da.dll'):
        source=libs/name; target=root/name
        if not source.is_file():raise ValueError('런타임 파일 누락: '+name)
        if target.is_file() and hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(target.read_bytes()).digest():continue
        temporary=root/(name+'.installing')
        try:
            shutil.copy2(source,temporary);os.replace(temporary,target)
        finally:
            if temporary.exists():temporary.unlink()
    if not ready(root,bundle):
        prepare(root/'EBOOT.elf',root/'spu-ir',bundle,progress)

