"""
core/limits.py

Modelo de "linha de limite" (limit line) e avaliacao de pass/fail, no
mesmo espirito dos arquivos de limite (.lim) do RadiMation: um conjunto
de segmentos (frequencia_inicial, frequencia_final, valor_inicial,
valor_final) com um tipo de interpolacao, para cada detector.

Isso permite plugar QUALQUER norma (nao so a CISPR15) desde que ela seja
descrita como uma lista de segmentos por detector, em um arquivo .json
dentro de core/standards/.

IMPORTANTE - RESPONSABILIDADE TECNICA: instrucoes completas sobre a
confiabilidade dos valores pre-carregados em core/standards/*.json e
como completa-los estao em instrucoes/02_pendencias_limites_de_norma.md.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

Interpolation = Literal["log-linear", "linear", "log-log"]

STANDARDS_DIR = Path(__file__).parent / "standards"


@dataclass
class LimitSegment:
    freq_start_hz: float
    freq_end_hz: float
    value_start: Optional[float]  # None = nao verificado / a preencher
    value_end: Optional[float]
    verified: bool = True
    note: str = ""

    def value_at(self, freq_hz: float, interpolation: Interpolation = "log-linear") -> Optional[float]:
        if self.value_start is None or self.value_end is None:
            return None
        if freq_hz <= self.freq_start_hz:
            return self.value_start
        if freq_hz >= self.freq_end_hz:
            return self.value_end
        if self.freq_start_hz <= 0 or self.freq_end_hz <= 0:
            interpolation = "linear"

        if interpolation == "log-linear":
            # valor (em dB) varia linearmente com log10(f) -- e o modelo
            # descrito na CISPR16-1-1/CISPR15 para os trechos "decreasing
            # linearly with the logarithm of frequency".
            x0, x1 = math.log10(self.freq_start_hz), math.log10(self.freq_end_hz)
            x = math.log10(freq_hz)
        elif interpolation == "log-log":
            x0, x1 = math.log10(self.freq_start_hz), math.log10(self.freq_end_hz)
            x = math.log10(freq_hz)
            # aqui o valor tambem seria log, mas como valores de limite
            # em dB ja sao log, tratamos igual ao log-linear.
        else:  # linear
            x0, x1 = self.freq_start_hz, self.freq_end_hz
            x = freq_hz

        if x1 == x0:
            return self.value_start
        frac = (x - x0) / (x1 - x0)
        return self.value_start + frac * (self.value_end - self.value_start)


@dataclass
class LimitLine:
    name: str
    detector: str  # ex.: "QP", "AV", "PK", "CISPR-AV"
    unit: str  # ex.: "dBuV", "dBuA/m", "dBuV/m"
    interpolation: Interpolation
    segments: list[LimitSegment] = field(default_factory=list)

    def value_at(self, freq_hz: float) -> Optional[float]:
        # Nas frequencias de transicao entre dois segmentos, a CISPR 15
        # (notas das tabelas do item 4) manda aplicar O LIMITE INFERIOR --
        # por isso pegamos o menor valor entre os segmentos que contem a
        # frequencia, em vez do primeiro que casar.
        values = [v for v in (seg.value_at(freq_hz, self.interpolation)
                              for seg in self.segments
                              if seg.freq_start_hz <= freq_hz <= seg.freq_end_hz)
                  if v is not None]
        return min(values) if values else None

    def is_fully_verified(self) -> bool:
        return all(s.verified and s.value_start is not None and s.value_end is not None for s in self.segments)


@dataclass
class StandardMethod:
    """Um 'metodo de ensaio' (ex.: conduzida, loop, radiada) dentro de uma norma."""
    id: str
    title: str
    standard_ref: str
    freq_range_hz: tuple[float, float]
    x_axis: str  # "log" ou "linear"
    limit_lines: list[LimitLine] = field(default_factory=list)
    notes: str = ""

    def limit_at(self, detector: str, freq_hz: float) -> Optional[float]:
        for ll in self.limit_lines:
            if ll.detector == detector:
                return ll.value_at(freq_hz)
        return None


def _segment_from_dict(d: dict) -> LimitSegment:
    return LimitSegment(
        freq_start_hz=float(d["freq_start_hz"]),
        freq_end_hz=float(d["freq_end_hz"]),
        value_start=(None if d.get("value_start") is None else float(d["value_start"])),
        value_end=(None if d.get("value_end") is None else float(d["value_end"])),
        verified=bool(d.get("verified", True)),
        note=d.get("note", ""),
    )


def load_method(json_path: Path) -> StandardMethod:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    limit_lines = []
    for ll in data["limit_lines"]:
        segs = [_segment_from_dict(s) for s in ll["segments"]]
        limit_lines.append(
            LimitLine(
                name=ll["name"],
                detector=ll["detector"],
                unit=ll["unit"],
                interpolation=ll.get("interpolation", "log-linear"),
                segments=segs,
            )
        )
    return StandardMethod(
        id=data["id"],
        title=data["title"],
        standard_ref=data["standard_ref"],
        freq_range_hz=(float(data["freq_range_hz"][0]), float(data["freq_range_hz"][1])),
        x_axis=data.get("x_axis", "log"),
        limit_lines=limit_lines,
        notes=data.get("notes", ""),
    )


def list_available_methods() -> list[Path]:
    return sorted(STANDARDS_DIR.glob("*.json"))


_SAFE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")


def validate_method_id(method_id: str) -> str:
    method_id = method_id.strip()
    if not method_id:
        raise ValueError("O id da norma nao pode ser vazio.")
    if not set(method_id) <= _SAFE_ID_CHARS:
        raise ValueError("Use apenas letras, numeros, '_' e '-' no id da norma.")
    return method_id


def new_method(method_id: str, title: str = "") -> Path:
    """Cria uma norma/metodo novo, vazio, pronto para ser configurado na GUI
    (sem nenhum segmento pre-carregado -- o usuario define tudo)."""
    method_id = validate_method_id(method_id)
    path = STANDARDS_DIR / f"{method_id}.json"
    if path.exists():
        raise FileExistsError(f"Ja existe uma norma com id '{method_id}'.")
    method = StandardMethod(
        id=method_id,
        title=title or method_id,
        standard_ref="",
        freq_range_hz=(9000.0, 30000000.0),
        x_axis="log",
        limit_lines=[],
        notes="",
    )
    save_method(method, path)
    return path


def duplicate_method(src_path: Path, new_id: str) -> Path:
    new_id = validate_method_id(new_id)
    dst = STANDARDS_DIR / f"{new_id}.json"
    if dst.exists():
        raise FileExistsError(f"Ja existe uma norma com id '{new_id}'.")
    method = load_method(src_path)
    method.id = new_id
    method.title = f"{method.title} (copia)"
    save_method(method, dst)
    return dst


def rename_method(path: Path, new_id: str) -> Path:
    new_id = validate_method_id(new_id)
    dst = STANDARDS_DIR / f"{new_id}.json"
    if dst != path and dst.exists():
        raise FileExistsError(f"Ja existe uma norma com id '{new_id}'.")
    method = load_method(path)
    method.id = new_id
    save_method(method, dst)
    if dst != path:
        path.unlink()
    return dst


def delete_method(path: Path) -> None:
    path.unlink()


def save_method(method: StandardMethod, json_path: Path) -> None:
    data = {
        "id": method.id,
        "title": method.title,
        "standard_ref": method.standard_ref,
        "freq_range_hz": list(method.freq_range_hz),
        "x_axis": method.x_axis,
        "notes": method.notes,
        "limit_lines": [
            {
                "name": ll.name,
                "detector": ll.detector,
                "unit": ll.unit,
                "interpolation": ll.interpolation,
                "segments": [
                    {
                        "freq_start_hz": s.freq_start_hz,
                        "freq_end_hz": s.freq_end_hz,
                        "value_start": s.value_start,
                        "value_end": s.value_end,
                        "verified": s.verified,
                        "note": s.note,
                    }
                    for s in ll.segments
                ],
            }
            for ll in method.limit_lines
        ],
    }
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
