"""
gui/theme.py

Identidade visual do HALO: paleta, tipografia, folha de estilo (QSS) e
o logotipo -- tudo desenhado em codigo, sem depender de arquivo de
imagem externo.

O nome HALO vem do anel de luz ao redor de uma fonte luminosa: e a
imagem exata do que o programa mede -- a emissao que se irradia de uma
luminaria. O logotipo sao arcos concentricos saindo de um nucleo aceso.

Para trocar o nome/subtitulo do programa, mexa so em APP_NAME e
APP_TAGLINE aqui embaixo -- o resto da interface le daqui.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QPainter,
                            QPainterPath, QPen, QPixmap, QRadialGradient)

# ============================================================================
# Identidade
# ============================================================================
APP_NAME = "HALO"
APP_TAGLINE = "Ensaios de emissão · CISPR 15"
APP_ORG = "Ensaios de EMC"
APP_VERSION = "0.9"
WINDOW_TITLE = f"{APP_NAME} — Ensaios de Emissão CISPR 15"

# ============================================================================
# Paleta — esquema escuro Material 3
# ============================================================================
# Segue os papeis de cor do Material Design 3 (primary / surface / outline
# etc.) num esquema escuro semeado em azul. Duas consequencias visiveis:
#
#  * no M3 escuro a cor primaria e CLARA (tom 80) e o texto sobre ela e
#    escuro -- por isso o botao principal e azul-claro com letra escura,
#    e nao o contrario;
#  * elevacao no M3 nao e sombra, e tinta: quanto mais "alto" o elemento,
#    mais clara a superficie. Dai a escada surface_container_*.
#
# "Success" e "warning" nao existem como papel no M3; ficam definidos aqui
# no mesmo formato (cor + container) para o resto seguir a mesma logica.

# --- cor de acao -------------------------------------------------------------
# Teal dessaturado. A escolha e deliberada: azul-claro saturado e a cor
# padrao de todo framework moderno e nao diz nada sobre o programa. Num
# software de instrumentacao a moldura e cinza e a COR FICA NO DADO --
# traco, limite, aprovado/reprovado. O acento aparece so em selecao e foco.
ACCENT = "#2fbfa8"
ACCENT_ON = "#04211c"
ACCENT_HI = "#45d4bd"
ACCENT_LO = "#1c5f53"
ACCENT_BG = "#123b34"

# --- superficies: grafite NEUTRO, sem tingimento azul -----------------------
BG = "#141517"          # canvas
SURFACE = "#1a1b1e"     # cartoes
SURFACE_2 = "#212226"   # botoes, campos elevados
SURFACE_3 = "#2b2c31"   # hover
FIELD = "#0f1012"       # fundo de campo e de tabela
FIELD_ALT = "#161719"   # linha alternada

BORDER = "#34363b"      # linhas de estrutura
BORDER_2 = "#4a4c53"    # contorno de campo

TEXT = "#e6e7ea"
TEXT_MUTED = "#9b9da4"
TEXT_DIM = "#6b6d75"

GLOW = "#d9a441"        # a marca (o halo) -- so no logotipo
GLOW_LO = "#a87c2c"

# --- estados: unica parte saturada da interface -----------------------------
OK = "#4eae7a"
OK_BG = "#12271c"
FAIL = "#d95c5c"
FAIL_BG = "#2e1516"
WARN = "#d9a441"
WARN_BG = "#2c2313"
INFO = "#5b9dc4"

# --- paleta de realce -------------------------------------------------------
# Cores fortes o bastante para identificar coisa a coisa num relance:
# detector, banda, tipo de ensaio. A moldura continua cinza; a cor entra
# nos elementos que carregam informacao.
CHIPS = {
    "teal":   ("#2fbfa8", "#0e332d"),
    "azul":   ("#4a90e2", "#12283f"),
    "roxo":   ("#8b6ff0", "#221b3d"),
    "rosa":   ("#e879a6", "#3a1a28"),
    "ambar":  ("#e8a33d", "#33240e"),
    "verde":  ("#4eae7a", "#12291d"),
    "vermelho": ("#d95c5c", "#331516"),
    "cinza":  ("#9b9da4", "#232427"),
}

# Cor fixa por detector: o mesmo detector tem sempre a mesma cor na
# interface inteira -- chip, tabela e legenda do grafico.
COR_DETECTOR = {
    "PK": "verde", "QP": "teal", "AV": "ambar",
    "CAV": "rosa", "RMS": "azul", "CRMS": "roxo",
}

# Cor por banda CISPR
COR_BANDA = {"A": "roxo", "B": "azul", "C": "teal", "D": "verde", "E": "ambar"}


def cor_chip(nome: str) -> tuple[str, str]:
    """(texto, fundo) do chip. Nome desconhecido cai em cinza."""
    return CHIPS.get(nome, CHIPS["cinza"])


# --- escala de formas: cantos pequenos --------------------------------------
# Cápsula (stadium) e a assinatura visual do Material 3 e destoa de
# ferramenta tecnica. 4-8 px e o que Figma, editores de audio e software
# de bancada usam.
SHAPE_XS = 3
SHAPE_SM = 5
SHAPE_MD = 7
SHAPE_LG = 10
SHAPE_FULL = 5          # botao: retangular com canto suave, nao capsula

# nomes M3 mantidos como apelido, para o QSS existente continuar valendo
M3_PRIMARY, M3_ON_PRIMARY = ACCENT, ACCENT_ON
M3_PRIMARY_CONTAINER, M3_ON_PRIMARY_CONTAINER = ACCENT_BG, "#a9ded8"
M3_SECONDARY_CONTAINER, M3_ON_SECONDARY_CONTAINER = SURFACE_3, TEXT
M3_SURFACE, M3_SURFACE_LOWEST, M3_SURFACE_LOW = BG, FIELD, SURFACE
M3_SURFACE_CONTAINER, M3_SURFACE_HIGH, M3_SURFACE_HIGHEST = SURFACE_2, SURFACE_3, "#35363c"
M3_ON_SURFACE, M3_ON_SURFACE_VARIANT = TEXT, TEXT_MUTED
M3_OUTLINE, M3_OUTLINE_VARIANT, M3_OUTLINE_MID = BORDER_2, BORDER, BORDER
M3_ERROR, M3_ERROR_CONTAINER = FAIL, FAIL_BG
M3_TERTIARY = GLOW

# Atalhos para setStyleSheet pontual em labels de status
CSS_MUTED = f"color:{TEXT_MUTED}; font-size:11px;"
CSS_DIM = f"color:{TEXT_DIM}; font-size:11px;"
CSS_OK = f"color:{OK}; font-size:11px;"
CSS_WARN = f"color:{WARN}; font-size:11px;"
CSS_FAIL = f"color:{FAIL}; font-size:11px; font-weight:600;"

# Cores de estado por veredito, usadas em tabelas e faixas de resultado
STATUS_COLORS = {
    "Pass": OK,
    "Fail": FAIL,
    "Indet.": WARN,
    "APROVADO": OK,
    "REPROVADO": FAIL,
}


def status_color(texto: str) -> QColor:
    """Cor do veredito. Aceita as variantes longas ('APROVADO (item 4.1)')."""
    t = (texto or "").upper()
    if t.startswith("APROVADO") or t == "PASS":
        return QColor(OK)
    if t.startswith("REPROVADO") or t == "FAIL":
        return QColor(FAIL)
    if t.startswith("INDET") or t.startswith("ATEN"):
        return QColor(WARN)
    return QColor(TEXT_MUTED)


# ============================================================================
# Tipografia
# ============================================================================
def _pick(*familias: str) -> str:
    disponiveis = set(QFontDatabase.families())
    for f in familias:
        if f in disponiveis:
            return f
    return familias[-1]


def ui_font(size: int = 10, weight: int = QFont.Normal) -> QFont:
    f = QFont(_pick("Segoe UI Variable Text", "Segoe UI", "Inter", "Sans Serif"))
    f.setPointSize(size)
    f.setWeight(weight)
    return f


def mono_font(size: int = 9) -> QFont:
    f = QFont(_pick("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Monospace"))
    f.setPointSize(size)
    return f


# ============================================================================
# Logotipo e icones (desenhados em runtime -- nao ha arquivo de imagem)
# ============================================================================
def logo_pixmap(size: int = 40) -> QPixmap:
    """O halo: nucleo aceso com arcos concentricos se irradiando."""
    px = QPixmap(size, size)
    px.setDevicePixelRatio(1.0)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)

    c = size / 2.0
    # brilho difuso do nucleo
    grad = QRadialGradient(c, c, size * 0.30)
    grad.setColorAt(0.0, QColor(255, 200, 110, 210))
    grad.setColorAt(1.0, QColor(255, 181, 71, 0))
    p.setBrush(grad)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(c - size * 0.30, c - size * 0.30, size * 0.60, size * 0.60))

    # nucleo
    p.setBrush(QColor(GLOW))
    p.drawEllipse(QRectF(c - size * 0.115, c - size * 0.115, size * 0.23, size * 0.23))

    # arcos: abertos a direita, sugerindo a emissao se propagando
    p.setBrush(Qt.NoBrush)
    for raio, alfa, esp in ((0.27, 235, 0.075), (0.375, 165, 0.062), (0.475, 95, 0.052)):
        cor = QColor(ACCENT)
        cor.setAlpha(alfa)
        pen = QPen(cor, max(1.0, size * esp))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        r = size * raio
        rect = QRectF(c - r, c - r, 2 * r, 2 * r)
        p.drawArc(rect, int(-58 * 16), int(296 * 16))
    p.end()
    return px


def app_icon() -> QIcon:
    ico = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ico.addPixmap(logo_pixmap(s))
    return ico


# --- pequenos glifos usados pela folha de estilo (seta, check) --------------
_ASSET_DIR: Path | None = None


def _asset_dir() -> Path:
    global _ASSET_DIR
    if _ASSET_DIR is not None:
        return _ASSET_DIR
    candidatos = [Path(__file__).parent / "_assets",
                  Path(tempfile.gettempdir()) / "halo_assets"]
    for d in candidatos:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / ".ok").write_text("", encoding="utf-8")
            _ASSET_DIR = d
            return d
        except Exception:
            continue
    _ASSET_DIR = Path(tempfile.gettempdir())
    return _ASSET_DIR


def _qss_path(p: Path) -> str:
    """QSS so aceita barra normal, inclusive no Windows."""
    return str(p).replace("\\", "/")


def _chevron(nome: str, cor: str, direcao: str, lado: int = 14) -> str:
    px = QPixmap(lado, lado)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(cor), 1.7)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    m, c = lado * 0.28, lado / 2.0
    if direcao == "down":
        pts = [(m, c - lado * 0.10), (c, c + lado * 0.16), (lado - m, c - lado * 0.10)]
    else:
        pts = [(m, c + lado * 0.10), (c, c - lado * 0.16), (lado - m, c + lado * 0.10)]
    path = QPainterPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    p.drawPath(path)
    p.end()
    caminho = _asset_dir() / f"{nome}.png"
    px.save(str(caminho), "PNG")
    return _qss_path(caminho)


def _check(nome: str, cor: str, lado: int = 14) -> str:
    px = QPixmap(lado, lado)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(cor), 2.1)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(lado * 0.24, lado * 0.52)
    path.lineTo(lado * 0.43, lado * 0.72)
    path.lineTo(lado * 0.78, lado * 0.29)
    p.drawPath(path)
    p.end()
    caminho = _asset_dir() / f"{nome}.png"
    px.save(str(caminho), "PNG")
    return _qss_path(caminho)


def _dash(nome: str, cor: str, lado: int = 14) -> str:
    px = QPixmap(lado, lado)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(cor), 2.1)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawLine(int(lado * 0.26), lado // 2, int(lado * 0.74), lado // 2)
    p.end()
    caminho = _asset_dir() / f"{nome}.png"
    px.save(str(caminho), "PNG")
    return _qss_path(caminho)


# ============================================================================
# Folha de estilo
# ============================================================================
def build_qss() -> str:
    """Folha de estilo no vocabulario do Material 3.

    Tres regras do M3 explicam quase tudo daqui para baixo:
    1. Elevacao e TINTA, nao sombra -- o que esta "acima" usa uma
       superficie mais clara (a escada surface_container_*).
    2. No esquema escuro a cor primaria e clara e o texto sobre ela e
       escuro (`on-primary`). Por isso o botao principal e azul-claro
       com letra escura, e nao o contrario.
    3. Interacao e "state layer": hover/pressed sao a cor de conteudo
       sobreposta com 8%/10% de opacidade -- aqui aproximada com cores
       solidas, porque o QSS nao compoe camadas.
    """
    seta_baixo = _chevron("chevron_down", M3_ON_SURFACE_VARIANT, "down")
    seta_baixo_hi = _chevron("chevron_down_hi", M3_PRIMARY, "down")
    seta_cima_mini = _chevron("chevron_up_mini", M3_ON_SURFACE_VARIANT, "up", 10)
    seta_baixo_mini = _chevron("chevron_down_mini", M3_ON_SURFACE_VARIANT, "down", 10)
    check_on = _check("check_on", M3_ON_PRIMARY)
    check_tri = _dash("check_tri", M3_ON_PRIMARY)

    return f"""
