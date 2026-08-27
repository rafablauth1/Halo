"""
core/corrections.py

Fatores de correcao aplicados a um Trace bruto do receiver antes de
comparar com o limite: perda de cabo, fator de insercao da LISN,
fator de antena (loop ou biconica/log-periodica na parte radiada).

Um CorrectionTable e uma lista de pontos (freq_hz, correction_dB)
interpolados linearmente em log(f). A convencao usada aqui e:

    nivel_corrigido = leitura_receiver + correction_dB

ou seja, "correction_dB" e o que voce SOMA a leitura para chegar no
nivel de fato na fonte (equivalente ao "Cable Loss"/"Antenna Factor"
somado no RadiMation e no EMC32 da R&S).

Instrucoes completas sobre de onde tirar esses valores reais (folha de
calibracao da LISN/antena/cabo) estao em
instrucoes/04_lisn_e_fatores_de_correcao.md. Os placeholders abaixo
(correction_dB=0.0) sao so ponto de partida -- substitua pelos dados
reais antes de usar em ensaio.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from core.trace import Trace


@dataclass
class CorrectionTable:
    name: str
    unit_note: str  # ex.: "dB somado a leitura do receiver"
    points: list[tuple[float, float]] = field(default_factory=list)  # (freq_hz, correction_dB)

    def value_at(self, freq_hz: float) -> float:
        if not self.points:
            return 0.0
        freqs = np.array([p[0] for p in self.points])
        corr = np.array([p[1] for p in self.points])
        if freq_hz <= freqs[0]:
            return float(corr[0])
        if freq_hz >= freqs[-1]:
            return float(corr[-1])
        log_f = np.log10(freqs)
        return float(np.interp(math.log10(freq_hz), log_f, corr))

    def apply(self, trace: Trace) -> Trace:
        corrected = trace.level + np.array([self.value_at(f) for f in trace.freq_hz])
        return Trace(freq_hz=trace.freq_hz.copy(), level=corrected, unit=trace.unit,
                     detector=trace.detector, label=trace.label + f" + {self.name}",
                     source_file=trace.source_file, meta=dict(trace.meta))

    @staticmethod
    def flat(name: str, value_db: float) -> "CorrectionTable":
        return CorrectionTable(name=name, unit_note="dB fixo em toda a faixa",
                                points=[(1.0, value_db), (3e9, value_db)])

    @staticmethod
    def from_csv(path: str | Path, name: Optional[str] = None) -> "CorrectionTable":
        path = Path(path)
        pts = []
        with open(path, "r", encoding="utf-8-sig") as f:
            sample = f.read(2000)
            f.seek(0)
            delim = ";" if sample.count(";") >= sample.count(",") else ","
            reader = csv.reader(f, delimiter=delim)
            for row in reader:
                if len(row) < 2:
                    continue
                try:
                    freq = float(row[0].replace(",", "."))
                    corr = float(row[1].replace(",", "."))
                except ValueError:
                    continue
                pts.append((freq, corr))
        return CorrectionTable(name=name or path.stem, unit_note="importado de CSV", points=pts)

    def to_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps({
            "name": self.name, "unit_note": self.unit_note, "points": self.points,
        }, indent=2), encoding="utf-8")

    @staticmethod
    def from_json(path: str | Path) -> "CorrectionTable":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return CorrectionTable(name=data["name"], unit_note=data.get("unit_note", ""),
                                points=[tuple(p) for p in data["points"]])


# Placeholders -- substitua pelos dados de calibracao reais do seu par
# receiver+LISN / receiver+loop antes de gerar laudos.
DEFAULT_LISN_ENV216_INSERTION_LOSS = CorrectionTable.flat("ENV216 insertion loss (placeholder)", 0.0)
DEFAULT_CABLE_LOSS = CorrectionTable.flat("Perda de cabo RF (placeholder)", 0.0)
DEFAULT_LOOP_ANTENNA_FACTOR = CorrectionTable.flat("Fator da antena loop (placeholder)", 0.0)


# ---------------------------------------------------------------------------
# Biblioteca de tabelas de correcao salvas em disco (core/corrections_lib/),
# no mesmo espirito de core/standards/: cada tabela de correcao (fator de
# LISN, de antena, perda de cabo etc.) e um arquivo .json que o usuario cria/
# edita/exclui pela GUI, em vez de valores fixos no codigo.
# ---------------------------------------------------------------------------

CORRECTIONS_DIR = Path(__file__).parent / "corrections_lib"
CORRECTIONS_DIR.mkdir(exist_ok=True)

_SAFE_NAME_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_- ")


def validate_correction_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("O nome da tabela de correcao nao pode ser vazio.")
    if not set(name) <= _SAFE_NAME_CHARS:
        raise ValueError("Use apenas letras, numeros, espaco, '_' e '-' no nome.")
    return name


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_") or "tabela"


def list_available_corrections() -> list[Path]:
    return sorted(CORRECTIONS_DIR.glob("*.json"))


def load_correction(path: str | Path) -> CorrectionTable:
    return CorrectionTable.from_json(path)


def save_correction(table: CorrectionTable, path: str | Path) -> None:
    table.to_json(path)


def new_correction(name: str, value_db: float = 0.0) -> Path:
    name = validate_correction_name(name)
    path = CORRECTIONS_DIR / f"{_slug(name)}.json"
    if path.exists():
        raise FileExistsError(f"Ja existe uma tabela de correcao chamada '{name}'.")
    table = CorrectionTable.flat(name, value_db)
    table.to_json(path)
    return path


def duplicate_correction(src_path: str | Path, new_name: str) -> Path:
    new_name = validate_correction_name(new_name)
    dst = CORRECTIONS_DIR / f"{_slug(new_name)}.json"
    if dst.exists():
        raise FileExistsError(f"Ja existe uma tabela de correcao chamada '{new_name}'.")
    table = CorrectionTable.from_json(src_path)
    table.name = new_name
    table.to_json(dst)
    return dst


def rename_correction(path: str | Path, new_name: str) -> Path:
    new_name = validate_correction_name(new_name)
    path = Path(path)
    dst = CORRECTIONS_DIR / f"{_slug(new_name)}.json"
    if dst != path and dst.exists():
        raise FileExistsError(f"Ja existe uma tabela de correcao chamada '{new_name}'.")
    table = CorrectionTable.from_json(path)
    table.name = new_name
    table.to_json(dst)
    if dst != path:
        path.unlink()
    return dst


def delete_correction(path: str | Path) -> None:
    Path(path).unlink()
