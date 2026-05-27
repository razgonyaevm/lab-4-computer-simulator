; 64-битная арифметика на 32-битном процессоре

(defun add64-low (al bl)
  (+ al bl)) ; Автоматически переполнится до 32 бит

(defun add64-carry (al bl res_low)
  ; Если сумма меньше одного из слагаемых, то произошел перенос (unsigned overflow)
  (if (< res_low al) 1 0))

(defun add64-high (ah bh carry)
  (+ (+ ah bh) carry))

; Инициализация чисел
(setq x_high 0)
(setq x_low 3000000000)

(setq y_high 0)
(setq y_low 2000000000)

; Вычисления
(setq res_low (add64-low x_low y_low))
(setq carry (add64-carry x_low y_low res_low))
(setq res_high (add64-high x_high y_high carry))

; Печать результата
(print "Result High: ")
(print res_high)
(print " Low: ")
(print res_low)