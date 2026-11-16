# start.S: rv32i bare metal on QEMU virt (RAM at 0x80000000). Stack at the top of the image's RAM, bss cleared by
# main, then main(); its return value leaves through semihosting SYS_EXIT.
    .section .text.start
    .globl _start
_start:
    la sp, __stack_top
    call main
    mv a1, a0
    li a0, 0x18                 # SYS_EXIT
    li t0, 0x20026              # ADP_Stopped_ApplicationExit
    beqz a1, 1f
    li t0, 0x20023              # ADP_Stopped_InternalError
1:  mv a1, t0
    call t3_semihost
2:  j 2b

# t3_semihost(op, arg): the RISC-V semihosting call, three uncompressed instructions in one page
    .globl t3_semihost
    .balign 16
t3_semihost:
    .option push
    .option norvc
    slli x0, x0, 0x1f
    ebreak
    srai x0, x0, 7
    .option pop
    ret
