#include "vel_runtime.h"
#include "queue.h"
#include "uart.h"

#define MMIO(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define UART0 0x40004000UL
#define TIMER0 0x40000000UL
#define MAX_TASKS 8U

static QueueHandle_t samples;
static TaskHandle_t producer_handle;
static uint32_t produced, consumed, commands;
static TaskStatus_t tasks[MAX_TASKS];

static void producer(void *arg)
{
    (void)arg;
    for (;;) {
        uint32_t next = produced + 1U;
        if (xQueueSend(samples, &next, 0) == pdPASS) {
            produced = next;
        }
        vTaskDelay(pdMS_TO_TICKS(140));
    }
}

static void consumer(void *arg)
{
    (void)arg;
    for (;;) {
        uint32_t sample;
        if (xQueueReceive(samples, &sample, portMAX_DELAY) == pdPASS) {
            consumed = sample;
        }
        vTaskDelay(pdMS_TO_TICKS(240));
    }
}

static void field(const char *name, uint32_t value)
{
    uart_putc(' ');
    uart_puts(name);
    uart_putc('=');
    uart_u32(value);
}

static void inspector(void *arg)
{
    (void)arg;
    for (;;) {
        /* Separate read and write paths for the UART. Reading DATA clears RXFULL. */
        if ((MMIO(UART0 + 4U) & 2U) != 0U) {
            uint32_t command = MMIO(UART0);
            if (command == 'p') {
                vTaskSuspend(producer_handle);
                ++commands;
            } else if (command == 'r') {
                vTaskResume(producer_handle);
                ++commands;
            }
        }

        const UBaseType_t count = uxTaskGetSystemState(tasks, MAX_TASKS, NULL);
        REQUIRE(count > 0U);
        uart_puts("VEL_BEGIN");
        field("tick", (uint32_t)xTaskGetTickCount());
        field("switches", g_switches);
        field("heap", (uint32_t)xPortGetFreeHeapSize());
        field("heap_min", (uint32_t)xPortGetMinimumEverFreeHeapSize());
        field("queue", (uint32_t)uxQueueMessagesWaiting(samples));
        field("produced", produced);
        field("consumed", consumed);
        field("commands", commands);
        field("cpuid", MMIO(0xE000ED00UL));
        field("icsr", MMIO(0xE000ED04UL));
        field("vtor", MMIO(0xE000ED08UL));
        field("systick_load", MMIO(0xE000E014UL));
        field("systick_value", MMIO(0xE000E018UL));
        field("nvic_enabled", MMIO(0xE000E100UL));
        field("nvic_pending", MMIO(0xE000E200UL));
        field("uart_ctrl", MMIO(UART0 + 8U));
        field("uart_state", MMIO(UART0 + 4U));
        field("uart_div", MMIO(UART0 + 0x10U));
        field("timer_ctrl", MMIO(TIMER0));
        field("timer_value", MMIO(TIMER0 + 4U));
        field("timer_reload", MMIO(TIMER0 + 8U));
        field("tasks", (uint32_t)count);
        uart_putc('\n');
        for (UBaseType_t i = 0; i < count; ++i) {
            const TaskStatus_t *task = &tasks[i];
            uart_puts("VEL_TASK ");
            uart_puts(task->pcTaskName);
            field("id", (uint32_t)task->xTaskNumber);
            field("state", (uint32_t)task->eCurrentState);
            field("priority", (uint32_t)task->uxCurrentPriority);
            field("stack_words", (uint32_t)task->usStackHighWaterMark);
            uart_putc('\n');
        }
        uart_puts("VEL_END\n");
        vTaskDelay(pdMS_TO_TICKS(350));
    }
}

int main(void)
{
    REQUIRE(uart_init());
    MMIO(UART0 + 8U) = 3U;   /* TX and RX. */
    MMIO(TIMER0 + 8U) = 25000000U;
    MMIO(TIMER0) = 1U;       /* Free-running APB Timer 0, no IRQ. */
    samples = xQueueCreate(4, sizeof(uint32_t));
    REQUIRE(samples != NULL);
    REQUIRE(xTaskCreate(producer, "Producer", 384, NULL, 1, &producer_handle) == pdPASS);
    REQUIRE(xTaskCreate(consumer, "Consumer", 384, NULL, 2, NULL) == pdPASS);
    REQUIRE(xTaskCreate(inspector, "Inspector", 512, NULL, 3, NULL) == pdPASS);
    vTaskStartScheduler();
    REQUIRE(0);
    return 1;
}
