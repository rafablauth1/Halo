"""Strings de comando GPIB do EM TEST UCS 500N (Burst 4-4 / Surge 4-5).

O manual do operador (UCS 500N5/N7, V5.16, 88 páginas, já vasculhado por
completo) documenta a interface IEEE-488/GPIB apenas como existente
(endereço 1-31, item 20 / Setup F3) e descreve a navegação por menus do
painel frontal — não publica o dicionário de comandos ASCII/SCPI usados
pelo software "iec.control". Esse dicionário existe como documento
separado ("Manual for remote commands", instalado junto com o iec.control
em C:\\Users\\Public\\Documents\\AMETEK CTS\\iec.control\\Manual) mas não
está disponível aqui — ver app/instruments/COMANDOS_PARA_TESTAR_UCS500N.txt
para como conseguir.

Os valores abaixo são TENTATIVAS baseadas em convenções padrão IEEE-488.2 /
SCPI (não confirmadas — o fabricante pode usar sintaxe totalmente diferente).
NÃO edite este arquivo para colocar os comandos reais: use em vez disso
Configurações > "Comandos do UCS 500N" no app, que salva a sobrescrita em
data/ucs500n_commands_override.json (via app/core/command_overrides.py) sem
precisar mudar código nem gerar um .exe novo.
"""

IDN_QUERY = "*IDN?"

# Seleção de módulo/menu (Burst = IEC 61000-4-4, Surge = IEC 61000-4-5/9)
SELECT_BURST_MENU = "*CLS"
SELECT_SURGE_MENU = "*CLS"

# "TEST ON" — habilita/desabilita a saída do gerador (arma o interlock de segurança).
# Controlável manualmente pelo operador, independente de rodar um ensaio automatizado.
TEST_ON = "OUTP ON"
TEST_OFF = "OUTP OFF"

# Parâmetros de Burst (ver manual seção 9.1.1 / 9.3)
SET_BURST_VOLTAGE = "VOLT {voltage}"
SET_BURST_FREQUENCY = "FREQ {frequency_hz}"
SET_BURST_COUPLING = "COUP {coupling}"
SET_BURST_POLARITY = "POL {polarity}"

# Parâmetros de Surge (ver manual seção 10.1.1 / 10.1.2)
SET_SURGE_VOLTAGE = "VOLT {voltage}"
SET_SURGE_PHASE_ANGLE = "PHAS {angle_deg}"
SET_SURGE_COUPLING = "COUP {coupling}"
SET_SURGE_POLARITY = "POL {polarity}"

TRIGGER_SINGLE_EVENT = "*TRG"
STOP_TEST = "OUTP OFF"
QUERY_STATUS = "*STB?"
