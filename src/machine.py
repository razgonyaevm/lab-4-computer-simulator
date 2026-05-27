"""Модуль симулятора процессора (виртуальной машины).

Реализует Harvard-архитектуру с потактовым (tick-by-tick) моделированием
выполнения команд, поддержку системных прерываний (Trap) и портов ввода-вывода (MMIO).
"""

import argparse
import json
import logging
import os
import struct
from collections.abc import Callable

from src.isa import (
    DATA_MEMORY_SIZE,
    MMIO_INPUT,
    MMIO_OUTPUT,
    VECTOR_SIZE,
    AddressingMode,
    OpCode,
    Register,
)

logging.basicConfig(level=logging.DEBUG, format="%(message)s")


class DataPath:
    """Тракт данных процессора.

    Содержит оперативную память данных, регистровые файлы (скалярный и векторный),
    буферы последовательного ввода и вывода. Предоставляет интерфейс чтения и записи.
    """

    def __init__(self, data_memory_size: int, instruction_memory: bytes) -> None:
        """Инициализирует память, регистры и системные шины ввода-вывода."""

        self.instruction_memory: bytes = instruction_memory
        self.data_memory: list[int] = [0] * data_memory_size

        self.registers: list[int] = [0] * 16
        # Вершина стека
        self.registers[Register.SP] = data_memory_size - 4
        self.registers[Register.FP] = data_memory_size - 4

        self.vector_registers: list[list[int]] = [[0] * VECTOR_SIZE for _ in range(4)]
        self.input_buffer: list[str] = []  # Буфер для последовательного ввода (--input)
        self.output_buffer: list[str] = []
        self.input_schedule: list[tuple[int, str]] = []  # Список кортежей (tick, value) для TRAP
        self.has_input: bool = False  # Флаг, указывающий, пришло на нам что-то на input
        self.mmio_input_val: int = 0  # Выделенный регистр-буфер ввода для MMIO портов

    def read_data(self, address: int) -> int:
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
            elif self.has_input:
                self.mmio_input_val = 0

            char_repr = chr(self.mmio_input_val) if 0 < self.mmio_input_val <= 255 else "EOF"
            logging.info(f">>> INPUT Read: {self.mmio_input_val} ('{char_repr}')")
            return self.mmio_input_val
        return self.data_memory[address]

    def write_data(self, address: int, value: int) -> None:
        """Записывает слово в память данных. Перехватывает обращения к MMIO_OUTPUT.

        Args:
            address: Адрес назначения в памяти.
            value: Записываемое значение.
        """

        if address == MMIO_OUTPUT:
            self.data_memory[MMIO_OUTPUT if MMIO_OUTPUT < len(self.data_memory) else 0] = value  # self fallback
            char = chr(value & 0xFF) if 0 <= value <= 255 else str(value)
            self.output_buffer.append(char)
            logging.info(f"<<< OUTPUT Write: {value} ('{char}')")
        else:
            self.data_memory[address] = value

    def push(self, value: int) -> None:
        """Помещает значение на стек (стек растет вниз, уменьшая SP)."""

        self.registers[Register.SP] -= 4
        self.write_data(self.registers[Register.SP], value)

    def pop(self) -> int:
        """Извлекает значение с вершины стека, увеличивая SP."""

        val = self.read_data(self.registers[Register.SP])
        self.registers[Register.SP] += 4
        return val