/* ---------------------------------------------------------------- base -- */
QWidget {{
    background-color: {M3_SURFACE};
    color: {M3_ON_SURFACE};
}}
QMainWindow {{ background-color: {M3_SURFACE}; }}
QDialog {{ background-color: {M3_SURFACE_HIGH}; }}
QWidget:disabled {{ color: {M3_OUTLINE}; }}

QToolTip {{
    background-color: {M3_SURFACE_HIGHEST};
    color: {M3_ON_SURFACE};
    border: 1px solid {M3_OUTLINE_VARIANT};
    border-radius: {SHAPE_XS}px;
    padding: 6px 9px;
}}

/* -------------------------------------------------------------- cabecalho */
QFrame#appHeader {{
    background-color: {M3_SURFACE_CONTAINER};
    border: none;
}}
QLabel#brandName {{
    color: {M3_ON_SURFACE};
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 3px;
    background: transparent;
}}
QLabel#brandTag {{
    color: {M3_ON_SURFACE_VARIANT};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#chipLabel {{
    color: {M3_ON_SURFACE_VARIANT};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#chipValue {{
    color: {M3_ON_SURFACE};
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}}
/* chip do M3: canto 8dp, contorno fino */
QFrame#chip {{
    background-color: {M3_SURFACE_HIGH};
    border: 1px solid {M3_OUTLINE_MID};
    border-radius: {SHAPE_SM}px;
}}
QFrame#headerSep {{ background-color: {M3_OUTLINE_MID}; border: none; }}

