; Демонстрация прерываний TRAP

(definterrupt interrupt_handler
    (begin
        (setq input_val stdin)
        (setq stdout input_val)))


; Фоновый бесконечный цикл
(while 1
    0)
