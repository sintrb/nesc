from __future__ import annotations

import unittest

from nesc.compiler import compile_source


SOURCE = """
volatile u8 PPUCTRL @ 0x2000 = 0x80;
volatile u8 PPUSTATUS @ 0x2002;
u8 frame = 0;

void tick(void) {
  frame = frame + 1;
}

void reset(void) {
  frame = 0;
  while (1) {
    tick();
  }
}

void nmi(void) {
  frame = frame + 1;
}
"""


class CompilerTests(unittest.TestCase):
    def test_compiler_emits_startup_and_vectors(self) -> None:
        assembly = compile_source(SOURCE)

        self.assertIn('.segment "ZEROPAGE"', assembly)
        self.assertIn('.segment "RAM"', assembly)
        self.assertIn('.segment "CODE"', assembly)
        self.assertIn('.segment "VECTORS"', assembly)
        self.assertIn("__reset_entry:", assembly)
        self.assertIn("jsr reset", assembly)
        self.assertIn("sta 0x2000", assembly)
        self.assertNotIn("sta 0x2002", assembly)
        self.assertIn("frame: .res 1", assembly)
        self.assertIn(".word __nmi_entry, __reset_entry, __irq_entry", assembly)

    def test_compiler_supports_global_arrays(self) -> None:
        source = """
u8 table[4] = {1, 2, 3, 4};
u8 index = 1;

void reset(void) {
  u8 value = table[index];
  table[2] = value + 1;
}
"""
        assembly = compile_source(source)

        self.assertIn("table: .res 4", assembly)
        self.assertIn("sta table+3", assembly)
        self.assertIn("lda table, x", assembly)
        self.assertIn("sta table, x", assembly)

    def test_compiler_supports_u8_parameters_and_discards_unused_functions(self) -> None:
        source = """
u8 add(u8 left, u8 right) {
  return left + right;
}

u8 dead(u8 value) {
  u8 local = value + 1;
  return local;
}

void reset(void) {
  u8 sum = add(2, 3);
}
"""
        assembly = compile_source(source)

        self.assertIn("__add_arg_left: .res 1", assembly)
        self.assertIn("__add_arg_right: .res 1", assembly)
        self.assertIn("sta __add_arg_left", assembly)
        self.assertIn("sta __add_arg_right", assembly)
        self.assertIn("add:", assembly)
        self.assertNotIn("__dead_arg_value", assembly)
        self.assertNotIn("dead:", assembly)


if __name__ == "__main__":
    unittest.main()
