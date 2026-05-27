"""Модуль симулятора процессора (виртуальной машины).

Реализует Harvard-архитектуру с потактовым (tick-by-tick) моделированием
выполнения команд, поддержку системных прерываний (Trap) и портов ввода-вывода (MMIO).
"""

import struct
import argparse
import logging
from src.isa import OpCode, Register, AddressingMode, DATA_MEMORY_SIZE, VECTOR_SIZE, MMIO_INPUT, MMIO_OUTPUT

logging.basicConfig(level=logging.DEBUG, format='%(message)s')


class DataPath:
    """Тракт данных процессора.

    Содержит оперативную память данных, регистровые файлы (скалярный и векторный),
    буферы последовательного ввода и вывода. Предоставляет интерфейс чтения и записи.
    """

    def __init__(self, data_memory_size, instruction_memory):
        """Инициализирует память, регистры и системные шины ввода-вывода."""

        self.instruction_memory = instruction_memory
        self.data_memory = [0] * data_memory_size

        self.registers = [0] * 16
        # Вершина стека
        self.registers[Register.SP] = data_memory_size - 4
        self.registers[Register.FP] = data_memory_size - 4

        self.vector_registers = [[0] * VECTOR_SIZE for _ in range(4)]
        self.input_buffer = []  # Буфер для последовательного ввода (--input)
        self.output_buffer = []
        self.input_schedule = []  # Список кортежей (tick, value) для TRAP
        self.mmio_input_val = 0  # Выделенный регистр-буфер ввода для MMIO портов

    def read_data(self, address):
        """Читает слово из памяти данных. Перехватывает обращения к порту MMIO_INPUT.

        Args:
            address: Адрес ячейки памяти или MMIO-порта.

        Returns:
            32-битное значение (целое число или код символа).
        """

        if address == MMIO_INPUT:
            # Читаем посимвольно из последовательного буфера ввода
            if self.input_buffer:
                char = self.input_buffer.pop(0)
                self.mmio_input_val = ord(char) if isinstance(char, str) else char
            else:
                self.mmio_input_val = 0  # 0 сигнализирует об EOF

            logging.info(
                f"MMIO: Reading from INPUT: {self.mmio_input_val} ('{chr(self.mmio_input_val) if 0 < self.mmio_input_val <= 255 else 'EOF'}')")
            return self.mmio_input_val
        return self.data_memory[address]

    def write_data(self, address, value):
        """Записывает слово в память данных. Перехватывает обращения к MMIO_OUTPUT.

        Args:
            address: Адрес назначения в памяти.
            value: Записываемое значение.
        """

        if address == MMIO_OUTPUT:
            self.data_memory[MMIO_OUTPUT if MMIO_OUTPUT < len(self.data_memory) else 0] = value  # self fallback
            char = chr(value & 0xFF) if 0 <= value <= 255 else str(value)
            self.output_buffer.append(char)
            logging.info(f"MMIO: Written '{char}' to OUTPUT")
        else:
            self.data_memory[address] = value

    def push(self, value):
        """Помещает значение на стек (стек растет вниз, уменьшая SP)."""

        self.registers[Register.SP] -= 4
        self.write_data(self.registers[Register.SP], value)

    def pop(self):
        """Извлекает значение с вершины стека, увеличивая SP."""

        val = self.read_data(self.registers[Register.SP])
        self.registers[Register.SP] += 4
        return val


