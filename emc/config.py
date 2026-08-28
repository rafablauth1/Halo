import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    # Empacotado com PyInstaller (.exe portátil) — dados ficam ao lado do .exe,
    # não na pasta temporária de extração (que some quando o programa fecha).
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Aponta pra onde fica o banco de dados (app.db) e os arquivos de projetos —
# por padrão, "data" do lado do .exe. Esse arquivo-ponteiro fica sempre do
# lado do .exe (não dentro de "data"), pra funcionar mesmo antes de saber
# onde "data" está. Trocado em Configurações → Diretório de dados; existe
# justamente pra sobreviver a atualizações do .exe (rebuild/cópia de uma
# versão nova) — o app nunca mais volta a criar um banco vazio do zero só
# porque o executável foi trocado, e dá pra apontar pra uma pasta de rede
# compartilhada entre vários PCs.
_DATA_DIR_POINTER_FILE = BASE_DIR / "data_dir_location.txt"


def _resolve_data_dir() -> Path:
    try:
        custom = _DATA_DIR_POINTER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        custom = ""
    return Path(custom) if custom else BASE_DIR / "data"


def set_data_dir_override(path: "Path | None") -> None:
    """Grava (ou remove, se path=None) o diretório de dados escolhido pelo
    operador. Só tem efeito depois de reiniciar o app — DATA_DIR/DB_PATH já
    foram calculados na importação deste módulo."""
    if path is None:
        _DATA_DIR_POINTER_FILE.unlink(missing_ok=True)
    else:
        _DATA_DIR_POINTER_FILE.write_text(str(path), encoding="utf-8")


DATA_DIR = _resolve_data_dir()
REPORTS_DIR = BASE_DIR / "reports"
DB_PATH = DATA_DIR / "app.db"

# Pasta espelhada (opcional, tipicamente de rede) SÓ pros roteiros de execução
# salvos em Templates — grava duplicado: local (funciona no portátil, offline,
# mesmo sem rede) E nessa pasta (compartilhada com o PC "normal"/outros PCs).
# Ao contrário de DATA_DIR, essa é lida em tempo real (não precisa reiniciar).
_TEMPLATES_MIRROR_POINTER_FILE = BASE_DIR / "templates_mirror_dir_location.txt"


def get_templates_mirror_dir() -> "Path | None":
    try:
        custom = _TEMPLATES_MIRROR_POINTER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        custom = ""
    return Path(custom) if custom else None


def set_templates_mirror_dir(path: "Path | None") -> None:
    if path is None:
        _TEMPLATES_MIRROR_POINTER_FILE.unlink(missing_ok=True)
    else:
        _TEMPLATES_MIRROR_POINTER_FILE.write_text(str(path), encoding="utf-8")

# Sem NI-VISA/hardware neste PC de desenvolvimento: modo simulado por padrão.
# Trocar para False no PC do laboratório, com NI-VISA instalado e os
# instrumentos conectados via GPIB.
SIMULATION_MODE = True

DEFAULT_GPIB_ADDRESSES = {
    "ucs500n": 6,
    "chroma": 30,
    "agilent_53131a": 1,
}

# Placa GPIB de cada instrumento. Confirmado em campo (NI MAX, PC do
# laboratório): só existe a placa GPIB0 — abrir uma placa inexistente
# (ex.: GPIB1, que um script antigo usava numa outra máquina) trava o
# driver NI-VISA com "access violation" em vez de dar um erro limpo.
DEFAULT_GPIB_BOARDS = {
    "agilent_53131a": 0,
}

# número da porta ASRL (ex.: 3 → COM3, formato ASRL3::INSTR do VISA),
# confirmado no script validado em campo (Timer_RTC.py) pro contador.
DEFAULT_SERIAL_PORTS = {
    "ucs500n": 3,
    "chroma": 4,
    "agilent_53131a": 3,
}

# Conexão padrão de cada instrumento: "gpib" ou "serial" (RS-232).
DEFAULT_UCS500N_CONNECTION = "gpib"
DEFAULT_CHROMA_CONNECTION = "gpib"
DEFAULT_COUNTER_CONNECTION = "gpib"

STANDARDS = {
    "4-2": "Descarga Eletrostática (ESD)",
    "4-3": "Campo Eletromagnético Irradiado (RS)",
    "4-4": "Transitórios Elétricos Rápidos em Salvas (Burst/EFT)",
    "4-5": "Surtos (Surge)",
    "4-6": "Perturbações Conduzidas Induzidas por Campos RF (CS)",
    "4-11": "Quedas de Tensão, Interrupções Curtas e Variações de Tensão (Dips)",
    "4-19": "Distúrbios Conduzidos de Corrente Contínua",
}

# Normas cobertas por automação de equipamento nesta primeira versão.
AUTOMATED_STANDARDS = ("4-4", "4-5", "4-11")

DATA_DIR.mkdir(parents=True, exist_ok=True)  # parents=True: pode ser um caminho de rede ainda não criado
REPORTS_DIR.mkdir(exist_ok=True)
