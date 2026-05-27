"""Модуль транслятора Lisp-подобного языка в бинарный код.

Выполняет токенизацию, построение S-выражений и двухпроходную генерацию
бинарного машинного кода для CISC-архитектуры.
"""

import re
import struct
import sys
from src.isa import OpCode, Register, AddressingMode, DATA_MEMORY_SIZE


def tokenize(code: str):
    """Разбивает исходный код программы на токены.

    Использует регулярные выражения для корректного выделения строк
    в кавычках с пробелами, скобок и символов без нарушения целостности строк.

    Args:
        code: Строка с исходным кодом на Lisp.

    Returns:
        Список строковых токенов.
    """

    # Очистка от комментариев и разбиение с учетом скобок
    code = re.sub(r';.*', '', code)
    # Регулярка ищет строки в кавычках, скобки или любые символы без пробелов
    pattern = r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+'
    return re.findall(pattern, code)


def parse_s_expression(tokens):
    """Рекурсивно строит дерево S-выражений из списка токенов.

    Args:
        tokens: Список токенов, полученных после токенизации.

    Returns:
        Вложенные списки, представляющие структуру S-выражений,
        целые числа (для числовых литералов) или строки (для символов).

    Raises:
        SyntaxError: Если обнаружен неожиданный конец файла (EOF).
    """

    if not tokens:
        raise SyntaxError("Unexpected EOF")
    token = tokens.pop(0)
    if token == '(':
        lst = []
        while tokens[0] != ')':
            lst.append(parse_s_expression(tokens))
        tokens.pop(0)  # Удаляем ')'
        return lst
    else:
        try:
            return int(token)
        except ValueError:
            # Если это строка в кавычках — убираем кавычки
            if token.startswith('"') and token.endswith('"'):
                return token[1:-1]
            return token


class Instruction:
    """Представление промежуточной ассемблерной инструкции до бинарной сборки.

    Атрибуты:
        opcode: Код операции (OpCode).
        mode: Режим адресации (AddressingMode).
        reg_d: Индекс целевого регистра.
        reg_s: Индекс регистра-источника.
        payload: Дополнительные данные (числовое значение или строковая метка).
    """

    def __init__(self, opcode, mode: AddressingMode = AddressingMode.REGISTER, reg_d=0, reg_s=0, payload=None):
        self.opcode = opcode
        self.mode = mode
        self.reg_d = reg_d
        self.reg_s = reg_s
        self.payload = payload


