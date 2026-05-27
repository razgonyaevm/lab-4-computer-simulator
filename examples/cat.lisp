; Программа CAT: копирует вывод и вывод до конца файла (EOF / 0)
(setq char stdin)

(while char
    (setq stdout char)
    (setq char stdin))