# LISN (ENV216/ESH2-Z5) e fatores de correção

## Comutação de fase L/N da LISN

A grande maioria das LISN/AMN passivas — incluindo a R&S ENV216 —
**não tem uma porta de controle remoto SCPI própria** para trocar a
fase medida (Line/Neutral). A troca é feita de uma destas formas:

- **manualmente**, por uma chave física na própria LISN;
- por um **comutador de fase auxiliar** controlado por outro software
  (é o que o EMC32 da R&S normalmente usa);
- em alguns modelos, por um **conector de controle remoto** dedicado
  (DB9/DB25), com protocolo próprio do fabricante — **não é SCPI
  padrão** e varia por modelo. Confirme no manual da sua ENV216
  (seção "remote control"/"Fernsteuerung") se ela tem esse conector.

`instruments/lisn.py` já tem uma função `require_manual_phase_switch`
que devolve a mensagem para pausar o software e pedir ao operador para
comutar manualmente entre as duas capturas (Line e Neutral), que é o
caminho mais confiável se você não tiver confirmado o conector remoto.
Se confirmar que sua LISN tem controle remoto real, implemente o
protocolo dela na classe `LisnInfo`/funções desse módulo.

## Fatores de correção (cabo, LISN, antena loop)

Em `core/corrections.py`, a convenção é:

```
nivel_corrigido = leitura_do_receiver + correction_dB
```

Ou seja, `correction_dB` é o que você soma à leitura crua para chegar
no nível real na fonte — o mesmo conceito de "Cable Loss"/"Antenna
Factor" que o RadiMation e o EMC32 usam.

**Os valores que vêm no projeto são todos placeholder de 0 dB**
(`DEFAULT_LISN_ENV216_INSERTION_LOSS`, `DEFAULT_CABLE_LOSS`,
`DEFAULT_LOOP_ANTENNA_FACTOR`). Isso é proposital: o fator de inserção
real da SUA LISN, o fator da SUA antena loop e a perda do SEU cabo
vêm de uma folha de calibração específica daquele equipamento (por
número de série), que eu não tenho como adivinhar.

### Como usar a correção certa (dependente de frequência)

A tela principal hoje só tem um campo de correção fixa em dB (útil
para um ajuste rápido). Para uma tabela de correção que varia com a
frequência (o caso real de LISN/antena/cabo), use
`CorrectionTable.from_csv(caminho)`, passando um CSV de 2 colunas
(frequência em Hz, correção em dB) — normalmente é exatamente o que
vem na folha de calibração do laboratório, só ajustando o formato. Ver
`core/corrections.py` para o método `from_csv`/`from_json`. (A GUI
ainda não tem botão para carregar esse CSV direto na tela — é uma
das melhorias sugeridas no arquivo 05.)
