"""
instruments/receiver_settings.py

Todos os parametros de configuracao do receiver que sao pertinentes a um
ensaio de emissao conforme CISPR 15 / CISPR 16-1-1 / CISPR 16-2-1,
reunidos em um objeto so (ReceiverSettings), mais:

- as bandas CISPR (A/B/C/D/E) com a RBW de 6 dB exigida por norma;
- presets de scan prontos para os 3 metodos da CISPR 15 (conduzida,
  loop 9 kHz-30 MHz, radiada 30-300 MHz);
- o tradutor settings -> sequencia de comandos SCPI, que usa o conjunto
  de comandos do MODELO escolhido (instruments/receiver_models.py).

Nada aqui e fixo: o usuario ajusta tudo pela aba "Receiver / GPIB" da
GUI e salva como preset em instruments/presets/*.json.

>>> Os valores default seguem a pratica usual de laboratorio de EMC e o
que a CISPR 16-1-1 define para RBW/detector por banda, mas o tempo de
medicao, atenuacao e nivel de referencia dependem do SEU arranjo e do
SEU EUT. Confira antes de usar em ensaio real. <<<
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from instruments.receiver_models import ReceiverModel

PRESETS_DIR = Path(__file__).parent / "presets"

_SAFE_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ")


# ---------------------------------------------------------------------------
# Bandas CISPR 16-1-1 (RBW de 6 dB por faixa)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CisprBand:
    name: str
    freq_min_hz: float
    freq_max_hz: float
    rbw_hz: float
    step_hz: float
    note: str = ""


CISPR_BANDS: dict[str, CisprBand] = {
    "A": CisprBand("Banda A", 9_000, 150_000, 200, 100,
                    "CISPR 16-1-1: RBW 200 Hz (6 dB) de 9 kHz a 150 kHz."),
    "B": CisprBand("Banda B", 150_000, 30_000_000, 9_000, 4_500,
                    "CISPR 16-1-1: RBW 9 kHz (6 dB) de 150 kHz a 30 MHz."),
    "C": CisprBand("Banda C", 30_000_000, 300_000_000, 120_000, 60_000,
                    "CISPR 16-1-1: RBW 120 kHz (6 dB) de 30 MHz a 300 MHz."),
    "D": CisprBand("Banda D", 300_000_000, 1_000_000_000, 120_000, 60_000,
                    "CISPR 16-1-1: RBW 120 kHz (6 dB) de 300 MHz a 1 GHz."),
    "E": CisprBand("Banda E", 1_000_000_000, 18_000_000_000, 1_000_000, 500_000,
                    "CISPR 16-1-1: RBW 1 MHz (6 dB) acima de 1 GHz."),
}

# CISPR 16-2-1: o passo de frequencia nao pode passar de METADE da largura
# de banda de resolucao, senao um sinal estreito pode cair entre dois pontos
# da varredura e nao ser medido.
PASSO_MAXIMO_SOBRE_RBW = 0.5


def banda_para_frequencia(freq_hz: float) -> Optional[str]:
    """Em qual banda CISPR esta esta frequencia."""
    for chave, banda in CISPR_BANDS.items():
        if banda.freq_min_hz <= freq_hz < banda.freq_max_hz:
            return chave
    return None


def passo_maximo_hz(rbw_hz: float) -> float:
    return rbw_hz * PASSO_MAXIMO_SOBRE_RBW


def validar_passo(rbw_hz: float, passo_hz: float) -> Optional[str]:
    """Avalia o passo contra a RBW. Devolve a mensagem, ou None se ok.

    Duas severidades, porque a pratica de laboratorio e legitimamente mais
    solta que a regra do livro:

    - passo > RBW: problema de verdade. Ha frequencias que nenhum ponto da
      varredura chega perto, entao um sinal estreito pode nao ser visto.
    - RBW/2 < passo <= RBW: aceitavel num PRESCAN em detector de pico, que
      e como o laboratório opera (passo 10 kHz com RBW 9 kHz). O que vale para o
      laudo e a medicao final, refeita nas frequencias de pico. So nao vale
      se a varredura for usada direto como resultado final.
    """
    if passo_hz <= 0:
        return "passo deve ser maior que zero"
    if passo_hz > rbw_hz:
        return (f"passo {passo_hz:g} Hz MAIOR que a RBW ({rbw_hz:g} Hz) — "
                "ha frequencias que a varredura nao cobre")
    if passo_hz > passo_maximo_hz(rbw_hz):
        return (f"passo {passo_hz:g} Hz acima de metade da RBW "
                f"({passo_maximo_hz(rbw_hz):g} Hz) — aceitavel para prescan em pico, "
                "desde que haja medicao final nos picos")
    return None


def severidade_passo(rbw_hz: float, passo_hz: float) -> str:
    """'ok' | 'aviso' (prescan) | 'erro' (cobertura insuficiente)."""
    if passo_hz <= 0 or passo_hz > rbw_hz:
        return "erro"
    if passo_hz > passo_maximo_hz(rbw_hz):
        return "aviso"
    return "ok"


def dividir_em_bandas_cispr(freq_min_hz: float, freq_max_hz: float, *,
                             meas_time_s: float = 1.0,
                             detectors: Optional[list[str]] = None) -> list["ScanRange"]:
    """Divide uma faixa de ensaio nas bandas CISPR que ela atravessa, cada
    uma ja com a RBW e o passo exigidos por norma.

    Ex.: 9 kHz - 30 MHz vira duas faixas (Banda A com RBW 200 Hz e Banda B
    com RBW 9 kHz), porque a norma muda a largura de banda em 150 kHz."""
    detectors = detectors or ["PK", "QP", "AV"]
    faixas: list[ScanRange] = []
    for chave, banda in CISPR_BANDS.items():
        ini = max(freq_min_hz, banda.freq_min_hz)
        fim = min(freq_max_hz, banda.freq_max_hz)
        if ini >= fim:
            continue  # o ensaio nao passa por esta banda
        faixas.append(ScanRange(
            band=chave, start_hz=ini, stop_hz=fim,
            rbw_hz=banda.rbw_hz, step_hz=banda.step_hz,
            meas_time_s=meas_time_s, detectors=list(detectors),
            note=banda.note,
        ))
    return faixas


# ---------------------------------------------------------------------------
# Uma sub-faixa de varredura
# ---------------------------------------------------------------------------

@dataclass
class ScanRange:
    """Uma linha da tabela de scan (equivale a uma 'range' do receiver R&S
    e a uma linha da tabela de varredura do RadiMation)."""
    enabled: bool = True
    band: str = "B"
    start_hz: float = 150_000.0
    stop_hz: float = 30_000_000.0
    rbw_hz: float = 9_000.0
    step_hz: float = 4_500.0
    meas_time_s: float = 1.0
    detectors: list[str] = field(default_factory=lambda: ["PK", "QP", "AV"])
    attenuation_db: float = 10.0
    attenuation_auto: bool = True
    preamp: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Configuracao completa do receiver
# ---------------------------------------------------------------------------

@dataclass
class ReceiverSettings:
    """Todos os parametros do receiver pertinentes a um ensaio CISPR 15."""

    # ---- identificacao do preset ----
    name: str = "Novo preset"
    description: str = ""

    # ---- modo de operacao ----
    receiver_mode: bool = True          # modo "receiver" (scan) vs analisador
    reset_before_config: bool = True    # *RST antes de configurar
    display_update: bool = True         # atualizar tela do instrumento (mais lento, mas visivel)

    # ---- tabela de scan (multi-banda) ----
    scan_ranges: list[ScanRange] = field(default_factory=list)

    # ---- banda de resolucao ----
    rbw_filter_cispr: bool = True       # filtro CISPR (6 dB) vs normal (3 dB)
    vbw_hz: Optional[float] = None      # None = automatico
    vbw_auto: bool = True

    # ---- detectores ----
    detectors: list[str] = field(default_factory=lambda: ["PK", "QP", "AV"])
    detector_trace_map: dict[str, int] = field(default_factory=lambda: {"PK": 1, "QP": 2, "AV": 3})

    # ---- tempos ----
    meas_time_s: float = 1.0            # tempo de medicao por ponto (CISPR: >= 1 s p/ QP)
    sweep_time_s: Optional[float] = None
    sweep_time_auto: bool = True
    sweep_points: Optional[int] = None
    sweep_count: int = 1
    hold_time_s: float = 0.0

    # ---- nivel / entrada ----
    ref_level_dbuv: float = 100.0
    ref_level_offset_db: float = 0.0
    attenuation_db: float = 10.0
    attenuation_auto: bool = True
    preamp: bool = False
    preamp_level_db: Optional[float] = None
    preselector: bool = True
    auto_range: bool = True
    level_unit: str = "DBUV"            # DBUV, DBUA, DBM, DBPW, DBUV_M, DBUA_M
    input_impedance_ohm: int = 50       # 50 ou 75
    input_coupling: str = "AC"          # AC ou DC
    noise_pulse_limiter: bool = False   # limitador de pulso (protege o front-end)

    # ---- trace ----
    trace_mode: str = "MAXH"            # WRIT (clear/write), MAXH (max hold), AVER, MINH, VIEW
    n_traces: int = 3

    # ---- transdutor / correcao ----
    transducer_name: str = ""           # nome do fator gravado no instrumento
    transducer_enabled: bool = False

    # ---- LISN / AMN (quando controlada pelo receiver) ----
    lisn_control: bool = False
    lisn_type: str = "ENV216"           # ENV216, ESH2Z5, ESH3Z5, ENV4200, ENV432
    lisn_phase: str = "L1"              # L1, L2, L3, N
    lisn_pe_grounded: bool = True
    lisn_highpass_150k: bool = False    # filtro passa-alta 150 kHz (ENV216)

    # ---- medicao final (peak search -> remedicao QP/AV) ----
    final_measurement: bool = True
    final_meas_margin_db: float = 15.0  # "all peaks above X dB below the limit lines"
    final_meas_max_peaks: int = 10      # numero de picos remedidos
    final_meas_detectors: list[str] = field(default_factory=lambda: ["QP", "AV"])
    # tempo de medicao e de observacao da medicao final, POR DETECTOR:
    #   {"QP": (measure_time_s, observation_time_s), ...}
    final_meas_times: dict[str, tuple[float, float]] = field(default_factory=dict)
    peak_discrimination: str = "None"

    # ---- conexao ----
    visa_resource: str = "GPIB0::20::INSTR"
    timeout_ms: int = 20000

    notes: str = ""

    # -------- helpers --------
    def total_span_hz(self) -> tuple[float, float]:
        active = [r for r in self.scan_ranges if r.enabled]
        if not active:
            return (0.0, 0.0)
        return (min(r.start_hz for r in active), max(r.stop_hz for r in active))


# ---------------------------------------------------------------------------
# Presets prontos dos 3 metodos da CISPR 15
# ---------------------------------------------------------------------------

def _range_from_band(band_key: str, start_hz: float, stop_hz: float,
                      detectors: list[str], meas_time_s: float = 1.0) -> ScanRange:
    band = CISPR_BANDS[band_key]
    return ScanRange(band=band_key, start_hz=start_hz, stop_hz=stop_hz,
                      rbw_hz=band.rbw_hz, step_hz=band.step_hz,
                      meas_time_s=meas_time_s, detectors=list(detectors),
                      note=band.note)


def preset_cispr15_conducted() -> ReceiverSettings:
    """Conduzida nos terminais de alimentacao: 9 kHz - 30 MHz (bandas A + B),
    detectores QP e AV, LISN comutando fase/neutro."""
    return ReceiverSettings(
        name="CISPR 15 - Conduzida (terminais de alimentacao)",
        description="9 kHz - 30 MHz via LISN/AMN. Banda A (RBW 200 Hz) + Banda B (RBW 9 kHz).",
        scan_ranges=[
            _range_from_band("A", 9_000, 150_000, ["PK", "QP", "AV"]),
            _range_from_band("B", 150_000, 30_000_000, ["PK", "QP", "AV"]),
        ],
        detectors=["PK", "QP", "AV"],
        level_unit="DBUV",
        lisn_control=True,
        lisn_type="ENV216",
        lisn_phase="L1",
        final_measurement=True,
        final_meas_detectors=["QP", "AV"],
        notes="CISPR 15 item 4.3.1 / item 8. Medir fase e neutro, um de cada vez.",
    )


def preset_cispr15_loop() -> ReceiverSettings:
    """Antena de loop (campo magnetico): 9 kHz - 30 MHz, detector QP."""
    return ReceiverSettings(
        name="CISPR 15 - Antena de loop (9 kHz - 30 MHz)",
        description="Campo magnetico com antena de quadro de 2 m, 3 direcoes (Loop A/B/C).",
        scan_ranges=[
            _range_from_band("A", 9_000, 150_000, ["PK", "QP"]),
            _range_from_band("B", 150_000, 30_000_000, ["PK", "QP"]),
        ],
        detectors=["PK", "QP"],
        level_unit="DBUA",
        lisn_control=False,
        transducer_enabled=True,
        final_measurement=True,
        final_meas_detectors=["QP"],
        notes="CISPR 15 item 4.4.1 / item 9. Fator da antena loop deve estar carregado "
              "como transdutor no receiver ou como tabela de correcao no software.",
    )


def preset_cispr15_radiated() -> ReceiverSettings:
    """Radiada 30 MHz - 300 MHz, detector QP, RBW 120 kHz."""
    return ReceiverSettings(
        name="CISPR 15 - Radiada (30 MHz - 300 MHz)",
        description="Campo eletrico, RBW 120 kHz (Banda C), conforme Anexo B da norma.",
        scan_ranges=[
            _range_from_band("C", 30_000_000, 300_000_000, ["PK", "QP"]),
        ],
        detectors=["PK", "QP"],
        level_unit="DBUV",
        preamp=True,
        transducer_enabled=True,
        final_measurement=True,
        final_meas_detectors=["QP"],
        notes="CISPR 15 item 4.4.2 / item 9. Fator de antena + perda de cabo obrigatorios.",
    )


# ---------------------------------------------------------------------------
# Presets transcritos da configuracao REAL do RadiMation do laboratório
# (RadiMation 2016.2.8, telas de Conducted Emission fotografadas).
#
# Estes sao os valores que o laboratorio usa de fato -- e em varios pontos
# eles diferem do "livro": o passo, por exemplo, e da ordem da propria RBW
# e nao de metade dela, porque a varredura inicial e so um PRESCAN com
# detector de pico; o que vale para o laudo e a medicao final, refeita nas
# frequencias de pico com QP/AV e tempo de observacao longo.
# ---------------------------------------------------------------------------

def preset_lab_conduzida() -> ReceiverSettings:
    """"Faixa 9kHz - 30MHz / neutro 220" — emissao conduzida, LISN neutro."""
    return ReceiverSettings(
        name="laboratório - Conduzida 9 kHz-30 MHz (neutro)",
        description="Transcrito do RadiMation do laboratório. Prescan em pico, "
                    "medicao final em Average + QP.",
        scan_ranges=[
            ScanRange(band="A", start_hz=9_000, stop_hz=150_000,
                       rbw_hz=200, step_hz=200, meas_time_s=50e-3,
                       attenuation_db=20.0, attenuation_auto=False, preamp=False,
                       detectors=["PK"], note="Banda A · RBW 200 Hz · passo 0,0002 MHz"),
            ScanRange(band="B", start_hz=150_000, stop_hz=30_000_000,
                       rbw_hz=9_000, step_hz=10_000, meas_time_s=1e-3,
                       attenuation_db=20.0, attenuation_auto=False, preamp=False,
                       detectors=["PK"], note="Banda B · RBW 9 kHz · passo 0,01 MHz"),
        ],
        detectors=["PK", "AV"],
        detector_trace_map={"PK": 1, "AV": 2},
        meas_time_s=1e-3,
        sweep_time_auto=True,
        sweep_count=1,
        ref_level_dbuv=100.0,
        attenuation_db=20.0,
        attenuation_auto=False,
        preamp=False,
        preamp_level_db=0.0,
        level_unit="DBUV",
        lisn_control=True,
        lisn_type="ENV216",
        lisn_phase="N",
        final_measurement=True,
        final_meas_margin_db=15.0,
        final_meas_max_peaks=10,
        final_meas_detectors=["AV", "QP"],
        final_meas_times={"PK": (0.100, 0.100), "AV": (0.050, 0.050),
                           "QP": (0.050, 0.050), "RMS": (0.100, 0.100)},
        notes="Limites: CISPR15_COND_150kHz-30MHz_AVG e _QP. "
              "Test Equipment: CISPR15_EMI_COND_neutro. "
              "ATENCAO: os 50 ms de medicao/observacao do quase-pico sao curtos "
              "frente as constantes de descarga do detector QP da CISPR 16-1-1 "
              "(500 ms na banda A, 160 ms na banda B). Um QP que nao estabiliza "
              "le PARA BAIXO, ou seja, para o lado que aprova. Conferir contra a "
              "CISPR 16-1-1 antes de usar em laudo -- ver instrucoes/09.",
    )


def preset_lab_loop() -> ReceiverSettings:
    """"Faixa 9 kHz - 30 MHz / Loop A 220" — antena de loop."""
    return ReceiverSettings(
        name="laboratório - Loop 9 kHz-30 MHz (Loop A)",
        description="Transcrito do RadiMation do laboratório. Pre-amplificador 10 dB "
                    "na banda A, medicao final em QP.",
        scan_ranges=[
            ScanRange(band="A", start_hz=9_000, stop_hz=150_000,
                       rbw_hz=200, step_hz=200, meas_time_s=50e-3,
                       attenuation_db=20.0, attenuation_auto=False, preamp=True,
                       detectors=["PK"], note="Banda A · RBW 200 Hz · passo 0,0002 MHz"),
            ScanRange(band="B", start_hz=150_000, stop_hz=30_000_000,
                       rbw_hz=9_000, step_hz=10_000, meas_time_s=1e-3,
                       attenuation_db=20.0, attenuation_auto=False, preamp=True,
                       detectors=["PK"], note="Banda B · RBW 9 kHz"),
        ],
        detectors=["PK"],
        detector_trace_map={"PK": 1},
        meas_time_s=50e-3,
        sweep_time_auto=True,
        sweep_count=1,
        ref_level_dbuv=100.0,
        attenuation_db=20.0,
        attenuation_auto=False,
        preamp=True,
        preamp_level_db=10.0,
        level_unit="DBUA",
        lisn_control=False,
        lisn_phase="N",
        transducer_enabled=True,
        final_measurement=True,
        final_meas_margin_db=20.0,
        final_meas_max_peaks=10,
        final_meas_detectors=["QP"],
        final_meas_times={"PK": (1.0, 5.0), "AV": (1.0, 5.0),
                           "QP": (1.0, 2.0), "RMS": (1.0, 5.0)},
        notes="Limite: CISPR15_QP_Rad_9kHz_150kHz. "
              "Test Equipment: CISPR15_RAD_9kHz-30MHz. Medir Loop A, B e C.",
    )


def preset_lab_anexo_b() -> ReceiverSettings:
    """"Faixa 30MHz - 300MHz - Anexo B 220V"."""
    return ReceiverSettings(
        name="laboratório - Anexo B 30-300 MHz",
        description="Transcrito do RadiMation do laboratório. Prescan em pico, "
                    "medicao final em QP com 15 s de observacao.",
        scan_ranges=[
            ScanRange(band="C", start_hz=30_000_000, stop_hz=300_000_000,
                       rbw_hz=120_000, step_hz=100_000, meas_time_s=500e-6,
                       attenuation_db=16.0, attenuation_auto=False, preamp=True,
                       detectors=["PK"], note="Banda C · RBW 120 kHz · passo 100 kHz"),
        ],
        detectors=["PK"],
        detector_trace_map={"PK": 1},
        meas_time_s=500e-6,
        sweep_time_auto=True,
        sweep_count=1,
        ref_level_dbuv=80.0,
        attenuation_db=16.0,
        attenuation_auto=False,
        preamp=True,
        level_unit="DBUV",
        lisn_control=False,
        lisn_phase="N",
        transducer_enabled=True,
        final_measurement=True,
        final_meas_margin_db=15.0,
        final_meas_max_peaks=10,
        final_meas_detectors=["QP"],
        final_meas_times={"PK": (1.0, 5.0), "AV": (1.0, 5.0),
                           "QP": (2.0, 15.0), "RMS": (1.0, 5.0)},
        notes="Limite: CISPR 15 Anexo B. Test Equipment: Anexo B_M3.",
    )


BUILTIN_PRESETS = {
    "cispr15_conducted": preset_cispr15_conducted,
    "cispr15_loop": preset_cispr15_loop,
    "cispr15_radiated": preset_cispr15_radiated,
    "lab_conduzida_neutro": preset_lab_conduzida,
    "lab_loop_a": preset_lab_loop,
    "lab_anexo_b": preset_lab_anexo_b,
}


# ---------------------------------------------------------------------------
# Tradutor: settings -> comandos SCPI do modelo escolhido
# ---------------------------------------------------------------------------

_DETECTOR_SCPI = {
    "PK": "POS",      # positive peak
    "QP": "QPE",      # quasi-peak
    "AV": "AVER",     # average
    "RMS": "RMS",
    "CAV": "CAV",     # CISPR average
    "CRMS": "CRMS",   # RMS-average
}

_LISN_SCPI = {
    "ENV216": "ENV216",
    "ESH2Z5": "ESH2Z5",
    "ESH3Z5": "ESH3Z5",
    "ENV4200": "ENV4200",
    "ENV432": "ENV432",
}

_UNIT_SCPI = {
    "DBUV": "DBUV",
    "DBUA": "DBUA",
    "DBM": "DBM",
    "DBPW": "DBPW",
    "DBUV_M": "DBUV_M",
    "DBUA_M": "DBUA_M",
}


def _fmt(template: str, **kwargs) -> str:
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template


def build_command_sequence(settings: ReceiverSettings,
                            model: ReceiverModel) -> list[tuple[str, str]]:
    """Traduz ReceiverSettings para a sequencia de comandos SCPI do modelo.

    Devolve uma lista de (descricao, comando) -- a descricao aparece na GUI
    para o usuario conferir o que cada linha faz ANTES de mandar para o
    instrumento. Comandos que o modelo nao suporta sao simplesmente
    omitidos (o campo fica vazio no JSON do modelo)."""
    seq: list[tuple[str, str]] = []

    def add(key: str, desc: str, **kwargs):
        template = model.command(key)
        if template:
            seq.append((desc, _fmt(template, **kwargs)))

    def onoff(flag: bool) -> str:
        return "ON" if flag else "OFF"

    # ---- preparacao ----
    if settings.reset_before_config:
        add("reset", "Reset do instrumento")
        add("clear_status", "Limpa registrador de status")
    if settings.display_update:
        add("remote_display_on", "Mantem a tela do instrumento atualizada")

    if settings.receiver_mode:
        add("select_receiver_mode", "Entra no modo Receiver (scan EMI)")
    else:
        add("select_analyzer_mode", "Entra no modo Analisador de espectro")

    # ---- filtro CISPR ----
    if settings.rbw_filter_cispr:
        add("rbw_filter_cispr", "Filtro de RBW tipo CISPR (largura de 6 dB)")
    else:
        add("rbw_filter_normal", "Filtro de RBW normal (largura de 3 dB)")

    # ---- entrada / nivel ----
    add("unit_level", f"Unidade de nivel = {settings.level_unit}",
        value=_UNIT_SCPI.get(settings.level_unit, settings.level_unit))
    add("ref_level", f"Nivel de referencia = {settings.ref_level_dbuv} dB",
        value=settings.ref_level_dbuv)
    if settings.ref_level_offset_db:
        add("ref_level_offset", f"Offset de nivel = {settings.ref_level_offset_db} dB",
            value=settings.ref_level_offset_db)
    add("attenuation_auto", f"Atenuacao automatica {onoff(settings.attenuation_auto)}",
        value=onoff(settings.attenuation_auto))
    if not settings.attenuation_auto:
        add("attenuation", f"Atenuacao RF = {settings.attenuation_db} dB",
            value=settings.attenuation_db)
    if model.has_preamp:
        add("preamp_state", f"Pre-amplificador {onoff(settings.preamp)}",
            value=onoff(settings.preamp))
        if settings.preamp and settings.preamp_level_db is not None:
            add("preamp_level", f"Ganho do pre-amplificador = {settings.preamp_level_db} dB",
                value=settings.preamp_level_db)
    if model.has_preselector:
        add("preselector_state", f"Pre-seletor {onoff(settings.preselector)}",
            value=onoff(settings.preselector))
    add("input_impedance", f"Impedancia de entrada = {settings.input_impedance_ohm} ohm",
        value=settings.input_impedance_ohm)
    add("input_coupling", f"Acoplamento de entrada = {settings.input_coupling}",
        value=settings.input_coupling)
    if settings.noise_pulse_limiter:
        add("noise_limiter", "Limitador de pulso ON (protecao do front-end)", value="ON")

    # ---- VBW ----
    if not settings.vbw_auto and settings.vbw_hz:
        add("vbw", f"Banda de video = {settings.vbw_hz} Hz", value=settings.vbw_hz)

    # ---- transdutor ----
    if settings.transducer_enabled and settings.transducer_name:
        add("transducer_select", f"Seleciona transdutor '{settings.transducer_name}'",
            value=settings.transducer_name)
        add("transducer_state", "Ativa o transdutor", value="ON")

    # ---- LISN ----
    if settings.lisn_control and model.has_lisn_control:
        add("lisn_type", f"Tipo de LISN = {settings.lisn_type}",
            value=_LISN_SCPI.get(settings.lisn_type, settings.lisn_type))
        add("lisn_phase", f"Fase medida = {settings.lisn_phase}", value=settings.lisn_phase)
        if settings.lisn_highpass_150k:
            add("lisn_highpass", "Filtro passa-alta 150 kHz ON", value="ON")

    # ---- detectores ----
    for det in settings.detectors:
        trace = settings.detector_trace_map.get(det, 1)
        add("detector", f"Trace {trace}: detector {det}",
            trace=trace, value=_DETECTOR_SCPI.get(det, det))
        add("trace_mode", f"Trace {trace}: modo {settings.trace_mode}",
            trace=trace, value=settings.trace_mode)

    # ---- tabela de scan ----
    active_ranges = [r for r in settings.scan_ranges if r.enabled]
    if model.has_scan_table and active_ranges:
        add("scan_ranges", f"Numero de sub-faixas de scan = {len(active_ranges)}",
            value=len(active_ranges))
        for i, rng in enumerate(active_ranges, start=1):
            band = CISPR_BANDS.get(rng.band)
            band_txt = f" ({band.name})" if band else ""
            add("scan_start", f"Faixa {i}{band_txt}: inicio {rng.start_hz:g} Hz",
                range=i, value=rng.start_hz)
            add("scan_stop", f"Faixa {i}: fim {rng.stop_hz:g} Hz", range=i, value=rng.stop_hz)
            add("scan_rbw", f"Faixa {i}: RBW {rng.rbw_hz:g} Hz", range=i, value=rng.rbw_hz)
            add("scan_step", f"Faixa {i}: passo {rng.step_hz:g} Hz", range=i, value=rng.step_hz)
            add("scan_meas_time", f"Faixa {i}: tempo de medicao {rng.meas_time_s} s",
                range=i, value=rng.meas_time_s)
            if not rng.attenuation_auto:
                add("scan_attenuation", f"Faixa {i}: atenuacao {rng.attenuation_db} dB",
                    range=i, value=rng.attenuation_db)
            if model.has_preamp:
                add("scan_preamp", f"Faixa {i}: pre-amplificador {onoff(rng.preamp)}",
                    range=i, value=onoff(rng.preamp))
    elif active_ranges:
        # Instrumento sem tabela de scan: configura a primeira faixa direto.
        rng = active_ranges[0]
        add("freq_start", f"Frequencia inicial = {rng.start_hz:g} Hz", value=rng.start_hz)
        add("freq_stop", f"Frequencia final = {rng.stop_hz:g} Hz", value=rng.stop_hz)
        add("rbw", f"RBW = {rng.rbw_hz:g} Hz", value=rng.rbw_hz)
        add("meas_time", f"Tempo de medicao = {rng.meas_time_s} s", value=rng.meas_time_s)

    # ---- tempos gerais ----
    if settings.sweep_time_auto:
        add("sweep_time_auto", "Tempo de varredura automatico")
    elif settings.sweep_time_s:
        add("sweep_time", f"Tempo de varredura = {settings.sweep_time_s} s",
            value=settings.sweep_time_s)
    if settings.sweep_points:
        add("sweep_points", f"Pontos por varredura = {settings.sweep_points}",
            value=settings.sweep_points)
    if settings.sweep_count and settings.sweep_count > 1:
        add("sweep_count", f"Numero de varreduras = {settings.sweep_count}",
            value=settings.sweep_count)

    # ---- medicao final ----
    if settings.final_measurement:
        add("final_meas_margin", f"Margem da medicao final = {settings.final_meas_margin_db} dB",
            value=settings.final_meas_margin_db)
        add("final_meas_peaks", f"Picos remedidos na medicao final = {settings.final_meas_max_peaks}",
            value=settings.final_meas_max_peaks)
        for det in settings.final_meas_detectors:
            tempos = settings.final_meas_times.get(det)
            if not tempos:
                continue
            medida, observacao = tempos
            add("final_meas_time", f"Medicao final {det}: tempo de medicao {medida:g} s",
                detector=_DETECTOR_SCPI.get(det, det), value=medida)
            add("final_meas_observation",
                f"Medicao final {det}: tempo de observacao {observacao:g} s",
                detector=_DETECTOR_SCPI.get(det, det), value=observacao)

    # ---- modo single sweep ----
    add("init_continuous_off", "Modo single sweep (varredura sob comando)")

    return seq


# ---------------------------------------------------------------------------
# Persistencia de presets
# ---------------------------------------------------------------------------

def validate_preset_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("O nome do preset nao pode ser vazio.")
    if not set(name) <= _SAFE_NAME_CHARS:
        raise ValueError("Use apenas letras, numeros, espaco, '_' e '-' no nome do preset.")
    return name


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_") or "preset"


def ensure_default_presets() -> None:
    PRESETS_DIR.mkdir(exist_ok=True)
    for key, factory in BUILTIN_PRESETS.items():
        path = PRESETS_DIR / f"{key}.json"
        if not path.exists():
            save_settings(factory(), path)


def list_available_presets() -> list[Path]:
    ensure_default_presets()
    return sorted(PRESETS_DIR.glob("*.json"))


def save_settings(settings: ReceiverSettings, path: str | Path) -> None:
    Path(path).write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False),
                          encoding="utf-8")


def load_settings(path: str | Path) -> ReceiverSettings:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ranges = [ScanRange(**{k: v for k, v in r.items()
                            if k in ScanRange.__dataclass_fields__})
              for r in data.pop("scan_ranges", [])]
    known = {f for f in ReceiverSettings.__dataclass_fields__}
    settings = ReceiverSettings(**{k: v for k, v in data.items() if k in known})
    settings.scan_ranges = ranges
    # JSON nao tem tupla: os tempos voltam como lista, converte de volta
    settings.final_meas_times = {
        det: (float(v[0]), float(v[1]))
        for det, v in (settings.final_meas_times or {}).items()
        if isinstance(v, (list, tuple)) and len(v) >= 2
    }
    return settings


def new_preset(name: str, base: Optional[ReceiverSettings] = None) -> Path:
    name = validate_preset_name(name)
    PRESETS_DIR.mkdir(exist_ok=True)
    path = PRESETS_DIR / f"{_slug(name)}.json"
    if path.exists():
        raise FileExistsError(f"Ja existe um preset chamado '{name}'.")
    settings = base or ReceiverSettings()
    settings.name = name
    save_settings(settings, path)
    return path


def delete_preset(path: str | Path) -> None:
    Path(path).unlink()
