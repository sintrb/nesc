from __future__ import annotations

import unittest
from pathlib import Path

from nesc.assembler import assemble_text
from nesc.config import load_project_config


class AssemblerTests(unittest.TestCase):
    def test_assembler_emits_valid_ines_image(self) -> None:
        config = load_project_config(Path("configs/nrom32.json"))
        source = """
.segment "CODE"
start:
  sei
  cld
  jmp start

.segment "VECTORS"
  .word start, start, start
"""
        image = assemble_text(source, config)

        self.assertEqual(image[:4], b"NES\x1a")
        self.assertEqual(len(image), 16 + 32768 + 8192)
        prg = image[16 : 16 + 32768]
        self.assertEqual(prg[-6:], bytes([0x00, 0x80, 0x00, 0x80, 0x00, 0x80]))

    def test_assembler_supports_absolute_x_addressing(self) -> None:
        config = load_project_config(Path("configs/nrom32.json"))
        source = """
.segment "CODE"
table:
  .byte 1, 2, 3, 4
start:
  ldx #0x02
  lda table, x
  sta 0x0200, x
  jmp start

.segment "VECTORS"
  .word start, start, start
"""
        image = assemble_text(source, config)
        prg = image[16 : 16 + 32768]

        self.assertIn(bytes([0xA2, 0x02, 0xBD]), prg)


if __name__ == "__main__":
    unittest.main()
