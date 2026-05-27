; Массив A по адресу 200: [100, 200, 300, 400]
(store 200 100)
(store 201 200)
(store 202 300)
(store 203 400)

; Массив B по адресу 300: [10, 20, 30, 40]
(store 300 10)
(store 301 20)
(store 302 30)
(store 303 40)

; Массив C по адресу 350: [10, 25, 30, 45] (для теста поэлементного сравнения)
(store 350 10)
(store 351 25)
(store 352 30)
(store 353 45)


; Загружаем исходные данные в векторные регистры V0, V1 и V3
(vload V0 200)
(vload V1 300)
(vload V3 350)

; Тест VADD (Сложение): V2 = V0 + V1 -> [110, 220, 330, 440]
(vload V2 200)
(vadd V2 V1)
(vstore 400 V2)

; Тест VSUB (Вычитание): V2 = V0 - V1 -> [90, 180, 270, 360]
(vload V2 200)
(vsub V2 V1)
(vstore 410 V2)

; Тест VMUL (Умножение): V2 = V0 * V1 -> [1000, 4000, 9000, 16000]
(vload V2 200)
(vmul V2 V1)
(vstore 420 V2)

; Тест VDIV (Деление): V2 = V0 / V1 -> [10, 10, 10, 10]
(vload V2 200)
(vdiv V2 V1)
(vstore 430 V2)

; Тест VCMP (Поэлементное сравнение): V1 = V1 == V3
; Сравниваем [10, 20, 30, 40] и [10, 25, 30, 45] -> [1, 0, 1, 0]
(vcmp V1 V3)
(vstore 440 V1)

(print "VADD: ")
(print (load 400)) (print " ") (print (load 401)) (print " ") (print (load 402)) (print " ") (print (load 403))
(print "  ")

(print "VSUB: ")
(print (load 410)) (print " ") (print (load 411)) (print " ") (print (load 412)) (print " ") (print (load 413))
(print "  ")

(print "VMUL: ")
(print (load 420)) (print " ") (print (load 421)) (print " ") (print (load 422)) (print " ") (print (load 423))
(print "  ")

(print "VDIV: ")
(print (load 430)) (print " ") (print (load 431)) (print " ") (print (load 432)) (print " ") (print (load 433))
(print "  ")

(print "VCMP: ")
(print (load 440)) (print " ") (print (load 441)) (print " ") (print (load 442)) (print " ") (print (load 443))