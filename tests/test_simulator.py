import os
import subprocess


def test_hello_world_integration():
    """Тест проверяет сквозную компиляцию и выполнение hello.lisp"""

    # 1. Шаг трансляции
    result_trans = subprocess.run(
        ["python", "-m", "src.translator", "examples/hello.lisp", "test_hello.bin"], capture_output=True, text=True
    )
    assert result_trans.returncode == 0
    assert "Compilation successful!" in result_trans.stdout

    # 2. Шаг симуляции
    result_mach = subprocess.run(["python", "-m", "src.machine", "test_hello.bin"], capture_output=True, text=True)
    assert result_mach.returncode == 0
    # Проверка, что в выводе симулятора есть наша строка
    assert "Simulation finished. Output: Hello, World!" in result_mach.stdout

    # Очистка временного файла
    if os.path.exists("test_hello.bin"):
        os.remove("test_hello.bin")
