from __future__ import annotations

import re
from dataclasses import dataclass

from .config import ProjectConfig, SegmentConfig


class AssemblerError(ValueError):
    pass


@dataclass(frozen=True)
class SegmentDirective:
    name: str
    line: int


@dataclass(frozen=True)
class Label:
    name: str
    line: int


@dataclass(frozen=True)
class DataDirective:
    kind: str
    values: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class ReserveDirective:
    count_expr: str
    fill_expr: str | None
    line: int


@dataclass(frozen=True)
class Instruction:
    mnemonic: str
    operand: str | None
    line: int


AsmItem = SegmentDirective | Label | DataDirective | ReserveDirective | Instruction


IMPLIED_OPS = {
    "clc": 0x18,
    "cld": 0xD8,
    "dex": 0xCA,
    "dey": 0x88,
    "inx": 0xE8,
    "iny": 0xC8,
    "nop": 0xEA,
    "rti": 0x40,
    "rts": 0x60,
    "sec": 0x38,
    "sei": 0x78,
    "tax": 0xAA,
    "tay": 0xA8,
    "txa": 0x8A,
    "txs": 0x9A,
    "tya": 0x98,
}

IMMEDIATE_OPS = {
    "adc": 0x69,
    "and": 0x29,
    "cmp": 0xC9,
    "eor": 0x49,
    "lda": 0xA9,
    "ldx": 0xA2,
    "ldy": 0xA0,
    "ora": 0x09,
    "sbc": 0xE9,
}

ABSOLUTE_OPS = {
    "adc": 0x6D,
    "and": 0x2D,
    "cmp": 0xCD,
    "eor": 0x4D,
    "jmp": 0x4C,
    "jsr": 0x20,
    "lda": 0xAD,
    "ldx": 0xAE,
    "ora": 0x0D,
    "sbc": 0xED,
    "sta": 0x8D,
}

ABSOLUTE_X_OPS = {
    "adc": 0x7D,
    "and": 0x3D,
    "cmp": 0xDD,
    "eor": 0x5D,
    "lda": 0xBD,
    "ldy": 0xBC,
    "ora": 0x1D,
    "sbc": 0xFD,
    "sta": 0x9D,
}

RELATIVE_OPS = {
    "bcc": 0x90,
    "bcs": 0xB0,
    "beq": 0xF0,
    "bne": 0xD0,
}

TOKEN_RE = re.compile(r"\$[0-9a-fA-F]+|0x[0-9a-fA-F]+|\d+|[A-Za-z_][A-Za-z0-9_]*|[+-]")


def assemble_text(source: str, config: ProjectConfig) -> bytes:
    items = parse_assembly(source)
    symbols = first_pass(items, config)
    return second_pass(items, symbols, config)


def parse_assembly(source: str) -> list[AsmItem]:
    items: list[AsmItem] = []
    for line_no, raw_line in enumerate(source.splitlines(), start=1):
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue

        while True:
            match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):", line)
            if not match:
                break
            items.append(Label(name=match.group(1), line=line_no))
            line = line[match.end() :].strip()
            if not line:
                break
        if not line:
            continue

        if line.startswith(".segment"):
            match = re.fullmatch(r'\.segment\s+"([^"]+)"', line)
            if not match:
                raise AssemblerError(f"invalid .segment syntax at line {line_no}")
            items.append(SegmentDirective(name=match.group(1), line=line_no))
            continue

        if line.startswith(".byte"):
            values = split_csv(line[5:].strip())
            items.append(DataDirective(kind="byte", values=tuple(values), line=line_no))
            continue

        if line.startswith(".word"):
            values = split_csv(line[5:].strip())
            items.append(DataDirective(kind="word", values=tuple(values), line=line_no))
            continue

        if line.startswith(".res"):
            values = split_csv(line[4:].strip())
            if not values:
                raise AssemblerError(f".res requires at least a count at line {line_no}")
            fill = values[1] if len(values) > 1 else None
            items.append(ReserveDirective(count_expr=values[0], fill_expr=fill, line=line_no))
            continue

        parts = line.split(None, 1)
        mnemonic = parts[0].lower()
        operand = parts[1].strip() if len(parts) == 2 else None
        items.append(Instruction(mnemonic=mnemonic, operand=operand, line=line_no))
    return items


def first_pass(items: list[AsmItem], config: ProjectConfig) -> dict[str, int]:
    symbols: dict[str, int] = {}
    offsets = {segment.name: 0 for segment in config.segments}
    current_segment: SegmentConfig | None = None

    for item in items:
        if isinstance(item, SegmentDirective):
            current_segment = config.segment_named(item.name)
            continue
        if current_segment is None:
            raise AssemblerError(f"line {item.line}: no active segment")
        if isinstance(item, Label):
            if item.name in symbols:
                raise AssemblerError(f"duplicate label {item.name!r} at line {item.line}")
            symbols[item.name] = current_segment.start + offsets[current_segment.name]
            continue

        size = item_size(item, current_segment)
        offsets[current_segment.name] += size
        if offsets[current_segment.name] > current_segment.size:
            raise AssemblerError(
                f"segment {current_segment.name!r} overflowed at line {item.line}: "
                f"{offsets[current_segment.name]} > {current_segment.size}"
            )

    return symbols


