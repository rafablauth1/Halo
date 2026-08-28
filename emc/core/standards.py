from dataclasses import dataclass


@dataclass(frozen=True)
class BurstLevel:
    level: int
    voltage: int


@dataclass(frozen=True)
class SurgeLevel:
    level: int
    voltage: int


@dataclass(frozen=True)
class DipsLevel:
    level: int
    percent_un: int  # % de QUEDA (o quanto a tensão cai) — 100 = interrupção total
    cycles: float


# Valores extraídos do manual EM TEST UCS 500Nx (V5.16), seções 9.1.2, 10.1.2 e 11.2.2 —
# são os níveis padrão definidos nas próprias normas IEC 61000-4-4/4-5/4-11, não são
# comandos proprietários do fabricante.

BURST_LEVELS = [
    BurstLevel(1, 500),
    BurstLevel(2, 1000),
    BurstLevel(3, 2000),
    BurstLevel(4, 4000),
]
BURST_SPIKE_FREQUENCIES_HZ = (5000, 100000)
BURST_DURATION_MS_BY_FREQ = {5000: 15.0, 100000: 0.75}
BURST_REPETITION_MS = 300
BURST_COUPLINGS = ("COM", "ALL", "CCC")  # COM = IEC Ed.2 (2004), ALL = IEC Ed.1 (1995)
BURST_POLARITIES = ("+", "-")
BURST_DEFAULT_DURATION_S = 60.0  # duração default por polaridade — ajustável no roteiro

SURGE_LEVELS = [
    SurgeLevel(1, 500),
    SurgeLevel(2, 1000),
    SurgeLevel(3, 2000),
    SurgeLevel(4, 4000),
]
SURGE_VOLTAGE_RISE_US = 1.2
SURGE_VOLTAGE_DURATION_US = 50
SURGE_CURRENT_RISE_US = 8
SURGE_CURRENT_DURATION_US = 20
SURGE_PHASE_ANGLES_DEG = (0, 90, 180, 270)
SURGE_COUPLINGS = ("L-N", "L-PE", "N-PE", "L+N-PE")
SURGE_POLARITIES = ("+", "-", "ALT")
SURGE_DEFAULT_PULSE_COUNT = 1  # pulsos por combinação polaridade×ângulo — ajustável no roteiro
SURGE_DEFAULT_INTERVAL_S = 1.0  # intervalo entre pulsos — ajustável no roteiro

# Combinações de fase para medidor bi/trifásico — o roteiro roda uma vez por combinação
# selecionada, com pausa para o operador trocar o setup entre uma e outra. Quais combinações
# se aplicam depende do medidor sob ensaio, por isso a seleção é sempre manual do operador.
# As 9 combinações (linha-neutro, linha-terra e linha-linha) vêm da tabela de sincronismo de
# fase do manual EM TEST UCS 500Nx V5.16, §10.1.4 (p.49-50) — antes faltavam as 3 de linha-terra.
SURGE_METER_PHASE_COMBINATIONS = (
    "L1-N", "L2-N", "L3-N",
    "L1-PE", "L2-PE", "L3-PE",
    "L1-L2", "L1-L3", "L2-L3",
)


# Duração em ciclos — é assim que a IEC 61000-4-11 define os níveis (não em ms):
# o número de ciclos é o mesmo em qualquer rede, mas a duração real em ms depende da
# frequência do ensaio (60Hz no Brasil), por isso a conversão pra ms é feita em tempo de
# execução (ver Chroma615xxDriver.run_test), a partir da frequência escolhida no roteiro.
# percent_un é % de QUEDA (100 = interrupção total) — a IEC 61000-4-11 classicamente
# publica esses níveis como % Un REMANESCENTE (40/70/80% Un), por isso os valores aqui
# são o complemento (100 - Un remanescente): nível 3 (40% Un remanescente) = 60% de
# queda, nível 4 (70% Un) = 30% de queda, nível 5 (80% Un) = 20% de queda.
DIPS_LEVELS = [
    DipsLevel(1, 100, 0.5),
    DipsLevel(2, 100, 1),
    DipsLevel(3, 60, 12),
    DipsLevel(4, 30, 30),
    DipsLevel(5, 20, 300),
]
DIPS_SHORT_INTERRUPTION_CYCLES = 300
DIPS_PHASE_ANGLES_DEG = (0, 90, 180, 270)
