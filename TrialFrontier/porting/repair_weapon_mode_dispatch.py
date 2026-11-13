"""Restore local weapon-mode branches using tables in the user's ELF.

Only accepts the exact TOC load / scaled index / in-place table lookup idiom.
Checks regenerated bodies against the current lift before writing any file.
"""
import argparse
import re
import struct
import sys
from pathlib import Path

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--elf', type=Path, required=True)
    ap.add_argument('--sdk', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    sys.path.insert(0, str(args.sdk / 'tools'))
    import ppu_disasm
    from ppu_lifter import PPULifter
    elf = args.elf.read_bytes()
    phoff = struct.unpack_from('>Q', elf, 32)[0]
    stride, count = struct.unpack_from('>HH', elf, 54)
    segments = [struct.unpack_from('>IIQQQQQQ', elf, phoff+i*stride) for i in range(count)]
    def word(a):
        for typ, flags, off, va, pa, size, memsize, align in segments:
            if typ == 1 and va <= a and a+4 <= va+size:
                return struct.unpack_from('>I', elf, off+a-va)[0]
        raise ValueError(hex(a))
    path = args.output / 'ppu_recomp_050.cpp'
    source = path.read_text(encoding='utf-8')
    matches = list(re.finditer(r'void func_([0-9A-F]{8})\(ppu_context\* ctx\) \{.*?\n\}', source, re.S))
    replacements = []
    for current, following in zip(matches, matches[1:]):
        start, end = int(current[1],16), int(following[1],16)
        if not 0x3662C4 <= start < 0x36849C:
            continue
        ins = [ppu_disasm.decode(word(a), a) for a in range(start,end,4)]
        tables = {}
        for k, inst in enumerate(ins):
            if inst.mnemonic != 'bctr' or k < 6:
                continue
            block = ins[k-6:k+1]
            if [x.mnemonic for x in block] != ['lwz','rlwinm','add','rldicl','lwz','mtctr','bctr']:
                continue
            ops = [[v.strip() for v in x.operands.split(',')] for x in block]
            assert ops[0][0]=='r0' and ops[0][1].endswith('(r2)')
            assert ops[1]==['r3','r3','2','0','29']
            assert ops[2]==['r3','r3','r0'] and ops[3]==['r3','r3','0','32']
            assert ops[4]==['r3','0x0(r3)'] and ops[5]==['r3']
            base=word(0x4AAD80+int(ops[0][1].split('(')[0],0))
            targets=[word(base+4*i) for i in range(3)]
            assert all(start<t<end and t%4==0 for t in targets)
            tables[start+k*4]=sorted(set(targets))
        if not tables:
            continue
        def generate(jumps):
            lifter=PPULifter(); lifter.toc_base=0x4AAD80; lifter.code_hi=0x3D1548
            lifter.jump_tables=jumps
            fn=lifter.lift_function(ins,start,end)
            lines=[line if line.startswith('loc_') else '    '+line for line in fn.body_lines]
            return f'void func_{start:08X}(ppu_context* ctx) {{\n    PPU_MM_SNAP\n'+'\n'.join(lines)+'\n}'
        old,new=generate({}),generate(tables)
        def normalize(s):
            s=re.sub(r'^loc_[0-9A-F]+:\n','',s,flags=re.M)
            return re.sub(r'switch \(\(uint32_t\)ctx->ctr\) \{ .*? \} return;', 'ps3_indirect_call(ctx); return;',s)
        assert normalize(old)==normalize(new)
        assert current[0] in (old,new), f'Unexpected edits {start:08X}'
        if args.check:
            assert current[0]==new, f'Not repaired {start:08X}'
        replacements.append((current.start(),current.end(),new))
        print(f'{start:08X}: {len(tables)} verified local mode table(s)')
    assert len(replacements)==17, f'Expected 17 mode functions, found {len(replacements)}'
    if not args.check:
        backup=path.with_suffix('.cpp.before-mode-repair')
        if not backup.exists(): backup.write_text(source,encoding='utf-8')
        for a,b,new in reversed(replacements): source=source[:a]+new+source[b:]
        path.write_text(source,encoding='utf-8')
    print('Verified 17 mode dispatches; only branches and labels change.')

if __name__=='__main__': main()

