# Equipamentos e certificados de calibração

Aba **Equipamentos / Certificados**: cadastro dos itens da cadeia de
medição (cabo, LISN, antena, atenuador, pré-amplificador, sonda de
corrente, adaptador) e dos seus certificados de calibração, com a
**correção do erro sistemático aplicada interpolada** ao ensaio.

---

## A ideia

Um certificado de calibração dá o erro sistemático do equipamento em
**algumas frequências discretas** — por exemplo, a perda de inserção do
cabo em 9 kHz, 150 kHz, 1 MHz, 10 MHz e 30 MHz. O ensaio, porém, mede em
milhares de frequências.

O software **interpola** os pontos do certificado (linear em log da
frequência, como é a prática em EMC) e soma a correção resultante ao
traço medido, ponto a ponto:

```
nível_corrigido = leitura_do_receiver + correção_interpolada
```

**Fora da faixa calibrada o valor da extremidade é mantido — não há
extrapolação.** Extrapolar certificado não tem respaldo metrológico, e o
software avisa quando a faixa do ensaio é maior que a calibrada.

---

## Cadastro

**Identificação:** tipo, fabricante, modelo, número de série, patrimônio,
descrição.

**Aplicar como** — define o sinal da correção:

| Tipo | Grandeza | Entra |
|---|---|---|
| Cabo | Perda de inserção (dB) | somando |
| LISN | Fator de divisão de tensão (dB) | somando |
| Antena | Fator de antena (dB/m) | somando |
| Atenuador | Atenuação (dB) | somando |
| **Pré-amplificador** | **Ganho (dB)** | **subtraindo** |

O padrão já vem certo por tipo, mas dá para trocar — se o seu certificado
declarar a grandeza com sinal invertido, é aqui que se ajusta.

---

## Certificados

Cada equipamento guarda **vários** certificados (histórico de
calibrações); o selecionado no combo é o que vale. Campos: número,
laboratório, data de calibração, data de validade, fator *k* e grandeza.

A validade aparece ao lado das datas, colorida:

- **verde** — válido
- **amarelo** — vence em menos de 60 dias
- **vermelho** — vencido

Um certificado vencido **não bloqueia** o uso: ele aplica a correção
normalmente e emite aviso, em vermelho, na cadeia de medição. A decisão
de usar ou não é sua.

### Pontos

Tabela de `frequência (Hz) · valor (dB) · incerteza U (dB)`. A incerteza
é a **expandida**, no fator *k* declarado no certificado.

**Importar CSV...** lê um arquivo de duas ou três colunas (frequência,
valor, incerteza — a terceira opcional) e pergunta a unidade da coluna de
frequência (Hz/kHz/MHz/GHz).

**Ver curva** abre o gráfico da correção interpolada, com os pontos do
certificado marcados e a faixa de incerteza sombreada. É exatamente a
curva que será somada ao ensaio — vale conferir aqui antes de usar.

---

## Cadeia de medição

Na aba **Análise / Relatório**, o grupo *Cadeia de medição
(certificados)* lista os equipamentos cadastrados. Marque os usados no
ensaio: as correções são **somadas** e as incertezas **combinadas por
RSS** (raiz da soma dos quadrados das incertezas padrão), conforme o GUM:

```
u_combinada = √( Σ (U_i / k_i)² )
U_combinada = k · u_combinada
```

O resumo abaixo da lista mostra a faixa da correção total, a incerteza
expandida máxima e os avisos (certificado vencido, ausente, ou faixa
insuficiente).

### Exemplo real

Marcando a LISN ENV216 (10,0 dB em 1 MHz) e o cabo RG214 (0,31 dB em
1 MHz), um pico de 62,40 dBµV passa a 72,71 dBµV — **+10,31 dB**. No
arquivo de demonstração isso muda o veredito de 5 para 10 reprovações.

Ou seja: **sem os certificados aplicados o laudo está errado.** É por
isso que este cadastro existe.

---

## Onde fica salvo

```
dados/equipamentos/*.json    ← um arquivo por equipamento, com todos os seus certificados
```

JSON simples, sem banco de dados — dá para copiar entre as máquinas do
laboratório e versionar.

---

## Relação com as "tabelas de correção"

O grupo *Correções* (ver `06_normas_e_correcoes_configuraveis.md`)
continua existindo para valores avulsos — um dB fixo, ou uma tabela solta
que não vem de certificado. As duas coisas se somam.

Para laudo, prefira o cadastro de equipamentos: ele carrega
rastreabilidade (número do certificado, laboratório, validade,
incerteza), que a tabela avulsa não tem.
