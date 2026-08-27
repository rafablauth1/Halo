"""
gui/widgets.py

Pecas de interface reaproveitaveis do HALO: o cabecalho da janela, os
chips de estado, o cartao com titulo e a faixa de veredito. Existem
para que todas as telas tenham o mesmo espacamento, o mesmo tamanho de
fonte e o mesmo raio de canto -- sem repetir estilo solto por ai.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QAbstractSpinBox, QComboBox, QFrame, QHBoxLayout,
                                QLabel, QScrollArea, QSizePolicy, QSlider,
                                QTableWidget, QVBoxLayout, QWidget)

from gui import theme


class Chip(QFrame):
    """Indicador compacto do cabecalho: um rotulo miudo em cima e o
    valor em destaque embaixo (ex.: NORMA / cispr15_mains_terminals)."""

    def __init__(self, rotulo: str, valor: str = "—", largura_max: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("chip")
        self._largura_max = largura_max
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(1)
        self._rotulo = QLabel(rotulo.upper())
        self._rotulo.setObjectName("chipLabel")
        self._valor = QLabel(valor)
        self._valor.setObjectName("chipValue")
        if largura_max:
            self._valor.setMaximumWidth(largura_max)
        lay.addWidget(self._rotulo)
        lay.addWidget(self._valor)

    def set_valor(self, texto: str, cor: str | None = None):
        # Texto comprido vira "...": o chip nunca estica o cabecalho.
        if self._largura_max:
            fm = QFontMetrics(self._valor.font())
            self._valor.setToolTip(texto if fm.horizontalAdvance(texto) > self._largura_max else "")
            texto = fm.elidedText(texto, Qt.ElideRight, self._largura_max)
        self._valor.setText(texto)
        self._valor.setStyleSheet(
            f"color:{cor}; font-size:12px; font-weight:600; background:transparent;"
            if cor else "")


class AppHeader(QFrame):
    """Barra superior: logotipo + nome + chips de estado a direita."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appHeader")
        self.setFixedHeight(64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 8, 18, 8)
        lay.setSpacing(14)

        logo = QLabel()
        logo.setPixmap(theme.logo_pixmap(38))
        logo.setFixedSize(38, 38)
        lay.addWidget(logo)

        marca = QVBoxLayout()
        marca.setSpacing(0)
        marca.setContentsMargins(0, 2, 0, 2)
        nome = QLabel(theme.APP_NAME)
        nome.setObjectName("brandName")
        tag = QLabel(f"{theme.APP_TAGLINE}  ·  {theme.APP_ORG}")
        tag.setObjectName("brandTag")
        marca.addWidget(nome)
        marca.addWidget(tag)
        lay.addLayout(marca)

        lay.addSpacing(8)
        sep = QFrame()
        sep.setObjectName("headerSep")
        sep.setFixedWidth(1)
        sep.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        lay.addWidget(sep)

        lay.addStretch(1)

        self.chip_norma = Chip("Norma", "—", largura_max=250)
        self.chip_traces = Chip("Traces", "nenhum", largura_max=140)
        self.chip_veredito = Chip("Veredito", "—", largura_max=160)
        for c in (self.chip_norma, self.chip_traces, self.chip_veredito):
            lay.addWidget(c)


class Card(QFrame):
    """Painel com titulo discreto. `body` e o layout onde vai o conteudo."""

    def __init__(self, titulo: str = "", parent=None, espacamento: int = 8):
        super().__init__(parent)
        self.setObjectName("card")
        externo = QVBoxLayout(self)
        externo.setContentsMargins(13, 11, 13, 13)
        externo.setSpacing(9)
        if titulo:
            cab = QHBoxLayout()
            cab.setContentsMargins(0, 0, 0, 0)
            cab.setSpacing(8)
            lbl = QLabel(titulo.upper())
            lbl.setObjectName("cardTitle")
            cab.addWidget(lbl)
            cab.addStretch(1)
            self.header = cab
            externo.addLayout(cab)
        else:
            self.header = None
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(espacamento)
        externo.addLayout(self.body, 1)

    def add(self, w: QWidget, stretch: int = 0):
        self.body.addWidget(w, stretch)
        return w


