"""Permite sobrescrever, sem precisar mexer em código nem gerar um .exe novo,
os comandos GPIB/SCPI de cada equipamento — usado principalmente pro UCS 500N
(cujo dicionário de comandos real do fabricante não é público), mas disponível
pra qualquer instrumento, caso surja alguma variação real de modelo/firmware.
O operador descobre/confirma os comandos certos testando no Terminal GPIB
(aba Comandos) e salva ali; os drivers passam a usar esses valores."""

import json

from emc.config import DATA_DIR

_FILENAMES = {
    "ucs500n": "ucs500n_commands_override.json",
    "chroma": "chroma_commands_override.json",
    "agilent_53131a": "agilent_53131a_commands_override.json",
}


def _path_for(instrument: str):
    filename = _FILENAMES.get(instrument, f"{instrument}_commands_override.json")
    return DATA_DIR / filename


def load_overrides(instrument: str) -> dict:
    path = _path_for(instrument)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_overrides(instrument: str, overrides: dict) -> None:
    with open(_path_for(instrument), "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2, ensure_ascii=False)
