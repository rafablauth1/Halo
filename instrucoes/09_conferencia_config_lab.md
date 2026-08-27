# Conferência da configuração do RadiMation contra a norma

Comparação entre a configuração real do RadiMation 2016.2.8 do laboratório
(telas de Conducted Emission) e o que consegui verificar nas normas.

**Fonte usada:** `CISPR 15:2018 (ed. 9.0)`, cópia em português disponível
no PC. **CISPR 16-1-1, 16-2-1 e 16-4-2 não estão disponíveis** — o que
depende delas está marcado como não verificado.

---

## 1. O que a CISPR 15 delega à CISPR 16

Ponto importante: **a CISPR 15 não define RBW nem passo de frequência.**
Em todas as cláusulas de método ela remete:

> "receptor conforme **CISPR 16-1-1**" · "método de medição conforme
> **CISPR 16-2-1**"

Logo, os valores abaixo **não puderam ser conferidos na fonte primária**:

| Parâmetro | Valor usado | Situação |
|---|---|---|
| RBW banda A (9–150 kHz) | 200 Hz | não verificado (CISPR 16-1-1) |
| RBW banda B (150 kHz–30 MHz) | 9 kHz | não verificado |
| RBW banda C (30–300 MHz) | 120 kHz | não verificado |
| Passo ≤ metade da RBW | regra | não verificado (CISPR 16-2-1) |
| Constantes do detector QP | ver item 3 | não verificado |

---

## 2. Achados na CISPR 15:2018 — divergências reais

### 2.1 Limites de 30–300 MHz mudaram entre edições ⚠

A CISPR 15:2018 diz, sobre a Tabela 10 (método CDNE):

> "Os limites CDNE entre 200 MHz e 300 MHz especificados na Tabela 10 são
> **mais rigorosos** do que os limites fornecidos na CISPR 15:2013. Uma
> margem crescente (**até 10 dB a 300 MHz**) foi aplicada entre 200 MHz e
> 300 MHz."

A tabela que está no software (transcrita do relatório de referência,
que cita **NBR IEC/CISPR 15/2014**) tem:

| Faixa | Limite QP |
|---|---|
| 230–300 MHz | **61 dBµV/m** ← *sobe* |

Na edição 2018 esse trecho **aperta** em vez de afrouxar. Ou seja: um
ensaio aprovado com 61 dBµV/m em 300 MHz pela edição de 2014 pode
reprovar pela de 2018.

**Não alterei nada.** Se o escopo acreditado do laboratório ainda é a
NBR/2014, está correto como está. Só vale saber que existe a diferença.

### 2.2 Restrição de aplicabilidade do método CDNE ⚠

> "O método CDNE e os limites associados até 300 MHz podem ser aplicados
> **somente para EUTs com frequências de clock abaixo ou iguais a
> 30 MHz**."

Vale checar a frequência de chaveamento do driver LED ensaiado. Acima de
30 MHz, o método CDNE não é aplicável e o ensaio teria que ir para
OATS/SAC.

Também: **dimensão máxima do EUT para CDNE = 3 m × 1 m × 1 m**.

### 2.3 Exceção para lâmpadas sem eletrodos — não implementada

> "Para equipamentos de iluminação que incorporem exclusivamente lâmpadas
> sem eletrodos, o limite na faixa de **2,2 MHz a 3,0 MHz** é de
> **73 dB(µV) quase-pico e 63 dB(µV) médio**."

E no método de loop, **39 dB(µA/m)** na mesma faixa. Nenhuma das cinco
tabelas do software tem essa exceção.

### 2.4 Atalho do item 4.1 — não implementado

> "desde que os níveis de perturbação do EUT sejam medidos usando o
> detector de quase-pico e sejam encontrados para atender aos limites
> médios, então o EUT deve ser considerado para atender a ambos os
> limites e a medição com o detector médio não precisa ser realizada."

Hoje o software marca AV como reprovado nesses casos. Deveria aprovar.

---

## 3. Preocupação técnica com a configuração ⚠⚠

**O tempo de quase-pico da conduzida parece curto.**

Configuração medida nas telas:

| Ensaio | QP: tempo de medição / observação |
|---|---|
| Conduzida 9 kHz–30 MHz | **50 ms / 50 ms** |
| Loop 9 kHz–30 MHz | 1 s / 2 s |
| Anexo B 30–300 MHz | 2 s / 15 s |

O detector de quase-pico da CISPR 16-1-1 tem constantes de tempo de
**descarga** da ordem de:

| Banda | Carga | Descarga |
|---|---|---|
| A (9–150 kHz) | 45 ms | **500 ms** |
| B (150 kHz–30 MHz) | 1 ms | **160 ms** |
| C/D (30–1000 MHz) | 1 ms | 550 ms |

Com 50 ms de observação, o detector fica em **1/10 da constante de
descarga na banda A** e menos de 1/3 na banda B — pode não estabilizar.

**O problema é a direção do erro:** um QP que não chegou ao regime lê
**abaixo** do valor real. Ou seja, erra para o lado que **aprova**.

As outras duas configurações (1 s e 2 s) são coerentes com isso; a da
conduzida é a exceção. Vale conferir contra a sua cópia da CISPR 16-1-1 —
**as constantes acima são do meu conhecimento de engenharia, não foram
verificadas na norma aqui.**

---

## 4. Passo de frequência

Valores reais medidos nas telas:

| Banda | RBW | Passo | Relação |
|---|---|---|---|
| A | 200 Hz | 200 Hz | passo = RBW |
| B | 9 kHz | **10 kHz** | passo > RBW |
| C | 120 kHz | 100 kHz | passo < RBW |

Na banda B o passo é maior que a RBW: sobra ~1 kHz entre pontos que o
filtro de 9 kHz não cobre no topo. Como é prescan com medição final nos
picos, o impacto é pequeno — mas um passo de 9 kHz fecharia a lacuna sem
custo de tempo relevante.

O software agora distingue as duas situações: passo entre RBW/2 e RBW é
**aviso** (aceitável em prescan); passo maior que a RBW é **erro**.

---

## 5. O que está certo

- Faixas de frequência de cada método ✓
- Detectores por método (QP+AV na conduzida, QP no loop e no Anexo B) ✓
- Limites das 5 tabelas conferidos ponto a ponto contra o relatório ✓
- Frequências de transição usando o limite inferior ✓
- Margem de busca de picos e número de picos (15/20 dB, 10 picos) ✓

---

## Resumo do que merece ação

| # | Achado | Gravidade |
|---|---|---|
| 3 | Tempo de QP de 50 ms na conduzida | **alta** — erra para o lado que aprova |
| 2.2 | CDNE só vale para clock ≤ 30 MHz | média — verificar o EUT |
| 2.1 | Limites 200–300 MHz mudaram na ed. 2018 | média — depende do escopo acreditado |
| 2.4 | Atalho do item 4.1 não implementado | baixa — só deixa de aprovar o que poderia |
| 2.3 | Lâmpadas sem eletrodos | baixa — só se ensaiar esse tipo |
| 4 | Passo 10 kHz com RBW 9 kHz | baixa — prescan |