class ControlUnit:
    """Управляющее устройство (Hardwired Control Unit) процессора.

    Реализует конечный автомат (FSM) цикла инструкции: Fetch (выборка),
    Decode (декодирование), Execute (выполнение) и обработку прерываний.
    """

    def __init__(self, data_path: DataPath):
        """Инициализирует УУ и связывает его с трактом данных."""

        self.dp = data_path
        self.tick_count = 0
        self._halt = False
        self.in_interrupt = False

    def tick(self, count=1):
        """Увеличивает счетчик тактов выполнения процессора."""

        self.tick_count += count

    def check_interrupt_schedule(self):
        """Проверяет расписание внешних прерываний (Trap).

        При наступлении такта прерывания приостанавливает выполнение программы,
        сохраняет контекст (PC, SR) на стек и переключает выполнение на обработчик.
        """

        if not self.in_interrupt and self.dp.input_schedule:
            next_intr_tick, value = self.dp.input_schedule[0]
            if self.tick_count >= next_intr_tick:
                self.dp.input_schedule.pop(0)
                logging.info(f"--- TRAP: Interrupt Triggered at tick {self.tick_count}! Input value: {value} ---")

                self.dp.mmio_input_val = ord(value) if isinstance(value, str) else value

                # Спасаем контекст на стеке
                self.dp.push(self.dp.registers[Register.PC])
                self.dp.push(self.dp.registers[Register.SR])

                # Эмуляция перехода на вектор прерывания.
                # Пусть обработчик прерывания находится на адресе 4 (первая команда программы после стартового JMP)
                self.in_interrupt = True
                self.dp.registers[Register.PC] = 4  # Переход к обработчику
                self.tick(3)  # Такты на переход и сохранение контекста

    def decode_and_execute(self):
        """Основной цикл одной CISC-инструкции.

        Выбирает заголовок команды, считывает операнды (включая переменные Payload),
        вызывает функции тракта данных и считает такты выполнения.
        """

        self.check_interrupt_schedule()

        pc = self.dp.registers[Register.PC]
        if pc >= len(self.dp.instruction_memory):
            self._halt = True
            return

        opcode, mode, reg_d, reg_s = struct.unpack('<BBBB', self.dp.instruction_memory[pc:pc + 4])
        self.tick()

        logging.debug(
            f"TICK: {self.tick_count:4} | PC: {pc:3} | OP: {OpCode(opcode).name} | R0: {self.dp.registers[Register.R0]}")

        if opcode == OpCode.HALT:
            self._halt = True
            self.tick()

        elif opcode == OpCode.MOV:
            if mode == AddressingMode.IMMEDIATE:
                payload = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
                self.dp.registers[reg_d] = payload
                self.dp.registers[Register.PC] += 8
                self.tick()
            else:
                self.dp.registers[reg_d] = self.dp.registers[reg_s]
                self.dp.registers[Register.PC] += 4
            self.tick()

        elif opcode == OpCode.LOAD:
            if mode == AddressingMode.INDIRECT:
                offset = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
                addr = self.dp.registers[reg_s] + offset
                self.dp.registers[reg_d] = self.dp.read_data(addr)
                self.dp.registers[Register.PC] += 8
                self.tick()
            elif mode == AddressingMode.DIRECT:
                addr = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
                self.dp.registers[reg_d] = self.dp.read_data(addr)
                self.dp.registers[Register.PC] += 8
                self.tick()
            self.tick()

        elif opcode == OpCode.STORE:
            if mode == AddressingMode.DIRECT:
                addr = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
                self.dp.write_data(addr, self.dp.registers[reg_s])
                self.dp.registers[Register.PC] += 8
                self.tick()
            elif mode == AddressingMode.INDIRECT:
                # Запись по адресу, лежащему в регистре reg_d
                offset = struct.unpack('<i', self.dp.instruction_memory[pc + 4: pc + 8])[0]
                addr = self.dp.registers[reg_d] + offset
                self.dp.write_data(addr, self.dp.registers[reg_s])
                self.dp.registers[Register.PC] += 8
                self.tick()
            self.tick()

        elif opcode == OpCode.ADD:
            if mode == AddressingMode.IMMEDIATE:
                payload = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
                self.dp.registers[reg_d] += payload
                self.dp.registers[Register.PC] += 8
                self.tick()
            else:
                self.dp.registers[reg_d] += self.dp.registers[reg_s]
                self.dp.registers[Register.PC] += 4
            self.tick()

        elif opcode == OpCode.SUB:
            self.dp.registers[reg_d] = self.dp.registers[reg_s] - self.dp.registers[reg_d]
            self.dp.registers[Register.PC] += 4
            self.tick()

        elif opcode == OpCode.MUL:
            self.dp.registers[reg_d] = self.dp.registers[reg_s] * self.dp.registers[reg_d]
            self.dp.registers[Register.PC] += 4
            self.tick()

        elif opcode == OpCode.DIV:
            self.dp.registers[reg_d] = self.dp.registers[reg_s] // self.dp.registers[reg_d]
            self.dp.registers[Register.PC] += 4
            self.tick()

        elif opcode == OpCode.PUSH:
            self.dp.push(self.dp.registers[reg_s])
            self.dp.registers[Register.PC] += 4
            self.tick()

        elif opcode == OpCode.POP:
            self.dp.registers[reg_d] = self.dp.pop()
            self.dp.registers[Register.PC] += 4
            self.tick()

        elif opcode == OpCode.CMP:
            if mode == AddressingMode.IMMEDIATE:
                payload = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
                val = self.dp.registers[reg_d] - payload
                self.dp.registers[Register.PC] += 8
                self.tick()
            else:
                val = self.dp.registers[reg_d] - self.dp.registers[reg_s]
                self.dp.registers[Register.PC] += 4

            # Кодируем флаги в SR: Bit 0 = ZF, Bit 1 = NF
            zf = 1 if val == 0 else 0
            nf = 1 if val < 0 else 0
            self.dp.registers[Register.SR] = (nf << 1) | zf
            self.tick()

        elif opcode == OpCode.JMP:
            target = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
            self.dp.registers[Register.PC] = target
            self.tick(2)

        elif opcode == OpCode.JZ:
            target = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
            zf = self.dp.registers[Register.SR] & 1
            if zf == 1:
                self.dp.registers[Register.PC] = target
            else:
                self.dp.registers[Register.PC] += 8
            self.tick(2)

        elif opcode == OpCode.JL:
            target = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
            nf = (self.dp.registers[Register.SR] >> 1) & 1
            if nf == 1:
                self.dp.registers[Register.PC] = target
            else:
                self.dp.registers[Register.PC] += 8
            self.tick(2)

        elif opcode == OpCode.CALL:
            target = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
            self.dp.push(pc + 8)
            self.dp.registers[Register.PC] = target
            self.tick(2)

        elif opcode == OpCode.RET:
            self.dp.registers[Register.PC] = self.dp.pop()
            self.tick(2)

        elif opcode == OpCode.IRET:
            # Возврат из прерывания: восстанавливаем контекст
            self.dp.registers[Register.SR] = self.dp.pop()
            self.dp.registers[Register.PC] = self.dp.pop()
            self.in_interrupt = False
            self.tick(2)

        elif opcode == OpCode.INT:
            payload = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
            if payload == 1:
                # Печать числа
                val = self.dp.registers[Register.R0]
                self.dp.output_buffer.append(str(val))
                logging.info(f"SYSTEM PRINT INT: {val}")
            elif payload == 2:
                # Печать C-style строки (null-terminated)
                addr = self.dp.registers[Register.R0]
                char_code = self.dp.read_data(addr)
                string_chars = []
                while char_code != 0 and len(string_chars) < 1000:  # Ограничитель безопасности
                    string_chars.append(chr(char_code))
                    addr += 1  # Переход на одно слово вперед
                    char_code = self.dp.read_data(addr)
                output_str = "".join(string_chars)
                self.dp.output_buffer.extend(string_chars)
                logging.info(f"SYSTEM PRINT STRING: {output_str}")

            self.dp.registers[Register.PC] += 8
            self.tick()

        # Векторные операции
        elif opcode == OpCode.VLOAD:
            v_reg = reg_d - 8
            addr = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
            for i in range(VECTOR_SIZE):
                self.dp.vector_registers[v_reg][i] = self.dp.read_data(addr + i)
                self.tick()
            self.dp.registers[Register.PC] += 8

        elif opcode == OpCode.VSTORE:
            v_reg = reg_s - 8
            addr = struct.unpack('<i', self.dp.instruction_memory[pc + 4:pc + 8])[0]
            for i in range(VECTOR_SIZE):
                self.dp.write_data(addr + i, self.dp.vector_registers[v_reg][i])
                self.tick()
            self.dp.registers[Register.PC] += 8

        elif opcode == OpCode.VADD:
            v_dest = reg_d - 8
            v_src = reg_s - 8
            for i in range(VECTOR_SIZE):
                self.dp.vector_registers[v_dest][i] += self.dp.vector_registers[v_src][i]
                self.tick()
            self.dp.registers[Register.PC] += 4

    def run(self):
        """Запускает симуляцию выполнения программы до команды HALT или лимита тактов."""

        while not self._halt and self.tick_count < 1_000_000:
            self.decode_and_execute()
        logging.info(f"Finished at tick {self.tick_count}")


