from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    pass


def parse_number(value: int | str) -> int:
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise ConfigError(f"cannot parse numeric value from {value!r}")

    text = value.strip().lower()
    if text.startswith("0x"):
        return int(text, 16)
    if text.startswith("$"):
        return int(text[1:], 16)
    return int(text, 10)


@dataclass(frozen=True)
class InesConfig:
    mapper: int
    mirroring: str
    battery: bool
    four_screen: bool
    prg_rom_size: int
    chr_rom_size: int


@dataclass(frozen=True)
class SegmentConfig:
    name: str
    kind: str
    start: int
    size: int
    file_offset: int | None
    fill: int


@dataclass(frozen=True)
class ProjectConfig:
    ines: InesConfig
    segments: tuple[SegmentConfig, ...]

    def segment_named(self, name: str) -> SegmentConfig:
        for segment in self.segments:
            if segment.name == name:
                return segment
        raise ConfigError(f"segment {name!r} is not defined in config")


def load_project_config(path: str | Path) -> ProjectConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    ines_raw = data.get("ines")
    if not isinstance(ines_raw, dict):
        raise ConfigError("config is missing an 'ines' object")

    ines = InesConfig(
        mapper=parse_number(ines_raw.get("mapper", 0)),
        mirroring=str(ines_raw.get("mirroring", "horizontal")).lower(),
        battery=bool(ines_raw.get("battery", False)),
        four_screen=bool(ines_raw.get("four_screen", False)),
        prg_rom_size=parse_number(ines_raw.get("prg_rom_size", 0)),
        chr_rom_size=parse_number(ines_raw.get("chr_rom_size", 0)),
    )

    if ines.prg_rom_size % 0x4000 != 0:
        raise ConfigError("prg_rom_size must be a multiple of 16384 bytes")
    if ines.chr_rom_size % 0x2000 != 0:
        raise ConfigError("chr_rom_size must be a multiple of 8192 bytes")
    if ines.mirroring not in {"horizontal", "vertical"}:
        raise ConfigError("mirroring must be 'horizontal' or 'vertical'")

    segment_list = data.get("segments")
    if not isinstance(segment_list, list) or not segment_list:
        raise ConfigError("config must define a non-empty 'segments' array")

    segments: list[SegmentConfig] = []
    seen_names: set[str] = set()
    for item in segment_list:
        if not isinstance(item, dict):
            raise ConfigError("each segment entry must be an object")

        name = str(item["name"])
        if name in seen_names:
            raise ConfigError(f"duplicate segment name {name!r}")
        seen_names.add(name)

        kind = str(item["kind"]).lower()
        if kind not in {"ram", "prg", "chr"}:
            raise ConfigError(f"unsupported segment kind {kind!r}")

        file_offset_raw = item.get("file_offset")
        file_offset = None if file_offset_raw is None else parse_number(file_offset_raw)
        if kind == "ram" and file_offset is not None:
            raise ConfigError(f"ram segment {name!r} must not define file_offset")
        if kind in {"prg", "chr"} and file_offset is None:
            raise ConfigError(f"segment {name!r} must define file_offset")

        segment = SegmentConfig(
            name=name,
            kind=kind,
            start=parse_number(item["start"]),
            size=parse_number(item["size"]),
            file_offset=file_offset,
            fill=parse_number(item.get("fill", 0)) & 0xFF,
        )
        if segment.size < 0:
            raise ConfigError(f"segment {name!r} has a negative size")
        segments.append(segment)

    return ProjectConfig(ines=ines, segments=tuple(segments))