class Translator:
    """Двухпроходный компилятор Lisp-кода в CISC машинные инструкции."""

    def __init__(self):
        """Инициализирует транслятор, резервируя MMIO порты в таблице символов."""

        self.instructions = []
        self.labels = {}
        self.data_memory = [0] * DATA_MEMORY_SIZE
        self.data_ptr = 0

        self.symbol_table = {
            "stdin": 0xFF00,  # MMIO_INPUT
            "stdout": 0xFF01  # MMIO_OUTPUT
        }
        self.label_counter = 0

    def get_new_label(self):
        """Генерирует уникальное имя метки для условных переходов и циклов.

        Returns:
            Строковое имя метки (например, "L_1").
        """

        self.label_counter += 1
        return f"L_{self.label_counter}"

    def get_current_address(self):
        """Вычисляет текущий байтовый адрес в памяти команд.

        Каждая инструкция занимает 4 байта (без payload) или 8 байт (с payload).

        Returns:
            Адрес следующей инструкции в байтах.
        """

        addr = 0
        for instr in self.instructions:
            addr += 8 if instr.payload is not None else 4
        return addr

    def add_instruction(self, opcode, mode: AddressingMode = AddressingMode.REGISTER, reg_d=0, reg_s=0, payload=None):
        """Добавляет промежуточную инструкцию в список для последующей компиляции."""

        instr = Instruction(opcode, mode, reg_d, reg_s, payload)
        self.instructions.append(instr)

    def add_label(self, label_name):
        """Связывает имя метки с текущим байтовым адресом в памяти команд."""

        self.labels[label_name] = self.get_current_address()

    def allocate_string(self, string):
        """Выделяет память в секции статических данных под C-style строку.

        Каждый символ строки записывается в отдельное 32-битное машинное слово,
        в конце ставится null-terminator (0)

        Args:
            string: Строковый литерал для сохранения.

        Returns:
            Адрес начала строки в памяти данных (в словах).
        """

        # Каждому символу выделяем по одному целому слову (4 байта)
        addr = self.data_ptr  # Адрес равен индексу слова в памяти данных
        for char in string:
            self.data_memory[self.data_ptr] = ord(char)
            self.data_ptr += 1
        self.data_memory[self.data_ptr] = 0  # null-terminator
        self.data_ptr += 1
        return addr

    def translate_expression(self, expr, local_vars=None):
        """Рекурсивно транслирует S-выражение в последовательность инструкций.

        Args:
            expr: Выражение (список, строка или число).
            local_vars: Словарь аргументов текущей функции для доступа относительно FP.
        """

        if local_vars is None:
            local_vars = {}

        if isinstance(expr, int):
            self.add_instruction(OpCode.MOV, AddressingMode.IMMEDIATE, Register.R0, 0, expr)
            return

        if isinstance(expr, str):
            if expr in local_vars:
                arg_idx = local_vars[expr]
                offset = 8 + arg_idx * 4
                self.add_instruction(OpCode.LOAD, AddressingMode.INDIRECT, Register.R0, Register.FP, offset)
            elif expr in self.symbol_table:
                addr = self.symbol_table[expr]
                self.add_instruction(OpCode.LOAD, AddressingMode.DIRECT, Register.R0, 0, addr)
            else:
                # если это не переменная, значит это строковый литерал
                addr = self.allocate_string(expr)
                self.add_instruction(OpCode.MOV, AddressingMode.IMMEDIATE, Register.R0, 0, addr)
            return

        if not isinstance(expr, list) or len(expr) == 0:
            return

        op = expr[0]

        # Переменные
        if op == "setq":
            var_name, val = expr[1], expr[2]
            self.translate_expression(val, local_vars)
            if var_name not in self.symbol_table:
                self.symbol_table[var_name] = self.data_ptr
                self.data_ptr += 1
            self.add_instruction(OpCode.STORE, AddressingMode.DIRECT, 0, Register.R0, self.symbol_table[var_name])

        # Арифметика (поддержка деления и остатка)
        elif op in ("+", "-", "*", "/"):
            self.translate_expression(expr[1], local_vars)
            self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)
            self.translate_expression(expr[2], local_vars)
            self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.R1, 0)

            opcode_map = {"+": OpCode.ADD, "-": OpCode.SUB, "*": OpCode.MUL, "/": OpCode.DIV}
            self.add_instruction(opcode_map[op], AddressingMode.REGISTER, Register.R0, Register.R1)

        # Сравнения
        elif op in ("=", "<"):
            self.translate_expression(expr[1], local_vars)
            self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)
            self.translate_expression(expr[2], local_vars)
            self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.R1, 0)

            self.add_instruction(OpCode.CMP, AddressingMode.REGISTER, Register.R1, Register.R0)

            true_lbl = self.get_new_label()
            end_lbl = self.get_new_label()

            if op == "=":
                self.add_instruction(OpCode.JZ, AddressingMode.IMMEDIATE, 0, 0, true_lbl)
            else:
                self.add_instruction(OpCode.JL, AddressingMode.IMMEDIATE, 0, 0, true_lbl)

            self.add_instruction(OpCode.MOV, AddressingMode.IMMEDIATE, Register.R0, 0, 0)
            self.add_instruction(OpCode.JMP, AddressingMode.IMMEDIATE, 0, 0, end_lbl)
            self.add_label(true_lbl)
            self.add_instruction(OpCode.MOV, AddressingMode.IMMEDIATE, Register.R0, 0, 1)
            self.add_label(end_lbl)

        # Условный оператор (if)
        elif op == "if":
            cond, then_branch, else_branch = expr[1], expr[2], expr[3]
            self.translate_expression(cond, local_vars)
            self.add_instruction(OpCode.CMP, AddressingMode.IMMEDIATE, Register.R0, 0, 0)

            else_lbl = self.get_new_label()
            end_lbl = self.get_new_label()

            self.add_instruction(OpCode.JZ, AddressingMode.IMMEDIATE, 0, 0, else_lbl)
            self.translate_expression(then_branch, local_vars)
            self.add_instruction(OpCode.JMP, AddressingMode.IMMEDIATE, 0, 0, end_lbl)

            self.add_label(else_lbl)
            self.translate_expression(else_branch, local_vars)
            self.add_label(end_lbl)

        # Цикл while: (while cond body)
        elif op == "while":
            cond = expr[1]
            bodies = expr[2:]
            start_lbl = self.get_new_label()
            end_lbl = self.get_new_label()

            self.add_label(start_lbl)
            self.translate_expression(cond, local_vars)
            self.add_instruction(OpCode.CMP, AddressingMode.IMMEDIATE, Register.R0, 0, 0)
            self.add_instruction(OpCode.JZ, AddressingMode.IMMEDIATE, 0, 0, end_lbl)

            # Транслируем каждое выражение в теле цикла по очереди
            for body in bodies:
                self.translate_expression(body, local_vars)

            self.add_instruction(OpCode.JMP, AddressingMode.IMMEDIATE, 0, 0, start_lbl)
            self.add_label(end_lbl)

        # Определение функций
        elif op == "defun":
            func_name, args = expr[1], expr[2]
            bodies = expr[3:]  # Поддерживаем множественные выражения в теле функции

            skip_lbl = self.get_new_label()
            self.add_instruction(OpCode.JMP, AddressingMode.IMMEDIATE, 0, 0, skip_lbl)

            self.add_label(func_name)
            self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.FP)
            self.add_instruction(OpCode.MOV, AddressingMode.REGISTER, Register.FP, Register.SP)

            func_locals = {arg_name: i for i, arg_name in enumerate(args)}
            for body in bodies:
                self.translate_expression(body, func_locals)

            self.add_instruction(OpCode.MOV, AddressingMode.REGISTER, Register.SP, Register.FP)
            self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.FP, 0)
            self.add_instruction(OpCode.RET, AddressingMode.REGISTER, 0, 0)

            self.add_label(skip_lbl)

        # Чтение по динамическому адресу: (load addr)
        elif op == "load":
            self.translate_expression(expr[1], local_vars)  # Оцениваем адрес в R0
            self.add_instruction(OpCode.LOAD, AddressingMode.INDIRECT, Register.R0, Register.R0, 0)

        # Запись по динамическому адресу: (store addr val)
        elif op == "store":
            self.translate_expression(expr[2], local_vars)  # Оцениваем значение в R0
            self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)  # Сохраняем значение на стек
            self.translate_expression(expr[1], local_vars)  # Оцениваем адрес в R0
            self.add_instruction(OpCode.MOV, AddressingMode.REGISTER, Register.R1, Register.R0)  # Адрес переносим в R1
            self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.R0, 0)  # Возвращаем значение в R0
            # Записываем значение R0 по адресу из R1
            self.add_instruction(OpCode.STORE, AddressingMode.INDIRECT, Register.R1, Register.R0, 0)

        # Печать строки из памяти: (print-str addr_or_string)
        elif op == "print-str":
            self.translate_expression(expr[1], local_vars)
            self.add_instruction(OpCode.INT, AddressingMode.IMMEDIATE, 0, 0, 2)

        # Вывод
        elif op == "print":
            arg = expr[1]
            if isinstance(arg, str) and arg not in local_vars and arg not in self.symbol_table:
                # Печать статистической строки
                self.translate_expression(arg, local_vars)
                self.add_instruction(OpCode.INT, AddressingMode.IMMEDIATE, 0, 0,
                                     2)  # INT 2 - системный вызов печати C-строки
            else:
                # Печать числа
                self.translate_expression(arg, local_vars)
                self.add_instruction(OpCode.INT, AddressingMode.IMMEDIATE, 0, 0,
                                     1)  # INT 1 - системный вызов печати числа

        # Векторные операции
        elif op == "vload":
            # (vload V0 addr) -> VLOAD V0, [addr]
            reg_d = getattr(Register, expr[1])
            addr = expr[2]
            self.add_instruction(OpCode.VLOAD, AddressingMode.DIRECT, reg_d, 0, addr)

        elif op == "vstore":
            # (vstore addr V0) -> VSTORE [addr], V0
            addr = expr[1]
            reg_s = getattr(Register, expr[2])
            self.add_instruction(OpCode.VSTORE, AddressingMode.DIRECT, 0, reg_s, addr)

        elif op == "vadd":
            reg_d = getattr(Register, expr[1])
            reg_s = getattr(Register, expr[2])
            self.add_instruction(OpCode.VADD, AddressingMode.REGISTER, reg_d, reg_s)

        # Вызов пользовательских функций
        else:
            args = expr[1:]
            for arg in reversed(args):
                self.translate_expression(arg, local_vars)
                self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)

            self.add_instruction(OpCode.CALL, AddressingMode.IMMEDIATE, 0, 0, op)
            if args:
                self.add_instruction(OpCode.ADD, AddressingMode.IMMEDIATE, Register.SP, 0, len(args) * 4)

    def compile_to_binary(self):
        """Выполняет второй проход компиляции.

        Разрешает символические адреса меток в реальные байтовые смещения
        и упаковывает структуру инструкций в сырые байты.

        Returns:
            Байтовая строка (скомпилированный машинный код).
        """

        binary = b""
        for instr in self.instructions:
            payload_val = None
            if instr.payload is not None:
                if isinstance(instr.payload, str):
                    payload_val = self.labels[instr.payload]
                else:
                    payload_val = instr.payload

            binary += struct.pack('<BBBB', int(instr.opcode), int(instr.mode), int(instr.reg_d), int(instr.reg_s))
            if payload_val is not None:
                binary += struct.pack('<i', payload_val)
        return binary


def main():
    if len(sys.argv) < 3:
        print("Usage: python -m src.translator <input_file.lisp> <output_file.bin>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, "r") as f:
        source = f.read()

    t = Translator()
    tokens = tokenize(source)
    while tokens:
        exp = parse_s_expression(tokens)
        t.translate_expression(exp)

    # Принудительно завершаем программу
    t.add_instruction(OpCode.HALT)

    binary_code = t.compile_to_binary()

    # Упаковываем только реально занятую часть памяти данных
    data_bytes = b""
    for i in range(t.data_ptr):
        data_bytes += struct.pack('<i', t.data_memory[i])

    # Формируем заголовок: [Размер кода (4B)] [Размер данных (4B)]
    header = struct.pack('<II', len(binary_code), len(data_bytes))

    with open(output_file, "wb") as f:
        f.write(header + binary_code + data_bytes)

    print(f"Compilation successful! Saved {len(header) + len(binary_code) + len(data_bytes)} bytes to {output_file}")


if __name__ == "__main__":
    main()
