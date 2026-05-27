; Функция чтения целого многозначного числа из stdin
(defun read-int ()
  (begin
      (setq val 0)
      (setq c stdin)

      ; Пропускаем пробелы (32) и переносы строк (10)
      (while (if (= c 32) 1 (if (= c 10) 1 0))
        (setq c stdin))

      ; Считываем цифры (ASCII коды от 48 до 57)
      (while (if (< c 48) 0 (if (< c 58) 1 0))
        (begin
            (setq val (+ (* val 10) (- c 48)))
            (setq c stdin)))
      val)) ; возвращаемое значение из общего begin

; Чтение массива чисел из ввода с помощью функции
(setq num (read-int))
(setq addr 100)

(while num
    (store addr num)
    (setq addr (+ addr 1))
    (setq num (read-int)))

(setq end_addr addr) ; Запоминаем конец массива

; Сортировка выбором
(setq i 100)
(while (< i end_addr)
    (setq j (+ i 1))
    (while (< j end_addr)
        (setq val_i (load i))
        (setq val_j (load j))
        (if (< val_j val_i)
            (begin
                (store i val_j)
                (store j val_i)
                (setq val_i val_j))
            0)
        (setq j (+ j 1)))
    (setq i (+ i 1)))

; Вывод отсортированного массива чисел
(setq i 100)
(while (< i end_addr)
    (print (load i))
    (print " ")
    (setq i (+ i 1)))