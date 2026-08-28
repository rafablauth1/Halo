# HALO — Ensaios de Emissão CISPR 15

Aplicação desktop para ensaios de compatibilidade eletromagnética de
**luminárias e equipamentos de iluminação** conforme a
**ABNT NBR IEC/CISPR 15:2014**.

Faz o papel do RadiMation no fluxo de um laboratório de EMC: controla o
receiver R&S por GPIB, aplica as correções da cadeia de medição, compara
o traço com os limites da norma e gera o laudo em PDF.

---

## O que ele faz

| | |
|---|---|
| **Normas** | 7 tabelas de limite (conduzida em terminais de alimentação, carga e comando; antena loop; irradiada 30–300 MHz; e as duas variantes para lâmpadas sem eletrodos) |
| **Receiver** | Catálogo de 31 modelos R&S (ESW, ESR, ESRP, ESU, ESIB, ESPI, ESCI, ESL, FSW, FSV…), cada um com seus comandos SCPI editáveis; conexão GPIB/VISA; modo de simulação para conferir a sequência antes de ir ao laboratório |
| **Bandas CISPR** | RBW e passo por banda conforme CISPR 16-1-1 (A 200 Hz · B 9 kHz · C/D 120 kHz · E 1 MHz), com validação do passo |
| **Correções** | Cadastro de cabos, LISNs, antenas e atenuadores com certificado de calibração; o erro sistemático é **interpolado em log da frequência** e aplicado ao traço |
| **Incerteza** | Faixas de U com fator k, combinação por RSS e três regras de decisão da ISO/IEC 17025 §7.8.6 (risco compartilhado, CISPR 16-4-2, banda de guarda) |
| **Detectores** | Um traço por detector (Peak, Quasi-Peak, Average…), como o RadiMation exporta; inclui o atalho do item 4.1 da CISPR 15 |
| **Laudo** | PDF com gráfico, tabela de picos numerados e veredito por detector |

---

## Instalação

Requer **Python 3.11+** no Windows.

```bash
git clone https://github.com/rafablauth1/Halo.git
cd Halo

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python main.py
```

### Atalho na área de trabalho (opcional)

```bash
python scripts/gerar_icone.py
powershell -File scripts\criar_atalho.ps1
```

Se a política de execução do Windows bloquear o `.ps1`, o mesmo conteúdo
funciona colado direto no PowerShell — o script é curto e comentado.

---

## GPIB

A conexão com o receiver é via **GPIB**, o que exige:

- um adaptador GPIB físico (NI GPIB-USB-HS ou equivalente);
- **NI-VISA** ou **R&S VISA** instalado — o `pyvisa-py` puro **não** fala
  GPIB, só LAN/USB/serial.

Os comandos SCPI do catálogo ainda **não foram validados contra hardware
real**. Antes do primeiro ensaio, use o **Modo simulação** para revisar a
sequência gerada e confira contra o manual do seu modelo. Veja
`instrucoes/03_validacao_receiver_scpi.md`.

---

## Estrutura

```
core/            regras de negócio, sem Qt
  limits.py        linhas de limite e a regra do limite inferior
  evaluation.py    comparação com o limite e detecção de picos
  equipamentos.py  certificados e interpolação do erro sistemático
  incerteza.py     regras de decisão da ISO/IEC 17025
  plotting.py      gráfico (tema claro = laudo, escuro = tela)
  report.py        laudo em PDF
  standards/       as 7 normas, em JSON editável pela própria tela
instruments/     catálogo de receivers e driver SCPI/VISA
gui/             interface PySide6 (Material 3 escuro)
instrucoes/      documentação em português — comece por 00_LEIA_PRIMEIRO.md
```

O núcleo não depende do Qt: `core/` e `instruments/` podem ser usados por
script, sem abrir a interface.

---

## Avisos técnicos em aberto

Estão documentados em `instrucoes/` e valem a leitura antes de usar em
ensaio acreditado:

- **Tempo de medição em quase-pico.** A configuração usa 50 ms, contra
  constantes de descarga de 160–550 ms da CISPR 16-1-1. O erro tende a
  **aprovar** — decisão do laboratório.
- **Escopo 2014.** A CISPR 15:2018 (ed. 9.0) aperta a faixa de
  200–300 MHz em até 10 dB. O software segue o escopo de 2014.
- **Antena loop.** A norma expressa o limite em dB(µA/m); a tabela
  transcrita está em dBµA. Confirmar antes de usar.
- **Cláusula 5** (cliques / perturbação descontínua) não implementada.

---

## Dados de laboratório

Nada que identifique o laboratório está no repositório. Estes ficam de
fora de propósito, porque trazem número de série, patrimônio, dados de
certificado de calibração e resultados de ensaio:

| Pasta | O que tem |
|---|---|
| `dados/dispositivos/` | Cadastro único — endereço GPIB, comandos e certificados de cada aparelho |
| `dados/equipamentos/` | Cadastro antigo de cabos, LISNs, antenas e atenuadores |
| `data/app.db`, `data/projetos/` | Projetos, EUTs e resultados da seção EMC |
| `reports/*.pdf`, `reports/*.docx` | Laudos emitidos |

### Instalando em outra máquina

O que vem junto do programa se reconstrói sozinho: na primeira abertura,
a aba **Dispositivos** monta a biblioteca de fábrica (31 receptores R&S +
3 instrumentos da seção EMC = 34 fichas). O banco da seção EMC também se
cria vazio sozinho. Não é preciso copiar nada para o programa abrir e
rodar em simulação.

O que **não** se reconstrói é o que é do laboratório: os aparelhos
cadastrados à mão, os números de série, os certificados e o histórico de
ensaios. Para levar isso, copie as pastas da tabela acima na mão (pen
drive ou rede) — o `git` não as carrega.

O botão **Restaurar biblioteca de fábrica**, na aba Dispositivos, recria
as fichas que vêm com o programa a qualquer momento. Ele nunca sobrescreve
ficha existente: endereço, série e certificados já preenchidos ficam como
estão.

---

*HALO · 2026*
