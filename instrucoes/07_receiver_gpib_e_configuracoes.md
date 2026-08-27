# Aba Receiver / GPIB — modelos R&S e configurações de ensaio

Esta aba reúne **todas as configurações de receiver pertinentes a um
ensaio CISPR 15** e um **catálogo de receivers Rohde & Schwarz
pré-setados**, cada um com o seu próprio conjunto de comandos SCPI.

> ⚠ **Leia antes de usar em ensaio real:** os comandos SCPI vieram da
> documentação das famílias R&S, mas **não foram validados contra
> hardware real** neste ambiente. Cada família — e às vezes cada versão
> de firmware — muda algum comando. Confira no manual *Remote Control
> Commands* do **seu** instrumento e corrija pela própria tela (ver
> "Editar os comandos de um modelo", abaixo). Enquanto o modelo estiver
> com "comandos NÃO conferidos", o software avisa antes de enviar.

---

## Catálogo de receivers

31 modelos pré-setados, um arquivo JSON cada em `instruments/receivers/`:

| Família | Modelos | Observação |
|---------|---------|------------|
| ESW | ESW8, ESW26, ESW44 | topo de linha atual |
| ESR | ESR3, ESR7, ESR26 | receiver EMI mais comum em laboratório |
| ESRP | ESRP3, ESRP7 | receiver EMI compacto |
| ESU | ESU8, ESU26, ESU40 | geração anterior de topo |
| ESIB | ESIB7, ESIB26, ESIB40 | linha anterior |
| ESPI / ESCI / ESL | ESPI3/7, ESCI3/7, ESL3/6 | compactos |
| ESCS / ESHS | ESCS30, ESHS10, ESHS30 | bancada clássica |
| FSW / FSV / FSVA / FPL / FSL | FSW8/26, FSV7/13, FSVA30, FPL1003/1007, FSL6 | analisadores com opção EMI (K54) |

Cada modelo guarda: faixa de frequência, detectores suportados, RBWs
CISPR, se tem pré-amplificador / pré-seletor / modo receiver / tabela de
scan / controle de LISN, endereço GPIB padrão e **o conjunto de comandos
SCPI daquela família**. O software só envia o que o modelo declara —
escolher um ESHS10 gera 17 comandos, um ESR3 gera 37.

### Editar os comandos de um modelo

Botão **"Gerenciar modelos / editar comandos..."** → aba **Comandos
SCPI**. Cada linha é `chave → comando`, com a explicação do que faz.
Nos comandos, os marcadores são substituídos na hora do envio:

- `{value}` → o valor configurado
- `{trace}` → o número do trace (detectores simultâneos)
- `{range}` → o número da sub-faixa da tabela de scan

**Comando em branco não é enviado** — é assim que se desliga um recurso
que o seu instrumento não tem. Marque *"Comandos já conferidos no manual
deste instrumento"* depois de validar, e o aviso some.

Também dá para **criar / duplicar / renomear / excluir** modelos — útil
para guardar "o ESR3 daqui, com os comandos que realmente funcionam".

---

## Conexão GPIB / VISA

Escolha a interface (GPIB, TCPIP, USB, Serial) e o endereço; o campo
**Recurso VISA** é montado sozinho (`GPIB0::20::INSTR`) e pode ser
editado à mão. Botões:

- **Listar VISA** — enumera o que a camada VISA enxerga
- **Conectar / *IDN?** — abre a sessão e mostra a identificação
- **Reset** — `*RST`
- **Erros** — lê a fila de erros do instrumento

> Para **GPIB** é preciso uma interface GPIB física (ex.: NI GPIB-USB-HS)
> com o driver VISA do fabricante instalado (NI-VISA ou R&S VISA). O
> `pyvisa-py` sozinho **não** fala GPIB — ele cobre TCPIP/USB/Serial.

---

## Configurações por sub-aba

