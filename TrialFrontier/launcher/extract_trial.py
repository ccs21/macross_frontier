"""Read-only PIDX text inventory. Outputs candidates, not a finished patch."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import struct
import zlib


class Pack:
    def __init__(self, folder, index_name='pack.idx'):
        self.folder = Path(folder)
        self.data = (self.folder / index_name).read_bytes()
        if len(self.data) < 40 or self.data[:4] != b'PIDX':
            raise ValueError('Not a PIDX archive')
        _, _, self.table, self.count, self.roots, _, _, self.names, self.names_size = struct.unpack_from('<9I', self.data, 4)
        if self.table + self.count * 24 > len(self.data) or self.names + self.names_size > len(self.data):
            raise ValueError('Index out of bounds')

    def name(self, offset):
        if offset >= self.names_size:
            raise ValueError('Name out of bounds')
        end = self.data.find(b'\0', self.names + offset, self.names + self.names_size)
        if end < 0:
            raise ValueError('Unterminated name')
        return self.data[self.names + offset:end].decode('cp932')

    def entries(self):
        visited = set()
        def walk(start, count, parent):
            if start + count > self.count:
                raise ValueError('Directory out of bounds')
            for i in range(start, start + count):
                if i in visited:
                    raise ValueError('Repeated directory entry')
                visited.add(i)
                row = struct.unpack_from('<6I', self.data, self.table + i * 24)
                name = self.name(row[1])
                if name in ('.', '..') or '/' in name or '\\' in name or ':' in name:
                    raise ValueError('Unsafe archive path')
                path = parent / name
                if row[0] == 1:
                    yield from walk(row[3], row[2], path)
                elif row[0] == 0:
                    yield i, path, row
                else:
                    raise ValueError('Unknown entry type')
        yield from walk(0, self.roots, PurePosixPath())

    def read(self, row):
        archive = self.folder / PurePosixPath(self.name(row[2]).replace('\\', '/')).name
        offset, expected, compressed = row[3:]
        if expected > 128 * 1024 * 1024:
            raise ValueError('Asset too large')
        stored = compressed if 0 < compressed < expected else expected
        if offset + stored > archive.stat().st_size:
            raise ValueError('Asset outside archive')
        with archive.open('rb') as stream:
            stream.seek(offset)
            raw = stream.read(stored)
        if stored == expected:
            return raw
        if raw[:4] != b'segs':
            result = zlib.decompress(raw)
        else:
            _, count, full, _ = struct.unpack_from('>HHII', raw, 4)
            if full != expected or not count or 16 + count * 8 > len(raw):
                raise ValueError('Invalid segment table')
            relative = struct.unpack_from('>I', raw, 20)[0] == 1
            result = bytearray()
            for i in range(count):
                size, length, position = struct.unpack_from('>HHI', raw, 16 + i * 8)
                length = length or 65536
                position = position - 1 + (16 + count * 8 if relative else 0)
                if position < 0 or position + size > len(raw):
                    raise ValueError('Segment out of bounds')
                chunk = raw[position:position + size]
                decoded = chunk if size == length else zlib.decompress(chunk, -15)
                if len(decoded) != length:
                    raise ValueError('Segment length mismatch')
                result.extend(decoded)
        if len(result) != expected:
            raise ValueError('Asset length mismatch')
        return bytes(result)

    def bundled_entries(self, group_name=None):
        """FSTS members may exist only inside a named fileset, not the loose index."""
        table, size = struct.unpack_from('<II', self.data, 24)
        if table + size > len(self.data) or size < 4:
            raise ValueError('Fileset table out of bounds')
        count = struct.unpack_from('<I', self.data, table)[0]
        if 4 + count * 4 > size:
            raise ValueError('Fileset pointer table out of bounds')
        for i in range(count):
            at = table + struct.unpack_from('<I', self.data, table + 4 + i * 4)[0]
            if at + 20 > table + size:
                raise ValueError('Fileset record out of bounds')
            name, archive_name, start, length, expected_count = struct.unpack_from('<5I', self.data, at)
            if group_name is not None and self.name(name) != group_name:
                continue
            archive = self.folder / PurePosixPath(self.name(archive_name).replace('\\', '/')).name
            with archive.open('rb') as stream:
                if start + length > archive.stat().st_size:
                    raise ValueError('Fileset outside archive')
                stream.seek(start)
                header = stream.read(32)
                if header[:4] != b'FSTS':
                    raise ValueError('Missing fileset header')
                members, records, names, names_length = struct.unpack_from('<4I', header, 4)
                if members != expected_count or records + members * 16 > names or names + names_length > length:
                    raise ValueError('Invalid fileset member table')
                stream.seek(start)
                index = stream.read(names + names_length)
            for j in range(members):
                filename, offset, expanded, compressed = struct.unpack_from('<4I', index, records + j * 16)
                if filename >= names_length:
                    raise ValueError('Fileset name out of bounds')
                end = index.find(b'\0', names + filename, names + names_length)
                if end < 0:
                    raise ValueError('Unterminated fileset name')
                path = PurePosixPath(index[names + filename:end].decode('cp932'))
                if path.is_absolute() or '..' in path.parts or '\\' in str(path) or ':' in str(path):
                    raise ValueError('Unsafe fileset path')
                stored = compressed if 0 < compressed < expanded else expanded
                if offset + stored > length:
                    raise ValueError('Fileset member outside group')
                yield self.name(name), path, (0, 0, archive_name, start + offset, expanded, compressed)


def strings(data):
    # Strict CP932, NUL-delimited printable runs containing kana. Binary false
    # positives remain possible; every exported entry explicitly needs review.
    for match in re.finditer(rb'[^\x00-\x08\x0b-\x1f]{4,}\x00', data):
        raw = match.group()[:-1]
        for encoding in ('utf-8', 'cp932'):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                pass
        else:
            continue
        if re.search('[\u3041-\u3096\u30a1-\u30fa]', text) and all(c.isprintable() or c in '\n\r\t' for c in text):
            yield match.start(), len(raw), text, encoding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--elf', type=Path)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.pack.resolve()):
        raise ValueError('Output must be outside original archive directory')
    pack = Pack(args.pack)
    inventory, texts = [], []
    def collect(path, data, base=0):
        for offset, length, text, encoding in strings(data):
            offset += base
            texts.append(dict(id=f'{path}@{offset:08x}', source=str(path), offset=offset,
                              source_bytes=length, encoding=encoding, japanese=text,
                              korean='', status='needs_review'))
    for index, path, row in pack.entries():
        inventory.append(dict(index=index, path=str(path), bytes=row[4]))
        if path.suffix.lower() in {'.fes', '.tbl', '.ini', '.csv', '.rb', '.ark'}:
            collect(str(path), pack.read(row))
    if args.elf:
        elf = args.elf.read_bytes()
        if elf[:6] != b'\x7fELF\x02\x02':
            raise ValueError('Expected big-endian ELF64')
        table = struct.unpack_from('>Q', elf, 40)[0]
        stride, count = struct.unpack_from('>HH', elf, 58)
        if stride < 64 or table + stride * count > len(elf):
            raise ValueError('Invalid ELF sections')
        for i in range(count):
            _, kind, flags, _, offset, length, *_ = struct.unpack_from('>IIQQQQIIQQ', elf, table + stride * i)
            if kind == 1 and flags & 2 and not flags & 4:
                if offset + length > len(elf):
                    raise ValueError('ELF section out of bounds')
                collect('EBOOT.elf', elf[offset:offset + length], offset)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, payload in [('inventory.json', inventory), ('japanese-candidates.json', texts)]:
        target = args.output / name
        # Never silently discard a translator's existing work.
        with target.open('x', encoding='utf-8') as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
    print(json.dumps(dict(files=len(inventory), candidates=len(texts)), ensure_ascii=False))


if __name__ == '__main__':
    main()
