"""Модуль транслятора Lisp-подобного языка в бинарный код.

Выполняет токенизацию, построение S-выражений и двухпроходную генерацию
бинарного машинного кода для CISC-архитектуры.
"""

import json
import re
import struct
import sys
from collections.abc import Callable
from typing import Any

from src.isa import DATA_MEMORY_SIZE, MMIO_INPUT, MMIO_OUTPUT, AddressingMode, OpCode, Register


def to_lisp_string(expr: Any) -> str:
    """Рекурсивно преобразует S-выражение обратно в строку формата Lisp"""

    if isinstance(expr, list):
        return "(" + " ".join(to_lisp_string(x) for x in expr) + ")"
    return str(expr)


def tokenize(code: str) -> list[str]:
    """Разбивает исходный код программы на токены.

    Использует регулярные выражения для корректного выделения строк
    в кавычках с пробелами, скобок и символов без нарушения целостности строк.

    Args:
        code: Строка с исходным кодом на Lisp.

    Returns:
        Список строковых токенов.
    """

    # Очистка от комментариев и разбиение с учетом скобок
    code = re.sub(r";.*", "", code)
    # Регулярка ищет строки в кавычках, скобки или любые символы без пробелов
    pattern = r'"(?:[^"\\]|\\.)*"|[()]|[^\s()]+'
    return re.findall(pattern, code)


def parse_s_expression(tokens: list[str]) -> Any:
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
    if token == "(":
        lst: list[Any] = []
        while tokens[0] != ")":
            lst.append(parse_s_expression(tokens))
        tokens.pop(0)  # Удаляем ')'
        return lst
    else:
        try:
            return int(token)
        except ValueError:
            # Если это строка в кавычках - убираем кавычки
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

    def __init__(
        self,
        opcode: OpCode,
        mode: AddressingMode = AddressingMode.REGISTER,
        reg_d: int = 0,
        reg_s: int = 0,
        payload: int | str | None = None,
    ) -> None:
        self.opcode: OpCode = opcode
        self.mode: AddressingMode = mode
        self.reg_d: int = reg_d
        self.reg_s: int = reg_s
        self.payload: int | str | None = payload