/* ------------------------------------------------------------------ rodape */
QFrame#appFooter {{
    background-color: {M3_SURFACE_CONTAINER};
    border: none;
}}
QLabel#footerText {{
    color: {M3_ON_SURFACE_VARIANT}; font-size: 11px; background: transparent;
}}

/* --------------------------------------------------------- caixas/cartoes */
/* Card do M3: canto 12dp, superficie um degrau acima do fundo. */
QGroupBox {{
    background-color: {M3_SURFACE_LOW};
    border: 1px solid {M3_OUTLINE_MID};
    border-radius: {SHAPE_MD}px;
    margin-top: 13px;
    padding: 14px 11px 11px 11px;
    font-size: 10px;
    font-weight: 700;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 2px;
    padding: 2px 9px;
    color: {ACCENT};
    background-color: {ACCENT_BG};
    border: 1px solid {ACCENT}44;
    border-radius: {SHAPE_XS}px;
}}
QFrame#card, QFrame#plotFrame {{
    background-color: {M3_SURFACE_LOW};
    border: 1px solid {M3_OUTLINE_MID};
    border-radius: {SHAPE_MD}px;
}}
QLabel#cardTitle {{
    color: {M3_ON_SURFACE_VARIANT};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    background: transparent;
}}

/* ----------------------------------------------------------------- botoes */
/* Padrao = "filled tonal button" do M3: secondary-container, forma stadium. */
QPushButton {{
    background-color: {M3_SECONDARY_CONTAINER};
    color: {M3_ON_SECONDARY_CONTAINER};
    border: none;
    border-radius: {SHAPE_SM}px;
    padding: 5px 12px;
    min-height: 17px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: #48576a; }}
QPushButton:pressed {{ background-color: #303c49; }}
QPushButton:disabled {{ background-color: #1e2126; color: {M3_OUTLINE}; }}
/* "filled button": acao principal da tela */
QPushButton#primary {{
    background-color: {M3_PRIMARY};
    color: {M3_ON_PRIMARY};
    border: none;
    border-radius: {SHAPE_SM}px;
    padding: 7px 16px;
    font-weight: 700;
    font-size: 11px;
}}
QPushButton#primary:hover {{ background-color: {ACCENT_HI}; }}
QPushButton#primary:pressed {{ background-color: #8fb6ee; }}
QPushButton#primary:disabled {{ background-color: #1e2126; color: {M3_OUTLINE}; }}
/* "outlined button" em tom de erro: acao destrutiva */
QPushButton#danger {{
    background: transparent;
    color: {M3_ERROR};
    border: 1px solid {M3_OUTLINE_MID};
}}
QPushButton#danger:hover {{
    background-color: {M3_ERROR_CONTAINER}; border-color: {M3_ERROR};
}}
/* botao de rotulo curtissimo (uma letra): a forma stadium do M3 tem
   padding lateral generoso, que numa largura fixa comeria o texto */
