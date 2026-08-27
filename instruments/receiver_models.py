"""
instruments/receiver_models.py

Catalogo de receivers/analisadores Rohde & Schwarz pre-setados, cada um
com sua faixa de frequencia, detectores, RBWs e -- principalmente -- seu
proprio conjunto de comandos SCPI.

Assim como core/standards/*.json (normas) e core/corrections_lib/*.json
(fatores de correcao), cada modelo de receiver e UM ARQUIVO JSON em
instruments/receivers/, criado/editado/excluido pela GUI. Os modelos
"de fabrica" abaixo sao apenas a semente inicial: na primeira execucao
eles sao gravados em disco e a partir dai o usuario manda no arquivo.

>>> IMPORTANTE - RESPONSABILIDADE TECNICA <<<
Os comandos SCPI abaixo seguem a documentacao das familias R&S, mas NAO
foram validados contra hardware real neste ambiente. Cada familia (e ate
cada versao de firmware) pode variar. ANTES de usar em ensaio real,
confira cada comando no manual "Remote Control Commands"/"SCPI Command
Reference" do SEU instrumento e corrija pela aba Receiver da GUI.
Ver instrucoes/03_validacao_receiver_scpi.md e
instrucoes/07_receiver_gpib_e_configuracoes.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

RECEIVERS_DIR = Path(__file__).parent / "receivers"

_SAFE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


# ---------------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------------

@dataclass
class ReceiverModel:
    id: str
    manufacturer: str = "Rohde & Schwarz"
    model: str = ""
    family: str = ""
    description: str = ""
    freq_min_hz: float = 9_000.0
    freq_max_hz: float = 30_000_000.0
    detectors: list[str] = field(default_factory=lambda: ["PK", "QP", "AV"])
    rbw_cispr_hz: list[float] = field(default_factory=lambda: [200.0, 9_000.0, 120_000.0, 1_000_000.0])
    rbw_all_hz: list[float] = field(default_factory=list)
    has_preamp: bool = False
    has_preselector: bool = False
    has_receiver_mode: bool = True
    has_lisn_control: bool = False
    has_scan_table: bool = False
    default_gpib_address: int = 20
    notes: str = ""
    verified: bool = False
    commands: dict[str, str] = field(default_factory=dict)

    def command(self, key: str) -> Optional[str]:
        """Comando SCPI deste modelo para `key`, ou None se nao houver.

        A distincao entre AUSENTE e VAZIO importa:

        * chave **vazia** ("") e uma decisao deliberada -- o modelo declara
          que nao tem esse comando (ex.: `select_receiver_mode` nos ESHS/
          ESCS analogicos). Continua devolvendo None, e nada e enviado.
        * chave **ausente** cai no BASE_COMMANDS. E o que permite acrescentar
          comandos novos ao catalogo sem ter que reescrever os 31 arquivos
          JSON ja salvos -- eles simplesmente herdam o padrao SCPI.
        """
        if key in self.commands:
            cmd = self.commands[key]
            return cmd if cmd else None
        cmd = BASE_COMMANDS.get(key, "")
        return cmd if cmd else None


# ---------------------------------------------------------------------------
# Conjuntos de comandos por familia
# ---------------------------------------------------------------------------

# Base comum IEEE 488.2 / SCPI -- vale para praticamente toda a linha R&S.
BASE_COMMANDS: dict[str, str] = {
    "idn": "*IDN?",
    "reset": "*RST",
    "clear_status": "*CLS",
    "opc_query": "*OPC?",
    "error_query": "SYST:ERR?",
    "remote_display_on": "SYST:DISP:UPD ON",

    # --- frequencia ---
    "freq_start": "FREQ:STAR {value}",
    "freq_stop": "FREQ:STOP {value}",
    "freq_center": "FREQ:CENT {value}",
    "freq_span": "FREQ:SPAN {value}",

    # --- banda de resolucao ---
    "rbw": "BAND:RES {value}",
    "rbw_filter_cispr": "BAND:RES:TYPE CISP",
    "rbw_filter_normal": "BAND:RES:TYPE NORM",
    "vbw": "BAND:VID {value}",

    # --- detector ---
    "detector": "SENS:DET{trace}:FUNC {value}",

    # --- tempo ---
    "meas_time": "SWE:TIME {value}",
    "sweep_time": "SWE:TIME {value}",
    "sweep_time_auto": "SWE:TIME:AUTO ON",
    "sweep_points": "SWE:POIN {value}",
    "sweep_count": "SWE:COUN {value}",

    # --- nivel / entrada ---
    "ref_level": "DISP:TRAC:Y:RLEV {value}",
    "ref_level_offset": "DISP:TRAC:Y:RLEV:OFFS {value}",
    "attenuation": "INP:ATT {value}",
    "attenuation_auto": "INP:ATT:AUTO {value}",
    "preamp_state": "INP:GAIN:STAT {value}",
    "preamp_level": "INP:GAIN {value}",
    "preselector_state": "INP:PRES:STAT {value}",
    "unit_level": "UNIT:POW {value}",
    "input_impedance": "INP:IMP {value}",
    "input_coupling": "INP:COUP {value}",
    "noise_limiter": "INP:ATT:PROT:STAT {value}",

    # --- trace ---
    "trace_mode": "DISP:TRAC{trace}:MODE {value}",
    "trace_data_query": "TRAC:DATA? TRACE{trace}",

    # --- transdutor (fator de antena / LISN / cabo) ---
    "transducer_select": "CORR:TRAN:SEL '{value}'",
    "transducer_state": "CORR:TRAN {value}",

    # --- controle de varredura ---
    "init_continuous_off": "INIT:CONT OFF",
    "init_continuous_on": "INIT:CONT ON",
    "init_immediate": "INIT",
    "abort": "ABOR",

    # --- medicao em frequencia fixa (medicao final, pico a pico) ---
    # Sintonizar em span zero e ler o marcador e o jeito portatil de
    # obter UM nivel numa frequencia: funciona em receiver dedicado e
    # em analisador, ao contrario da funcao FMEas, que so existe na
    # linha de topo.
    "marker_on": "CALC:MARK1 ON",
    "marker_freq": "CALC:MARK1:X {value}",
    "marker_level_query": "CALC:MARK1:Y?",

    # --- consultas de eixo ---
    "query_sweep_points": "SWE:POIN?",
    "query_freq_start": "FREQ:STAR?",
    "query_freq_stop": "FREQ:STOP?",
}

# Receivers EMI dedicados modernos (ESR / ESW / ESRP): tem modo receiver,
# tabela de scan, controle de LISN e medicao final (final measurement).
MODERN_RECEIVER_COMMANDS: dict[str, str] = {
    **BASE_COMMANDS,
    "select_receiver_mode": "INST:SEL REC",
    "select_analyzer_mode": "INST:SEL SAN",

    # tabela de scan multi-banda (uma linha por sub-faixa CISPR)
    "scan_start": "SCAN{range}:STAR {value}",
    "scan_stop": "SCAN{range}:STOP {value}",
    "scan_step": "SCAN{range}:STEP {value}",
    "scan_rbw": "SCAN{range}:BAND:RES {value}",
    "scan_meas_time": "SCAN{range}:TIME {value}",
    "scan_attenuation": "SCAN{range}:INP:ATT {value}",
    "scan_preamp": "SCAN{range}:INP:GAIN:STAT {value}",
    "scan_count": "SCAN:COUN {value}",
    "scan_ranges": "SCAN:RANG:COUN {value}",

    # medicao final (peak search -> remede em QP/AV), estilo RadiMation
    "final_meas_margin": "CALC:MARK:FUNC:FMEas:LIM:MARG {value}",
    "final_meas_peaks": "CALC:MARK:FUNC:FMEas:PEAK:COUN {value}",
    "final_meas_run": "CALC:MARK:FUNC:FMEas",
    "final_meas_query": "CALC:MARK:FUNC:FMEas:RES?",
    # tempo de medicao e de observacao da medicao final, por detector
    "final_meas_time": "SENS:FME:TIME:{detector} {value}",
    "final_meas_observation": "SENS:FME:OTIM:{detector} {value}",

    # LISN / AMN controlada pelo proprio receiver
    "lisn_type": "INP:LISN:TYPE {value}",
    "lisn_phase": "INP:LISN:PHAS {value}",
    "lisn_pe": "INP:LISN:FILT:HPAS {value}",
    "lisn_highpass": "INP:LISN:FILT:HPAS {value}",
}

# ESU / ESIB (geracao anterior de topo de linha).
LEGACY_FLAGSHIP_COMMANDS: dict[str, str] = {
    **MODERN_RECEIVER_COMMANDS,
    "select_receiver_mode": "INST:SEL REC",
    "rbw_filter_cispr": "BAND:RES:TYPE CISP",
}

# ESPI / ESCI / ESL (receivers/analisadores compactos).
COMPACT_RECEIVER_COMMANDS: dict[str, str] = {
    **BASE_COMMANDS,
    "select_receiver_mode": "INST:SEL REC",
    "select_analyzer_mode": "INST:SEL SAN",
    "scan_start": "SCAN{range}:STAR {value}",
    "scan_stop": "SCAN{range}:STOP {value}",
    "scan_step": "SCAN{range}:STEP {value}",
    "scan_rbw": "SCAN{range}:BAND:RES {value}",
    "scan_meas_time": "SCAN{range}:TIME {value}",
    "scan_ranges": "SCAN:RANG:COUN {value}",
    "final_meas_run": "CALC:MARK:FUNC:FMEas",
    "final_meas_query": "CALC:MARK:FUNC:FMEas:RES?",
}

# Receivers analogicos antigos (ESHS/ESCS): sem modo receiver SCPI moderno,
# sem tabela de scan; varredura banda a banda no braco.
CLASSIC_RECEIVER_COMMANDS: dict[str, str] = {
    **BASE_COMMANDS,
    "select_receiver_mode": "",
    "select_analyzer_mode": "",
    "rbw_filter_cispr": "",
    "preselector_state": "",
    "trace_mode": "",
}

# Analisadores de espectro com opcao de medicao EMI (K54): ficam em modo
# analisador; a parte "receiver" e a funcao de medicao final + filtro CISPR.
ANALYZER_EMI_COMMANDS: dict[str, str] = {
    **BASE_COMMANDS,
    "select_receiver_mode": "INST:SEL SAN",
    "select_analyzer_mode": "INST:SEL SAN",
    "final_meas_margin": "CALC:MARK:FUNC:FMEas:LIM:MARG {value}",
    "final_meas_peaks": "CALC:MARK:FUNC:FMEas:PEAK:COUN {value}",
    "final_meas_run": "CALC:MARK:FUNC:FMEas",
    "final_meas_query": "CALC:MARK:FUNC:FMEas:RES?",
}


COMMAND_SETS = {
    "modern_receiver": MODERN_RECEIVER_COMMANDS,
    "legacy_flagship": LEGACY_FLAGSHIP_COMMANDS,
    "compact_receiver": COMPACT_RECEIVER_COMMANDS,
    "classic_receiver": CLASSIC_RECEIVER_COMMANDS,
    "analyzer_emi": ANALYZER_EMI_COMMANDS,
}


# ---------------------------------------------------------------------------
# Semente do catalogo
# ---------------------------------------------------------------------------

_FULL_DET = ["PK", "QP", "AV", "RMS", "CAV", "CRMS"]
_BASIC_DET = ["PK", "QP", "AV", "RMS"]
_CLASSIC_DET = ["PK", "QP", "AV"]

_RBW_CISPR = [200.0, 9_000.0, 120_000.0, 1_000_000.0]
_RBW_FULL = [10.0, 100.0, 200.0, 1_000.0, 9_000.0, 10_000.0, 100_000.0,
             120_000.0, 1_000_000.0, 3_000_000.0]

# (id, modelo, familia, descricao, fmin, fmax, cmd_set, preamp, presel,
#  lisn, scan_table, detectores)
_SEED: list[tuple] = [
    # --- ESW: topo de linha atual ---
    ("esw8", "ESW8", "ESW", "EMI Test Receiver 2 Hz - 8 GHz", 2, 8e9, "modern_receiver", True, True, True, True, _FULL_DET),
    ("esw26", "ESW26", "ESW", "EMI Test Receiver 2 Hz - 26.5 GHz", 2, 26.5e9, "modern_receiver", True, True, True, True, _FULL_DET),
    ("esw44", "ESW44", "ESW", "EMI Test Receiver 2 Hz - 44 GHz", 2, 44e9, "modern_receiver", True, True, True, True, _FULL_DET),

    # --- ESR: receiver EMI mais comum em laboratorio ---
    ("esr3", "ESR3", "ESR", "EMI Test Receiver 10 Hz - 3.6 GHz", 10, 3.6e9, "modern_receiver", True, True, True, True, _FULL_DET),
    ("esr7", "ESR7", "ESR", "EMI Test Receiver 10 Hz - 7 GHz", 10, 7e9, "modern_receiver", True, True, True, True, _FULL_DET),
    ("esr26", "ESR26", "ESR", "EMI Test Receiver 10 Hz - 26.5 GHz", 10, 26.5e9, "modern_receiver", True, True, True, True, _FULL_DET),

    # --- ESRP: receiver EMI compacto ---
    ("esrp3", "ESRP3", "ESRP", "EMI Test Receiver 9 kHz - 3.6 GHz", 9e3, 3.6e9, "modern_receiver", True, True, True, True, _FULL_DET),
    ("esrp7", "ESRP7", "ESRP", "EMI Test Receiver 9 kHz - 7 GHz", 9e3, 7e9, "modern_receiver", True, True, True, True, _FULL_DET),

    # --- ESU: geracao anterior de topo ---
    ("esu8", "ESU8", "ESU", "EMI Test Receiver 20 Hz - 8 GHz", 20, 8e9, "legacy_flagship", True, True, True, True, _FULL_DET),
    ("esu26", "ESU26", "ESU", "EMI Test Receiver 20 Hz - 26.5 GHz", 20, 26.5e9, "legacy_flagship", True, True, True, True, _FULL_DET),
    ("esu40", "ESU40", "ESU", "EMI Test Receiver 20 Hz - 40 GHz", 20, 40e9, "legacy_flagship", True, True, True, True, _FULL_DET),

    # --- ESIB ---
    ("esib7", "ESIB7", "ESIB", "EMI Test Receiver 20 Hz - 7 GHz", 20, 7e9, "legacy_flagship", True, True, True, True, _BASIC_DET),
    ("esib26", "ESIB26", "ESIB", "EMI Test Receiver 20 Hz - 26.5 GHz", 20, 26.5e9, "legacy_flagship", True, True, True, True, _BASIC_DET),
    ("esib40", "ESIB40", "ESIB", "EMI Test Receiver 20 Hz - 40 GHz", 20, 40e9, "legacy_flagship", True, True, True, True, _BASIC_DET),

    # --- ESPI / ESCI / ESL: compactos ---
    ("espi3", "ESPI3", "ESPI", "EMI Test Receiver 9 kHz - 3 GHz", 9e3, 3e9, "compact_receiver", True, True, True, True, _BASIC_DET),
    ("espi7", "ESPI7", "ESPI", "EMI Test Receiver 9 kHz - 7 GHz", 9e3, 7e9, "compact_receiver", True, True, True, True, _BASIC_DET),
    ("esci3", "ESCI3", "ESCI", "EMI Test Receiver 9 kHz - 3 GHz", 9e3, 3e9, "compact_receiver", True, True, False, True, _BASIC_DET),
    ("esci7", "ESCI7", "ESCI", "EMI Test Receiver 9 kHz - 7 GHz", 9e3, 7e9, "compact_receiver", True, True, False, True, _BASIC_DET),
    ("esl3", "ESL3", "ESL", "Analisador/receiver 9 kHz - 3 GHz", 9e3, 3e9, "compact_receiver", True, False, False, True, _BASIC_DET),
    ("esl6", "ESL6", "ESL", "Analisador/receiver 9 kHz - 6 GHz", 9e3, 6e9, "compact_receiver", True, False, False, True, _BASIC_DET),

    # --- Classicos (bancada antiga) ---
    ("escs30", "ESCS30", "ESCS", "EMI Test Receiver 9 kHz - 2.75 GHz (classico)", 9e3, 2.75e9, "classic_receiver", False, True, False, False, _CLASSIC_DET),
    ("eshs10", "ESHS10", "ESHS", "Test Receiver 9 kHz - 30 MHz (classico)", 9e3, 30e6, "classic_receiver", False, True, False, False, _CLASSIC_DET),
    ("eshs30", "ESHS30", "ESHS", "Test Receiver 20 MHz - 1 GHz (classico)", 20e6, 1e9, "classic_receiver", False, True, False, False, _CLASSIC_DET),

    # --- Analisadores com opcao EMI (K54) ---
    ("fsw8", "FSW8", "FSW", "Analisador de sinal 2 Hz - 8 GHz (EMI: opcao K54)", 2, 8e9, "analyzer_emi", True, True, False, False, _FULL_DET),
    ("fsw26", "FSW26", "FSW", "Analisador de sinal 2 Hz - 26.5 GHz (EMI: opcao K54)", 2, 26.5e9, "analyzer_emi", True, True, False, False, _FULL_DET),
    ("fsv7", "FSV7", "FSV", "Analisador de sinal 9 kHz - 7 GHz (EMI: opcao K54)", 9e3, 7e9, "analyzer_emi", True, True, False, False, _BASIC_DET),
    ("fsv13", "FSV13", "FSV", "Analisador de sinal 9 kHz - 13.6 GHz (EMI: opcao K54)", 9e3, 13.6e9, "analyzer_emi", True, True, False, False, _BASIC_DET),
    ("fsva30", "FSVA30", "FSVA", "Analisador de sinal 10 Hz - 30 GHz (EMI: opcao K54)", 10, 30e9, "analyzer_emi", True, True, False, False, _FULL_DET),
    ("fpl1003", "FPL1003", "FPL", "Analisador 5 kHz - 3 GHz (EMI: opcao K54)", 5e3, 3e9, "analyzer_emi", True, False, False, False, _BASIC_DET),
    ("fpl1007", "FPL1007", "FPL", "Analisador 5 kHz - 7.5 GHz (EMI: opcao K54)", 5e3, 7.5e9, "analyzer_emi", True, False, False, False, _BASIC_DET),
    ("fsl6", "FSL6", "FSL", "Analisador 9 kHz - 6 GHz (EMI: opcao K54)", 9e3, 6e9, "analyzer_emi", True, False, False, False, _BASIC_DET),
]


def _seed_models() -> list[ReceiverModel]:
    models = []
    for (mid, model, family, desc, fmin, fmax, cmd_set,
         preamp, presel, lisn, scan_table, detectors) in _SEED:
        models.append(ReceiverModel(
            id=mid,
            model=model,
            family=family,
            description=desc,
            freq_min_hz=float(fmin),
            freq_max_hz=float(fmax),
            detectors=list(detectors),
            rbw_cispr_hz=list(_RBW_CISPR),
            rbw_all_hz=list(_RBW_FULL),
            has_preamp=preamp,
            has_preselector=presel,
            has_receiver_mode=(cmd_set != "analyzer_emi"),
            has_lisn_control=lisn,
            has_scan_table=scan_table,
            notes=("Comandos SCPI da familia " + family + " -- NAO validados contra hardware "
                   "real neste ambiente. Confira no manual de controle remoto do seu "
                   "instrumento antes de usar em ensaio."),
            verified=False,
            commands=dict(COMMAND_SETS[cmd_set]),
        ))
    return models


# ---------------------------------------------------------------------------
# Persistencia / CRUD (mesmo padrao de core/standards e core/corrections_lib)
# ---------------------------------------------------------------------------

def validate_receiver_id(receiver_id: str) -> str:
    receiver_id = receiver_id.strip()
    if not receiver_id:
        raise ValueError("O id do receiver nao pode ser vazio.")
    if not set(receiver_id) <= _SAFE_ID_CHARS:
        raise ValueError("Use apenas letras, numeros, '_' e '-' no id do receiver.")
    return receiver_id


def save_receiver(model: ReceiverModel, path: str | Path) -> None:
    Path(path).write_text(json.dumps(asdict(model), indent=2, ensure_ascii=False),
                          encoding="utf-8")


def load_receiver(path: str | Path) -> ReceiverModel:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    known = {f for f in ReceiverModel.__dataclass_fields__}
    return ReceiverModel(**{k: v for k, v in data.items() if k in known})


def ensure_default_catalog() -> None:
    """Grava os modelos de fabrica em disco na primeira execucao. Nao
    sobrescreve nada que ja exista -- o que o usuario editou fica como esta."""
    RECEIVERS_DIR.mkdir(exist_ok=True)
    for model in _seed_models():
        path = RECEIVERS_DIR / f"{model.id}.json"
        if not path.exists():
            save_receiver(model, path)


def list_available_receivers() -> list[Path]:
    ensure_default_catalog()
    return sorted(RECEIVERS_DIR.glob("*.json"))


def new_receiver(receiver_id: str, model_name: str = "") -> Path:
    receiver_id = validate_receiver_id(receiver_id)
    RECEIVERS_DIR.mkdir(exist_ok=True)
    path = RECEIVERS_DIR / f"{receiver_id}.json"
    if path.exists():
        raise FileExistsError(f"Ja existe um receiver com id '{receiver_id}'.")
    model = ReceiverModel(id=receiver_id, model=model_name or receiver_id,
                          commands=dict(BASE_COMMANDS))
    save_receiver(model, path)
    return path


def duplicate_receiver(src_path: str | Path, new_id: str) -> Path:
    new_id = validate_receiver_id(new_id)
    dst = RECEIVERS_DIR / f"{new_id}.json"
    if dst.exists():
        raise FileExistsError(f"Ja existe um receiver com id '{new_id}'.")
    model = load_receiver(src_path)
    model.id = new_id
    model.model = f"{model.model} (copia)"
    save_receiver(model, dst)
    return dst


def rename_receiver(path: str | Path, new_id: str) -> Path:
    new_id = validate_receiver_id(new_id)
    path = Path(path)
    dst = RECEIVERS_DIR / f"{new_id}.json"
    if dst != path and dst.exists():
        raise FileExistsError(f"Ja existe um receiver com id '{new_id}'.")
    model = load_receiver(path)
    model.id = new_id
    save_receiver(model, dst)
    if dst != path:
        path.unlink()
    return dst


def delete_receiver(path: str | Path) -> None:
    Path(path).unlink()