def second_pass(items: list[AsmItem], symbols: dict[str, int], config: ProjectConfig) -> bytes:
    offsets = {segment.name: 0 for segment in config.segments}
    current_segment: SegmentConfig | None = None
    segment_bytes = {
        segment.name: bytearray([segment.fill] * segment.size)
        for segment in config.segments
        if segment.kind in {"prg", "chr"}
    }

    for item in items:
        if isinstance(item, SegmentDirective):
            current_segment = config.segment_named(item.name)
            continue
        if current_segment is None:
            raise AssemblerError(f"line {item.line}: no active segment")
        if isinstance(item, Label):
            continue

        offset = offsets[current_segment.name]
        if isinstance(item, DataDirective):
            data = encode_data_directive(item, symbols)
        elif isinstance(item, ReserveDirective):
            count = eval_expr(item.count_expr, symbols)
            if count < 0:
                raise AssemblerError(f"negative .res count at line {item.line}")
            fill = eval_expr(item.fill_expr, symbols) if item.fill_expr is not None else current_segment.fill
            data = bytes([fill & 0xFF] * count)
        else:
            data = encode_instruction(item, symbols, current_segment.start + offset)

        offsets[current_segment.name] += len(data)
        if current_segment.kind in {"prg", "chr"}:
            target = segment_bytes[current_segment.name]
            target[offset : offset + len(data)] = data

    header = build_ines_header(config)
    prg = bytearray([0x00] * config.ines.prg_rom_size)
    chr_rom = bytearray([0x00] * config.ines.chr_rom_size)
    prg_written = [False] * len(prg)
    chr_written = [False] * len(chr_rom)

    for segment in config.segments:
        if segment.kind == "ram":
            continue
        payload = segment_bytes[segment.name]
        if segment.kind == "prg":
            write_segment_payload(segment, payload, prg, prg_written, config.ines.prg_rom_size)
        else:
            write_segment_payload(segment, payload, chr_rom, chr_written, config.ines.chr_rom_size)

    return bytes(header + prg + chr_rom)


def write_segment_payload(
    segment: SegmentConfig,
    payload: bytearray,
    target: bytearray,
    written: list[bool],
    total_size: int,
) -> None:
    assert segment.file_offset is not None
    end = segment.file_offset + len(payload)
    if end > total_size:
        raise AssemblerError(
            f"segment {segment.name!r} exceeds its target region: "
            f"offset {segment.file_offset} + size {len(payload)} > {total_size}"
        )
    for index in range(segment.file_offset, end):
        if written[index]:
            raise AssemblerError(f"segment {segment.name!r} overlaps another output segment")
        written[index] = True
    target[segment.file_offset:end] = payload


def encode_data_directive(item: DataDirective, symbols: dict[str, int]) -> bytes:
    if item.kind == "byte":
        return bytes(eval_expr(value, symbols) & 0xFF for value in item.values)
    if item.kind == "word":
        output = bytearray()
        for value in item.values:
            resolved = eval_expr(value, symbols) & 0xFFFF
            output.extend((resolved & 0xFF, (resolved >> 8) & 0xFF))
        return bytes(output)
    raise AssemblerError(f"unknown data directive {item.kind!r}")


def encode_instruction(item: Instruction, symbols: dict[str, int], address: int) -> bytes:
    operand = item.operand
    mnemonic = item.mnemonic

    if operand is None:
        opcode = IMPLIED_OPS.get(mnemonic)
        if opcode is None:
            raise AssemblerError(f"unsupported implied instruction {mnemonic!r} at line {item.line}")
        return bytes([opcode])

    if mnemonic in RELATIVE_OPS:
        target = eval_expr(operand, symbols)
        delta = target - (address + 2)
        if not -128 <= delta <= 127:
            raise AssemblerError(f"branch out of range at line {item.line}")
        return bytes([RELATIVE_OPS[mnemonic], delta & 0xFF])

    if operand.startswith("#"):
        opcode = IMMEDIATE_OPS.get(mnemonic)
        if opcode is None:
            raise AssemblerError(f"unsupported immediate instruction {mnemonic!r} at line {item.line}")
        value = eval_expr(operand[1:], symbols)
        return bytes([opcode, value & 0xFF])

    indexed_operand = parse_indexed_operand(operand)
    if indexed_operand is not None:
        base_expr, register = indexed_operand
        if register != "x":
            raise AssemblerError(f"unsupported indexed register {register!r} at line {item.line}")
        opcode = ABSOLUTE_X_OPS.get(mnemonic)
        if opcode is None:
            raise AssemblerError(f"unsupported absolute,x instruction {mnemonic!r} at line {item.line}")
        value = eval_expr(base_expr, symbols)
        return bytes([opcode, value & 0xFF, (value >> 8) & 0xFF])

    opcode = ABSOLUTE_OPS.get(mnemonic)
    if opcode is None:
        raise AssemblerError(f"unsupported absolute instruction {mnemonic!r} at line {item.line}")
    value = eval_expr(operand, symbols)
    return bytes([opcode, value & 0xFF, (value >> 8) & 0xFF])


