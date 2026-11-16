#!/bin/sh
# build.sh OUT_DIR: t3_token.c with main_rv32.c and start.S for rv32i (no M extension), bare metal on QEMU virt.
# Needs clang with the riscv32 target and ld.lld (Homebrew llvm and lld); then the scan for multipliers.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$HERE/out}
LLVM=${LLVM:-/opt/homebrew/opt/llvm/bin}
LLD=${LLD:-/opt/homebrew/bin/ld.lld}
PY=${PY:-python3}
mkdir -p "$OUT"
CF="--target=riscv32-unknown-elf -march=rv32i -mabi=ilp32 -O2 -fno-unroll-loops -ffreestanding -fno-builtin -nostdlib -mcmodel=medany -DLANES=1"
$LLVM/clang $CF -c "$HERE/start.S" -o "$OUT/start.o"
$LLVM/clang $CF -c "$HERE/../t3_token.c" -o "$OUT/t3_token.o"
$LLVM/clang $CF -c "$HERE/main_rv32.c" -o "$OUT/main_rv32.o"
$LLD -T "$HERE/virt.ld" --no-relax "$OUT/start.o" "$OUT/t3_token.o" "$OUT/main_rv32.o" -o "$OUT/t3_rv32.elf"
OBJDUMP=$LLVM/llvm-objdump $PY -I "$HERE/../t3_nomul.py" "$OUT/t3_rv32.elf"