class VerdictBar(QFrame):
    """Faixa larga com o resultado geral do ensaio, colorida pelo estado."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("verdictBar")
        self.setFixedHeight(52)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(14)

        self._marca = QFrame()
        self._marca.setFixedWidth(4)
        self._marca.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        lay.addWidget(self._marca)

        col = QVBoxLayout()
        col.setSpacing(1)
        self._titulo = QLabel("Sem dados")
        self._titulo.setObjectName("verdictText")
        self._sub = QLabel("Importe um trace ou carregue o exemplo sintético.")
        self._sub.setObjectName("verdictSub")
        col.addWidget(self._titulo)
        col.addWidget(self._sub)
        lay.addLayout(col, 1)
        self.set_estado("neutro", "Sem dados",
                        "Importe um trace ou carregue o exemplo sintético.")

    def set_estado(self, estado: str, titulo: str, subtitulo: str = ""):
        """estado: 'ok' | 'fail' | 'warn' | 'neutro'."""
        cores = {
            "ok": (theme.OK, theme.OK_BG),
            "fail": (theme.FAIL, theme.FAIL_BG),
            "warn": (theme.WARN, theme.WARN_BG),
            "neutro": (theme.TEXT_DIM, theme.SURFACE),
        }
        cor, fundo = cores.get(estado, cores["neutro"])
        self.setStyleSheet(
            f"QFrame#verdictBar {{ background-color:{fundo}; "
            f"border:1px solid {cor}44; border-radius:9px; }}")
        self._marca.setStyleSheet(f"background-color:{cor}; border-radius:2px;")
        self._titulo.setStyleSheet(
            f"color:{cor}; font-size:14px; font-weight:700; background:transparent;")
        self._sub.setStyleSheet(
            f"color:{theme.TEXT_MUTED}; font-size:11px; background:transparent;")
        self._titulo.setText(titulo)
        self._sub.setText(subtitulo)


class RodaSoComFoco(QObject):
    """Impede que combo/spin/slider "roubem" a roda do mouse.

    Dentro de uma area rolavel, passar a roda por cima de um QComboBox ou
    QSpinBox troca o VALOR do campo em vez de rolar a pagina -- da para
    mudar a norma ou um limite sem perceber, so rolando a tela. Com este
    filtro o campo so responde a roda depois de receber o foco (clique);
    fora disso o evento sobe para a area de rolagem.
    """

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and not obj.hasFocus():
            event.ignore()
            return True
        return False


def desarmar_roda(raiz: QWidget) -> int:
    """Aplica `RodaSoComFoco` a todo combo/spin/slider abaixo de `raiz`.
    Devolve quantos widgets foram protegidos.

    Aproveita a varredura para corrigir outro incomodo: um QSpinBox criado
    ja no valor minimo nunca escreve esse valor no campo -- so a chamada a
    setValue() dispara a escrita, e ficar no minimo nao e uma mudanca.
    Resultado: o campo aparece VAZIO em vez de mostrar "0" (era o caso de
    "Placa / board" na aba do receiver). `interpretText()` forca a escrita.
    """
    if not hasattr(raiz, "_filtro_roda"):
        raiz._filtro_roda = RodaSoComFoco(raiz)
    filtro = raiz._filtro_roda
    n = 0
    for w in raiz.findChildren(QWidget):
        if isinstance(w, (QComboBox, QAbstractSpinBox, QSlider)):
            w.setFocusPolicy(Qt.StrongFocus)   # so recebe foco por clique/Tab
            w.installEventFilter(filtro)
            n += 1
        if isinstance(w, QAbstractSpinBox) and not w.text():
            w.interpretText()
    return n


class FitTable(QTableWidget):
    """Tabela que reavalia a largura das colunas sempre que muda de
    tamanho. Sem isso, a largura e calculada uma vez -- quando o widget
    ainda nem sabe o proprio tamanho -- e a tabela fica curta, sobrando
    um vazio a direita."""

    def __init__(self, parent=None):
        super().__init__(0, 0, parent)
        self._ajuste = None

    def set_ajuste(self, fn):
        """`fn(tabela)` e chamada a cada redimensionamento."""
        self._ajuste = fn

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._ajuste is not None and self.columnCount():
            self._ajuste(self)


class AppFooter(QFrame):
    """Rodape com uma mensagem de estado a esquerda e a versao a direita."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appFooter")
        self.setFixedHeight(28)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 0, 18, 0)
        self._msg = QLabel("Pronto.")
        self._msg.setObjectName("footerText")
        direita = QLabel(f"{theme.APP_NAME} {theme.APP_VERSION}  ·  {theme.APP_ORG}")
        direita.setObjectName("footerText")
        lay.addWidget(self._msg, 1)
        lay.addWidget(direita, 0, Qt.AlignRight)

    def set_mensagem(self, texto: str, cor: str | None = None):
        self._msg.setText(texto)
        self._msg.setStyleSheet(
            f"color:{cor}; font-size:11px; background:transparent;" if cor else "")


def area_rolavel(conteudo: QWidget, largura_min: int = 0,
                  largura_max: int = 0) -> QScrollArea:
    """QScrollArea com o comportamento de rolagem acertado:

    * passo da roda em ~3 linhas de uma vez (o padrao do Qt e 1 px por
      "tick" em alguns temas, o que faz a tela parecer travada);
    * sem moldura propria, para nao duplicar a borda dos cartoes;
    * barra horizontal so quando faz falta -- nada fica invisivel;
    * combos e spins la dentro nao roubam mais a roda.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    area.setWidget(conteudo)
    area.verticalScrollBar().setSingleStep(24)
    area.verticalScrollBar().setPageStep(240)
    area.horizontalScrollBar().setSingleStep(24)
    if largura_min:
        area.setMinimumWidth(largura_min)
    if largura_max:
        area.setMaximumWidth(largura_max)
    desarmar_roda(conteudo)
    return area


def separador(horizontal: bool = True) -> QFrame:
    f = QFrame()
    f.setObjectName("headerSep")
    if horizontal:
        f.setFixedHeight(1)
    else:
        f.setFixedWidth(1)
    return f
