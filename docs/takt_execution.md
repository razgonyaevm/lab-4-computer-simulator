# Потактовое выполнение инструкций процессора (Takt-by-Takt)

* [Обозначения сигналов и шин на схеме](#обозначения-сигналов-и-шин-на-схеме)
* [Общие фазы](#i-общие-фазы-выборка-и-декодирование)
    * [1. Фаза Fetch (выборка заголовка инструкции) - Такт 1 (T1)](#1-фаза-fetch-выборка-заголовка-инструкции---такт-1-t1)
    * [2. Фаза Fetch Payload (Выборка полезной нагрузки) - Такт 2 (T2)](#2-фаза-fetch-payload-выборка-полезной-нагрузки---такт-2-t2)
* [Инструкции управления данными](#ii-инструкции-управления-данными)
    * [1. `MOV` (MOV DST, SRC / #imm)](#1-mov-mov-dst-src--imm)
    * [2. `LOAD` (Загрузка из ОЗУ в регистр)](#2-load-загрузка-из-озу-в-регистр)
    * [3. `STORE` (Запись из регистра в ОЗУ)](#3-store-запись-из-регистра-в-озу)
* [Арифметико-логические инструкции скалярного тракта](#iii-арифметико-логические-инструкции-скалярного-тракта)
    * [1. `ADD` (Сложение)](#1-add-сложение)
    * [2. `SUB`, `MUL`, `DIV` (Вычитание, Умножение, Деление)](#2-sub-mul-div-вычитание-умножение-деление)
    * [3. `CMP` (Сравнение)](#3-cmp-сравнение)
* [Команды управления стеком и подпрограммами](#iv-команды-управления-стеком-и-подпрограммами)
    * [1. `PUSH` (Запись на стек)](#1-push-запись-на-стек---выполняется-за-два-шага-такты-t2-и-t3)
    * [2. `POP` (Извлечение со стека)](#2-pop-извлечение-со-стека---выполняется-в-два-шага-такты-t2-и-t3)
    * [3. `CALL` (Вызов функции)](#3-call-вызов-функции---выполняется-за-три-шага-такты-t3-t4-и-t5)
    * [4. `RET` (Возврат из функции)](#4-ret-возврат-из-функции---выполняется-за-два-шага-такты-t2-и-t3)
* [Команды управления потоком (Переходы)](#v-команды-управления-потоком-переходы)
    * [1. `JMP` (Безусловный переход)](#1-jmp-безусловный-переход---выполняется-на-такте-t3)
    * [2. `JZ` (Переход по равенству нулю)](#2-jz-переход-по-равенству-нулю---выполняется-на-такте-t3)
    * [3. `JNZ` (Переход по неравенству нулю)](#3-jnz-переход-по-неравенству-нулю---выполняется-на-такте-t3)
    * [4. `JL` (Переход по знаку меньше)](#4-jl-переход-по-знаку-меньше---выполняется-на-такте-t3)
* [Системные команды и прерывания](#vi-системные-команды-и-прерывания)
    * [1. `IRET` (Выход из прерывания)](#1-iret-выход-из-прерывания---выполняется-за-три-шага-такты-t2-t3-и-t4)
    * [2. `INT` (Системный вызов)](#2-int-системный-вызов---выполняется-на-такте-t3)
* [Векторные (SIMD) инструкции](#vii-векторные-simd-инструкции)
    * [1.
      `VLOAD` (Векторная загрузка из ОЗУ)](#1-vload-векторная-загрузка-из-озу---выполняется-за-четыре-шага-такты-t3-t4-t5-и-t6)
    * [2.
      `VSTORE` (Векторная запись в ОЗУ)](#2-vstore-векторная-запись-в-озу---выполняется-за-четыре-шага-такты-t3-t4-t5-и-t6)
    * [3. `VADD` (Векторное сложение)](#3-vadd-векторное-сложение---выполняется-за-четыре-шага-такты-t2-t3-t4-и-t5)
    * [4. `VSUB`, `VMUL`, `VDIV`,
      `VCMP` (Векторные вычитание, умножение, деление и сравнение)](#4-vsub-vmul-vdiv-vcmp-векторные-вычитание-умножение-деление-и-сравнение)
* [`HALT` (Останов процессора)](#viii-halt-останов-процессора---выполняется-на-такте-t2)
* [Аппаратный цикл обработки внешнего прерывания (TRAP)](#аппаратный-цикл-обработки-внешнего-прерывания-trap)

### Обозначения сигналов и шин на схеме:

* **`PC_Out`** - 32-битный выход счетчика команд.
* **`IM.addr`, `IM.out`** - адресный вход и выход данных ПЗУ команд (Instruction Memory).
* **`DM.addr`, `DM.data_in`, `DM.out`** - входы адреса/данных и выход ОЗУ данных (Data Memory).
* **`IR`, `PR`** - регистр команды Instruction Register и регистр полезной нагрузки Payload Register (внутри CU).
* **`Rd_Out`, `Rs_Out`, `SP_Out`, `SR_Out`** - выходы скалярного регистрового файла RF.
* **`Vd_Out`, `Vs_Out`** - последовательные 32-битные выходы элементов векторного файла VRF.
* **`ALU_Left`, `ALU_Right`** - входы скалярного ALU.
* **`ALU_Out`, `Vector_ALU_Out`** - выходы результатов скалярного и векторного ALU.

---

## I. Общие фазы (выборка и декодирование)

### 1. Фаза Fetch (выборка заголовка инструкции) - Такт 1 (T1)

Выполняется для всех без исключения инструкций процессора.

* **Микрооперации на шинах:**
    * `PC_Out` $\rightarrow$ `IM.addr` (выставляем адрес команды на шину памяти команд).
    * `IM.out` $\rightarrow$ `IR` (загружаем 4-байтовый заголовок инструкции в регистр команд).
* **Управляющие сигналы CU:**
    * `IR_Write = 1` (разрешить запись в IR).
    * `PC_Sel = 0` (выбрать на мультиплексоре `PC MUX` вход от сумматора `PC + 4`).
    * `PC_Write = 1` (разрешить обновление счетчика команд).
* **Результат по тактовому импульсу `CLK`:** В `IR` защелкивается заголовок команды, `PC` увеличивается на `4`.

### 2. Фаза Fetch Payload (Выборка полезной нагрузки) - Такт 2 (T2)

Выполняется **только** для инструкций с режимами адресации `IMMEDIATE`, `DIRECT` или `INDIRECT`.

* **Микрооперации на шинах:**
    * `PC_Out` $\rightarrow$ `IM.addr`.
    * `IM.out` $\rightarrow$ `PR` (загружаем 4-байтовый Payload константы/адреса в Payload Register).
* **Управляющие сигналы CU:**
    * `PR_Write = 1` (разрешить запись в PR).
    * `PC_Sel = 0` (выбрать вход сумматора `PC + 4`, делая суммарный сдвиг PC равным 8 байтам за два такта).
    * `PC_Write = 1`.
* **Результат по тактовому импульсу `CLK`:** В `PR` защелкивается Payload константы, `PC` увеличивается еще на `4` (
  указывая на следующую команду в памяти).

---

## II. Инструкции управления данными

### 1. `MOV` (MOV DST, SRC / #imm)

#### Вариант: `MOV Rd, #imm` (Непосредственная адресация) - Выполняется на такте T3:

* **Микрооперации:**
    * Шина `Payload` (из `PR`) $\rightarrow$ вход `1` мультиплексора `ALU_Right_MUX` $\rightarrow$ правый вход АЛУ (
      `ALU_Right`).
    * АЛУ работает в режиме прохода: `ALU_Out = ALU_Right` (результат на выходе АЛУ будет равен нашей константе из
      Payload)
    * Шина `ALU_Out` $\rightarrow$ вход 3 мультиплексора `RegFile MUX` $\rightarrow$ `Write_Data`
* **Сигналы CU:**
    * `ALU_Right_Sel = 1` (выбрать Payload на правом входе).
    * `ALU_Op = PASS_B` (режим сквозного пропуска правого входа в ALU).
    * `Reg_Data_Sel = 0` (выбрать выход `ALU_Out` на `RegFile MUX`).
    * `Reg_Write = 1` (разрешить запись в регистр Rd).
* **Результат:** В регистр `Rd` записывается константа из `Payload`.

#### Вариант: `MOV Rd, Rs` (Регистровая адресация) - Выполняется на такте T2:

* **Микрооперации:**
    * Шина `Rs_Out` $\rightarrow$ вход `0` мультиплексора `ALU_Right_MUX` $\rightarrow$ левый вход ALU.
    * Выполняется сквозной проход ALU (ALU_Out = ALU_Rught).
    * `ALU_Out` $\rightarrow$ вход 3 мультиплексора `RegFile MUX` $\rightarrow$ `Write_Data`.
* **Сигналы CU:** `ALU_Right_Sel = 0` (выбрать Rs), `ALU_Op = PASS_THRU`, `Reg_Data_Sel = 0` (выбрать ALU_Out),
  `Reg_Write = 1`.
* **Результат:** Значение регистра `Rs` копируется в `Rd`.

---

### 2. `LOAD` (Загрузка из ОЗУ в регистр)

#### Вариант: `LOAD Rd, [addr]` (Прямая адресация) - Выполняется на такте T3:

* **Микрооперации:**
    * Шина `Payload` $\rightarrow$ вход 0 мультиплексора `Address MUX` $\rightarrow$ `AR`.
    * Выход `mem_addr` из `AR` $\rightarrow$ `DM.addr` (выставляем адрес на ОЗУ данных).
    * Дешифратор адреса активирует линию `CS_RAM = 1`.
    * Прочитанные данные `DM.out` по шине `Data_Out` $\rightarrow$ вход `0` мультиплексора `RegFile MUX` $\rightarrow$
      `Write_Data`.
* **Сигналы CU:** `mem_rd = 1`, `Addr_Sel = 0` (выбрать Payload), `Reg_Data_Sel = 0` (выбрать Data_Out),
  `Reg_Write = 1`.
* **Результат:** В регистр `Rd` записывается значение из ячейки памяти `[Payload]`.

#### Вариант: `LOAD Rd, [Rs + offset]` (Косвенная адресация со смещением) - Выполняется на такте T3:

* **Микрооперации:**
    * Шина `Rs_Out` $\rightarrow$ вход 1 мультиплексора `Addr_Base_MUX` $\rightarrow$ правый вход `Address Adder`.
    * Шина `Payload` $\rightarrow$ левый вход `Address Adder`.
    * Выход сумматора `Rs_Out + Payload` $\rightarrow$ вход 2 мультиплексора `Address MUX` $\rightarrow$ `AR`.
    * Выход `mem_addr` из `AR` $\rightarrow$ `DM.addr`.
    * Прочитанные данные `DM.out` по шине `data_out` $\rightarrow$ вход 0 `RegFile MUX` $\rightarrow$ `Write_Data`.
* **Сигналы CU:** `mem_rd = 1`, `Addr_Base_Sel = 1` (выбрать Rs), `Addr_Sel = 1` (выбрать Address Adder),
  `Reg_Data_Sel = 1` (выбрать Data_Out), `Reg_Write = 1`.
* **Результат:** В регистр `Rd` записывается значение по вычисленному адресу.

---

### 3. `STORE` (Запись из регистра в ОЗУ)

#### Вариант: `STORE [addr], Rs` (Прямая адресация) - Выполняется на такте T3:

* **Микрооперации:**
    * Шина `Payload` $\rightarrow$ вход 0 мультиплексора `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Шина `Rs_Out` $\rightarrow$ вход 1 мультиплексора `Data_In MUX` $\rightarrow$ `DM.data_in`.
    * Дешифратор активирует `CS_RAM = 1`.
* **Сигналы CU:** `mem_wr = 1`, `Addr_Sel = 0` (выбрать Payload), `Data_In_Sel = 1` (выбрать Rs).
* **Результат:** Значение `Rs` записывается в ячейку ОЗУ `[Payload]`.

#### Вариант: `STORE [Rd + offset], Rs` (Косвенная адресация со смещением) - Выполняется на такте T3:

* **Микрооперации:**
    * Шина `Rd_Out` $\rightarrow$ вход 2 мультиплексора `Addr_Base_MUX` $\rightarrow$ правый вход `Address Adder`.
    * Шина `Payload` $\rightarrow$ левый вход `Address Adder`.
    * Выход сумматора `Rd_Out + Payload` $\rightarrow$ вход 2 мультиплексора `Address MUX` $\rightarrow$
      `AR` $\rightarrow$ `DM.addr`.
    * Шина `Rs_Out` $\rightarrow$ вход 1 мультиплексора `Data_In MUX` $\rightarrow$ `DM.data_in`.
* **Сигналы CU:** `mem_wr = 1`, `Addr_Base_Sel = 2` (выбрать Rd), `Addr_Sel = 2` (выбрать Address Adder),
  `Data_In_Sel = 1` (выбрать Rs).

---

## III. Арифметико-логические инструкции скалярного тракта

### 1. `ADD` (Сложение)

#### Вариант: `ADD Rd, #imm` (Непосредственная адресация) - Выполняется на такте T3:

* **Микрооперации:**
    * Шина `Rd_Out` $\rightarrow$ вход 0 мультиплексора `ALU_Left_MUX` $\rightarrow$ левый вход АЛУ.
    * Шина `Payload` $\rightarrow$ вход 1 мультиплексора `ALU_Right_MUX` $\rightarrow$ правый вход АЛУ.
    * Результат `ALU_Out` $\rightarrow$ вход 3 мультиплексора `RegFile MUX` $\rightarrow$ `Write_Data`.
* **Сигналы CU:** `ALU_Op = ADD`, `ALU_Left_Sel = 0` (Rd), `ALU_Right_Sel = 1` (Payload), `Reg_Data_Sel = 0` (ALU_Out),
  `Reg_Write = 1`.

#### Вариант: `ADD Rd, Rs` (Регистровая адресация) - Выполняется на такте T2:

* **Микрооперации:**
    * `Rd_Out` $\rightarrow$ левый вход АЛУ; `Rs_Out` $\rightarrow$ правый вход АЛУ.
    * Результат `ALU_out` $\rightarrow$ вход 3 мультиплексора `RegFile MUX` $\rightarrow$ `Write_Data`.
* **Сигналы CU:** `ALU_Op = ADD`, `ALU_Left_Sel = 0` (Rd), `ALU_Right_Sel = 0` (Rs), `Reg_Data_Sel = 3`,
  `Reg_Write = 1`.

---

### 2. `SUB`, `MUL`, `DIV` (Вычитание, Умножение, Деление)

*(Выполняются только в режиме REGISTER на такте T2)*.

* **Микрооперации:**
    * Шина `Rs_Out` $\rightarrow$ вход 1 мультиплексора `ALU_Left_MUX` $\rightarrow$ левый вход АЛУ.
    * Шина `Rd_Out` $\rightarrow$ вход 1 мультиплексора `ALU_Right_MUX` $\rightarrow$ правый вход АЛУ.
    * Результат `ALU_Out` $\rightarrow$ вход 3 `RegFile MUX` $\rightarrow$ `Write_Data`.
* **Сигналы CU:** `ALU_Op = SUB/MUL/DIV`, `ALU_Left_Sel = 0` (Rs), `ALU_Right_Sel = 0` (Rd), `Reg_Data_Sel = 3`,
  `Reg_Write = 1`.

---

### 3. `CMP` (Сравнение)

#### Вариант: `CMP Rd, #imm` (Непосредственная адресация) - Выполняется на такте T3:

* **Микрооперации:**
    * `Rd_Out` $\rightarrow$ левый вход АЛУ; `Payload` $\rightarrow$ правый вход АЛУ.
    * АЛУ выполняет вычитание `Rd - Payload`. Вырабатывает флаги `ZF` и `NF` $\rightarrow$ вход `ALU_Flags_In` в RF.
* **Сигналы CU:** `ALU_Op = CMP`, `ALU_Left_Sel = 0` (Rd), `ALU_Right_Sel = 1` (Payload). Флаги автоматически
  записываются в регистр `SR` по тактовому импульсу.

#### Вариант: `CMP Rd, Rs` (Регистровая адресация) - Выполняется на такте T2:

* **Микрооперации:**
    * `Rd_Out` $\rightarrow$ левый вход АЛУ; `Rs_Out` $\rightarrow$ правый вход АЛУ.
    * АЛУ выполняет вычитание `Rd - Rs`. Аппаратные флаги `ZF`/`NF` поступают на вход `ALU_Flags_In` регистрового файла.
* **Сигналы CU:** `ALU_Op = CMP`, `ALU_Left_Sel = 0` (Rd), `ALU_Right_Sel = 0` (Rs).

---

## IV. Команды управления стеком и подпрограммами

### 1. `PUSH` (Запись на стек) - Выполняется за два шага (такты T2 и T3):

* **Такт T2 (Декремент указателя стека SP):**
    * Шина `SP_Out` $\rightarrow$ вычитатель `SP - 4` $\rightarrow$ вход 1 мультиплексора `RegFile MUX` $\rightarrow$
      `Write_Data` (для записи обновленного SP).
    * *Сигналы CU:* `Reg_data_sel = 1` (выбрать SP - 4), `Reg_Write = 1` (записать новый SP)
    * *Результат по CLK:* SP уменьшается на 4, в ОЗУ пока что ничего не пишется
* **Такт T3 (запись данных в стек по новому адресу):**
    * SP_out $\rightarrow$ вход 2 `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`
    * `Rs_out` $\rightarrow$ вход 1 `Data_In MUX` $\rightarrow$ `DM.data_in`
    * *Сигналы CU:* `mem_wr = 1`, `Addr_Sel = 2` (выбрать SP_out), `Data_In_Sel = 0` (выбрать Rs_out)
    * *Результат по CLK:* Значение `Rs` записывается в ОЗУ по новому адресу `SP`

---

### 2. `POP` (Извлечение со стека) - Выполняется в два шага (такты T2 и T3):

Поскольку у регистрового файла только один порт записи, мы не можем одновременно записать данные в `Rd` и увеличить `SP`
за один такт. Мы разбиваем операцию на два микрошага:

* **Такт T2 (Чтение стека и загрузка в `Rd`):**
    * `SP_Out` $\rightarrow$ вход 1 мультиплексора `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Прочитанные данные `DM.out` по шине `data_out` $\rightarrow$ вход 0 мультиплексора `RegFile MUX` $\rightarrow$
      `Write_Data` (направляется на запись в регистр `Rd`).
    * *Сигналы CU:* `mem_rd = 1`, `Addr_Sel = 1` (выбрать SP), `Reg_Data_Sel = 0` (выбрать data_out), `Reg_Write = 1` (
      запись в Rd).
* **Такт T3 (Инкремент указателя стека `SP`):**
    * `SP_Out` $\rightarrow$ сумматор `SP + 4` $\rightarrow$ вход 2 мультиплексора `RegFile MUX` $\rightarrow$
      `Write_Data` (направляется на запись в регистр `SP`).
    * *Сигналы CU:* `Reg_Data_Sel = 2` (выбрать SP+4), `Reg_Write = 1` (запись в SP, CU принудительно выставляет индекс
      SP на вход `Rd_Idx`).

---

### 3. `CALL` (Вызов функции) - Выполняется за три шага (такты T3, T4 и T5):

* **Такт T3 (Декремент SP):**
    * `SP_Out` $\rightarrow$ вычитатель `SP - 4` $\rightarrow$ вход 1 `RegFile MUX` $\rightarrow$ `Write_Data` (запись
      нового SP).
    * *Сигналы CU:* `Reg_Data_sel = 1` (выбрать SP - 4), `Reg_Write = 1` (записать новый SP)
* **Такт T4 (Запись PC возврата на стек):**
    * `SP_out` (который теперь равен SP - 4) $\rightarrow$ вход 1 `Address MUX` $\rightarrow$ `AR` $\rightarrow$
      `DM.addr`
    * `PC_out` (адрес возврата) $\rightarrow$ вход 2 `Data_In MUX` $\rightarrow$ `DM.data_in`
    * *Сигналы CU:* `mem_wr = 1`, `Addr_sel = 1` (выбрать SP_out), `Data_In_sel = 2` (выбрать PC_out)
* **Такт T5 (Безусловный переход на адрес подпрограммы):**
    * Шина `Payload` (из PR) $\rightarrow$ вход 2 `PC MUX` $\rightarrow$ `PC_next`
    * *Сигналы CU:* `PC_sel = 2` (выбрать Payload), `PC_write = 1`

---

### 4. `RET` (Возврат из функции) - Выполняется за два шага (такты T2 и T3):

* **Такт T2 (Восстановление `PC` со стека):**
    * `SP_Out` $\rightarrow$ вход 1 мультиплексора `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Прочитанный адрес `DM.out` по шине `data_out` $\rightarrow$ вход 4 мультиплексора `PC MUX` $\rightarrow$
      `PC_Next`.
    * *Сигналы CU:* `mem_rd = 1`, `Addr_sel = 1` (выбрать SP), `PC_sel = 4` (выбрать Data_Out), `PC_write = 1`.
* **Такт T3 (Инкремент указателя стека `SP`):**
    * `SP_Out` $\rightarrow$ сумматор `SP + 4` $\rightarrow$ вход `2` мультиплексора `RegFile MUX` $\rightarrow$
      `Write_Data` (для записи в `SP`).
    * *Сигналы CU:* `Reg_Data_Sel = 2` (выбрать SP+4), `Reg_Write = 1` (запись в SP).

---

## V. Команды управления потоком (Переходы)

### 1. `JMP` (Безусловный переход) - Выполняется на такте T3:

* **Микрооперации:**
    * Шина `Payload` (из `PR`) $\rightarrow$ вход 2 мультиплексора `PC MUX` $\rightarrow$ `PC_next`.
* **Сигналы CU:** `PC_Sel = 2` (выбрать Payload), `PC_Write = 1`.

### 2. `JZ` (Переход по равенству нулю) - Выполняется на такте T3:

* **Микрооперации:**
    * Дешифратор анализирует флаг `ZF` с шины `SR_out`.
    * *Если `SR_Out.ZF == 1`:* Шина `Payload` $\rightarrow$ вход 2 мультиплексора `PC MUX` $\rightarrow$ `PC_next`.
      Сигнал `PC_write = 1` (совершается переход).
    * *Если `SR_Out.ZF == 0`:* Никаких сигналов не подается, `PC` остается неизменным (указывает на следующую
      инструкцию).

### 3. `JNZ` (Переход по неравенству нулю) - Выполняется на такте T3:

* **Микрооперации:**
    * Дешифратор анализирует флаг `ZF` с шины `SR_out`.
    * *Если `SR_Out.ZF == 0`:* Шина `Payload` $\rightarrow$ вход 2 мультиплексора `PC MUX` $\rightarrow$ `PC_next`.
      Сигнал `PC_write = 1`.
    * *Если `SR_Out.ZF == 1`:* Переход игнорируется.

### 4. `JL` (Переход по знаку меньше) - Выполняется на такте T3:

* **Микрооперации:**
    * Дешифратор анализирует флаг `NF` (Negative Flag) с шины `SR_out`.
    * *Если `SR_Out.NF == 1`:* Шина `Payload` $\rightarrow$ вход 2 мультиплексора `PC MUX` $\rightarrow$ `PC_next`.
      Сигнал `PC_write = 1`.
    * *Если `SR_Out.NF == 0`:* Переход игнорируется.

---

## VI. Системные команды и прерывания

### 1. `IRET` (Выход из прерывания) - Выполняется за три шага (такты T2, T3 и T4):

* **Такт T2 (Восстановление регистра флагов `SR` со стека):**
    * `SP_Out` $\rightarrow$ вход 1 мультиплексора `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * `DM.out` по шине `data_out` $\rightarrow$ вход 0 мультиплексора `RegFile MUX` $\rightarrow$ `Write_Data` (
      направляется в регистр `SR`).
    * *Сигналы CU:* `mem_rd = 1`, `Addr_Sel = 1` (SP), `Reg_Data_Sel = 0` (Data_Out), `Reg_Write = 1` (запись в SR),
      `SR_MUX_sel = 0` (выбор Write_Data на запись в SR).
* **Такт T3 (Восстановление `PC` и первый инкремент стека):**
    * `SP_Out` (который уже равен `old_SP + 4`) $\rightarrow$ вход 1 мультиплексора `Address MUX` $\rightarrow$
      `AR` $\rightarrow$ `DM.addr`.
    * Прочитанный адрес `DM.out` по шине `data_out` $\rightarrow$ вход 4 мультиплексора `PC MUX` $\rightarrow$
      `PC_next` (восстановление PC).
    * *Сигналы CU:* `mem_rd = 1`, `Addr_sel = 1` (SP), `PC_sel = 4` (data_out), `PC_write = 1`.
* **Такт T4 (Финальный инкремент `SP`):**
    * `SP_Out` $\rightarrow$ сумматор `SP + 4` $\rightarrow$ вход 2 `RegFile MUX` $\rightarrow$ `Write_Data` (
      восстановление SP).
    * *Сигналы CU:* `Reg_Data_Sel = 2` (выбрать SP+4), `Reg_Write = 1` (запись в SP). Признак `in_interrupt`
      сбрасывается в `0`.

---

### 2. `INT` (Системный вызов) - Выполняется на такте T3:

* **Микрооперации:**
    * `Rd_idx` устанавливается в 0 (индекс R0). Регистровый файл выдает значение R0 на шину `Rd_out`
    * *Если `PR == 1` (Печать числа):* Значение шины `Rd_out` поступает на внешний системный порт вывода процессора в
      симуляторе это перехватывается средой Python и записывается в `output_buffer`).
    * *Если `PR == 2` (Печать строки):* Значение `Rd_out` подается на вход `Address Adder` со смещением 0; результат
      `Rd_out + 0` $\rightarrow$ `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr` для последовательного чтения
      символов ОЗУ в буфер вывода.

---

## VII. Векторные (SIMD) инструкции

### 1. `VLOAD` (Векторная загрузка из ОЗУ) - Выполняется за четыре шага (такты T3, T4, T5 и T6):

* **Такт T3 (Запись в слово `W0`):**
    * `V_Element_Idx` (который на шаге T3 равен 0) $\rightarrow$ вход 0 `Addr_Base_MUX` $\rightarrow$ правый вход
      `Address Adder`.
    * Шина `Payload` (из `PR` = `200`) $\rightarrow$ левый вход `Address Adder`.
    * `Address Adder` вычисляет `0 + 200 = 200` $\rightarrow$ вход 2 `Address MUX` $\rightarrow$ `AR` $\rightarrow$
      `DM.addr`.
    * Прочитанный элемент `DM.out` по шине `Data_out` $\rightarrow$ вход 1 `Vector MUX` $\rightarrow$ `V_Write_Data` (
      запись в ячейку `W0` регистра `V_dest` под управлением `V_Element_Idx = 00`).
    * *Сигналы CU:* `mem_rd = 1`, `Addr_Base_Sel = 0` (V_Element_Idx), `Addr_Sel = 2` (Address Adder),
      `Vector_Sel = 1` (Data_out), `V_Reg_Write = 1`, `V_Element_Idx = 00`.
* **Такт T4 (Запись в слово `W1`):**
    * `V_Element_Idx` (равен 1) + `Payload` (равен `200`) вычисляется в `Address Adder` как `201` $\rightarrow$
      `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * `DM.out` по шине `Data_out` $\rightarrow$ `V_Write_Data` (запись в `W1` под управлением `V_Element_Idx = 01`).
    * *Сигналы CU:* `mem_rd = 1`, `Addr_Base_Sel = 0`, `Addr_Sel = 2`, `Vector_Sel = 1`, `V_Reg_Write = 1`,
      `V_Element_Idx = 01`.
* **Такт T5 (Запись в слово `W2`):**
    * `Address Adder` вычисляет `2 + 200 = 202` $\rightarrow$ `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * `DM.out` по шине `Data_out` $\rightarrow$ `V_Write_Data` (запись в `W2` под управлением `V_Element_Idx = 10`).
    * *Сигналы CU:* `mem_rd = 1`, `Addr_Base_Sel = 0`, `Addr_Sel = 2`, `Vector_Sel = 1`, `V_Reg_Write = 1`,
      `V_Element_Idx = 10`.
* **Такт T6 (Запись в слово `W3`):**
    * `Address Adder` вычисляет `3 + 200 = 203` $\rightarrow$ `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * `DM.out` по шине `Data_Out` $\rightarrow$ `V_Write_Data` (запись в `W3` под управлением `V_Element_Idx = 11`).
    * *Сигналы CU:* `mem_rd = 1`, `Addr_Base_Sel = 0`, `Addr_Sel = 2`, `Vector_Sel = 1`, `V_Reg_Write = 1`,
      `V_Element_Idx = 11`.

---

### 2. `VSTORE` (Векторная запись в ОЗУ) - Выполняется за четыре шага (такты T3, T4, T5 и T6):

* **Такт T3 (Запись слова `W0` в ОЗУ):**
    * `V_Element_Idx` (равен 0) + `Payload` (равен `200`) вычисляется в `Address Adder` как `200` $\rightarrow$
      `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Элемент вектора `Vs_out` (считанный из VRF под управлением `V_Element_Idx = 00`) $\rightarrow$ вход 3
      мультиплексора `Data_In MUX` $\rightarrow$ `DM.data_in`.
    * *Сигналы CU:* `mem_wr = 1`, `Addr_Base_Sel = 0` (V_Element_Idx), `Addr_Sel = 2` (Address Adder),
      `Data_In_Sel = 3` (Vs_Out), `V_Element_Idx = 00`.
* **Такт T4 (Запись слова `W1` в ОЗУ):**
    * `Address Adder` вычисляет `1 + 200 = 201` $\rightarrow$ `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Элемент `Vs_Out` (считанный при `V_Element_Idx = 01`) $\rightarrow$ вход 3 `Data_In MUX` $\rightarrow$
      `DM.data_in`.
    * *Сигналы CU:* `mem_wr = 1`, `Addr_Base_Sel = 0`, `Addr_Sel = 2`, `Data_In_Sel = 3`, `V_Element_Idx = 01`.
* **Такт T5 (Запись слова `W2` в ОЗУ):**
    * `Address Adder` вычисляет `2 + 200 = 202` $\rightarrow$ `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Элемент `Vs_Out` (считанный при `V_Element_Idx = 10`) $\rightarrow$ вход 3 `Data_In MUX` $\rightarrow$
      `DM.data_in`.
    * *Сигналы CU:* `mem_wr = 1`, `Addr_Base_Sel = 0`, `Addr_Sel = 2`, `Data_In_Sel = 3`, `V_Element_Idx = 10`.
* **Такт T6 (Запись слова `W3` в ОЗУ):**
    * `Address Adder` вычисляет `3 + 200 = 203` $\rightarrow$ `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Элемент `Vs_Out` (считанный при `V_Element_Idx = 11`) $\rightarrow$ вход 3 `Data_In MUX` $\rightarrow$
      `DM.data_in`.
    * *Сигналы CU:* `mem_wr = 1`, `Addr_Base_Sel = 0`, `Addr_Sel = 2`, `Data_In_Sel = 3`, `V_Element_Idx = 11`.

---

### 3. `VADD` (Векторное сложение) - Выполняется за четыре шага (такты T2, T3, T4 и T5):

*(Выполняется в режиме REGISTER)*.

* **Такт T2 (Сложение 1-го элемента):**
    * Элементы `Vd_Out` и `Vs_Out` (считанные из VRF при `V_Element_Idx = 00`) подаются на входы **Vector ALU**.
    * Выход `Vector_ALU_Out` $\rightarrow$ вход 0 мультиплексора `Vector MUX` $\rightarrow$ `V_Write_Data` (запись в
      ячейку `W0` вектора назначения).
    * *Сигналы CU:* `Vector_ALU_Op = VADD`, `Vector_Sel = 0` (выбрать Vector_ALU_Out), `V_Reg_Write = 1`,
      `V_Element_Idx = 00`.
* **Такт T3 (Сложение 2-го элемента):**
    * Элементы `Vd_Out` и `Vs_Out` (считанные при `V_Element_Idx = 01`) складываются в АЛУ.
    * `Vector_ALU_Out` $\rightarrow$ `V_Write_Data` (запись в ячейку `W1` вектора назначения).
    * *Сигналы CU:* `Vector_ALU_Op = VADD`, `Vector_Sel = 0`, `V_Reg_Write = 1`, `V_Element_Idx = 01`.
* **Такт T4 (Сложение 3-го элемента):**
    * Элементы `Vd_Out` и `Vs_Out` (при `V_Element_Idx = 10`) складываются в АЛУ.
    * `Vector_ALU_Out` $\rightarrow$ `V_Write_Data` (запись в ячейку `W2`).
    * *Сигналы CU:* `Vector_ALU_Op = VADD`, `Vector_Sel = 0`, `V_Reg_Write = 1`, `V_Element_Idx = 10`.
* **Такт T5 (Сложение 4-го элемента):**
    * Элементы `Vd_Out` и `Vs_Out` (при `V_Element_Idx = 11`) складываются в АЛУ.
    * `Vector_ALU_Out` $\rightarrow$ `V_Write_Data` (запись в ячейку `W3`).
    * *Сигналы CU:* `Vector_ALU_Op = VADD`, `Vector_Sel = 0`, `V_Reg_Write = 1`, `V_Element_Idx = 11`.

---

### 4. `VSUB`, `VMUL`, `VDIV`, `VCMP` (Векторные вычитание, умножение, деление и сравнение)

*(Потактово полностью идентичны вектору `VADD`, за исключением кода операции `Vector_ALU_Op`)*.

* **Такты выполнения:** T2, T3, T4, T5.
* **Управляющий сигнал:** `Vector_ALU_Op = VSUB / VMUL / VDIV / VCMP`.
* *Особенность VCMP:* при сравнении элементов Vector ALU выдает `1`, если элементы равны, и `0`, если не равны.
  Результат записывается в соответствующее слово вектора назначения.

---

## VIII. `HALT` (Останов процессора) - Выполняется на такте T2:

* **Такт T2 (Фаза выполнения):**
    * Дешифратор `Combinational Decoder` декодирует опкод `0xFF`
    * Вырабатывается аппаратный сигнал останова, который переводит внутренний триггер симулятора `self._halt` в
      состояние `True`
    * Тактовый генератор прекращает подачу импульсов `CLK`, фиксируя конечное значение тактов

---

## Аппаратный цикл обработки внешнего прерывания (TRAP)

Выполняется асинхронно перед фазой Fetch очередной инструкции, если наступил такт прерывания из расписания,
`in_interrupt == False` и вектор зарегистрирован.

#### **Аппаратный цикл прерывания `TRAP` - Выполняется за 5 тактов (`T1–T5`):**

* **Такт T1 (Декремент `SP` для сохранения `PC`):**
    * `SP_out` $\rightarrow$ вычитатель `SP - 4` $\rightarrow$ вход 1 `RegFile MUX` $\rightarrow$ `Write_Data`.
    * *Сигналы CU:* `Reg_Data_Sel = 1` (выбрать `SP - 4`), `Reg_Write = 1` (записать новый SP).
    * *Результат по CLK:* `SP` уменьшается на 4, в ОЗУ пока ничего не пишется.
* **Такт T2 (Запись `PC` возврата на стек):**
    * `SP_Out` $\rightarrow$ вход 1 `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Шина текущего адреса возврата `PC_Out` $\rightarrow$ вход 2 мультиплексора `Data_In MUX` $\rightarrow$
      `DM.data_in`.
    * *Сигналы CU:* `mem_wr = 1`, `Addr_Sel = 1` (выбрать `SP_Out`), `Data_In_Sel = 2` (выбрать `PC_Out`).
    * *Результат по CLK:* Адрес возврата `PC` записывается в ОЗУ по новому адресу SP, обновленному на предыдущем такте.
* **Такт T3 (Декремент `SP` для сохранения `SR`):**
    * `SP_Out` $\rightarrow$ вычитатель `SP - 4` $\rightarrow$ вход 1 `RegFile MUX` $\rightarrow$ `Write_Data`.
    * *Сигналы CU:* `Reg_Data_Sel = 1` (выбрать `SP - 4`), `Reg_Write = 1`.
    * *Результат по CLK:* `SP` уменьшается еще на 4.
* **Такт T4 (Запись флагов `SR` на стек):**
    * `SP_Out` $\rightarrow$ вход 1 `Address MUX` $\rightarrow$ `AR` $\rightarrow$ `DM.addr`.
    * Шина флагов `SR_Out` $\rightarrow$ вход 0 мультиплексора `Data_In MUX` $\rightarrow$ `DM.data_in`.
    * *Сигналы CU:* `mem_wr = 1`, `Addr_Sel = 1` (выбрать `SP_Out`), `Data_In_Sel = 0` (выбрать `SR_Out`).
    * *Результат по CLK:* Флаги состояния `SR` записываются в ОЗУ по новому адресу SP, обновленному на предыдущем такте.
* **Такт T5 (Аппаратный переход на вектор):**
    * Шина `Intr_Vector` (из CU) $\rightarrow$ вход 3 `PC MUX` $\rightarrow$ `PC_Next`.
    * *Сигналы CU:* `PC_Sel = 3` (выбрать `Intr_Vector`), `PC_Write = 1`. Взводится аппаратный триггер
      `in_interrupt = True`.
    * *Результат по CLK:* `PC` получает адрес начала обработчика.

