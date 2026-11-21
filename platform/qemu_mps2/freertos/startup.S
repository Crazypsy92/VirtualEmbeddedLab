.syntax unified
.cpu cortex-m3
.thumb
.section .isr_vector,"a",%progbits
.balign 256
.global vector_table
vector_table:
.word _stack_top, Reset_Handler, Default_Handler, HardFault_Handler
.word Default_Handler, Default_Handler, Default_Handler
.word 0,0,0,0
.word SVC_Handler, Default_Handler, 0, PendSV_Handler, SysTick_Handler
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
1: cmp r1,r2
bcs 2f
ldr r3,[r0],#4
str r3,[r1],#4
b 1b
2: ldr r1,=_sbss
ldr r2,=_ebss
movs r3,#0
3: cmp r1,r2
bcs 4f
str r3,[r1],#4
b 3b
4: bl main
b Default_Handler
.size Reset_Handler,.-Reset_Handler

/* ABI-preserving register canaries span a genuine blocking context switch. */
.section .text.context_roundtrip,"ax",%progbits
.global context_roundtrip
.type context_roundtrip,%function
.thumb_func
context_roundtrip:
push {r4-r8,lr}
mov r7,r0
ldr r4,=0x44444444
add r4,r7
ldr r5,=0x55555555
add r5,r7
mov r8,sp
movs r0,#3
bl vTaskDelay
ldr r0,=0x44444444
add r0,r7
cmp r0,r4
bne 5f
ldr r0,=0x55555555
add r0,r7
cmp r0,r5
bne 5f
mov r0,sp
cmp r0,r8
bne 5f
movs r0,#0
b 6f
5: movs r0,#1
6: pop {r4-r8,pc}
.size context_roundtrip,.-context_roundtrip
.section .note.GNU-stack,"",%progbits