class Translator:
    """Двухпроходный компилятор Lisp-кода в CISC машинные инструкции."""

    def __init__(self) -> None:
        """Инициализирует транслятор, резервируя MMIO порты в таблице символов."""

        self.instructions: list[Instruction] = []
        self.labels: dict[str, int] = {}
        self.data_memory: list[int] = [0] * DATA_MEMORY_SIZE
        self.data_ptr: int = 0

        self.symbol_table = {"stdin": MMIO_INPUT, "stdout": MMIO_OUTPUT}
        self.label_counter: int = 0

        self.debug_info: dict[int, str] = {}  # Карта: байтовый адрес -> Lisp-код
        self.current_source: str = ""  # Текущее транслируемое выражение

    def generate_debug_text(self) -> str:
        """Генерирует отладочный текстовый вывод в формате:
        <address> - <HEXCODE> - <mnemonic>
        """

        lines = []
        current_address = 0
        for instr in self.instructions:
            payload_val = None
            if instr.payload is not None:
                if isinstance(instr.payload, str):
                    payload_val = self.labels[instr.payload]
                else:
                    payload_val = instr.payload

            # Временная упаковка одной конкретной инструкции в байты
            instr_bytes = struct.pack("<BBBB", int(instr.opcode), int(instr.mode), int(instr.reg_d), int(instr.reg_s))
            if payload_val is not None:
                instr_bytes += struct.pack("<I", payload_val)

            # Получаем HEX-код команды
            hex_code = instr_bytes.hex()

            # Форматируем мнемонику
            mnemonic = Translator._format_mnemonic(instr, payload_val)

            # Записываем в требуемом формате
            lines.append(f"{current_address} - {hex_code} - {mnemonic}")

            current_address += len(instr_bytes)
        return "\n".join(lines)

    @staticmethod
    def _format_mnemonic(instr: Instruction, payload_val: int | None) -> str:
        """Преобразует бинарную инструкцию в читаемую ассемблерную мнемонику"""

        op_name = instr.opcode.name.lower()
        reg_d_name = Register(instr.reg_d).name.lower()
        reg_s_name = Register(instr.reg_s).name.lower()

        if instr.mode == AddressingMode.REGISTER:
            return Translator._format_register_mode(instr, op_name, reg_d_name, reg_s_name)
        elif instr.mode == AddressingMode.IMMEDIATE:
            return Translator._format_immediate_mode(instr, op_name, reg_d_name, payload_val)
        elif instr.mode == AddressingMode.DIRECT:
            return Translator._format_direct_mode(instr, op_name, reg_d_name, reg_s_name, payload_val)
        elif instr.mode == AddressingMode.INDIRECT:
            return Translator._format_indirect_mode(instr, op_name, reg_d_name, reg_s_name, payload_val)

        return op_name

    @staticmethod
    def _format_register_mode(instr: Instruction, op_name: str, reg_d: str, reg_s: str) -> str:
        """Вспомогательный метод форматирования для регистровой адресации"""

        if instr.opcode in (OpCode.PUSH, OpCode.POP):
            reg = reg_s if instr.opcode == OpCode.PUSH else reg_d
            return f"{op_name} {reg}"
        if instr.opcode in (OpCode.RET, OpCode.IRET, OpCode.HALT):
            return op_name
        return f"{op_name} {reg_d}, {reg_s}"

    @staticmethod
    def _format_immediate_mode(instr: Instruction, op_name: str, reg_d: str, payload: int | None) -> str:
        """Вспомогательный метод форматирования для непосредственной адресации"""

        val = f"#{payload}" if payload is not None else ""
        if instr.opcode in (OpCode.JMP, OpCode.JZ, OpCode.JL, OpCode.CALL):
            return f"{op_name} {payload if payload is not None else ''}"
        return f"{op_name} {reg_d}, {val}"

    @staticmethod
    def _format_direct_mode(instr: Instruction, op_name: str, reg_d: str, reg_s: str, payload: int | None) -> str:
        """Вспомогательный метод форматирования для прямой адресации"""

        addr = f"[{payload}]" if payload is not None else ""
        if instr.opcode == OpCode.STORE:
            return f"{op_name} {addr}, {reg_s}"
        if instr.opcode in (OpCode.VLOAD, OpCode.VSTORE):
            vreg = reg_d if instr.opcode == OpCode.VLOAD else reg_s
            return f"{op_name} {vreg}, {addr}"
        return f"{op_name} {reg_d}, {addr}"

    @staticmethod
    def _format_indirect_mode(instr: Instruction, op_name: str, reg_d: str, reg_s: str, payload: int | None) -> str:
        """Вспомогательный метод форматирования для косвенной адресации"""

        offset = f"{payload}" if payload is not None else "0"
        if instr.opcode == OpCode.STORE:
            return f"{op_name} [{reg_d} + {offset}], {reg_s}"
        return f"{op_name} {reg_d}, [{reg_s} + {offset}]"

    def get_new_label(self) -> str:
        """Генерирует уникальное имя метки для условных переходов и циклов.

        Returns:
            Строковое имя метки (например, "L_1").
        """

        self.label_counter += 1
        return f"L_{self.label_counter}"

    def get_current_address(self) -> int:
        """Вычисляет текущий байтовый адрес в памяти команд.

        Каждая инструкция занимает 4 байта (без payload) или 8 байт (с payload).

        Returns:
            Адрес следующей инструкции в байтах.
        """

        addr = 0
        for instr in self.instructions:
            addr += 8 if instr.payload is not None else 4
        return addr

    def add_instruction(
        self,
        opcode: OpCode,
        mode: AddressingMode = AddressingMode.REGISTER,
        reg_d: int = 0,
        reg_s: int = 0,
        payload: int | str | None = None,
    ) -> None:
        """Добавляет промежуточную инструкцию в список для последующей компиляции.

        Фиксирует метаданные инструкции (опкод, режим адресации, используемые регистры
        и полезную нагрузку), а также связывает её текущий байтовый адрес с активным
        исходным Lisp-выражением для генерации карты отладочных символов.

        Args:
            opcode: Код операции (OpCode), определяющий тип выполняемого микродействия.
            mode: Режим адресации (AddressingMode), указывающий способ извлечения операндов.
            reg_d: Индекс целевого регистра (Destination Register), куда пишется результат
                или который используется как базовый при косвенной записи STORE.
            reg_s: Индекс регистра-источника (Source Register) для правого операнда ALU,
                содержимого для записи STORE или базового при косвенном чтении LOAD.
            payload: Дополнительная 32-битная полезная нагрузка. Может быть числовой
                константой, прямым адресом ОЗУ, смещением или строковой меткой перехода,
                разрешаемой на втором проходе компиляции.
        """

        # Записываем отладочную информацию для текущего байтового адреса перед добавлением
        addr = self.get_current_address()
        self.debug_info[addr] = self.current_source

        instr = Instruction(opcode, mode, reg_d, reg_s, payload)
        self.instructions.append(instr)

    def add_label(self, label_name: str) -> None:
        """Связывает имя метки с текущим байтовым адресом в памяти команд."""

        self.labels[label_name] = self.get_current_address()

    def allocate_string(self, string: str) -> int:
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

    def translate_expression(self, expr: Any, local_vars: dict[str, int] | None = None) -> None:
        """Рекурсивно транслирует S-выражение в последовательность инструкций.

        Args:
            expr: Выражение (список, строка или число).
            local_vars: Словарь аргументов текущей функции для доступа относительно FP.
        """

        if local_vars is None:
            local_vars = {}

        # Запоминаем текущее выражение для генератора инструкций
        self.current_source = to_lisp_string(expr)

        if isinstance(expr, int):
            self.add_instruction(OpCode.MOV, AddressingMode.IMMEDIATE, Register.R0, 0, expr)
            return

        if isinstance(expr, str):
            self._translate_variable(expr, local_vars)
            return

        if not isinstance(expr, list) or len(expr) == 0:
            return

        op = expr[0]

        # Диспетчеризация через словарь методов
        handlers: dict[str, Callable[[Any, Any], None]] = {
            "setq": self._translate_setq,
            "+": self._translate_arithmetic,
            "-": self._translate_arithmetic,
            "*": self._translate_arithmetic,
            "/": self._translate_arithmetic,
            "=": self._translate_comparison,
            "<": self._translate_comparison,
            "if": self._translate_if,
            "while": self._translate_while,
            "defun": self._translate_defun,
            "definterrupt": self._translate_definterrupt,
            "print": self._translate_print,
            "vload": self._translate_vload,
            "vstore": self._translate_vstore,
            "vadd": self._translate_vadd,
            "vsub": self._translate_vsub,
            "vmul": self._translate_vmul,
            "vdiv": self._translate_vdiv,
            "vcmp": self._translate_vcmp,
            "begin": self._translate_begin,
            "progn": self._translate_begin,
            "load": self._translate_load,
            "store": self._translate_store,
            "print-str": self._translate_print_str,
        }

        if op in handlers:
            handlers[op](expr, local_vars)
        else:
            self._translate_call(expr, local_vars)

    def _translate_variable(self, expr: str, local_vars: dict[str, int]) -> None:
        """Транслирует обращение к переменной.

        Определяет область видимости переменной (локальная во фрейме FP или глобальная)
        и генерирует соответствующую команду загрузки LOAD. Если переменная не найдена,
        трактует её как статический строковый литерал.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

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

    def _translate_setq(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует операцию присваивания значения переменной (setq var val).

        Проверяет область видимости: если переменная локальная (в local_vars),
        генерирует косвенную запись на стек [FP + offset]. Если глобальная -
        записывает в статическую память данных по прямому адресу.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        var_name, val = expr[1], expr[2]
        self.translate_expression(val, local_vars)  # Результат вычисления в R0

        # Если переменная локальная (аргумент функции)
        if var_name in local_vars:
            arg_idx = local_vars[var_name]
            offset = 8 + arg_idx * 4
            # Записываем значение R0 на стек по адресу [FP + offset]
            self.add_instruction(OpCode.STORE, AddressingMode.INDIRECT, Register.FP, Register.R0, offset)
        else:
            # Если переменная глобальная
            if var_name not in self.symbol_table:
                self.symbol_table[var_name] = self.data_ptr
                self.data_ptr += 1
            self.add_instruction(OpCode.STORE, AddressingMode.DIRECT, 0, Register.R0, self.symbol_table[var_name])

    def _translate_binary_operands(self, expr: list, local_vars: dict[str, int]) -> None:
        """Вычисляет два операнда бинарной операции и подготавливает регистры.

        Оценивает левый операнд (результат в R0), временно сохраняет его на стек,
        затем оценивает правый операнд (результат в R0) и извлекает левый обратно в R1.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        self.translate_expression(expr[1], local_vars)
        self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)
        self.translate_expression(expr[2], local_vars)
        self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.R1, 0)

    def _translate_arithmetic(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует базовые математические операции (+, -, *, /).

        Использует _translate_binary_operands и выполняет соответствующее вычисление в ALU.
        Включает оптимизацию непосредственного сложения (ADD Rd, #imm) для
        избежания накладных расходов стека при сложении с константой.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        op = expr[0]

        # Оптимизация: если складываем с числовым литералом справа: (+ x 5)
        if op == "+" and isinstance(expr[2], int):
            self.translate_expression(expr[1], local_vars)  # Левый операнд в R0
            self.add_instruction(OpCode.ADD, AddressingMode.IMMEDIATE, Register.R0, 0, expr[2])
            return

        # Оптимизация: если складываем с числовым литералом слева: (+ 5 x)
        if op == "+" and isinstance(expr[1], int):
            self.translate_expression(expr[2], local_vars)  # Правый операнд в R0
            self.add_instruction(OpCode.ADD, AddressingMode.IMMEDIATE, Register.R0, 0, expr[1])
            return

        # Вычисляем операнды для всех остальных случаев и будем вычислять через регистры
        self._translate_binary_operands(expr, local_vars)
        opcode_map = {"+": OpCode.ADD, "-": OpCode.SUB, "*": OpCode.MUL, "/": OpCode.DIV}
        self.add_instruction(opcode_map[op], AddressingMode.REGISTER, Register.R0, Register.R1)

    def _translate_comparison(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует операции сравнения (=, <).

        Сравнивает левый и правый операнды с помощью команды CMP, выполняет
        условный переход (JZ или JL) и возвращает логическое значение (1 или 0) в R0.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        op = expr[0]
        # Вычисляем операнды
        self._translate_binary_operands(expr, local_vars)
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

    def _translate_if(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует условный оператор (if cond then else).

        Вычисляет условие cond, сравнивает результат с нулем и генерирует
        условный переход JZ на ветку else в случае ложного условия.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

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

    def _translate_while(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует цикл (while cond body1 body2 ...).

        Создает метки начала и конца цикла, на каждом шаге вычисляет cond
        и осуществляет переход к концу при ложном условии. Последовательно
        транслирует все выражения внутри тела цикла.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        cond = expr[1]
        bodies = expr[2:]
        start_lbl = self.get_new_label()
        end_lbl = self.get_new_label()

        self.add_label(start_lbl)
        self.translate_expression(cond, local_vars)
        self.add_instruction(OpCode.CMP, AddressingMode.IMMEDIATE, Register.R0, 0, 0)
        self.add_instruction(OpCode.JZ, AddressingMode.IMMEDIATE, 0, 0, end_lbl)

        for body in bodies:
            self.translate_expression(body, local_vars)

        self.add_instruction(OpCode.JMP, AddressingMode.IMMEDIATE, 0, 0, start_lbl)
        self.add_label(end_lbl)

    def _translate_defun(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует объявление функции (defun name (args) body1 body2 ...).

        Генерирует обход тела функции JMP при линейном выполнении кода,
        создает пролог фрейма стека (сохранение FP, MOV FP, SP), транслирует
        тело с локальным словарем аргументов и генерирует эпилог с возвратом RET.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """

        func_name, args = expr[1], expr[2]
        bodies = expr[3:]

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

    def _translate_definterrupt(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует обработчик прерывания.

        В отличие от обычной функции, он компилируется без пролога/эпилога FP
        и принудительно завершается командой IRET.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        func_name = expr[1]
        bodies = expr[2:]

        skip_lbl = self.get_new_label()
        self.add_instruction(OpCode.JMP, AddressingMode.IMMEDIATE, 0, 0, skip_lbl)

        self.add_label(func_name)

        # Сохраняем контекст регистров R0 и R1 на стек
        self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)
        self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R1)

        for body in bodies:
            self.translate_expression(body, local_vars)

        # Восстанавливаем контекст регистров R1 и R0 со стека в обратном порядке
        self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.R1, 0)
        self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.R0, 0)

        self.add_instruction(OpCode.IRET, AddressingMode.REGISTER, 0, 0)
        self.add_label(skip_lbl)

    def _translate_print(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует системную операцию вывода (print expr).

        Анализирует тип аргумента: если это статический строковый литерал,
        использует прерывание печати строки (INT 2), иначе - печать числа (INT 1).

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        arg = expr[1]
        if isinstance(arg, str) and arg not in local_vars and arg not in self.symbol_table:
            self.translate_expression(arg, local_vars)
            self.add_instruction(OpCode.INT, AddressingMode.IMMEDIATE, 0, 0, 2)
        else:
            self.translate_expression(arg, local_vars)
            self.add_instruction(OpCode.INT, AddressingMode.IMMEDIATE, 0, 0, 1)

    def _translate_vload(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует команду загрузки вектора из памяти (vload V_reg addr).

        Генерирует векторную инструкцию VLOAD для переноса данных из DIRECT-памяти.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """

        reg_d = getattr(Register, expr[1])
        addr = expr[2]
        self.add_instruction(OpCode.VLOAD, AddressingMode.DIRECT, reg_d, 0, addr)

    def _translate_vstore(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует команду сохранения вектора в память (vstore addr V_reg).

        Генерирует векторную инструкцию VSTORE для сохранения данных из векторного регистра.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """

        addr = expr[1]
        reg_s = getattr(Register, expr[2])
        self.add_instruction(OpCode.VSTORE, AddressingMode.DIRECT, 0, reg_s, addr)

    def _translate_vadd(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует сложение векторных регистров (vadd V_dest V_src).

        Генерирует поэлементную векторную инструкцию VADD.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """

        reg_d = getattr(Register, expr[1])
        reg_s = getattr(Register, expr[2])
        self.add_instruction(OpCode.VADD, AddressingMode.REGISTER, reg_d, reg_s)

    def _translate_vsub(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует вычитание векторных регистров (vsub V_dest V_src).

        Генерирует поэлементную векторную инструкцию VSUB.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """

        reg_d = getattr(Register, expr[1])
        reg_s = getattr(Register, expr[2])
        self.add_instruction(OpCode.VSUB, AddressingMode.REGISTER, reg_d, reg_s)

    def _translate_vmul(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует умножение векторных регистров (vmul V_dest V_src).

        Генерирует поэлементную векторную инструкцию VMUL.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """
        reg_d = getattr(Register, expr[1])
        reg_s = getattr(Register, expr[2])
        self.add_instruction(OpCode.VMUL, AddressingMode.REGISTER, reg_d, reg_s)

    def _translate_vdiv(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует деление векторных регистров (vdiv V_dest V_src).

        Генерирует поэлементную векторную инструкцию VDIV.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """
        reg_d = getattr(Register, expr[1])
        reg_s = getattr(Register, expr[2])
        self.add_instruction(OpCode.VDIV, AddressingMode.REGISTER, reg_d, reg_s)

    def _translate_vcmp(self, expr: list, _local_vars: dict[str, int]) -> None:
        """Транслирует сравнение векторных регистров (vcmp V_dest V_src).

        Генерирует поэлементную векторную инструкцию VCMP.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
        """
        reg_d = getattr(Register, expr[1])
        reg_s = getattr(Register, expr[2])
        self.add_instruction(OpCode.VCMP, AddressingMode.REGISTER, reg_d, reg_s)

    def _translate_begin(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует блок последовательного выполнения выражений (begin/progn ...).

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        for sub_expr in expr[1:]:
            self.translate_expression(sub_expr, local_vars)

    def _translate_load(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует примитив чтения по динамическому адресу (load addr_expr).

        Оценивает выражение адреса и выполняет косвенное чтение из памяти через LOAD.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        self.translate_expression(expr[1], local_vars)
        self.add_instruction(OpCode.LOAD, AddressingMode.INDIRECT, Register.R0, Register.R0, 0)

    def _translate_store(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует примитив записи по динамическому адресу (store addr_expr val_expr).

        Оценивает значение и адрес, после чего выполняет косвенную запись в память через STORE.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        self.translate_expression(expr[2], local_vars)
        self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)
        self.translate_expression(expr[1], local_vars)
        self.add_instruction(OpCode.MOV, AddressingMode.REGISTER, Register.R1, Register.R0)
        self.add_instruction(OpCode.POP, AddressingMode.REGISTER, Register.R0, 0)
        self.add_instruction(OpCode.STORE, AddressingMode.INDIRECT, Register.R1, Register.R0, 0)

    def _translate_print_str(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует явную команду вывода строки по адресу (print-str addr_expr).

        Вычисляет адрес начала строки и инициирует прерывание INT 2.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        self.translate_expression(expr[1], local_vars)
        self.add_instruction(OpCode.INT, AddressingMode.IMMEDIATE, 0, 0, 2)

    def _translate_call(self, expr: list, local_vars: dict[str, int]) -> None:
        """Транслирует вызов пользовательской функции.

        Вычисляет аргументы в обратном порядке, помещает их на стек через PUSH,
        вызывает функцию через CALL и выполняет очистку стека аргументов после возврата.

        Args:
            expr: Список, представляющий дерево S-выражения текущей операции
                (например, ['setq', 'x', 10] или ['+', 'i', 1]). Первый элемент
                всегда содержит имя оператора.
            local_vars: Словарь вида {имя_переменной: индекс_аргумента}, сопоставляющий
                локальные параметры текущей функции с их индексами на стеке для
                генерации косвенной адресации относительно регистра кадра FP.
        """

        op = expr[0]
        args = expr[1:]
        for arg in reversed(args):
            self.translate_expression(arg, local_vars)
            self.add_instruction(OpCode.PUSH, AddressingMode.REGISTER, 0, Register.R0)
        self.add_instruction(OpCode.CALL, AddressingMode.IMMEDIATE, 0, 0, op)
        if args:
            self.add_instruction(OpCode.ADD, AddressingMode.IMMEDIATE, Register.SP, 0, len(args) * 4)

    def compile_to_binary(self) -> bytes:
        """Выполняет второй проход компиляции.

        Разрешает символические адреса меток в реальные байтовые смещения
        и упаковывает структуру инструкций в сырые байты.

        Returns:
            Байтовая строка (скомпилированный машинный код).
        """

        binary = b""
        for instr in self.instructions:
            payload_val: int | None = None
            if instr.payload is not None:
                # Если в полезной нагрузке текстовая метка,
                # заменяем её числовым байтовым адресом перехода
                if isinstance(instr.payload, str):
                    payload_val = self.labels[instr.payload]
                else:
                    payload_val = instr.payload

            # Формирование 4-байтового заголовка: [OpCode (1B)] [AddressingMode (1B)] [RegDest (1B)] [RegSrc (1B)]
            binary += struct.pack("<BBBB", int(instr.opcode), int(instr.mode), int(instr.reg_d), int(instr.reg_s))

            # Если требуется, упаковываем 4-байтовый payload в Little-Endian ('<I')
            if payload_val is not None:
                binary += struct.pack("<I", payload_val)
        return binary


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m src.translator <input_file.lisp> <output_file.bin>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, encoding="utf-8") as f:
        source = f.read()

    t = Translator()
    tokens = tokenize(source)
    while tokens:
        exp = parse_s_expression(tokens)
        t.translate_expression(exp)

    # Принудительно завершаем программу
    t.add_instruction(OpCode.HALT)

    # Вызываем второй проход компиляции (формируем байт-код инструкций)
    binary_code = t.compile_to_binary()

    # Определяем вектор прерывания
    intr_vector = 0
    if "interrupt_handler" in t.labels:
        intr_vector = t.labels["interrupt_handler"]

    # Упаковываем только реально занятую часть памяти данных
    data_bytes = b""
    for i in range(t.data_ptr):
        data_bytes += struct.pack("<I", t.data_memory[i])

    # Формируем заголовок: [Размер кода (4B)] [Размер данных (4B)] [Вектор прерывания (4B)]
    header = struct.pack("<III", len(binary_code), len(data_bytes), intr_vector)

    with open(output_file, "wb") as f:
        # header (12 байт заголовка секций) + binary_code (секция кода) + data_bytes (секция данных)
        f.write(header + binary_code + data_bytes)

    # Генерируем отладочный текстовый дамп мнемоник
    debug_text = t.generate_debug_text()
    txt_file = output_file + ".txt"
    with open(txt_file, "w", encoding="utf-8") as f_txt:
        f_txt.write(debug_text)

    # Сохраняем отладочную карту в JSON-файл
    debug_file = output_file + ".dbg"
    with open(debug_file, "w", encoding="utf-8") as f_debug:
        json.dump(t.debug_info, f_debug, indent=4)

    print(f"Compilation successful! Saved {len(header) + len(binary_code) + len(data_bytes)} bytes to {output_file}")


if __name__ == "__main__":
    main()
