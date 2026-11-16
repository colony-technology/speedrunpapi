/* t3_rv32.c: the t3 stream machine of t3.c, one lane, freestanding, for a core without a multiplier (rv32i).
 * No libc, no threads, no vector types. The same words: op << 14 | i, op 0 ADD, 1 SUB, 2 STEP, 3 EMIT.
 *   ADD i   s = s + x[i]
 *   SUB i   s = s - x[i]
 *   STEP    acc = acc + acc; acc = acc + s; s = 0
 *   EMIT    STEP, then y[row] = acc; acc = 0; row = row + 1
 * s is 32 bits, acc 64 bits (on rv32i two registers: add, sltu for the carry, add). Returns the words run.
 *
 * Build (Homebrew LLVM 23, no emulator here):
 *   clang --target=riscv32-unknown-elf -march=rv32i -mabi=ilp32 -O2 -ffreestanding -nostdlib -c t3_rv32.c
 *   python t3_nomul.py t3_rv32.o
 */
#include <stdint.h>

uint32_t t3_rv32_run(const uint16_t *p, int32_t rows, const int32_t *x, int64_t *y) {
    int32_t s = 0;
    int64_t acc = 0;
    uint32_t words = 0;
    while (rows > 0) {
        uint32_t w = *p++;
        uint32_t op = w >> 14;
        words += 1;
        if (op == 0u) {
            s += x[w & 0x3FFFu];
        } else if (op == 1u) {
            s -= x[w & 0x3FFFu];
        } else {
            acc = acc + acc;
            acc = acc + (int64_t)s;
            s = 0;
            if (op == 3u) {
                *y++ = acc;
                acc = 0;
                rows -= 1;
            }
        }
    }
    return words;
}
