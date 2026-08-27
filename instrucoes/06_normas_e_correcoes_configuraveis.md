# Normas e tabelas de correcao configuraveis pela GUI

Este arquivo documenta o que foi adicionado para que **nada fique fixo
no codigo**: tanto as normas/metodos de ensaio quanto as tabelas de
correcao (LISN, antena, cabo) sao criadas, editadas e excluidas pela
propria tela, no mesmo espirito dos arquivos `.lim` e das tabelas de
correcao do RadiMation.

## Gerenciar normas ("Gerenciar normas (novo/duplicar/excluir)...")

Botao na tela principal, ao lado do combo de norma. Abre uma lista de
todas as normas em `core/standards/*.json` com:

- **Nova...** — cria uma norma vazia (sem nenhum segmento pre-carregado)
  a partir de um id que voce escolhe, e ja abre o editor para voce
  preencher.
- **Duplicar...** — copia uma norma existente com um novo id (util para
  criar uma variante a partir de uma norma pronta).
- **Renomear id...** — troca o id/nome do arquivo.
- **Excluir** — apaga o arquivo `.json` da norma.
- **Editar...** (ou duplo-clique) — abre o editor completo.

## Editor de norma (`gui/limit_editor.py`)

Alem dos metadados da norma (titulo, referencia, faixa de frequencia,
tipo de eixo, notas), a tabela de segmentos agora tem colunas
**Detector**, **Unidade** e **Interpolacao** por linha -- ou seja, cada
linha da tabela e livre para definir um detector novo (ex.: `QP`, `AV`,
`PK`, ou qualquer nome que a sua norma customizada precise), com sua
propria unidade (`dBuV`, `dBuA/m`, `dBm`, ...) e tipo de interpolacao
(`log-linear`, `linear`, `log-log`). Ao salvar, as linhas sao agrupadas
por detector automaticamente para formar as `limit_lines` do JSON.

Isso substitui o comportamento antigo, em que so dava para editar
detectores que ja existiam no arquivo -- agora e possivel criar uma
norma inteira do zero, com quantos detectores/linhas de limite forem
necessarios.

## Gerenciar tabelas de correcao ("Gerenciar tabelas de correcao...")

Botao na secao "Correcoes" da tela principal. Abre um gerenciador com
lista de tabelas salvas em `core/corrections_lib/*.json` e um editor de
pontos (frequencia Hz x correcao dB, interpolados em log(f)):

- **Nova / Duplicar / Excluir** — gerencia as tabelas salvas.
- **Importar CSV...** — le um CSV de 2 colunas (frequencia, correcao em
  dB) e salva como uma nova tabela na biblioteca.
- Editor de pontos com **Adicionar ponto / Remover ponto** e campos de
  nome/observacao, com botao **Salvar tabela**.

Na tela principal, os campos "Perda de cabo" e "Fator LISN/antena" agora
sao combos: escolha uma tabela salva da biblioteca, ou "Manual (dB
fixo)" para digitar um valor constante no campo ao lado (comportamento
antigo). Isso substitui os dois campos numericos fixos que existiam
antes -- agora e possivel ter varias tabelas de correcao dependentes de
frequencia (uma por LISN, por antena, por cabo) e trocar entre elas sem
reeditar nada manualmente.

## Onde tudo isso fica salvo

```
core/standards/*.json        <- normas/metodos (ja existia, agora com CRUD completo)
core/corrections_lib/*.json  <- tabelas de correcao (novo)
```

Nenhum dos dois usa banco de dados -- sao arquivos JSON simples, faceis
de copiar entre maquinas do laboratorio ou versionar.
