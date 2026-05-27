; Находит наибольший палиндром, полученный произведением двух 3-значных чисел


; Функция реверсирования числа (инлайнит остаток от деления для экономии тактов)
(defun reverse_num (n)
    (begin
        (setq rev 0)
        (while (< 0 n)
            (begin
                ; Инлайнинг остатка: d = n - 10 * (n / 10)
                (setq d (- n (* 10 (/ n 10))))
                (setq rev (+ (* rev 10) d))
                (setq n (/ n 10))))
        rev))

; Проверка числа на палиндромность
(defun is_palindrome (n)
    (= n (reverse_num n)))

; Основной алгоритм обратного поиска
(setq max_pal 900000)
(setq i 999)

; Оптимизация внешнего цикла: если i * 999 <= max_pal, то продолжать поиск бессмысленно
(while (if (< 99 i) (< max_pal (* i 999)) 0)
    (begin
        (setq j 999)
        (while (< max_pal (* i j))
            (begin
                (setq prod (* i j))
                (if (is_palindrome prod)
                    (setq max_pal prod)
                    0)
                (setq j (- j 1))))
        (setq i (- i 1))))

(print "Largest Palindrome: ")
(print max_pal)