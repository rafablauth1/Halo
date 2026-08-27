"""
core/trace.py

Modelo de "trace" (varredura de frequencia x nivel) e importadores de
arquivo. Cobre dois casos de uso:

1) Arquivo ASCII exportado por um receiver Rohde & Schwarz (familia
   ESR/ESRP/ESPI/FSx) via "Trace > Export > ASCII File" ou pelo
   comando SCPI MMEMory:STORe:TRACe. Esse formato tem um cabecalho
   com metadados (Type;, Version;, Mode;, x-Unit;, y-Unit; etc.) e
   depois uma secao "Values;<N>" com pares "frequencia;nivel".
   OBS: o layout exato pode variar por familia/versao de firmware --
   o parser abaixo e tolerante (procura a secao Values e os nomes de
   unidade) mas SEMPRE confira visualmente o resultado importado,
   e ajuste _parse_rs_ascii se o seu instrumento usar outro layout.

2) CSV/TSV genérico de 2 colunas (frequencia, nivel), com cabecalho
   ou nao, separador ',', ';' ou tab, frequencia em Hz/kHz/MHz.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np


@dataclass
class Trace:
    freq_hz: np.ndarray
    level: np.ndarray  # na unidade nativa do arquivo (dBuV, dBuA/m, dBuV/m...)
    unit: str = "dBuV"
    detector: str = "unknown"  # QP, AV, PK, unknown
    label: str = "trace"
    source_file: Optional[str] = None
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        order = np.argsort(self.freq_hz)
        self.freq_hz = self.freq_hz[order]
        self.level = self.level[order]

    def value_at(self, freq_hz: float) -> Optional[float]:
        if len(self.freq_hz) == 0:
            return None
        return float(np.interp(freq_hz, self.freq_hz, self.level))


_FREQ_UNIT_SCALE = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}


def _looks_like_rs_ascii(text: str) -> bool:
    head = text[:2000].lower()
    return ("values;" in head or "\nvalues" in head) and ("type;" in head or "x-unit;" in head)


def _parse_rs_ascii(text: str, source_file: Optional[str] = None) -> Trace:
    lines = text.splitlines()
    meta: dict[str, str] = {}
    x_unit = "hz"
    y_unit = "dbuv"
    detector = "unknown"
    values_start = None

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("values"):
            values_start = i + 1
            break
        if ";" in line:
            parts = line.split(";")
            key = parts[0].strip().lower()
            val = parts[1].strip() if len(parts) > 1 else ""
            meta[key] = val
            if key == "x-unit":
                x_unit = val.lower()
            elif key == "y-unit":
                y_unit = val.lower()
            elif key == "detector":
                detector = val.upper()

    if values_start is None:
        raise ValueError("Nao encontrei a secao 'Values;' no arquivo ASCII do R&S.")

    freqs, levels = [], []
    for raw in lines[values_start:]:
        line = raw.strip()
        if not line:
            continue
        sep = ";" if ";" in line else ("\t" if "\t" in line else ",")
        parts = [p for p in line.split(sep) if p != ""]
        if len(parts) < 2:
            continue
        try:
            f = float(parts[0].replace(",", "."))
            v = float(parts[1].replace(",", "."))
        except ValueError:
            continue
        freqs.append(f)
        levels.append(v)

    scale = _FREQ_UNIT_SCALE.get(x_unit, 1.0)
    freq_hz = np.array(freqs) * scale
    level = np.array(levels)

    unit_map = {"dbuv": "dBuV", "dbuv/m": "dBuV/m", "dbua/m": "dBuA/m", "dbm": "dBm"}
    unit = unit_map.get(y_unit, y_unit or "dBuV")

    return Trace(freq_hz=freq_hz, level=level, unit=unit, detector=detector or "unknown",
                 label=Path(source_file).stem if source_file else "R&S trace",
                 source_file=source_file, meta=meta)


def _sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        return dialect.delimiter
    except Exception:
        for cand in (";", ",", "\t"):
            if cand in sample:
                return cand
        return ","


def _parse_generic_csv(text: str, source_file: Optional[str] = None,
                        freq_unit: str = "hz", unit: str = "dBuV",
                        detector: str = "unknown") -> Trace:
    sample = "\n".join(text.splitlines()[:20])
    delim = _sniff_delimiter(sample)

    freqs, levels = [], []
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    for row in reader:
        if len(row) < 2:
            continue
        f_raw, v_raw = row[0].strip(), row[1].strip()
        f_raw = f_raw.replace(",", ".") if f_raw.count(",") == 1 and f_raw.count(".") == 0 else f_raw
        v_raw = v_raw.replace(",", ".") if v_raw.count(",") == 1 and v_raw.count(".") == 0 else v_raw
        try:
            f = float(f_raw)
            v = float(v_raw)
        except ValueError:
            continue  # linha de cabecalho ou nao numerica
        freqs.append(f)
        levels.append(v)

    if not freqs:
        raise ValueError("Nao consegui extrair pares (frequencia, nivel) numericos deste arquivo CSV.")

    scale = _FREQ_UNIT_SCALE.get(freq_unit.lower(), 1.0)
    freq_hz = np.array(freqs) * scale
    level = np.array(levels)
    return Trace(freq_hz=freq_hz, level=level, unit=unit, detector=detector,
                 label=Path(source_file).stem if source_file else "trace",
                 source_file=source_file)


def load_trace(path: str | Path, *, freq_unit: str = "hz", unit: str = "dBuV",
                detector: str = "unknown") -> Trace:
    """Ponto de entrada unico de importacao. Detecta automaticamente se
    o arquivo e um export ASCII de receiver R&S; caso contrario, trata
    como CSV/TSV generico de 2 colunas usando freq_unit/unit/detector
    informados pelo usuario na GUI (ou pelos defaults acima)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if _looks_like_rs_ascii(text):
        return _parse_rs_ascii(text, source_file=str(path))
    return _parse_generic_csv(text, source_file=str(path), freq_unit=freq_unit,
                               unit=unit, detector=detector)
