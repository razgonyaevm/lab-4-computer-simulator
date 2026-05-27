; Выводим приглашение
(print "What is your name? ")

(setq char stdin)
(setq addr 100) ; Начало буфера для хранения имени

; Читаем имя, пока не встретим Enter (10) или EOF (0)
; if проверяет: если char == 10 то 0, если char == 0 то 0, иначе 1
(while (if (= char 10) 0 (if (= char 0) 0 1))
    (store addr char)
    (setq addr (+ addr 1))
    (setq char stdin))

(store addr 0) ; Закрываем строку нулем (null-terminator)

; Выводим приветствие
(print "Hello, ")
(print-str 100) ; Печатаем строку, лежащую по адресу 100
(print "!")