### Frequência / Scan
Tabela de varredura, uma linha por sub-faixa: banda, início, fim, RBW,
passo, tempo de medição, atenuação (auto/manual) e pré-amp. Os botões
**A / B / C / D / E** inserem a banda CISPR já com a RBW de norma:

| Banda | Faixa | RBW (6 dB) |
|-------|-------|-----------|
| A | 9 – 150 kHz | 200 Hz |
| B | 150 kHz – 30 MHz | 9 kHz |
| C | 30 – 300 MHz | 120 kHz |
| D | 300 MHz – 1 GHz | 120 kHz |
| E | acima de 1 GHz | 1 MHz |

Mais: filtro CISPR (6 dB) vs normal (3 dB), VBW, modo receiver vs
analisador, `*RST` antes de configurar.

### Detector / Tempo
Detectores simultâneos com o trace de cada um (PK, QP, AV, RMS, CAV =
média CISPR, CRMS = RMS-média); tempo de medição por ponto (CISPR 16-2-1:
tipicamente ≥ 1 s para quase-pico); tempo de varredura (auto/manual),
pontos, número de varreduras, hold time; modo do trace (Clear/Write, Max
Hold, Average…).

### Nível / Entrada
Nível de referência e offset, unidade (dBµV, dBµA, dBm, dBpW, dBµV/m,
dBµA/m), auto range, atenuação RF (auto/manual), pré-amplificador e
ganho, pré-seletor, impedância de entrada (50/75 Ω), acoplamento AC/DC,
limitador de pulso.

### LISN / Transdutor
Controle da LISN pelo receiver (tipo ENV216 / ESH2-Z5 / ESH3-Z5 /
ENV4200 / ENV432, fase L1-L2-L3-N, PE aterrado, filtro passa-alta
150 kHz) e transdutor gravado no instrumento. A CISPR 15 item 8 pede
medição de fase e neutro, um de cada vez — troque a fase aqui e repita a
varredura.

Alternativa: deixar o transdutor desligado e aplicar os fatores pelo
próprio software, na aba de análise (ver
`06_normas_e_correcoes_configuraveis.md`).

### Medição final
Peak search seguido de remedição em QP/AV — é o mesmo critério dos
relatórios do laboratório ("picos dentro de 6 dB do limite de
quase-pico"). Configura a margem (padrão 6 dB), a quantidade de picos
(padrão 10) e quais detectores remedir.

### Comandos SCPI
Mostra **exatamente** a sequência que será enviada, comando por comando,
com a explicação de cada linha. Confira aqui antes de clicar em
**Aplicar no instrumento**.

---

## Presets de ensaio

Três presets prontos em `instruments/presets/`, um por método da norma:

- **CISPR 15 – Conduzida** — 9 kHz–30 MHz (bandas A + B), PK/QP/AV, LISN ligada
- **CISPR 15 – Antena de loop** — 9 kHz–30 MHz, PK/QP, unidade dBµA, transdutor ligado
- **CISPR 15 – Radiada** — 30–300 MHz (banda C), PK/QP, pré-amp ligado

Salvar / Novo / Excluir criam os seus próprios presets. Como tudo mais no
projeto, são JSON — dá para copiar entre as máquinas do laboratório.

---

## Fluxo típico

1. Escolha o **modelo** do receiver e confira os comandos.
2. Monte o **endereço GPIB** e clique em *Conectar / *IDN?*.
3. Escolha o **preset** do ensaio (ou monte a tabela de scan na mão).
4. Ajuste nível/atenuação/LISN conforme o seu arranjo e EUT.
5. Confira a aba **Comandos SCPI**.
6. **Aplicar no instrumento** → **Executar varredura e importar**.
7. O trace medido cai direto na aba *Análise / Relatório*, onde é
   comparado com o limite e vira PDF.

---

## Onde fica salvo

```
instruments/receivers/*.json   ← catálogo de modelos + comandos SCPI
instruments/presets/*.json     ← presets de configuração de ensaio
```

Ambos são recriados com os valores de fábrica se a pasta estiver vazia,
e **nunca sobrescrevem** o que você já editou.
