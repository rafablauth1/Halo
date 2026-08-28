"""Comandos SCPI reais do Chroma 61501/61502/61503/61504 (Programmable AC Source),
usados no ensaio de Quedas de Tensão / Interrupções (IEC 61000-4-11).

Testado em campo (Teste_IEC61000-4-11.py, Pedro Henrique De Ros/EMC, e testes
diretos neste projeto): tanto o modo PULSE (PULSe:*/TRIG) quanto o modo LIST
(LIST:*/TRIG) estão documentados no manual oficial (§8.6.2.7 e §8.6.2.8) mas,
na prática, em DOIS testes reais separados, `OUTP:MODE {LIST|PULSE}` seguido
de `TRIG ON` nunca fez o equipamento sair da tensão nominal nem mostrar
RUNNING — só escrever VOLT direto e esperar em software realmente muda a
saída. Por isso o driver usa só esse caminho simples.
"""

IDN_QUERY = "*IDN?"
RESET = "*RST"
CLEAR_STATUS = "*CLS"

OUTPUT_STATE = "OUTP {state}"  # ON | OFF
VOLTAGE_RANGE = "VOLT:RANGe {range}"  # LOW | HIGH | AUTO — trava a faixa (AUTO troca relé 150V/300V sozinho)

SET_VOLTAGE_AC = "VOLT:AC {voltage}"
SET_FREQUENCY = "FREQ {frequency_hz}"

ERROR_QUERY = "SYST:ERRor?"