class ControlUnit:
    """Управляющее устройство (Hardwired Control Unit) процессора.

    Реализует конечный автомат (FSM) цикла инструкции: Fetch (выборка),
    Decode (декодирование), Execute (выполнение) и обработку прерываний.
    """

    def __init__(self, data_path: DataPath, intr_vector: int = 0, debug_map: dict[str, str] | None = None) -> None:
        """Инициализирует УУ и связывает его с трактом данных."""

        self.dp: DataPath = data_path
        self.tick_count: int = 0
        self._halt: bool = False
        self.in_interrupt: bool = False
        self.intr_vector = intr_vector
        self.debug_map: dict[str, str] = debug_map if debug_map is not None else {}

    def dump_memories(self) -> None:
        """Выводит раздельный дамп памяти команд и памяти данных

        Необходимо для явной верификации состояния Harvard-архитектуры в тестах.
        """

        logging.info("HARVARD MEMORY DUMP")

        # Дамп памяти команд (Instruction Memory)
        logging.info("INSTRUCTION MEMORY (Code Section):")
        pc = 0
        while pc < len(self.dp.instruction_memory):
            opcode, mode, reg_d, reg_s = struct.unpack("<BBBB", self.dp.instruction_memory[pc : pc + 4])
            instr_name = OpCode(opcode).name if opcode in OpCode.__members__.values() else f"0x{opcode:02X}"
            source = self.debug_map.get(str(pc), "No Source")

            # Определяем, есть ли у команды payload (смещение/константа/адрес)
            has_payload = mode in (AddressingMode.IMMEDIATE, AddressingMode.DIRECT, AddressingMode.INDIRECT)
            instr_details = f"   [{pc:04d}]: {instr_name:<6} Mode:{mode:<2} Rd:{reg_d:<2} Rs:{reg_s:<2}"
            if has_payload and pc + 8 <= len(self.dp.instruction_memory):
                payload = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
                instr_details += f" Payload: {payload:<10}"
                pc += 8
            else:
                pc += 4
            logging.info(f"{instr_details:<60} | {source}")

        logging.info("-" * 80)

        # 2. Дамп памяти данных (Data Memory)
        logging.info("DATA MEMORY (Used Non-Zero Words & Active Stack):")
        for addr in range(len(self.dp.data_memory)):
            val = self.dp.data_memory[addr]
            # Печатаем ячейку, если она не пустая, или если она находится в активной зоне стека
            is_stack = addr >= self.dp.registers[Register.SP]
            is_static = addr < self.dp.registers[Register.SP]  # Всё, что выше стека

            if val != 0 or is_stack:
                tag = " (STACK)" if is_stack else " (STATIC/GLOBAL)" if is_static else ""
                char_repr = f"'{chr(val)}'" if 32 <= val <= 126 else ""
                logging.info(f"  [{addr:04d}]: {val:<10} {char_repr:<5} {tag}")
        logging.info("=" * 80)

    def tick(self, count: int = 1) -> None:
        """Увеличивает счетчик тактов выполнения процессора."""

        self.tick_count += count

    def check_interrupt_schedule(self) -> None:
        """Проверяет расписание внешних прерываний (Trap).

        При наступлении такта прерывания приостанавливает выполнение программы,
        сохраняет контекст (PC, SR) на стек и переключает выполнение на обработчик.
        """

        if not self.in_interrupt and self.dp.input_schedule:
            if not self.in_interrupt and self.dp.input_schedule:
                next_intr_tick, value = self.dp.input_schedule[0]
                if self.tick_count >= next_intr_tick:
                    self.dp.input_schedule.pop(0)

                    # Проверяем, зарегистрирован ли вообще обработчик прерывания
                    if self.intr_vector != 0:
                        logging.info(
                            f"--- TRAP: Interrupt Triggered at tick {self.tick_count}! Input value: {value} ---"
                        )

                        self.dp.mmio_input_val = ord(value) if isinstance(value, str) else value

                        # Спасаем контекст на стеке
                        self.dp.push(self.dp.registers[Register.PC])
                        self.dp.push(self.dp.registers[Register.SR])

                        # Переходим на вектор прерывания
                        self.in_interrupt = True
                        self.dp.registers[Register.PC] = self.intr_vector  # Переход к обработчику
                        self.tick(3)  # Такты на переход и сохранение контекста

    def decode_and_execute(self) -> None:
        """Основной цикл одной CISC-инструкции.

        Выбирает заголовок команды, считывает операнды (включая переменные Payload),
        вызывает функции тракта данных и считает такты выполнения.
        """

        self.check_interrupt_schedule()

        pc = self.dp.registers[Register.PC]
        if pc >= len(self.dp.instruction_memory):
            self._halt = True
            return

        opcode, mode, reg_d, reg_s = struct.unpack("<BBBB", self.dp.instruction_memory[pc : pc + 4])
        self.tick()

        # Извлекаем оригинальный Lisp-код для текущего PC
        source_code = self.debug_map.get(str(pc), "Unknown Lisp Source")

        # Форматируем состояние скалярных регистров и флагов
        reg_strs = []
        for r in range(8):
            reg_strs.append(f"R{r}:{self.dp.registers[r]}")
        reg_strs.append(f"SP:{self.dp.registers[Register.SP]}")
        reg_strs.append(f"FP:{self.dp.registers[Register.FP]}")

        zf = self.dp.registers[Register.SR] & 1
        nf = (self.dp.registers[Register.SR] >> 1) & 1
        reg_strs.append(f"SR:{self.dp.registers[Register.SR]} (ZF={zf}, NF={nf})")

        # Форматируем состояние векторных регистров (только если они используются)
        v_strs = []
        for v in range(4):
            v_strs.append(f"V{v}:{self.dp.vector_registers[v]}")

        # Выводим структурированный лог состояния процессора в журнал
        logging.debug(f"TICK: {self.tick_count:4} | PC: {pc:3} | Instruction: {OpCode(opcode).name} (Mode: {mode})")
        logging.debug(f"  LISP SOURCE : {source_code}")
        logging.debug(f"  SCALAR REGS : {', '.join(reg_strs)}")
        logging.debug(f"  VECTOR REGS : {', '.join(v_strs)}")
        logging.debug("-" * 80)

        # Таблица диспетчеризации опкодов
        handlers: dict[OpCode, Callable[[int, int, int, int], None]] = {
            OpCode.HALT: self._execute_halt,
            OpCode.MOV: self._execute_mov,
            OpCode.LOAD: self._execute_load,
            OpCode.STORE: self._execute_store,
            OpCode.ADD: self._execute_add,
            OpCode.SUB: self._execute_sub,
            OpCode.MUL: self._execute_mul,
            OpCode.DIV: self._execute_div,
            OpCode.PUSH: self._execute_push,
            OpCode.POP: self._execute_pop,
            OpCode.CMP: self._execute_cmp,
            OpCode.JMP: self._execute_jmp,
            OpCode.JZ: self._execute_jz,
            OpCode.JL: self._execute_jl,
            OpCode.CALL: self._execute_call,
            OpCode.RET: self._execute_ret,
            OpCode.IRET: self._execute_iret,
            OpCode.INT: self._execute_int,
            OpCode.VLOAD: self._execute_vload,
            OpCode.VSTORE: self._execute_vstore,
            OpCode.VADD: self._execute_vadd,
            OpCode.VSUB: self._execute_vsub,
            OpCode.VMUL: self._execute_vmul,
            OpCode.VDIV: self._execute_vdiv,
            OpCode.VCMP: self._execute_vcmp,
        }

        if opcode in handlers:
            handlers[opcode](mode, reg_d, reg_s, pc)
        else:
            raise ValueError(f"Unknown OpCode: {opcode}")

    def _execute_halt(self, _mode: int, _reg_d: int, _reg_s: int, _pc: int) -> None:
        """Выполняет остановку симуляции процессора (HALT)."""

        self._halt = True
        self.tick()

    def _execute_mov(self, mode: int, reg_d: int, reg_s: int, pc: int) -> None:
        """Выполняет операцию MOV.

        Записывает в целевой регистр непосредственное значение (payload)
        или копирует значение из другого регистра.
        """

        if mode == AddressingMode.IMMEDIATE:
            payload = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
            self.dp.registers[reg_d] = payload
            self.dp.registers[Register.PC] += 8
            self.tick()
        else:
            self.dp.registers[reg_d] = self.dp.registers[reg_s]
            self.dp.registers[Register.PC] += 4
        self.tick()

    def _execute_load(self, mode: int, reg_d: int, reg_s: int, pc: int) -> None:
        """Выполняет операцию загрузки данных из памяти в регистр (LOAD).

        Поддерживает прямую (DIRECT) и косвенную (INDIRECT со смещением) адресации.
        """

        if mode == AddressingMode.INDIRECT:
            offset = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
            addr = self.dp.registers[reg_s] + offset
            self.dp.registers[reg_d] = self.dp.read_data(addr)
            self.dp.registers[Register.PC] += 8
            self.tick()
        elif mode == AddressingMode.DIRECT:
            addr = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
            self.dp.registers[reg_d] = self.dp.read_data(addr)
            self.dp.registers[Register.PC] += 8
            self.tick()
        self.tick()

    def _execute_store(self, mode: int, reg_d: int, reg_s: int, pc: int) -> None:
        """Выполняет операцию записи данных из регистра в память (STORE).

        Поддерживает прямую (DIRECT) и косвенную (INDIRECT со смещением) адресации.
        """

        if mode == AddressingMode.DIRECT:
            addr = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
            self.dp.write_data(addr, self.dp.registers[reg_s])
            self.dp.registers[Register.PC] += 8
            self.tick()
        elif mode == AddressingMode.INDIRECT:
            offset = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
            addr = self.dp.registers[reg_d] + offset
            self.dp.write_data(addr, self.dp.registers[reg_s])
            self.dp.registers[Register.PC] += 8
            self.tick()
        self.tick()

    def _execute_add(self, mode: int, reg_d: int, reg_s: int, pc: int) -> None:
        """Выполняет операцию сложения (ADD) в ALU.

        Производит беззнаковое сложение с автоматическим 32-битным переполнением.
        """

        if mode == AddressingMode.IMMEDIATE:
            payload = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
            self.dp.registers[reg_d] = (self.dp.registers[reg_d] + payload) & 0xFFFFFFFF
            self.dp.registers[Register.PC] += 8
            self.tick()
        else:
            self.dp.registers[reg_d] = (self.dp.registers[reg_d] + self.dp.registers[reg_s]) & 0xFFFFFFFF
            self.dp.registers[Register.PC] += 4
        self.tick()

    def _execute_sub(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет вычитание в ALU с 32-битным переполнением."""

        self.dp.registers[reg_d] = (self.dp.registers[reg_s] - self.dp.registers[reg_d]) & 0xFFFFFFFF
        self.dp.registers[Register.PC] += 4
        self.tick()

    def _execute_mul(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет умножение в ALU с 32-битным переполнением."""

        self.dp.registers[reg_d] = (self.dp.registers[reg_s] * self.dp.registers[reg_d]) & 0xFFFFFFFF
        self.dp.registers[Register.PC] += 4
        self.tick()

    def _execute_div(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет целочисленное деление в ALU с 32-битным переполнением."""

        self.dp.registers[reg_d] = (self.dp.registers[reg_s] // self.dp.registers[reg_d]) & 0xFFFFFFFF
        self.dp.registers[Register.PC] += 4
        self.tick()

    def _execute_push(self, _mode: int, _reg_d: int, reg_s: int, _pc: int) -> None:
        """Сохраняет значение регистра на вершину аппаратного стека (PUSH)."""

        self.dp.push(self.dp.registers[reg_s])
        self.dp.registers[Register.PC] += 4
        self.tick()

    def _execute_pop(self, _mode: int, reg_d: int, _reg_s: int, _pc: int) -> None:
        """Извлекает значение с вершины аппаратного стека в целевой регистр (POP)."""

        self.dp.registers[reg_d] = self.dp.pop()
        self.dp.registers[Register.PC] += 4
        self.tick()

    def _execute_cmp(self, mode: int, reg_d: int, reg_s: int, pc: int) -> None:
        """Выполняет сравнение двух значений с помощью вычитания (CMP).

        Обновляет флаги состояния в регистре SR (Bit 0 = ZF, Bit 1 = NF).
        """

        payload = 0
        if mode == AddressingMode.IMMEDIATE:
            payload = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
            val = self.dp.registers[reg_d] - payload
            self.dp.registers[Register.PC] += 8
            self.tick()
        else:
            val = self.dp.registers[reg_d] - self.dp.registers[reg_s]
            self.dp.registers[Register.PC] += 4
        zf = 1 if val == 0 else 0
        nf = (
            1
            if (self.dp.registers[reg_d] < (payload if mode == AddressingMode.IMMEDIATE else self.dp.registers[reg_s]))
            else 0
        )
        self.dp.registers[Register.SR] = (nf << 1) | zf
        self.tick()

    def _execute_jmp(self, _mode: int, _reg_d: int, _reg_s: int, pc: int) -> None:
        """Выполняет безусловный переход на указанный адрес (JMP)."""

        target = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
        self.dp.registers[Register.PC] = target
        self.tick(2)

    def _execute_jz(self, _mode: int, _reg_d: int, _reg_s: int, pc: int) -> None:
        """Выполняет условный переход, если взведен флаг Zero (JZ)."""

        target = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
        zf = self.dp.registers[Register.SR] & 1
        if zf == 1:
            self.dp.registers[Register.PC] = target
        else:
            self.dp.registers[Register.PC] += 8
        self.tick(2)

    def _execute_jl(self, _mode: int, _reg_d: int, _reg_s: int, pc: int) -> None:
        """Выполняет условный переход, если взведен флаг Negative (JL)."""

        target = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
        nf = (self.dp.registers[Register.SR] >> 1) & 1
        if nf == 1:
            self.dp.registers[Register.PC] = target
        else:
            self.dp.registers[Register.PC] += 8
        self.tick(2)

    def _execute_call(self, _mode: int, _reg_d: int, _reg_s: int, pc: int) -> None:
        """Выполняет вызов подпрограммы (CALL).

        Сохраняет адрес возврата (PC + 8) на стеке и совершает безусловный переход.
        """

        target = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
        self.dp.push(pc + 8)
        self.dp.registers[Register.PC] = target
        self.tick(2)

    def _execute_ret(self, _mode: int, _reg_d: int, _reg_s: int, _pc: int) -> None:
        """Выполняет возврат из подпрограммы (RET).

        Извлекает адрес возврата со стека и записывает его в PC.
        """

        self.dp.registers[Register.PC] = self.dp.pop()
        self.tick(2)

    def _execute_iret(self, _mode: int, _reg_d: int, _reg_s: int, _pc: int) -> None:
        """Выполняет возврат из обработчика прерывания (IRET).

        Восстанавливает регистр флагов SR и счетчик команд PC со стека.
        """
        self.dp.registers[Register.SR] = self.dp.pop()
        self.dp.registers[Register.PC] = self.dp.pop()
        self.in_interrupt = False
        self.tick(2)

    def _execute_int(self, _mode: int, _reg_d: int, _reg_s: int, pc: int) -> None:
        """Выполняет программное прерывание / системный вызов (INT).

        Поддерживает:
        - INT 1: Вывод целого числа из R0.
        - INT 2: Вывод null-terminated C-строки, начинающейся с адреса в R0.
        """

        payload = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
        if payload == 1:
            val = self.dp.registers[Register.R0]
            self.dp.output_buffer.append(str(val))
            logging.info(f"SYSTEM PRINT INT: {val}")
        elif payload == 2:
            addr = self.dp.registers[Register.R0]
            char_code = self.dp.read_data(addr)
            string_chars: list[str] = []
            while char_code != 0 and len(string_chars) < 1000:
                string_chars.append(chr(char_code))
                addr += 1
                char_code = self.dp.read_data(addr)
            output_str = "".join(string_chars)
            self.dp.output_buffer.extend(string_chars)
            logging.info(f"SYSTEM PRINT STRING: {output_str}")
        self.dp.registers[Register.PC] += 8
        self.tick()

    def _execute_vload(self, _mode: int, reg_d: int, _reg_s: int, pc: int) -> None:
        """Выполняет последовательную загрузку значений памяти в векторный регистр V_reg."""

        v_reg = reg_d - 8
        addr = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
        for i in range(VECTOR_SIZE):
            self.dp.vector_registers[v_reg][i] = self.dp.read_data(addr + i)
            self.tick()
        self.dp.registers[Register.PC] += 8

    def _execute_vstore(self, _mode: int, _reg_d: int, reg_s: int, pc: int) -> None:
        """Выполняет последовательное сохранение векторного регистра V_reg в память данных."""

        v_reg = reg_s - 8
        addr = struct.unpack("<I", self.dp.instruction_memory[pc + 4 : pc + 8])[0]
        for i in range(VECTOR_SIZE):
            self.dp.write_data(addr + i, self.dp.vector_registers[v_reg][i])
            self.tick()
        self.dp.registers[Register.PC] += 8

    def _execute_vadd(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет поэлементное векторное сложение двух V-регистров за VECTOR_SIZE тактов."""

        v_dest = reg_d - 8
        v_src = reg_s - 8
        for i in range(VECTOR_SIZE):
            self.dp.vector_registers[v_dest][i] = (
                self.dp.vector_registers[v_dest][i] + self.dp.vector_registers[v_src][i]
            ) & 0xFFFFFFFF
            self.tick()
        self.dp.registers[Register.PC] += 4

    def _execute_vsub(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет поэлементное векторное вычитание двух V-регистров за VECTOR_SIZE тактов."""

        v_dest = reg_d - 8
        v_src = reg_s - 8
        for i in range(VECTOR_SIZE):
            self.dp.vector_registers[v_dest][i] = (
                self.dp.vector_registers[v_dest][i] - self.dp.vector_registers[v_src][i]
            ) & 0xFFFFFFFF
            self.tick()
        self.dp.registers[Register.PC] += 4

    def _execute_vmul(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет поэлементное векторное произведение двух V-регистров за VECTOR_SIZE тактов."""

        v_dest = reg_d - 8
        v_src = reg_s - 8
        for i in range(VECTOR_SIZE):
            self.dp.vector_registers[v_dest][i] = (
                self.dp.vector_registers[v_dest][i] * self.dp.vector_registers[v_src][i]
            ) & 0xFFFFFFFF
            self.tick()
        self.dp.registers[Register.PC] += 4

    def _execute_vdiv(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет поэлементное векторное деление двух V-регистров за VECTOR_SIZE тактов."""

        v_dest = reg_d - 8
        v_src = reg_s - 8
        for i in range(VECTOR_SIZE):
            if self.dp.vector_registers[v_src][i] != 0:
                self.dp.vector_registers[v_dest][i] = (
                    self.dp.vector_registers[v_dest][i] // self.dp.vector_registers[v_src][i]
                ) & 0xFFFFFFFF
            else:
                self.dp.vector_registers[v_dest][i] = 0
            self.tick()
        self.dp.registers[Register.PC] += 4

    def _execute_vcmp(self, _mode: int, reg_d: int, reg_s: int, _pc: int) -> None:
        """Выполняет поэлементное векторное сравнение двух V-регистров за VECTOR_SIZE тактов."""

        v_dest = reg_d - 8
        v_src = reg_s - 8
        for i in range(VECTOR_SIZE):
            self.dp.vector_registers[v_dest][i] = (
                1 if self.dp.vector_registers[v_dest][i] == self.dp.vector_registers[v_src][i] else 0
            )
            self.tick()
        self.dp.registers[Register.PC] += 4

    def run(self) -> None:
        """Запускает симуляцию выполнения программы до команды HALT или лимита тактов."""

        while not self._halt and self.tick_count < 1_000_000:
            self.decode_and_execute()
        logging.info(f"Finished at tick {self.tick_count}")

        # Выгружаем обе памяти в лог перед выходом
        self.dump_memories()


def main() -> None:
    parser = argparse.ArgumentParser(description="CISC Harvard Processor Simulator")
    parser.add_argument("binary_file", help="Path to compiled program.bin")
    parser.add_argument("--input", help="Path to file with plain input for MMIO stdin", default=None)
    parser.add_argument("--schedule", help="Path to schedule file for TRAP interrupts", default=None)
    # По умолчанию лог будет писаться в simulation.log
    parser.add_argument(
        "--log", help="Path to log file (default: simulation.log, use 'console' for stdout", default="simulation.log"
    )

    args = parser.parse_args()

    # Динамическая настройка логирования на основе флага --log
    if args.log.lower() == "console":
        logging.basicConfig(level=logging.DEBUG, format="%(message)s", force=True)
    else:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s", filename=args.log, filemode="w", force=True)

    with open(args.binary_file, "rb") as f:
        # Читаем заголовок (12 байт)
        header = f.read(12)
        code_size, data_size, intr_vector = struct.unpack("<III", header)

        # Читаем секции по размерам
        instr_mem = f.read(code_size)
        data_bytes = f.read(data_size)

    debug_file = args.binary_file + ".dbg"
    debug_map = {}
    if os.path.exists(debug_file):
        with open(debug_file, encoding="utf-8") as f_debug:
            debug_map = json.load(f_debug)

    dp = DataPath(DATA_MEMORY_SIZE, instr_mem)

    # Загружаем инициализированные данные в память данных
    for i in range(data_size // 4):
        val = struct.unpack("<I", data_bytes[i * 4 : (i + 1) * 4])[0]
        dp.data_memory[i] = val

    # Явное заполнение последовательного буфера ввода (--input)
    if args.input:
        with open(args.input, encoding="utf-8") as f:
            content = f.read()
        dp.input_buffer = list(content)
        dp.has_input = True

    # Обработка прерываний по расписанию (--schedule)
    if args.schedule:
        with open(args.schedule, encoding="utf-8") as f:
            content = f.read()

        # Принудительно заменяем экранированные переносы строк на нормальные
        content = content.replace("\\r\\n", "\n").replace("\\n", "\n")

        # Разбиваем по строкам
        for line in content.splitlines():
            if line.strip():
                t_tick, val = line.strip().split(",")
                dp.input_schedule.append((int(t_tick), val))

    cu = ControlUnit(dp, intr_vector=intr_vector, debug_map=debug_map)
    cu.run()
    print(f"Simulation finished. Output: {''.join(dp.output_buffer)}")


if __name__ == "__main__":
    main()
