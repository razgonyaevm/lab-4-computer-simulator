import os
import subprocess


def run_pipeline(lisp_file, input_content=None, schedule_content=None, expected_output=None):
    """Вспомогательная функция для прохождения полного цикла компиляции и симуляции."""

    bin_file = "temp_program.bin"
    input_file = "temp_input.txt"
    schedule_file = "temp_schedule.txt"
    log_file = "temp_simulation.log"

    try:
        # 1. Шаг трансляции
        res_trans = subprocess.run(
            ["python", "-m", "src.translator", lisp_file, bin_file], capture_output=True, text=True
        )

        assert res_trans.returncode == 0, f"Translation failed: {res_trans.stderr}"

        # Формируем команду запуска симуляции с логированием во временный файл
        cmd = ["python", "-m", "src.machine", bin_file, "--log", log_file]

        # 2. Если есть входные данные, сохраняем их во временный файл ввода
        if input_content is not None:
            with open(input_file, "w", encoding="utf-8") as f:
                f.write(input_content)
            cmd += ["--input", input_file]

        # 3. Если есть расписание прерываний, сохраняем во временный файл
        if schedule_content is not None:
            with open(schedule_file, "w", encoding="utf-8") as f:
                f.write(schedule_content)
            cmd += ["--schedule", schedule_file]

        # 4. Шаг симуляции
        res_mach = subprocess.run(cmd, capture_output=True, text=True)

        assert res_mach.returncode == 0, f"Simulation failed: {res_mach.stderr}"

        # 5. Проверяем вывод симулятора
        if expected_output is not None:
            assert expected_output in res_mach.stdout, (
                f"Expected '{expected_output}' not found in stdout: '{res_mach.stdout}'"
            )
    finally:
        # Очистка всех временных файлов
        for temp_file in (bin_file, input_file, log_file, schedule_file):
            if os.path.exists(temp_file):
                os.remove(temp_file)


def test_hello_world():
    """Тест программы вывода статической строки."""
    run_pipeline("examples/hello.lisp", expected_output="Hello, World!")


def test_cat_stream():
    """Тест программы копирования потока ввода в вывод."""
    test_str = "Integration testing of MMIO Stream processing!"
    run_pipeline("examples/cat.lisp", input_content=test_str, expected_output=test_str)


def test_hello_user_name():
    """Тест интерактивного ввода имени и вывода приветствия."""
    run_pipeline(
        "examples/hello_user_name.lisp", input_content="Maxim\n", expected_output="What is your name? Hello, Maxim!"
    )


def test_sort_algorithm():
    """Тест математической сортировки чисел."""
    run_pipeline("examples/sort_numbers.lisp", input_content="95 21 100 8 3", expected_output="3 8 21 95 100")


def test_sort_ascii():
    """Тест на сортировку цифр и вывод в ascii коде"""
    run_pipeline("examples/sort_ascii.lisp", input_content="9521738", expected_output="49 50 51 53 55 56 57")


def test_math64_double_precision():
    """Тест 64-битного сложения с переполнением."""
    run_pipeline("examples/math64.lisp", expected_output="Result High: 1 Low: 705032704")


def test_project_euler_problem_1():
    """Тест решения задачи по варианту"""
    run_pipeline("examples/prob1.lisp", expected_output="233168")


def test_interrupt_integration():
    """Интеграционный тест для проверки прерываний TRAP по расписанию."""
    schedule_data = "30,Y\n60,e\n90,s\n"

    run_pipeline(lisp_file="examples/trap_demo.lisp", schedule_content=schedule_data, expected_output="Yes")


def test_vector_benchmark_integration():
    """Интеграционный тест для проверки векторных (SIMD) вычислений."""
    expected_result = (
        "VADD: 110 220 330 440  VSUB: 90 180 270 360  VMUL: 1000 4000 9000 16000  VDIV: 10 10 10 10  VCMP: 1 0 1 0"
    )
    run_pipeline(lisp_file="examples/vector_benchmark.lisp", expected_output=expected_result)
