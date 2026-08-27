"""
instruments/acquisition.py

Orquestra um scan "estilo CISPR" cobrindo varias sub-faixas com RBW
diferente (como exige a CISPR16-1-1: RBW 200 Hz entre 9-150kHz e RBW
9kHz entre 150kHz-30MHz) e junta tudo num Trace so, pronto para
avaliar contra o limite.

Assim como scpi_receiver.py, este modulo ainda precisa ser validado
com hardware real -- ver instrucoes/03_validacao_receiver_scpi.md.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.trace import Trace
from instruments.scpi_receiver import RohdeSchwarzEMIReceiver


@dataclass
class ScanBand:
    start_hz: float
    stop_hz: float
    rbw_hz: float
    sweep_time_s: float | None = None


# Bandas "default" do metodo conduzido da CISPR15 (RBW conforme CISPR16-1-1).
# CONFIRME estes valores de RBW/sweep time com o texto oficial da norma e
# com a pratica do seu laboratorio antes de usar.
CISPR15_CONDUCTED_BANDS = [
    ScanBand(start_hz=9_000, stop_hz=150_000, rbw_hz=200),
    ScanBand(start_hz=150_000, stop_hz=30_000_000, rbw_hz=9_000),
]


def run_multi_band_scan(receiver: RohdeSchwarzEMIReceiver, bands: list[ScanBand],
                         detector: str = "QP", unit: str = "dBuV") -> Trace:
    freq_chunks, level_chunks = [], []
    for band in bands:
        receiver.configure_scan(start_hz=band.start_hz, stop_hz=band.stop_hz,
                                 rbw_hz=band.rbw_hz, detector=detector,
                                 sweep_time_s=band.sweep_time_s)
        receiver.run_scan()
        trace = receiver.read_trace(detector=detector, unit=unit)
        freq_chunks.append(trace.freq_hz)
        level_chunks.append(trace.level)

    freq_hz = np.concatenate(freq_chunks)
    level = np.concatenate(level_chunks)
    return Trace(freq_hz=freq_hz, level=level, unit=unit, detector=detector,
                  label=f"Scan multi-banda ({detector})")
