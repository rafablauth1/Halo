# Instalação e uso

## Instalação

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Requer Python 3.10+. As dependências (PySide6, matplotlib, numpy,
pandas, reportlab, pyvisa, pyvisa-py) estão em `requirements.txt`.

## Fluxo básico na tela principal

1. **Escolha a norma/método** no combo à esquerda: `cispr15_conducted`
   (conduzida, LISN), `cispr15_loop` (loop/campo magnético) ou
   `cispr15_radiated` (radiada).
2. **Importe os dados**:
   - "Carregar exemplo sintético" — dados fictícios, só para ver o
     fluxo funcionando sem nenhum arquivo seu.
   - "Importar arquivo (CSV / ASCII R&S)..." — abre um CSV de 2
     colunas (frequência, nível) ou um export ASCII de um receiver
     R&S (o programa detecta o formato sozinho, procurando a seção
     `Values;` típica desse export).
3. **Ajuste as correções** (perda de cabo, fator de LISN/antena) se
   quiser somar algum valor fixo em dB à leitura — ver
   `04_lisn_e_fatores_de_correcao.md` para o caso de correção
   dependente da frequência (tabela, não valor fixo).
4. **Avaliar** — recalcula a margem e o veredito por detector (QP/AV)
   e atualiza o gráfico e a tabela de resultado.
5. **Editar limites desta norma...** — abre um editor de tabela para
   corrigir/completar os segmentos de frequência x valor da norma
   escolhida (grava direto no JSON em `core/standards/`). Veja
   `02_pendencias_limites_de_norma.md` para saber o que falta
   preencher.
6. **Gerar PDF...** — preenche os campos de EUT/operador/receiver/LISN
   e salva um relatório com gráfico + tabela de veredito. Se algum
   trecho do limite usado não estiver marcado como verificado, o PDF
   mostra um aviso em vermelho automaticamente — isso é proposital,
   não é bug.

## Formatos de arquivo aceitos na importação

- **CSV/TSV genérico**: 2 colunas, frequência e nível, com ou sem
  cabeçalho, separador `,`, `;` ou tab. A frequência é interpretada em
  Hz por padrão — se seu arquivo estiver em kHz/MHz, ajuste a unidade
  ao chamar `core.trace.load_trace(..., freq_unit="mhz")` (a GUI atual
  não tem esse seletor ainda; ver "Próximos passos" no arquivo 05).
- **ASCII export de receiver R&S** (famílias ESR/ESRP/ESPI/FSx): o
  parser (`core/trace.py`, função `_parse_rs_ascii`) procura um
  cabeçalho com `x-Unit;`, `y-Unit;`, `Detector;` e a seção
  `Values;<N>` seguida dos pares frequência;nível. Isso cobre o
  layout mais comum, mas **cada família/firmware pode variar
  ligeiramente** — se a importação falhar ou vier com valores
  estranhos, abra o arquivo exportado num editor de texto, compare com
  o que o parser espera, e ajuste `_parse_rs_ascii` conforme o seu
  layout real.
