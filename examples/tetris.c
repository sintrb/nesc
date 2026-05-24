volatile u8 PPUCTRL @ 0x2000;
volatile u8 PPUMASK @ 0x2001;
volatile u8 PPUSTATUS @ 0x2002;
volatile u8 PPUSCROLL @ 0x2005;
volatile u8 PPUADDR @ 0x2006;
volatile u8 PPUDATA @ 0x2007;
volatile u8 JOY1 @ 0x4016;

u8 board[200];

u8 palette_data[32] = {
  0x0f, 0x16, 0x27, 0x30,
  0x0f, 0x11, 0x21, 0x30,
  0x0f, 0x06, 0x17, 0x28,
  0x0f, 0x09, 0x19, 0x29,
  0x0f, 0x16, 0x27, 0x30,
  0x0f, 0x11, 0x21, 0x30,
  0x0f, 0x06, 0x17, 0x28,
  0x0f, 0x09, 0x19, 0x29
};

u8 screen_row_lo[30] = {
  0, 32, 64, 96, 128, 160, 192, 224, 0, 32,
  64, 96, 128, 160, 192, 224, 0, 32, 64, 96,
  128, 160, 192, 224, 0, 32, 64, 96, 128, 160
};

u8 screen_row_hi[30] = {
  32, 32, 32, 32, 32, 32, 32, 32, 33, 33,
  33, 33, 33, 33, 33, 33, 34, 34, 34, 34,
  34, 34, 34, 34, 35, 35, 35, 35, 35, 35
};

u8 frame_row_lo[22] = {
  105, 137, 169, 201, 233, 9, 41, 73, 105, 137, 169,
  201, 233, 9, 41, 73, 105, 137, 169, 201, 233, 9
};

u8 frame_row_hi[22] = {
  32, 32, 32, 32, 32, 33, 33, 33, 33, 33, 33,
  33, 33, 34, 34, 34, 34, 34, 34, 34, 34, 35
};

u8 board_row_lo[20] = {
  138, 170, 202, 234, 10, 42, 74, 106, 138, 170,
  202, 234, 10, 42, 74, 106, 138, 170, 202, 234
};

u8 board_row_hi[20] = {
  32, 32, 32, 32, 33, 33, 33, 33, 33, 33,
  33, 33, 34, 34, 34, 34, 34, 34, 34, 34
};

u8 row_base[20] = {
  0, 10, 20, 30, 40, 50, 60, 70, 80, 90,
  100, 110, 120, 130, 140, 150, 160, 170, 180, 190
};

u8 type_base[7] = {0, 16, 32, 48, 64, 80, 96};
u8 rot_base[4] = {0, 4, 8, 12};

u8 piece_dx[112] = {
  0, 1, 2, 3, 2, 2, 2, 2, 0, 1, 2, 3, 1, 1, 1, 1,
  1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2, 1, 2,
  1, 0, 1, 2, 1, 1, 2, 1, 0, 1, 2, 1, 1, 0, 1, 1,
  1, 2, 0, 1, 1, 1, 2, 2, 1, 2, 0, 1, 0, 0, 1, 1,
  0, 1, 1, 2, 2, 1, 2, 1, 0, 1, 1, 2, 1, 0, 1, 0,
  0, 0, 1, 2, 1, 2, 1, 1, 0, 1, 2, 2, 1, 1, 0, 1,
  2, 0, 1, 2, 1, 1, 1, 2, 0, 1, 2, 0, 0, 1, 1, 1
};

u8 piece_dy[112] = {
  1, 1, 1, 1, 0, 1, 2, 3, 2, 2, 2, 2, 0, 1, 2, 3,
  0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1, 1,
  0, 1, 1, 1, 0, 1, 1, 2, 1, 1, 1, 2, 0, 1, 1, 2,
  0, 0, 1, 1, 0, 1, 1, 2, 1, 1, 2, 2, 0, 1, 1, 2,
  0, 0, 1, 1, 0, 1, 1, 2, 1, 1, 2, 2, 0, 1, 1, 2,
  0, 1, 1, 1, 0, 0, 1, 2, 1, 1, 1, 2, 0, 1, 2, 2,
  0, 1, 1, 1, 0, 1, 2, 2, 1, 1, 1, 2, 0, 0, 1, 2
};

u8 piece_x = 3;
u8 piece_y = 0;
u8 piece_rot = 0;
u8 piece_type = 0;
u8 next_piece = 0;
u8 game_over = 0;
u8 fall_timer = 0;
u8 redraw = 0;