def item_size(item: AsmItem, segment: SegmentConfig) -> int:
    if isinstance(item, (SegmentDirective, Label)):
        return 0
    if isinstance(item, DataDirective):
        return len(item.values) if item.kind == "byte" else len(item.values) * 2
    if isinstance(item, ReserveDirective):
        count = eval_expr(item.count_expr, {})
        if count < 0:
            raise AssemblerError(f"negative .res count at line {item.line}")
        return count
    if isinstance(item, Instruction):
        if item.operand is None:
            if item.mnemonic not in IMPLIED_OPS:
                raise AssemblerError(f"unsupported implied instruction {item.mnemonic!r} at line {item.line}")
            return 1
        if item.mnemonic in RELATIVE_OPS:
            return 2
        if item.operand.startswith("#"):
            if item.mnemonic not in IMMEDIATE_OPS:
                raise AssemblerError(f"unsupported immediate instruction {item.mnemonic!r} at line {item.line}")
            return 2
        indexed_operand = parse_indexed_operand(item.operand)
        if indexed_operand is not None:
            _, register = indexed_operand
            if register != "x":
                raise AssemblerError(f"unsupported indexed register {register!r} at line {item.line}")
            if item.mnemonic not in ABSOLUTE_X_OPS:
                raise AssemblerError(f"unsupported absolute,x instruction {item.mnemonic!r} at line {item.line}")
            if segment.kind == "ram":
                raise AssemblerError(f"cannot place instructions in ram segment {segment.name!r} at line {item.line}")
            return 3
        if item.mnemonic not in ABSOLUTE_OPS:
            raise AssemblerError(f"unsupported absolute instruction {item.mnemonic!r} at line {item.line}")
        if segment.kind == "ram":
            raise AssemblerError(f"cannot place instructions in ram segment {segment.name!r} at line {item.line}")
        return 3
    raise AssemblerError(f"unknown item {item!r}")


def build_ines_header(config: ProjectConfig) -> bytearray:
    prg_units = config.ines.prg_rom_size // 0x4000
    chr_units = config.ines.chr_rom_size // 0x2000
    flags6 = 0
    if config.ines.mirroring == "vertical":
        flags6 |= 0x01
    if config.ines.battery:
        flags6 |= 0x02
    if config.ines.four_screen:
        flags6 |= 0x08
    flags6 |= (config.ines.mapper & 0x0F) << 4
    flags7 = config.ines.mapper & 0xF0
    return bytearray(
        [
            0x4E,
            0x45,
            0x53,
            0x1A,
            prg_units & 0xFF,
            chr_units & 0xFF,
            flags6 & 0xFF,
            flags7 & 0xFF,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
            0x00,
        ]
    )


def eval_expr(expr: str | None, symbols: dict[str, int]) -> int:
    if expr is None:
        raise AssemblerError("missing expression")
    tokens = TOKEN_RE.findall(expr.replace(" ", ""))
    if not tokens:
        raise AssemblerError(f"invalid expression {expr!r}")

    expecting_term = True
    sign = 1
    value = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if expecting_term:
            if token == "+":
                sign = 1
                index += 1
                continue
            if token == "-":
                sign = -1
                index += 1
                continue
            value += sign * resolve_term(token, symbols)
            sign = 1
            expecting_term = False
            index += 1
            continue
        if token not in {"+", "-"}:
            raise AssemblerError(f"invalid expression {expr!r}")
        sign = 1 if token == "+" else -1
        expecting_term = True
        index += 1

    if expecting_term:
        raise AssemblerError(f"trailing operator in expression {expr!r}")
    return value


def resolve_term(token: str, symbols: dict[str, int]) -> int:
    if token.lower().startswith("0x"):
        return int(token, 16)
    if token.startswith("$"):
        return int(token[1:], 16)
    if token.isdigit():
        return int(token, 10)
    if token in symbols:
        return symbols[token]
    raise AssemblerError(f"unknown symbol {token!r}")


def split_csv(text: str) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_indexed_operand(operand: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"(.+),\s*([A-Za-z])", operand)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).lower()
