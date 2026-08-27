# Validação do controle remoto do receiver R&S (SCPI)

O módulo `instruments/scpi_receiver.py` implementa um driver SCPI/VISA
genérico para a família de receivers de EMI da Rohde & Schwarz
(ESR/ESRP/ESPI/ESCS, ou um FSx/FPL com opção de receiver de EMI).

## Por que isso ainda não está "pronto para produção"

Este software foi desenvolvido num ambiente de nuvem, sem nenhum
receiver R&S conectado. Os comandos SCPI usados seguem o padrão
documentado publicamente pela R&S para essa família de instrumentos
(`FREQ:STAR`, `FREQ:STOP`, `BAND:RES`, `SENS:DET1:FUNC`, `INIT`,
`TRAC:DATA?`, etc.), mas a sintaxe exata **varia entre modelo e versão
de firmware**. Cada comando no código está marcado com um comentário
`# VERIFICAR:` apontando o que precisa ser conferido.

## Passo a passo para validar no seu laboratório

1. Instale o driver VISA do fabricante (R&S VISA ou NI-VISA) no PC que
   vai rodar o programa — o `pyvisa-py` sozinho funciona para LAN/TCP,
   mas para GPIB/USB normalmente precisa do VISA da fabricante.
2. Descubra o endereço do instrumento (LAN: IP fixo do receiver; ou
   rode `instruments.scpi_receiver.list_visa_resources()` para listar
   os recursos VISA visíveis).
3. Teste **só a conexão e a identificação** primeiro:
   ```python
   from instruments.scpi_receiver import RohdeSchwarzEMIReceiver, ReceiverConfig
   r = RohdeSchwarzEMIReceiver(ReceiverConfig(resource="TCPIP0::<IP_DO_RECEIVER>::INSTR"))
   print(r.connect())   # deve imprimir o *IDN? do seu receiver
   r.disconnect()
   ```
4. Abra o manual **"Remote control via SCPI"** (ou o manual de
   operação com o capítulo de programação) do SEU modelo exato e
   confira, um a um, os comandos marcados com `# VERIFICAR:` em
   `configure_scan`, `run_scan` e `read_trace`. Ajuste o texto do
   comando se o seu firmware usar outra grafia.
5. Só depois disso rode `configure_scan` + `run_scan` + `read_trace`
   com uma faixa de frequência pequena e curta, e confira se o trace
   devolvido bate com o que aparece no display do instrumento.
6. Para cobrir as sub-faixas de RBW da CISPR 15 (ex.: 200 Hz entre
   9–150 kHz e 9 kHz entre 150 kHz–30 MHz), use
   `instruments/acquisition.py` (`run_multi_band_scan`), que chama o
   driver uma vez por faixa e junta o resultado num só `Trace` — mas
   confirme esses valores de RBW/tempo de varredura contra o texto
   oficial da norma antes de usar (ver arquivo 02).

## Sobre a LISN durante a aquisição ao vivo

O receiver por si só não comuta entre medir a fase Line e a fase
Neutral da LISN — isso é tratado em `instruments/lisn.py` e no arquivo
`04_lisn_e_fatores_de_correcao.md`.

## Se o seu instrumento não for da R&S

A camada de conexão (`pyvisa`, `ResourceManager`, `open_resource`,
`write`/`query`) é genérica e funciona com qualquer instrumento
LAN/GPIB/USB compatível com SCPI. Só os mnemônicos dentro de
`configure_scan`/`read_trace` são específicos da família R&S — troque
por outra classe de driver seguindo o mesmo padrão se usar outro
fabricante.