u8 btn_a = 0;
u8 btn_b = 0;
u8 btn_select = 0;
u8 btn_start = 0;
u8 btn_up = 0;
u8 btn_down = 0;
u8 btn_left = 0;
u8 btn_right = 0;

u8 prev_a = 0;
u8 prev_b = 0;
u8 prev_select = 0;
u8 prev_start = 0;
u8 prev_up = 0;
u8 prev_down = 0;
u8 prev_left = 0;
u8 prev_right = 0;

void wait_vblank(void) {
  while (PPUSTATUS < 0x80) {
  }
}

void set_ppu_addr(u8 hi, u8 lo) {
  u8 latch = PPUSTATUS;
  PPUADDR = hi;
  PPUADDR = lo;
  latch = latch;
}

void write_palettes(void) {
  u8 i = 0;
  set_ppu_addr(0x3f, 0x00);
  while (i < 32) {
    PPUDATA = palette_data[i];
    i = i + 1;
  }
}

void clear_nametable(void) {
  u8 row = 0;
  u8 col = 0;
  while (row < 30) {
    set_ppu_addr(screen_row_hi[row], screen_row_lo[row]);
    col = 0;
    while (col < 32) {
      PPUDATA = 0;
      col = col + 1;
    }
    row = row + 1;
  }
}

void clear_attribute_table(void) {
  u8 i = 0;
  set_ppu_addr(0x23, 0xc0);
  while (i < 64) {
    PPUDATA = 0;
    i = i + 1;
  }
}

void draw_frame(void) {
  u8 row = 0;
  u8 col = 0;
  while (row < 22) {
    set_ppu_addr(frame_row_hi[row], frame_row_lo[row]);
    if (row == 0) {
      col = 0;
      while (col < 12) {
        PPUDATA = 8;
        col = col + 1;
      }
    } else {
      if (row == 21) {
        col = 0;
        while (col < 12) {
          PPUDATA = 8;
          col = col + 1;
        }
      } else {
        PPUDATA = 8;
        col = 1;
        while (col < 11) {
          PPUDATA = 0;
          col = col + 1;
        }
        PPUDATA = 8;
      }
    }
    row = row + 1;
  }
}

void draw_board(void) {
  u8 row = 0;
  u8 col = 0;
  u8 index = 0;
  while (row < 20) {
    set_ppu_addr(board_row_hi[row], board_row_lo[row]);
    col = 0;
    while (col < 10) {
      index = row_base[row] + col;
      PPUDATA = board[index];
      col = col + 1;
    }
    row = row + 1;
  }
}

void refresh_playfield(void) {
  PPUMASK = 0x00;
  draw_board();
  if (game_over == 0) {
    draw_active_piece();
  }
  PPUSCROLL = 0x00;
  PPUSCROLL = 0x00;
  PPUMASK = 0x0a;
}

void clear_board(void) {
  u8 index = 0;
  while (index < 200) {
    board[index] = 0;
    index = index + 1;
  }
}

void read_controller(void) {
  prev_a = btn_a;
  prev_b = btn_b;
  prev_select = btn_select;
  prev_start = btn_start;
  prev_up = btn_up;
  prev_down = btn_down;
  prev_left = btn_left;
  prev_right = btn_right;

  JOY1 = 0x01;
  JOY1 = 0x00;

  btn_a = JOY1 & 0x01;
  btn_b = JOY1 & 0x01;
  btn_select = JOY1 & 0x01;
  btn_start = JOY1 & 0x01;
  btn_up = JOY1 & 0x01;
  btn_down = JOY1 & 0x01;
  btn_left = JOY1 & 0x01;
  btn_right = JOY1 & 0x01;
}

void draw_active_piece(void) {
  u8 i = 0;
  u8 offset = 0;
  u8 cell_x = 0;
  u8 cell_y = 0;

  while (i < 4) {
    offset = type_base[piece_type] + rot_base[piece_rot];
    offset = offset + i;
    cell_x = piece_x + piece_dx[offset];
    cell_y = piece_y + piece_dy[offset];
    set_ppu_addr(board_row_hi[cell_y], board_row_lo[cell_y] + cell_x);
    PPUDATA = 1;
    i = i + 1;
  }
}

u8 check_collision_at(u8 x, u8 y, u8 rot) {
  u8 i = 0;
  u8 offset = 0;
  u8 cell_x = 0;
  u8 cell_y = 0;
  u8 cell_index = 0;

  while (i < 4) {
    offset = type_base[piece_type] + rot_base[rot];
    offset = offset + i;
    cell_x = x + piece_dx[offset];
    if (cell_x >= 10) {
      return 1;
    }
    cell_y = y + piece_dy[offset];
    if (cell_y >= 20) {
      return 1;
    }
    cell_index = row_base[cell_y] + cell_x;
    if (board[cell_index] != 0) {
      return 1;
    }
    i = i + 1;
  }
  return 0;
}