QPushButton#compact {{
    padding: 6px 4px;
    border-radius: {SHAPE_SM}px;
    font-weight: 700;
}}

/* botao de alternancia (mostrar/ocultar painel): precisa ser visivel
   quando desligado -- se so aparecer depois de ligado, ninguem descobre
   que existe. Ligado, fica preenchido na cor primaria. */
QPushButton#toggle {{
    background-color: {M3_SURFACE_HIGH};
    color: {M3_ON_SURFACE_VARIANT};
    border: 1px solid {M3_OUTLINE_MID};
    border-radius: {SHAPE_SM}px;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 600;
}}
QPushButton#toggle:hover {{ color: {M3_ON_SURFACE}; border-color: {M3_PRIMARY}; }}
QPushButton#toggle:checked {{
    background-color: {M3_PRIMARY_CONTAINER};
    color: {M3_ON_PRIMARY_CONTAINER};
    border-color: {M3_PRIMARY};
}}

/* "text button": acao secundaria, sem peso visual */
QPushButton#ghost {{
    background: transparent;
    border: none;
    color: {M3_PRIMARY};
    padding: 6px 12px;
    font-weight: 600;
}}
QPushButton#ghost:hover {{ background-color: {M3_SURFACE_HIGH}; }}
QPushButton#ghost:checked {{
    background-color: {M3_PRIMARY_CONTAINER}; color: {M3_ON_PRIMARY_CONTAINER};
}}

