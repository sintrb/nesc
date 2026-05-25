# nesc

一个最小可用的 NES 定向工具链原型：

- `C 子集 -> 6502 汇编 -> .nes`
- 汇编器通过 JSON 配置控制 CPU MEMORY 布局和 `.nes` 文件内 PRG/CHR 布局
- 不依赖标准库
- 语法刻意收缩到更适合 6502 的范围

当前目标不是完整 C 编译器，而是先把一条清晰、可扩展的 MVP 路径打通。

## 当前支持的 C 子集

- 类型：`u8`、`void`
- 顶层：全局变量、全局 `u8` 数组、函数定义
- 语句：局部变量声明、赋值、`if`、`while`、`return`
- 表达式：常量、变量、数组下标读取、函数调用、`+ - & | ^ == != < <= > >= !`
- 内存映射寄存器：`volatile u8 PPUCTRL @ 0x2000;`
- 绝对地址数组：`u8 OAM[256] @ 0x0200;`
- 参数：支持 `u8` 参数，参数/局部变量按“每函数固定槽位”静态分配

当前有意不支持：

- 标准库
- 指针、结构体、递归
- 多参数函数
- 在临时值存活期间调用函数的复杂表达式，比如 `a = foo() + 1`

注：这里的“数组不支持”现在只剩下更完整的 C 数组语义不支持。
当前原型已经支持全局 `u8` 数组、常量大小声明、花括号初始化，以及 `array[index]` 读写。

当前原型里还做了两个偏工程化的简化：

- 普通全局变量在 `reset` 入口统一初始化
- 未显式初始化的局部变量在声明点按 `0` 写入
- 递归、可重入和中断重入安全不保证，由开发者自行规避
- 编译器只为从 `reset` / `nmi` / `irq` 可达的函数生成代码和分配函数槽位

## 汇编器方言

支持的指令和伪指令只覆盖当前编译器需要的范围：

- 伪指令：`.segment`、`.byte`、`.word`、`.res`
- 指令：`lda ldx ldy sta adc sbc and ora eor cmp`
- 流程：`jmp jsr rts rti beq bne bcc bcs`
- 状态：`sei cld clc sec tax tay txa tya txs inx iny dex dey nop`
- 寻址：支持 `absolute`、`immediate`、`absolute,x`

## 配置格式

示例见 [configs/nrom32.json](configs/nrom32.json) 和 [configs/uxrom_fixed.json](configs/uxrom_fixed.json)。

核心思路：

- `ram` 段只提供地址空间，不直接写入 ROM
- `prg` / `chr` 段通过 `file_offset` 指定它们在最终 `.nes` 文件有效载荷中的位置
- `mapper`、镜像方式、PRG/CHR 大小都由配置决定

这意味着你可以先从 NROM 起步，再逐步把布局迁移到固定尾银行、分银行 PRG 等 mapper 设计上。

## 用法

编译成汇编：

```bash
python3 -m nesc compile examples/counter.c -o build/counter.asm
```

把汇编组装成 `.nes`：

```bash
python3 -m nesc assemble build/counter.asm --config configs/nrom32.json -o build/counter.nes
```

一步构建：

```bash
python3 -m nesc build examples/counter.c --config configs/nrom32.json -o build/counter.nes --asm-out build/counter.asm
```

追加一段汇编再组装：

```bash
python3 -m nesc build examples/tetris.c --config configs/nrom32.json --append-asm examples/tetris_chr.asm -o build/tetris.nes --asm-out build/tetris.asm
```

## 示例源码

示例程序位于 [examples/counter.c](examples/counter.c)、[examples/color_cycle.c](examples/color_cycle.c) 和 [examples/tetris.c](examples/tetris.c)。

`counter.c` 演示了：

- memory-mapped I/O 寄存器声明
- 全局变量初始化
- 零参数函数调用
- `while (1)` 主循环

`color_cycle.c` 演示了：

- 轮询 `PPUSTATUS` 等待 vblank
- 向 `$3F00` 写入 universal background color
- 打开背景渲染后，让整屏颜色以肉眼可见的速度循环切换

`tetris.c` 演示了：

- 全局数组、数组初始化与 `array[index]` 读写
- 用背景层绘制固定棋盘，用 sprite 绘制当前下落方块
- 轮询手柄输入、碰撞检测、锁定方块与消行
- 通过 `--append-asm` 追加 CHR 图样汇编生成完整 `.nes`

## 测试

```bash
python3 -m unittest discover -s tests -v
```
