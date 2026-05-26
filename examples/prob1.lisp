; Определение вспомогательной функции нахождения остатка от деления
(defun mod (a b)
    (- a (* b (/ a b))))

; Главный блок программы
(setq sum 0)
(setq i 1)

(while (< i 1000)
    (if (= (mod i 3) 0)
        (setq sum (+ sum i))
        (if (= (mod i 5) 0)
            (setq sum (+ sum i))
            0))
    (setq i (+ i 1)))

(print sum)