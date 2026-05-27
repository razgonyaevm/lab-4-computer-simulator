; Чтение массива чисел из ввода
(setq num stdin)
(setq addr 100) ; Начало массива в памяти

(while num
    (store addr num)
    (setq addr (+ addr 1))
    (setq num stdin))

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
                ; Обновляем локальную копию val_i для дальнейшего сравнения в цикле
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