def main():
    parser = argparse.ArgumentParser(description="CISC Harvard Processor Simulator")
    parser.add_argument("binary_file", help="Path to compiled program.bin")
    parser.add_argument("--input", help="Path to file with plain input for MMIO stdin", default=None)
    parser.add_argument("--schedule", help="Path to schedule file for TRAP interrupts", default=None)

    args = parser.parse_args()

    with open(args.binary_file, "rb") as f:
        # Читаем заголовок (8 байт)
        header = f.read(8)
        code_size, data_size = struct.unpack('<II', header)

        # Читаем секции по размерам
        instr_mem = f.read(code_size)
        data_bytes = f.read(data_size)

    dp = DataPath(DATA_MEMORY_SIZE, instr_mem)

    # Загружаем инициализированные данные в память данных
    for i in range(data_size // 4):
        val = struct.unpack('<i', data_bytes[i * 4: (i + 1) * 4])[0]
        dp.data_memory[i] = val

    # Явное заполнение последовательного буфера ввода (--input)
    if args.input:
        with open(args.input, 'r', encoding="utf-8") as f:
            content = f.read()
        dp.input_buffer = list(content)

    # Обработка прерываний по расписанию (--schedule)
    if args.schedule:
        with open(args.schedule, 'r', encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    t_tick, val = line.strip().split(",")
                    dp.input_schedule.append((int(t_tick), val))

    cu = ControlUnit(dp)
    cu.run()
    print(f"Simulation finished. Output: {''.join(dp.output_buffer)}")


if __name__ == "__main__":
    main()
