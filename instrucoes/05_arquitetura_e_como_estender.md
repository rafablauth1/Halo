# Arquitetura e como estender

```
core/limits.py         modelo de "linha de limite" (segmentos por detector)
core/standards/*.json  uma norma/método = um arquivo JSON (edite ou crie um novo)
core/trace.py          importação de CSV / ASCII R&S -> objeto Trace
core/corrections.py    fatores de correção (LISN, cabo, antena) aplicados ao Trace
core/evaluation.py     Trace corrigido x StandardMethod -> margem/veredito
core/plotting.py       figura matplotlib compartilhada (GUI e PDF)
core/report.py         gera o PDF final
instruments/           driver SCPI do receiver R&S + notas de LISN + varredura multi-banda
gui/                   janela PySide6 (importar, editar limites, avaliar, exportar PDF)
main.py                ponto de entrada
data/                  exemplos sintéticos de trace para testar sem hardware
```

## Como adicionar uma norma/ensaio novo

1. Copie um dos arquivos em `core/standards/` (ex.:
   `cispr15_conducted.json`) para um nome novo.
2. Ajuste `id`, `title`, `standard_ref`, `freq_range_hz` e os
   segmentos de cada `limit_line` (um por detector: QP, AV, PK...).
3. Pronto — ele aparece automaticamente no combo da GUI, sem precisar
   mexer em código Python. É o mesmo princípio dos arquivos `.lim` do
   RadiMation.

Se a norma nova precisar de lógica que não é "traço x linha de
limite" (por exemplo, contagem de cliques da CISPR15 Clause 5 —
descontínua), aí sim precisa de um módulo novo em `core/`, seguindo o
padrão de `evaluation.py`.

## Melhorias sugeridas (não implementadas ainda)

- Seletor de unidade de frequência/nível na tela de importação de CSV
  genérico (hoje só dá pra trocar chamando `load_trace(...)` com
  parâmetros; a GUI sempre assume Hz/dBµV para CSV genérico).
- Botão na GUI para carregar uma tabela de correção (CSV) dependente
  de frequência, em vez de só o valor fixo em dB.
- Tela de aquisição ao vivo (hoje o driver SCPI existe em
  `instruments/`, mas a GUI ainda não tem uma aba chamando ele — é o
  próximo passo natural depois de validar o driver no laboratório, ver
  `03_validacao_receiver_scpi.md`).
- Suporte a CISPR15 Clause 5 (descontínua/cliques) e a outras normas
  CISPR, seguindo o padrão acima.

## Testes já feitos neste ambiente (sem hardware)

- Importação dos 3 exemplos sintéticos (`data/sample_*.csv`) para os 3
  métodos.
- Avaliação e cálculo de margem/veredito por detector.
- Geração de PDF para os 3 métodos, incluindo o aviso automático de
  "limite não verificado" quando aplicável (loop e radiada).

O que **não** foi testado (porque não há hardware neste ambiente): o
driver SCPI do receiver contra um instrumento real, e a exatidão
numérica dos limites que estão marcados como não verificados — ver
`02_pendencias_limites_de_norma.md` e `03_validacao_receiver_scpi.md`.
