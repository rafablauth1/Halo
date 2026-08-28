import os
import shutil
import string
from pathlib import Path
from typing import Callable, Optional

from emc import config

FOLDER_ROOT_NAME = "arquivos_projetos"

# Pastas do sistema que não valem a pena vasculhar (deixam a busca lenta e
# não é onde o operador salva arquivo gerado por outro software).
_SKIP_DIR_NAMES = {
    "Windows",
    "Program Files",
    "Program Files (x86)",
    "ProgramData",
    "$Recycle.Bin",
    "System Volume Information",
    "node_modules",
    ".git",
    "$WinREAgent",
    "Recovery",
}


def _root_dir() -> Path:
    root = config.DATA_DIR / FOLDER_ROOT_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_project_folder(project_id: int) -> Path:
    folder = _root_dir() / str(project_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def list_project_files(project_id: int) -> list[Path]:
    folder = get_project_folder(project_id)
    return sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.name)


def _available_drives() -> list[Path]:
    drives = []
    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        if root.exists():
            drives.append(root)
    return drives


def find_matching_files(
    protocolo: str,
    root_dirs: Optional[list[Path]] = None,
    stop_flag: Optional[Callable[[], bool]] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> list[Path]:
    """Vasculha por arquivos .txt cujo nome começa com '{protocolo}_' — é
    assim que o outro software nomeia os arquivos gerados (ex.:
    26070472_4-19_120V.txt). root_dirs: pastas onde procurar; se None,
    procura em todas as unidades de disco disponíveis ("buscar no PC
    todo")."""
    prefix = f"{protocolo}_"
    matches: list[Path] = []
    project_files_root = _root_dir()
    roots = root_dirs if root_dirs is not None else _available_drives()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda e: None):
            if stop_flag is not None and stop_flag():
                return matches
            current = Path(dirpath)
            if current == project_files_root or project_files_root in current.parents:
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith("$")]
            if on_progress is not None:
                on_progress(dirpath)
            for filename in filenames:
                if filename.startswith(prefix) and filename.lower().endswith(".txt"):
                    matches.append(current / filename)
    return matches


def _unique_destination(dest: Path) -> Path:
    n = 1
    candidate = dest
    while candidate.exists():
        candidate = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
        n += 1
    return candidate


def move_files_to_project(project_id: int, files: list[Path]) -> tuple[int, int]:
    """Move os arquivos pra pasta do projeto. Pula (sem sobrescrever) se já
    existir um arquivo igual (mesmo nome e tamanho) no destino. Retorna
    (movidos, ignorados)."""
    folder = get_project_folder(project_id)
    moved = 0
    skipped = 0
    for src in files:
        if not src.exists() or not src.is_file():
            skipped += 1
            continue
        dest = folder / src.name
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            skipped += 1
            continue
        dest = _unique_destination(dest)
        shutil.move(str(src), str(dest))
        moved += 1
    return moved, skipped