/* ---------------------------------------------------------------- campos */
/* "outlined text field" do M3: contorno 1px, 2px em foco, canto 4dp. */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background-color: {M3_SURFACE_LOWEST};
    color: {M3_ON_SURFACE};
    border: 1px solid {M3_OUTLINE};
    border-radius: {SHAPE_SM}px;
    padding: 3px 8px;
    min-height: 17px;
    font-size: 11px;
    selection-background-color: {M3_PRIMARY_CONTAINER};
    selection-color: {M3_ON_PRIMARY_CONTAINER};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QComboBox:hover {{
    border-color: {M3_ON_SURFACE};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus, QComboBox:on {{
    border: 1px solid {ACCENT};
    background-color: #0c1615;
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background-color: #16181c; color: {M3_OUTLINE}; border-color: {M3_OUTLINE_VARIANT};
}}
QPlainTextEdit, QTextEdit {{ padding: 8px; }}

QComboBox {{ padding-right: 28px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right;
    width: 24px; border: none; background: transparent;
}}
QComboBox::down-arrow {{ image: url({seta_baixo}); width: 14px; height: 14px; }}
QComboBox::down-arrow:on, QComboBox::down-arrow:hover {{ image: url({seta_baixo_hi}); }}
/* menu suspenso = "menu" do M3 */
QComboBox QAbstractItemView {{
    background-color: {M3_SURFACE_HIGH};
    color: {M3_ON_SURFACE};
    border: 1px solid {M3_OUTLINE_VARIANT};
    border-radius: {SHAPE_XS}px;
    padding: 4px;
    outline: none;
    selection-background-color: {M3_SECONDARY_CONTAINER};
    selection-color: {M3_ON_SECONDARY_CONTAINER};
}}
QComboBox QAbstractItemView::item {{
    padding: 6px 9px; border-radius: {SHAPE_XS}px; min-height: 22px;
}}

QSpinBox::up-button, QDoubleSpinBox::up-button, QDateEdit::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button, QDateEdit::down-button {{
    background: transparent; border: none; width: 18px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QDateEdit::up-arrow {{
    image: url({seta_cima_mini}); width: 10px; height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QDateEdit::down-arrow {{
    image: url({seta_baixo_mini}); width: 10px; height: 10px;
}}

/* ------------------------------------------------------- checkbox / radio */
QCheckBox, QRadioButton {{ spacing: 9px; font-size: 12px; background: transparent; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 2px solid {M3_ON_SURFACE_VARIANT};
    border-radius: 2px;
    background-color: transparent;
}}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {M3_PRIMARY}; }}
QCheckBox::indicator:checked {{
    background-color: {M3_PRIMARY}; border-color: {M3_PRIMARY}; image: url({check_on});
}}
QCheckBox::indicator:indeterminate {{
    background-color: {M3_PRIMARY}; border-color: {M3_PRIMARY}; image: url({check_tri});
}}
QRadioButton::indicator:checked {{
    background-color: {M3_PRIMARY}; border-color: {M3_PRIMARY};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    border-color: {M3_OUTLINE_VARIANT};
}}

/* ------------------------------------------------------------------- abas */
/* "primary tabs" do M3: indicador de 3dp na cor primaria. */
QTabWidget::pane {{ border: none; background: transparent; top: -1px; }}
QTabBar {{ qproperty-drawBase: 0; background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {M3_ON_SURFACE_VARIANT};
    border: none;
    border-bottom: 3px solid transparent;
    padding: 8px 15px;
    margin-right: 2px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.4px;
}}
QTabBar::tab:hover {{ color: {M3_ON_SURFACE}; }}
QTabBar::tab:selected {{ color: {M3_PRIMARY}; border-bottom: 3px solid {M3_PRIMARY}; }}
QTabBar::tab:disabled {{ color: {M3_OUTLINE_VARIANT}; }}

QTabWidget#mainTabs > QTabBar::tab {{
    padding: 11px 22px; font-size: 13px; letter-spacing: 0.3px;
}}

/* --------------------------------------------------------------- tabelas */
QTableWidget, QTableView {{
    font-family: "Cascadia Mono", "Consolas", monospace;
    background-color: {M3_SURFACE_LOWEST};
    alternate-background-color: {FIELD_ALT};
    color: {M3_ON_SURFACE};
    gridline-color: {M3_OUTLINE_MID};
    border: 1px solid {M3_OUTLINE_MID};
    border-radius: {SHAPE_MD}px;
    font-size: 12px;
    selection-background-color: {M3_SECONDARY_CONTAINER};
    selection-color: {M3_ON_SECONDARY_CONTAINER};
    outline: none;
}}
QTableWidget::item, QTableView::item {{ padding: 4px 6px; border: none; }}
QHeaderView {{ background: transparent; border: none; }}
QHeaderView::section {{
    font-family: "Segoe UI", sans-serif;
    background-color: {M3_SURFACE_CONTAINER};
    color: {M3_ON_SURFACE_VARIANT};
    padding: 7px 8px;
    border: none;
    border-right: 1px solid {M3_OUTLINE_MID};
    border-bottom: 1px solid {M3_OUTLINE_MID};
    font-size: 11px;
    font-weight: 700;
}}
QHeaderView::section:first {{ border-top-left-radius: 11px; }}
QHeaderView::section:last {{ border-right: none; border-top-right-radius: 11px; }}
QHeaderView::section:vertical {{ border-radius: 0px; }}
QTableCornerButton::section {{ background-color: {M3_SURFACE_CONTAINER}; border: none; }}

/* ---------------------------------------------------------------- listas */
QListWidget, QTreeWidget {{
    background-color: {M3_SURFACE_LOWEST};
    color: {M3_ON_SURFACE};
    border: 1px solid {M3_OUTLINE_MID};
    border-radius: {SHAPE_SM}px;
    padding: 4px;
    font-size: 12px;
    outline: none;
}}
QListWidget::item, QTreeWidget::item {{
    padding: 6px 8px; border-radius: {SHAPE_XS}px; min-height: 20px;
}}
QListWidget::item:hover {{ background-color: {M3_SURFACE_HIGH}; }}
QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {M3_SECONDARY_CONTAINER}; color: {M3_ON_SECONDARY_CONTAINER};
}}
QListWidget::indicator {{
    width: 15px; height: 15px; border: 2px solid {M3_ON_SURFACE_VARIANT};
    border-radius: 2px; background-color: transparent;
}}
QListWidget::indicator:checked {{
    background-color: {M3_PRIMARY}; border-color: {M3_PRIMARY}; image: url({check_on});
}}

