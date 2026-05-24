from __future__ import annotations

import unittest
from pathlib import Path
import subprocess
import tempfile

from nesc.assembler import assemble_text
from nesc.compiler import compile_source
from nesc.config import load_project_config


SOURCE = """
volatile u8 PPUCTRL @ 0x2000 = 0x80;
volatile u8 PPUMASK @ 0x2001 = 0x1e;
u8 frame = 0;

void tick(void) {
  frame = frame + 1;
}

void reset(void) {
  while (1) {
    tick();
  }
}

void irq(void) {
  return;
}
"""


class EndToEndTests(unittest.TestCase):
    def test_compile_and_assemble(self) -> None:
        config = load_project_config(Path("configs/nrom32.json"))
        assembly = compile_source(SOURCE)
        image = assemble_text(assembly, config)

        self.assertEqual(image[:4], b"NES\x1a")
        self.assertEqual(image[4], 2)
        self.assertEqual(image[5], 1)
        prg = image[16 : 16 + 32768]
        reset_vector = prg[-4:-2]
        self.assertEqual(reset_vector, bytes([0x00, 0x80]))

    def test_uxrom_fixed_bank_layout(self) -> None:
        config = load_project_config(Path("configs/uxrom_fixed.json"))
        assembly = compile_source(SOURCE)
        image = assemble_text(assembly, config)

        self.assertEqual(image[:4], b"NES\x1a")
        self.assertEqual(image[4], 8)
        self.assertEqual(image[6] >> 4, 2)
        prg = image[16 : 16 + 131072]
        self.assertEqual(prg[-4:-2], bytes([0x00, 0xc0]))

    def test_color_cycle_example_builds(self) -> None:
        config = load_project_config(Path("configs/nrom32.json"))
        source = Path("examples/color_cycle.c").read_text(encoding="utf-8")
        assembly = compile_source(source)
        image = assemble_text(assembly, config)

        self.assertEqual(image[:4], b"NES\x1a")
        self.assertEqual(len(image), 16 + 32768 + 8192)
        self.assertIn("PPUADDR", source)

    def test_build_accepts_append_asm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            source_path = tmpdir / "mini.c"
            extra_path = tmpdir / "extra.asm"
            output_path = tmpdir / "mini.nes"
            asm_out_path = tmpdir / "mini.asm"

            source_path.write_text(
                """
void reset(void) {
}
""",
                encoding="utf-8",
            )
            extra_path.write_text(
                """
.segment "CHR"
  .byte 1, 2, 3, 4
  .res 8192 - 4, 0
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python3",
                    "-m",
                    "nesc",
                    "build",
                    str(source_path),
                    "--config",
                    "configs/nrom32.json",
                    "--append-asm",
                    str(extra_path),
                    "-o",
                    str(output_path),
                    "--asm-out",
                    str(asm_out_path),
                ],
                cwd=Path.cwd(),
                check=True,
            )

            image = output_path.read_bytes()
            self.assertEqual(image[:4], b"NES\x1a")
            self.assertEqual(image[16 + 32768 : 16 + 32768 + 4], bytes([1, 2, 3, 4]))

    def test_tetris_example_builds(self) -> None:
        config = load_project_config(Path("configs/nrom32.json"))
        assembly = compile_source(Path("examples/tetris.c").read_text(encoding="utf-8"))
        assembly += "\n" + Path("examples/tetris_chr.asm").read_text(encoding="utf-8")
        image = assemble_text(assembly, config)

        self.assertEqual(image[:4], b"NES\x1a")
        self.assertEqual(len(image), 16 + 32768 + 8192)


if __name__ == "__main__":
    unittest.main()
