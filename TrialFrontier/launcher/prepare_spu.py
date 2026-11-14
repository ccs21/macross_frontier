"""Generate the SPU runtime from the user's installed ELF, never shipped IR.

Recipes contain references into locally lifted instructions plus authored fixes.
They do not contain extracted images or complete translated game programs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
from external_process import native_dll_search, native_environment

IMAGES = [('signal', 'signal', 0x435000, 0xc90),
          ('title', 'title', 0x42b700, 0x7810),
          ('sound', 'sound', 0x435d00, 0x15844),
          ('mission', 'mission', 0x418f80, 0x12780),
          ('hangar_anim', 'hangar', 0x40fb80, 0x9210),
          ('mission_aux', 'aux', 0x40dd00, 0x1e50)]

def normalize(source):
    source = source.replace('../../runtime/spu/spu_helpers.h', 'spu_helpers.h')
    return re.sub(r'ctx->pc = (0x[0-9A-F]+); g_spu_trampoline_fn = (trial_\w+_spu_func_[0-9A-F]+); return;',
                  r'SPU_DIRECT(ctx, \1, \2);', source)

def image_bytes(elf, offset, size, sound=False):
    blob = elf[offset:offset+size]
    if len(blob) != size:
        raise ValueError('SPU 영역이 없는 실행 파일입니다.')
    if not sound:
        return blob
    if blob[:7] != b'\x7fELF\x01\x02\x01':
        raise ValueError('지원되는 SPU 사운드 ELF를 찾을 수 없습니다.')
    phoff = struct.unpack_from('>I', blob, 28)[0]
    phnum = struct.unpack_from('>H', blob, 44)[0]
    memory = bytearray(262144); end = 0
    for i in range(phnum):
        typ, ofs, va, _, sz, _, _, _ = struct.unpack_from('>8I', blob, phoff+32*i)
        if typ != 1:
            continue
        if va+sz > len(memory) or ofs+sz > len(blob):
            raise ValueError('잘못된 SPU ELF 세그먼트입니다.')
        memory[va:va+sz] = blob[ofs:ofs+sz]; end = max(end, va+sz)
    return bytes(memory[:end])

def lift(bundle, raw, bounds, prefix, output):
    (output/'input.bin').write_bytes(raw)
    (output/'functions.json').write_text(json.dumps(bounds), encoding='utf-8')
    argv, paths = sys.argv[:], sys.path[:]
    try:
        sys.path.insert(0, str(bundle/'tools'))
        sys.argv = ['spu_lifter.py', str(output/'input.bin'), '--functions',
                    str(output/'functions.json'), '--symbol-prefix', f'trial_{prefix}_',
                    '--output', str(output)]
        runpy.run_path(str(bundle/'tools/spu_lifter.py'), run_name='__main__')
    finally:
        sys.argv, sys.path = argv, paths
    return normalize((output/'spu_recomp.c').read_text(encoding='utf-8'))

def reconstruct(lines, recipe):
    result = []
    for item in recipe:
        if isinstance(item, str):
            result.append(item)
            continue
        index, indent, flags = item
        line = lines[index].strip()
        if flags & 1:
            ops = {'fa':0, 'fm':1, 'fma':2, 'fms':3, 'fnms':4, 'fs':5}
            def rz(m):
                op, args = m.groups()
                if op in ('fa', 'fm', 'fs'): args += ', (u128){0}'
                return f'rz_candidate_scoped({ops[op]}, {args})'
            line = re.sub(r'spu_(fa|fm|fma|fms|fnms|fs)\(([^;\n]+)\)', rz, line)
        if flags & 2: line = line.replace('SPU_DIRECT(', '_mm_setcsr(outer_mxcsr); SPU_DIRECT(')
        if flags & 4: line = line.replace('return;', '_mm_setcsr(saved); return;')
        if flags & 8: line = line.replace('SPU_DIRECT(', '_mm_setcsr(saved); SPU_DIRECT(')
        result.append(' '*indent+line)
    return '\n'.join(result)+'\n'

def prepare(elf_path, destination, bundle, progress=lambda text,pct:None):
    elf_path, destination, bundle = map(Path, (elf_path, destination, bundle))
    manifest = json.loads((bundle/'recipes.json').read_text(encoding='utf-8'))
    elf = elf_path.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.spu-build-', dir=destination.parent) as temp:
        work = Path(temp); result = work/'result'; result.mkdir(); imports = set()
        for i, (folder, prefix, offset, size) in enumerate(IMAGES):
            progress('SPU 실행 코드 생성: '+prefix, 5+i*14)
            stage = work/folder; stage.mkdir(); entry = manifest['images'][prefix]
            baseline = lift(bundle, image_bytes(elf,offset,size,prefix=='sound'), entry['bounds'], prefix, stage)
            # Validate instruction structure, not an ISO/ROM reference hash.
            lines = baseline.splitlines()
            shape = '\n'.join(re.sub(r'0x[0-9a-fA-F]+|\d+', '#', s.strip()) for s in lines)
            if hashlib.sha256(shape.encode()).hexdigest() != entry['shape']:
                raise ValueError('SPU 코드 구조가 지원되는 버전과 다릅니다: '+prefix)
            source = reconstruct(lines,entry['recipe'])
            if prefix == 'sound':
                source = source.replace('#include "../audio_trace.h"', 'int frontier_jit_audio_trace_enabled(void);')
                source = source.replace('frontier_audio_trace_enabled()', 'frontier_jit_audio_trace_enabled()')
            (stage/'spu_recomp.c').write_text(source,encoding='utf-8')
            (stage/'spu_recomp.h').write_text(entry['header'],encoding='utf-8')
            output = result/(prefix+'.ll')
            compiler = bundle/'compiler/clang-cl.exe'
            command = [str(compiler), '/nologo','/c','/MD','/O2','/GS-','/utf-8','-mavx2',
                       '/clang:-fwrapv','-fno-strict-aliasing','/clang:-ffp-contract=off',
                       '/clang:-S','/clang:-emit-llvm','/DSPU_USE_DISPATCH_MT','/D_CRT_SECURE_NO_WARNINGS',
                       '/FI'+str(bundle/'include/jit_context.h'), '/I'+str(stage),
                       '/I'+str(bundle/'include'), '/clang:-nostdinc',
                       '/clang:-isystem','/clang:'+str(bundle/'compiler/include'),
                       '/I'+str(bundle/'crt'), str(stage/'spu_recomp.c'),
                       '/clang:-o','/clang:'+str(output)]
            if prefix == 'mission': command.append('/clang:-mfma')
            with native_dll_search():
                proc = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                      env=native_environment(),
                                      creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if proc.returncode:
                (destination.parent/'spu-build-error.log').write_bytes(proc.stdout)
                raise ValueError('SPU 컴파일 실패: '+prefix+' (spu-build-error.log 확인)')
            ir = output.read_text(encoding='utf-8').replace('dllimport ', '')
            if 'thread_local' in ir: raise ValueError('지원하지 않는 SPU TLS')
            output.write_text(ir,encoding='utf-8')
            names = set(re.findall(r'^declare\b[^\n]*?@([\w.$]+)\(',ir,re.M))
            names.update(re.findall(r'^@([\w.$]+) = external\b',ir,re.M))
            imports.update(n for n in names if not n.startswith('llvm.'))
        (result/'imports.txt').write_text('\n'.join(sorted(imports|{'memcpy','memmove','memset'}))+'\n')
        (result/'build-state.json').write_text(json.dumps({'recipe':hashlib.sha256((bundle/'recipes.json').read_bytes()).hexdigest(),
             'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in result.iterdir()}}))
        backup = work/'previous'
        if destination.exists(): destination.rename(backup)
        try: result.rename(destination)
        except Exception:
            if backup.exists(): backup.rename(destination)
            raise
    progress('SPU 준비 완료',100)

def ready(root, bundle):
    root, bundle = Path(root), Path(bundle)
    try:
        state = json.loads((root/'spu-ir/build-state.json').read_text())
        if state['recipe'] != hashlib.sha256((bundle/'recipes.json').read_bytes()).hexdigest(): return False
        required = {prefix+'.ll' for _,prefix,_,_ in IMAGES}|{'imports.txt'}
        return required <= state['files'].keys() and all(
            hashlib.sha256((root/'spu-ir'/name).read_bytes()).hexdigest()==digest
            for name,digest in state['files'].items())
    except (OSError,ValueError,KeyError): return False

if __name__ == '__main__':
    prepare(*sys.argv[1:4],progress=lambda text,pct:print(pct,text,flush=True))