/* -------------------------------------------------------------- rolagem */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{
    background: {M3_SURFACE_LOWEST}; width: 12px; margin: 0;
    border-left: 1px solid {M3_OUTLINE_VARIANT};
}}
QScrollBar::handle:vertical {{
    background: {M3_OUTLINE_MID}; border-radius: 4px; min-height: 36px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{ background: {M3_OUTLINE}; }}
QScrollBar:horizontal {{
    background: {M3_SURFACE_LOWEST}; height: 12px; margin: 0;
    border-top: 1px solid {M3_OUTLINE_VARIANT};
}}
QScrollBar::handle:horizontal {{
    background: {M3_OUTLINE_MID}; border-radius: 4px; min-width: 36px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{ background: {M3_OUTLINE}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ------------------------------------------------------------- divisores */
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}
QSplitter::handle:hover {{ background: {M3_PRIMARY_CONTAINER}; }}

/* ------------------------------------------------------------ formularios */
QLabel {{ background: transparent; font-size: 12px; }}

/* --------------------------------------------------------- caixa de aviso */
QMessageBox, QInputDialog {{ background-color: {M3_SURFACE_HIGH}; }}
QMessageBox QLabel, QInputDialog QLabel {{ color: {M3_ON_SURFACE}; font-size: 12px; }}

/* ------------------------------------------------------------ badges */
QLabel#badge {{
    border-radius: {SHAPE_XS}px;
    padding: 2px 7px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.4px;
}}

/* ------------------------------------- rotulo miudo acima do campo */
QLabel#microLabel {{
    color: {TEXT_DIM};
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.8px;
    background: transparent;
}}

/* ------------------------------------------------ secao recolhivel */
QFrame#secao {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {SHAPE_MD}px;
}}
QPushButton#secaoHeader {{
    background-color: {SURFACE_2};
    color: {TEXT_MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    border-top-left-radius: {SHAPE_MD}px;
    border-top-right-radius: {SHAPE_MD}px;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
    padding: 7px 11px;
    text-align: left;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.9px;
}}
QPushButton#secaoHeader:hover {{ color: {TEXT}; background-color: {SURFACE_3}; }}
QPushButton#secaoHeader:checked {{ color: {ACCENT}; }}

/* ------------------------------------------------ faixa de veredito geral */
QFrame#verdictBar {{ border-radius: {SHAPE_MD}px; border: 1px solid {M3_OUTLINE_MID}; }}
QLabel#verdictText {{ font-size: 14px; font-weight: 700; background: transparent; }}
QLabel#verdictSub {{ font-size: 11px; background: transparent; }}
"""


def apply_theme(app) -> None:
    """Aplica fonte, icone e folha de estilo a aplicacao inteira."""
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_ORG)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    app.setFont(ui_font(10))
    app.setStyle("Fusion")   # base previsivel para o QSS em cima
    app.setStyleSheet(build_qss())
