volatile u8 PPUCTRL @ 0x2000 = 0x80;
volatile u8 PPUMASK @ 0x2001 = 0x1e;
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
