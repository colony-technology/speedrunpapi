#!/bin/sh
# run.sh RUN_DIR: the rv32i kernel on QEMU virt, bare metal, one hart, 128 MB, UART on stdout, semihosting for
# t3k.blob and tokens.bin in RUN_DIR (prompt_host.py writes them), exact instruction counts (-icount shift=0).
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
RUN=$1
QEMU=${QEMU:-qemu-system-riscv32}
cd "$RUN"
exec $QEMU -machine virt -cpu rv32,m=false,a=false,f=false,d=false,c=false -smp 1 -m 128M -nographic -bios none \
  -icount shift=0 -semihosting-config enable=on,target=native -kernel "${ELF:-$HERE/out/t3_rv32.elf}"
