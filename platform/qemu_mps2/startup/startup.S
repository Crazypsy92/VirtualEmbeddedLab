.syntax unified
.cpu cortex-m3
.thumb
.section .isr_vector,"a",%progbits
.balign 256
.global vector_table
vector_table:
.word _stack_top
.word Reset_Handler
.word Default_Handler
.word HardFault_Handler
.word Default_Handler, Default_Handler, Default_Handler
.word 0, 0, 0, 0
.word SVC_Handler
.word Default_Handler
.word 0
.word PendSV_Handler
.word SysTick_Handler
.rept 32
.word Default_Handler
.endr
.section .text.Reset_Handler,"ax",%progbits
.global Reset_Handler
.type Reset_Handler,%function
.thumb_func
Reset_Handler:
ldr r0, =_sidata
ldr r1, =_sdata
ldr r2, =_edata
1: cmp r1, r2
bcs 2f
ldr r3, [r0], #4
str r3, [r1], #4
b 1b
2: ldr r1, =_sbss
ldr r2, =_ebss
movs r3, #0
3: cmp r1, r2
bcs 4f
str r3, [r1], #4
b 3b
4: bl main
b Default_Handler
.size Reset_Handler, .-Reset_Handler

/* Pass the hardware basic frame and EXC_RETURN without a C prologue. */
.macro EXCEPTION name, target
.section .text.\name,"ax",%progbits
.global \name
.type \name,%function
.thumb_func
\name:
tst lr, #4
ite eq
mrseq r0, msp
mrsne r0, psp
mov r1, lr
b \target
.size \name, .-\name
.endm
EXCEPTION SVC_Handler, svc_dispatch
EXCEPTION PendSV_Handler, pendsv_dispatch

.section .text.svc_psp_call,"ax",%progbits
.global svc_psp_call
.type svc_psp_call,%function
.thumb_func
svc_psp_call:
msr psp, r1
movs r2, #2
msr control, r2
isb
svc #42
movs r2, #0
msr control, r2
isb
bx lr
.size svc_psp_call, .-svc_psp_call
.section .note.GNU-stack,"",%progbits
