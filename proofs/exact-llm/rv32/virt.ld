/* virt.ld: QEMU virt, RAM from 0x80000000; the image, then bss, then the arena and the stack (128 MB in all) */
OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x80000000, LENGTH = 128M }
SECTIONS {
    .text : { *(.text.start) *(.text .text.*) } > RAM
    .rodata : { *(.rodata .rodata.* .srodata .srodata.*) } > RAM
    .data : { *(.data .data.* .sdata .sdata.*) } > RAM
    .bss (NOLOAD) : { __bss_start = .; *(.bss .bss.* .sbss .sbss.* COMMON) __bss_end = .; } > RAM
    . = ALIGN(16);
    __arena_start = .;
    __stack_top = ORIGIN(RAM) + LENGTH(RAM);
    __arena_end = __stack_top - 0x100000;          /* 1 MB of stack */
}
