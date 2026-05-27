; Инициализация вектора A по адресу 200
(store 200 10)
(store 201 20)
(store 202 30)
(store 203 40)

; Инициализация вектора B по адресу 300
(store 300 5)
(store 301 4)
(store 302 3)
(store 303 2)

; Загрузка в векторные регистры
(vload V0 200)
(vload V1 300)

; Сложение векторов V0 = V0 + V1
(vadd V0 V1)

; Сохранение результирующего вектора по адресу 400
(vstore 400 V0)

; Вывод результатов
(print (load 400))
(print " ")
(print (load 401))
(print " ")
(print (load 402))
(print " ")
(print (load 403))
(print " ")