void spawn_piece(void) {
  piece_type = next_piece;
  next_piece = next_piece + 1;
  if (next_piece >= 7) {
    next_piece = 0;
  }
  piece_rot = 0;
  piece_x = 3;
  piece_y = 0;
  fall_timer = 0;
  if (check_collision_at(piece_x, piece_y, piece_rot) != 0) {
    game_over = 1;
  }
  redraw = 1;
}

void lock_piece(void) {
  u8 i = 0;
  u8 offset = 0;
  u8 cell_x = 0;
  u8 cell_y = 0;
  u8 cell_index = 0;
  u8 tile = 1;

  while (i < 4) {
    offset = type_base[piece_type] + rot_base[piece_rot];
    offset = offset + i;
    cell_x = piece_x + piece_dx[offset];
    cell_y = piece_y + piece_dy[offset];
    cell_index = row_base[cell_y] + cell_x;
    board[cell_index] = tile;
    i = i + 1;
  }
}

void clear_lines(void) {
  u8 row = 19;
  u8 col = 0;
  u8 full = 0;
  u8 dst_index = 0;
  u8 src_index = 0;
  u8 src = 0;

  while (row < 20) {
    full = 1;
    col = 0;
    while (col < 10) {
      dst_index = row_base[row] + col;
      if (board[dst_index] == 0) {
        full = 0;
      }
      col = col + 1;
    }

    if (full != 0) {
      src = row;
      while (src > 0) {
        col = 0;
        while (col < 10) {
          dst_index = row_base[src] + col;
          src_index = row_base[src - 1] + col;
          board[dst_index] = board[src_index];
          col = col + 1;
        }
        src = src - 1;
      }
      col = 0;
      while (col < 10) {
        board[col] = 0;
        col = col + 1;
      }
      row = row + 1;
    }

    if (row == 0) {
      row = 255;
    } else {
      row = row - 1;
    }
  }
}

void step_piece_down(void) {
  if (check_collision_at(piece_x, piece_y + 1, piece_rot) != 0) {
    lock_piece();
    clear_lines();
    spawn_piece();
  } else {
    piece_y = piece_y + 1;
    redraw = 1;
  }
}

void try_move_left(void) {
  if (check_collision_at(piece_x - 1, piece_y, piece_rot) == 0) {
    piece_x = piece_x - 1;
    redraw = 1;
  }
}

void try_move_right(void) {
  if (check_collision_at(piece_x + 1, piece_y, piece_rot) == 0) {
    piece_x = piece_x + 1;
    redraw = 1;
  }
}

void try_rotate(void) {
  u8 next_rot = piece_rot + 1;
  if (next_rot >= 4) {
    next_rot = 0;
  }
  if (check_collision_at(piece_x, piece_y, next_rot) == 0) {
    piece_rot = next_rot;
    redraw = 1;
  }
}

void handle_input(void) {
  if (btn_left != 0) {
    if (prev_left == 0) {
      try_move_left();
    }
  }
  if (btn_right != 0) {
    if (prev_right == 0) {
      try_move_right();
    }
  }
  if (btn_a != 0) {
    if (prev_a == 0) {
      try_rotate();
    }
  }
}

void update_fall(void) {
  u8 threshold = 40;
  if (btn_down != 0) {
    threshold = 5;
  }
  fall_timer = fall_timer + 1;
  if (fall_timer >= threshold) {
    fall_timer = 0;
    step_piece_down();
  }
}

void init_video(void) {
  PPUCTRL = 0x00;
  PPUMASK = 0x00;
  wait_vblank();
  wait_vblank();
  write_palettes();
  clear_nametable();
  clear_attribute_table();
  draw_frame();
  draw_board();
  PPUSCROLL = 0x00;
  PPUSCROLL = 0x00;
  PPUCTRL = 0x00;
  PPUMASK = 0x0a;
}

void init_game(void) {
  clear_board();
  game_over = 0;
  next_piece = 0;
  fall_timer = 0;
  spawn_piece();
  redraw = 1;
  refresh_playfield();
  redraw = 0;
}

void reset(void) {
  init_video();
  init_game();

  while (1) {
    wait_vblank();
    read_controller();

    if (game_over != 0) {
      if (btn_start != 0) {
        if (prev_start == 0) {
          init_game();
        }
      }
    } else {
      handle_input();
      update_fall();
    }

    if (redraw != 0) {
      refresh_playfield();
      redraw = 0;
    }
  }
}
