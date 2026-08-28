"""Valida fotos de um display (ex.: mostrador de radar de velocidade) contra
uma velocidade esperada, que pode mudar por faixa de horário durante o
ensaio — usado quando se tem centenas/milhares de fotos (ex.: 1 por segundo
por 30 min) e precisa achar rápido quais divergiram do esperado ou não deram
pra ler (falha de OCR)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional

from PIL import Image, ExifTags

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")

_EXIF_DATETIME_TAG = next(
    (k for k, v in ExifTags.TAGS.items() if v == "DateTimeOriginal"), None
)


@dataclass
class ScheduleEntry:
    start: dt_time
    end: dt_time
    expected_value: str  # comparado como texto (ex.: "60") — evita ambiguidade de casas decimais


@dataclass
class PhotoResult:
    path: Path
    timestamp: Optional[datetime]
    expected_value: Optional[str]
    read_value: Optional[str]
    status: str  # "ok" | "divergente" | "erro_leitura" | "sem_horario"
    ocr_confidence: Optional[float] = None


@dataclass
class Roi:
    """Retângulo de recorte, em FRAÇÃO da imagem (0..1) — assim vale pra
    qualquer resolução, desde que o enquadramento da câmera seja fixo entre
    as fotos (mesmo tripé/posição), como é o caso de um ensaio de radar."""

    left: float
    top: float
    right: float
    bottom: float

    def crop_box(self, width: int, height: int) -> tuple[int, int, int, int]:
        return (
            int(self.left * width),
            int(self.top * height),
            int(self.right * width),
            int(self.bottom * height),
        )


def list_photos(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]
    files.sort(key=lambda p: p.name)
    return files


def photo_timestamp(path: Path) -> Optional[datetime]:
    """Tenta EXIF (DateTimeOriginal) primeiro — é o horário real da captura,
    mais confiável que o mtime do arquivo (que muda se o arquivo for
    copiado/movido). Se não tiver EXIF, cai pro mtime."""
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if exif and _EXIF_DATETIME_TAG in exif:
                raw = exif[_EXIF_DATETIME_TAG]
                return datetime.strptime(raw, "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def expected_value_for(timestamp: Optional[datetime], schedule: list[ScheduleEntry]) -> Optional[str]:
    if timestamp is None:
        return None
    t = timestamp.time()
    for entry in schedule:
        if entry.start <= entry.end:
            if entry.start <= t <= entry.end:
                return entry.expected_value
        else:
            # faixa que cruza a meia-noite (ex.: 23:50 às 00:10)
            if t >= entry.start or t <= entry.end:
                return entry.expected_value
    return None


_DIGITS_RE = re.compile(r"\d+(?:[.,]\d+)?")


def extract_numeric(ocr_texts: list[str]) -> Optional[str]:
    """Junta os textos que o OCR achou na imagem/recorte e extrai o primeiro
    número (o mostrador do radar mostra só um valor). Normaliza vírgula pra
    ponto pra comparação, mas mantém como string (evita erro de
    arredondamento de float)."""
    joined = " ".join(ocr_texts)
    match = _DIGITS_RE.search(joined)
    if not match:
        return None
    return match.group(0).replace(",", ".")


def values_match(expected: str, read: str) -> bool:
    try:
        return float(expected.replace(",", ".")) == float(read.replace(",", "."))
    except ValueError:
        return expected.strip() == read.strip()


class OcrEngine:
    """Encapsula o RapidOCR — import tardio, pra não pagar o custo (~1-2s de
    carregar os modelos ONNX) se essa aba nunca for usada na sessão."""

    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR

        self._engine = RapidOCR()

    def read(self, image_path: Path, roi: Optional[Roi] = None) -> tuple[list[str], Optional[float]]:
        import numpy as np

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            if roi is not None:
                img = img.crop(roi.crop_box(*img.size))
            arr = np.array(img)

        result, _ = self._engine(arr)
        if not result:
            return [], None
        texts = [r[1] for r in result]
        confidences = [float(r[2]) for r in result if len(r) > 2]
        avg_conf = sum(confidences) / len(confidences) if confidences else None
        return texts, avg_conf


@dataclass
class JsonResult:
    path: Path
    folder_name: str
    found_value: object
    status: str  # "ok" | "divergente" | "erro"
    error_message: str = ""
    timestamp: Optional[datetime] = None


def find_json_files(root: Path) -> list[Path]:
    """Acha os .json dentro de cada subpasta imediata de `root` — uma pasta
    por caso de ensaio, cada uma com seu json de resultado."""
    files = []
    for sub in sorted(root.iterdir()):
        if sub.is_dir():
            files.extend(sorted(sub.glob("*.json")))
    return files


def _json_values_match(found, expected) -> bool:
    try:
        return float(found) == float(expected)
    except (TypeError, ValueError):
        return found == expected


JSON_TIMESTAMP_KEY = "Timestamp"


def _parse_json_timestamp(raw) -> Optional[datetime]:
    """Formato ISO 8601 com milissegundos e 'Z' de UTC, ex.:
    "2026-08-18T16:54:23.479Z" — datetime.fromisoformat não aceita o 'Z'
    direto em versões mais antigas, então troca por '+00:00'."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def validate_json_file(path: Path, key: str, expected_value: str) -> JsonResult:
    import json

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        return JsonResult(
            path=path, folder_name=path.parent.name, found_value=None, status="erro", error_message=str(exc)
        )

    timestamp = _parse_json_timestamp(data.get(JSON_TIMESTAMP_KEY))

    if key not in data:
        return JsonResult(
            path=path,
            folder_name=path.parent.name,
            found_value=None,
            status="erro",
            error_message=f'Chave "{key}" não encontrada no JSON.',
            timestamp=timestamp,
        )

    found = data[key]
    status = "ok" if _json_values_match(found, expected_value) else "divergente"
    return JsonResult(path=path, folder_name=path.parent.name, found_value=found, status=status, timestamp=timestamp)


def validate_photo(
    engine: OcrEngine,
    path: Path,
    schedule: list[ScheduleEntry],
    roi: Optional[Roi] = None,
) -> PhotoResult:
    timestamp = photo_timestamp(path)
    expected = expected_value_for(timestamp, schedule)

    try:
        texts, confidence = engine.read(path, roi)
    except Exception:
        texts, confidence = [], None

    read_value = extract_numeric(texts)

    if expected is None:
        status = "sem_horario"
    elif read_value is None:
        status = "erro_leitura"
    elif values_match(expected, read_value):
        status = "ok"
    else:
        status = "divergente"

    return PhotoResult(
        path=path,
        timestamp=timestamp,
        expected_value=expected,
        read_value=read_value,
        status=status,
        ocr_confidence=confidence,
    )
