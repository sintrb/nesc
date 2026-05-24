volatile u8 PPUCTRL @ 0x2000;
volatile u8 PPUMASK @ 0x2001;
volatile u8 PPUSTATUS @ 0x2002;
volatile u8 PPUSCROLL @ 0x2005;
volatile u8 PPUADDR @ 0x2006;
volatile u8 PPUDATA @ 0x2007;

u8 color = 0x01;
u8 phase = 0;

void wait_vblank(void) {
  while (PPUSTATUS < 0x80) {
  }
}

void write_backdrop(void) {
  PPUADDR = 0x3f;
  PPUADDR = 0x00;
  PPUDATA = color;
}

void next_color(void) {
  if (phase == 0) {
    color = 0x01;
    phase = 1;
    return;
  }
  if (phase == 1) {
    color = 0x16;
    phase = 2;
    return;
  }
  if (phase == 2) {
    color = 0x2a;
    phase = 3;
    return;
  }
  color = 0x30;
  phase = 0;
}

void delay_frames(void) {
  u8 wait = 0;
  while (wait < 15) {
    wait_vblank();
    wait = wait + 1;
  }
}

void reset(void) {
  PPUCTRL = 0x00;
  PPUMASK = 0x00;

  wait_vblank();
  wait_vblank();

  write_backdrop();
  PPUSCROLL = 0x00;
  PPUSCROLL = 0x00;
  PPUMASK = 0x08;

  while (1) {
    delay_frames();
    next_color();
    write_backdrop();
  }
}
