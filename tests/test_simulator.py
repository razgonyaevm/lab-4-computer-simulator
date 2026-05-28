"""Модуль автоматического интеграционного тестирования процессора.

Реализует декларативный прогон Golden-тестов на основе конфигурационных файлов YAML.
"""

import os
import subprocess

import pytest
import yaml

# Единый блок конфигурации временных файлов
TEMP_LISP = "temp_program.lisp"
TEMP_BIN = "temp_program.bin"
TEMP_INPUT = "temp_input.txt"
TEMP_SCHEDULE = "temp_schedule.txt"
TEMP_LOG = "temp_simulation.log"
TEMP_DBG = f"{TEMP_BIN}.dbg"
TEMP_TXT = f"{TEMP_BIN}.txt"

GOLDEN_DIR = "golden"


def get_golden_tests() -> list[str]:
    """Автоматически находит все файлы конфигураций тестов в папке golden/."""

    if os.path.exists(GOLDEN_DIR):
        return sorted([f for f in os.listdir(GOLDEN_DIR) if f.endswith((".yaml", ".yml"))])
    return []


@pytest.mark.parametrize("golden_file", get_golden_tests())
def test_golden_scenarios(golden_file: str) -> None:
    """Универсальный параметризованный тест для прогона Golden-сценариев."""

    filepath = os.path.join(GOLDEN_DIR, golden_file)
    with open(filepath, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    try:
        # 1. Записываем Lisp-код из YAML во временный файл
        with open(TEMP_LISP, "w", encoding="utf-8") as f_lisp:
            f_lisp.write(config["source_code"])

        # 2. Шаг трансляции
        res_trans = subprocess.run(
            ["python", "-m", "src.translator", TEMP_LISP, TEMP_BIN], capture_output=True, text=True, check=True
        )
        assert res_trans.returncode == 0

        # 3. Сверяем сгенерированное бинарное дизассемблирование
        with open(TEMP_TXT, encoding="utf-8") as f_disasm:
            actual_disasm = f_disasm.read()
        assert actual_disasm.strip() == config["disassembly"].strip()

        # 4. Подготавливаем аргументы запуска симулятора
        is_heavy = "prob1" in golden_file
        limit_val = 5000000 if is_heavy else 10000
        cmd = ["python", "-m", "src.machine", TEMP_BIN, "--log", TEMP_LOG, "--limit", str(limit_val)]

        # Для легких тестов включаем debug, чтобы тестить потактово
        if not is_heavy:
            cmd.append("--debug")

        # Опционально подключаем файлы ввода и расписания
        if config.get("input"):
            with open(TEMP_INPUT, "w", encoding="utf-8") as f_in:
                f_in.write(config["input"])
            cmd += ["--input", TEMP_INPUT]

        if config.get("schedule"):
            with open(TEMP_SCHEDULE, "w", encoding="utf-8") as f_sch:
                f_sch.write(config["schedule"])
            cmd += ["--schedule", TEMP_SCHEDULE]

        # 5. Шаг симуляции
        res_mach = subprocess.run(cmd, capture_output=True, text=True, check=True)
        assert res_mach.returncode == 0

        # 6. Сверяем вывод в консоль (stdout)
        assert config["expected_stdout"].strip() in res_mach.stdout.strip()

        # 7. Сверяем ключевые вехи потактового журнала
        with open(TEMP_LOG, encoding="utf-8") as f_log:
            actual_log = f_log.read()

        for expected_line in config["log_journal"].strip().splitlines():
            if expected_line.strip():
                assert expected_line.strip() in actual_log

    finally:
        # Централизованная очистка абсолютно всех созданных файлов
        for file in (TEMP_LISP, TEMP_BIN, TEMP_DBG, TEMP_TXT, TEMP_INPUT, TEMP_SCHEDULE, TEMP_LOG):
            if os.path.exists(file):
                os.remove(file)
