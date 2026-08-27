# Limites de norma — situação atual

> **Atualizado.** As cinco tabelas de limite da **ABNT NBR IEC/CISPR
> 15/2014** estão preenchidas e marcadas como verificadas, transcritas
> das tabelas do relatório de ensaio **laboratório/relatório de ensaio de referência**
> (itens 4.3.1 a 4.4.2 da norma). O aviso vermelho de "limite não
> verificado" no PDF só aparece agora se **você** criar/editar uma norma
> e deixar algum segmento sem confirmar.

## As cinco tabelas (`core/standards/*.json`)

### `cispr15_mains_terminals.json` — Terminais de alimentação (item 4.3.1)

| Faixa (MHz) | QP (dBµV) | AV (dBµV) |
|---|---|---|
| 0,009 – 0,05 | 110 | — |
| 0,05 – 0,15 | 90 → 80 | — |
| 0,15 – 0,5 | 66 → 56 | 56 → 46 |
| 0,5 – 5 | 56 | 46 |
| 5 – 30 | 60 | 50 |

Decrescimento log-linear em 50–150 kHz e 150–500 kHz. Não há limite de
detector Média abaixo de 150 kHz.

### `cispr15_load_terminals.json` — Terminais de carga (item 4.3.2)

| Faixa (MHz) | QP (dBµV) | AV (dBµV) |
|---|---|---|
| 0,15 – 0,5 | 80 | 70 |
| 0,5 – 30 | 74 | 64 |

### `cispr15_control_terminals.json` — Terminais de controle (item 4.3.3)

| Faixa (MHz) | QP (dBµV) | AV (dBµV) |
|---|---|---|
| 0,15 – 0,5 | 84 → 74 | 74 → 64 |
| 0,5 – 30 | 74 | 64 |

Decrescimento log-linear em 0,15–0,5 MHz.

### `cispr15_loop_antenna.json` — Antena de loop 2 m (item 4.4.1)

| Faixa (MHz) | Limite (dBµA) |
|---|---|
| 0,009 – 0,07 | 88 |
| 0,07 – 0,15 | 88 → 58 |
| 0,15 – 3 | 58 → 22 |
| 3 – 30 | 22 |

Decrescimento log-linear em 70–150 kHz e 150 kHz–3 MHz. Medir nas três
direções do campo (Loop A, B e C).

### `cispr15_radiated_30_300.json` — Radiada 30–300 MHz (item 4.4.2)

| Faixa (MHz) | QP (dBµV/m) |
|---|---|
| 30 – 100 | 64 → 54 |
| 100 – 230 | 54 |
| 230 – 300 | 61 |

Decrescimento log-linear em 30–100 MHz.

## Frequências de transição

Todas as tabelas trazem a nota *"na frequência de transição, aplica-se o
limite inferior"*. Isso está implementado em `core/limits.py`: quando
uma frequência cai na fronteira entre dois segmentos, o software usa o
**menor** dos dois valores. Exemplos já conferidos:

| Frequência | Limite aplicado | Em vez de |
|---|---|---|
| 50 kHz (alimentação, QP) | 90 | 110 |
| 150 kHz (alimentação, QP) | 66 | 80 |
| 5 MHz (alimentação, QP) | 56 | 60 |
| 230 MHz (radiada, QP) | 54 | 61 |

## Ainda não coberto

- **Incertezas de medição** — a tabela do relatório (4,5 dB em
  9–150 kHz; 4,4 dB em 150 kHz–30 MHz; 4,8 dB em 9–30 MHz radiado;
  3,7 dB em 30–300 MHz; todos com k = 2,00) ainda não entra no PDF nem
  na regra de decisão.
- **CISPR 15 Cláusula 5** (perturbação descontínua / contagem de
  cliques) — precisa de lógica própria, não é "traço x linha de limite".
- **Perdas de inserção** (150 kHz – 1,605 MHz, método das lâmpadas
  substitutas).

## Se precisar mexer

Pela GUI: escolha a norma → **"Editar esta norma..."**. Dá para corrigir
valores, adicionar segmentos, criar detectores novos e marcar/desmarcar
"Verificado". Ver `06_normas_e_correcoes_configuraveis.md`.

Se a sua edição da norma divergir do que está aqui (edições diferentes
mudam valores), **a sua cópia oficial manda** — corrija pela tela e
mantenha o campo Verificado coerente com o que você conferiu.
