from __future__ import annotations

import argparse
from pathlib import Path

from .assembler import assemble_text
from .compiler import compile_source
from .config import load_project_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="nesc", description="Compile a small C subset into NES ROM images.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile", help="compile C subset source to 6502 assembly")
    compile_parser.add_argument("source", type=Path)
    compile_parser.add_argument("-o", "--output", required=True, type=Path)

    assemble_parser = subparsers.add_parser("assemble", help="assemble 6502 assembly into a .nes image")
    assemble_parser.add_argument("source", type=Path)
    assemble_parser.add_argument("--config", required=True, type=Path)
    assemble_parser.add_argument("-o", "--output", required=True, type=Path)
    assemble_parser.add_argument(
        "--append-asm",
        action="append",
        default=[],
        type=Path,
        help="append additional assembly sources before assembling",
    )

    build_parser = subparsers.add_parser("build", help="compile and assemble in one step")
    build_parser.add_argument("source", type=Path)
    build_parser.add_argument("--config", required=True, type=Path)
    build_parser.add_argument("-o", "--output", required=True, type=Path)
    build_parser.add_argument("--asm-out", type=Path, help="optionally keep the generated assembly")
    build_parser.add_argument(
        "--append-asm",
        action="append",
        default=[],
        type=Path,
        help="append additional assembly sources after the generated assembly",
    )

    args = parser.parse_args()

    if args.command == "compile":
        assembly = compile_source(args.source.read_text(encoding="utf-8"))
        args.output.write_text(assembly, encoding="utf-8")
        return

    config = load_project_config(args.config)
    if args.command == "assemble":
        assembly = args.source.read_text(encoding="utf-8")
        for path in args.append_asm:
            assembly += "\n" + path.read_text(encoding="utf-8")
        image = assemble_text(assembly, config)
        args.output.write_bytes(image)
        return

    assembly = compile_source(args.source.read_text(encoding="utf-8"))
    for path in args.append_asm:
        assembly += "\n" + path.read_text(encoding="utf-8")
    if args.asm_out is not None:
        args.asm_out.write_text(assembly, encoding="utf-8")
    image = assemble_text(assembly, config)
    args.output.write_bytes(image)


if __name__ == "__main__":
    main()
