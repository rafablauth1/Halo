"""Comandos SCPI do contador Agilent 53131A usados pelo app.

Validados em campo: o erro SCPI -213 "Init ignored" exigiu usar FETCH em vez
de :MEASure:...? pra ler o resultado (esse último dispara outro INIT por
dentro); o erro SCPI -420 "Query UNTERMINATED" exigiu nunca mandar uma
consulta nova sem ter lido por completo a resposta da consulta anterior.
"""

IDN_QUERY = "*IDN?"
RECALL = "*RCL {register}"
CONFIGURE_TOTALIZE_TIMED = ":CONFigure:TOTalize:TIMed {gate_time_s}"
INIT = "INIT"
FETCH = ":FETCh?"
