"""
instruments/lisn.py

Notas e helper para a LISN/AMN usada no ensaio conduzido da CISPR15
(ex.: Rohde & Schwarz ENV216 - "Two-line V-network", ou a mais antiga
ESH2-Z5).

Instrucoes completas (comutacao de fase L/N, por que a maioria das
LISN nao tem controle remoto SCPI, e o que fazer a respeito) estao em
instrucoes/04_lisn_e_fatores_de_correcao.md. Este modulo fica como
esqueleto/placeholder ate a confirmacao descrita la.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LisnPhase(Enum):
    LINE = "L"
    NEUTRAL = "N"


@dataclass
class LisnInfo:
    model: str = "R&S ENV216"
    serial_number: str = ""
    calibration_file: str = ""  # caminho para o CSV/JSON de insertion loss real
    has_remote_phase_switch: bool = False  # ver docstring acima -- confirme no seu equipamento


def require_manual_phase_switch(phase: LisnPhase, lisn: LisnInfo) -> str:
    """Retorna a mensagem que a GUI deve mostrar ao operador quando a
    LISN nao tem comutacao remota de fase confirmada."""
    return (f"Comute manualmente a LISN ({lisn.model}) para medir a fase "
            f"{phase.value} e confirme na GUI para continuar o scan.")
