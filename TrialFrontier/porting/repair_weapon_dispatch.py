"""Recover Trial's intra-function weapon switches from the user's own ELF.

The generic lift misses the in-place add/clrldi/lwz absolute-table idiom.
These four functions each select three weapon slots through three tables.
Only switch dispatches and labels may differ from the original lift. No game
bytes or generated game functions are shipped in this tool.
"""
from pathlib import Path
import argparse
import re
import struct
import sys

FUNCTIONS = (
    (0x36849C, 0x368CA8, 'ppu_recomp_050.cpp', (0x368820, 0x3688C4, 0x368C24)),
    (0x368CA8, 0x36949C, 'ppu_recomp_050.cpp', (0x36902C, 0x3690D0, 0x369418)),
    (0x36949C, 0x369CA8, 'ppu_recomp_051.cpp', (0x369820, 0x3698C4, 0x369C24)),
    (0x369CA8, 0x36A4B4, 'ppu_recomp_051.cpp', (0x36A02C, 0x36A0D0, 0x36A430)),
)


def repair(elf_path, sdk, output, check=False):
    sys.path.insert(0, str(Path(sdk) / 'tools'))
    import ppu_disasm
    from ppu_lifter import PPULifter
    elf = Path(elf_path).read_bytes()
    phoff = struct.unpack_from('>Q', elf, 32)[0]
    stride, count = struct.unpack_from('>HH', elf, 54)
    segments = [struct.unpack_from('>IIQQQQQQ', elf, phoff + i * stride) for i in range(count)]

    def read32(address):
        for typ, flags, offset, va, pa, size, memsize, align in segments:
            if typ == 1 and va <= address and address + 4 <= va + size:
                return struct.unpack_from('>I', elf, offset + address - va)[0]
        raise ValueError(f'Unmapped ELF address {address:08X}')

    pending = {}
    for start, end, filename, dispatches in FUNCTIONS:
        instructions = [ppu_disasm.decode(read32(a), a) for a in range(start, end, 4)]
        tables = {}
        for address in dispatches:
            block = [ppu_disasm.decode(read32(a), a) for a in range(address - 24, address + 4, 4)]
            assert [i.mnemonic for i in block] == ['lwz', 'add', 'rldicl', 'lwz', 'rldicl', 'mtctr', 'bctr']
            ops = [[p.strip() for p in i.operands.split(',')] for i in block]
            assert ops[0][0] == 'r9' and ops[0][1].endswith('(r2)')
            assert ops[1] == ['r9', 'r29', 'r9']
            assert ops[2] == ops[4] == ['r9', 'r9', '0', '32']
            assert ops[3] == ['r9', '0x0(r9)'] and ops[5] == ['r9']
            base = read32(0x4AAD80 + int(ops[0][1].split('(')[0], 0))
            targets = [read32(base + i * 4) for i in range(3)]
            assert all(start < t < end and t % 4 == 0 for t in targets)
            tables[address] = sorted(set(targets))

        def generate(jumps):
            lifter = PPULifter()
            lifter.toc_base = 0x4AAD80
            lifter.code_hi = 0x3D1548
            lifter.jump_tables = jumps
            function = lifter.lift_function(instructions, start, end)
            lines = [line if line.startswith('loc_') else '    ' + line for line in function.body_lines]
            return f'void func_{start:08X}(ppu_context* ctx) {{\n    PPU_MM_SNAP\n' + '\n'.join(lines) + '\n}'

        old, new = generate({}), generate(tables)
        # Prove the repair adds no instruction changes beyond local dispatch.
        normalized = re.sub(r'^loc_[0-9A-F]+:\n', '', new, flags=re.M)
        normalized = re.sub(r'switch \(\(uint32_t\)ctx->ctr\) \{ .*? \} return;', 'ps3_indirect_call(ctx); return;', normalized)
        assert normalized == re.sub(r'^loc_[0-9A-F]+:\n', '', old, flags=re.M)
        path = Path(output) / filename
        source = pending.get(path, path.read_text(encoding='utf-8'))
        pattern = rf'void func_{start:08X}\(ppu_context\* ctx\) \{{.*?\n\}}'
        match = re.search(pattern, source, re.S)
        assert match and match[0] in (old, new), f'Unexpected edits in {start:08X}; refusing overwrite'
        if check:
            assert match[0] == new, f'Unrepaired weapon function {start:08X}'
        pending[path] = source[:match.start()] + new + source[match.end():]
    if not check:
        for path, source in pending.items():
            path.write_text(source, encoding='utf-8')
    print('Verified 12 weapon dispatches / 36 table slots; only local branches and labels changed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    repair(args.elf, args.sdk, args.output, args.check)
