"""
gui/widgets.py

Pecas de interface reaproveitaveis do HALO: o cabecalho da janela, os
chips de estado, o cartao com titulo e a faixa de veredito. Existem
para que todas as telas tenham o mesmo espacamento, o mesmo tamanho de
fonte e o mesmo raio de canto -- sem repetir estilo solto por ai.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (QAbstractSpinBox, QComboBox, QFrame, QHBoxLayout,
                                QLabel, QLineEdit, QListWidget, QListWidgetItem,
                                QScrollArea, QSizePolicy, QSlider,
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


class Badge(QLabel):
    """Etiqueta colorida compacta.

    Serve para identificar coisa a coisa num relance -- detector, banda
    CISPR, origem do dado. A cor vem de `theme.CHIPS` e e a MESMA em toda
    a interface: o que e âmbar no chip e âmbar na tabela e no grafico.
    """

    def __init__(self, texto: str, cor: str = "cinza", parent=None):
        super().__init__(texto, parent)
        self.setObjectName("badge")
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.set_cor(cor)

    def set_cor(self, cor: str):
        frente, fundo = theme.cor_chip(cor)
        self.setStyleSheet(
            f"QLabel#badge {{ color:{frente}; background-color:{fundo}; "
            f"border:1px solid {frente}55; border-radius:3px; "
            f"padding:2px 7px; font-size:10px; font-weight:700; }}")


class Ladrilho(QLabel):
    """Quadrado colorido com uma letra -- o marcador de identidade que as
    ferramentas de projeto usam na frente de cada item da lista. Aqui
    identifica o tipo de ensaio (Conduzida, Loop, Irradiada) sem precisar
    ler o nome inteiro."""

    def __init__(self, letra: str, cor: str = "teal", lado: int = 26, parent=None):
        super().__init__(letra[:1].upper(), parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(lado, lado)
        self.set_cor(cor)

    def set_cor(self, cor: str):
        frente, fundo = theme.cor_chip(cor)
        self.setStyleSheet(
            f"color:{frente}; background-color:{fundo}; border:1px solid {frente}66; "
            f"border-radius:6px; font-size:13px; font-weight:800;")


class CampoRotulado(QWidget):
    """Campo com o rótulo MIÚDO EM CIMA, não ao lado.

    É o arranjo das ferramentas de projeto (Figma, Sketch, editores de
    áudio): o nome do parâmetro em versalete pequeno e o valor logo
    abaixo. Ganha-se densidade — várias propriedades cabem lado a lado
    numa grade — e some a coluna de rótulos alinhados que come largura
    num formulário tradicional.
    """

    def __init__(self, rotulo: str, campo: QWidget, dica: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.rotulo = QLabel(rotulo.upper())
        self.rotulo.setObjectName("microLabel")
        self.campo = campo
        lay.addWidget(self.rotulo)
        lay.addWidget(campo)
        if dica:
            self.setToolTip(dica)
            campo.setToolTip(dica)


class GradeCampos(QWidget):
    """Grade de `CampoRotulado`, N por linha.

    O padrão de 2 a 4 colunas é o que faz uma tela de configuração caber
    sem virar uma lista vertical interminável."""

    def __init__(self, colunas: int = 2, parent=None):
        super().__init__(parent)
        self._grade = QGridLayout(self)
        self._grade.setContentsMargins(0, 0, 0, 0)
        self._grade.setHorizontalSpacing(10)
        self._grade.setVerticalSpacing(9)
        self._colunas = colunas
        self._n = 0

    def add(self, rotulo: str, campo: QWidget, dica: str = "", span: int = 1):
        item = CampoRotulado(rotulo, campo, dica)
        linha, col = divmod(self._n, self._colunas)
        if span > 1 and col + span > self._colunas:      # não cabe: pula linha
            self._n += self._colunas - col
            linha, col = divmod(self._n, self._colunas)
        self._grade.addWidget(item, linha, col, 1, span)
        self._n += span
        return item

    def add_linha_cheia(self, w: QWidget):
        """Widget ocupando a linha inteira (botões, avisos)."""
        if self._n % self._colunas:
            self._n += self._colunas - (self._n % self._colunas)
        linha = self._n // self._colunas
        self._grade.addWidget(w, linha, 0, 1, self._colunas)
        self._n += self._colunas
        return w


class Secao(QFrame):
    """Cartão com cabeçalho clicável que recolhe o conteúdo.

    Numa tela com muitos grupos, poder fechar os que não interessam vale
    mais que qualquer ajuste de cor: o operador esconde o que já
    configurou e fica só com o que está mexendo.
    """

    def __init__(self, titulo: str, aberta: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("secao")
        externo = QVBoxLayout(self)
        externo.setContentsMargins(0, 0, 0, 0)
        externo.setSpacing(0)

        self._botao = QPushButton(f"▾  {titulo.upper()}")
        self._botao.setObjectName("secaoHeader")
        self._botao.setCheckable(True)
        self._botao.setChecked(aberta)
        self._botao.setCursor(Qt.PointingHandCursor)
        self._botao.toggled.connect(self._alternar)
        externo.addWidget(self._botao)

        self._corpo = QWidget()
        self.body = QVBoxLayout(self._corpo)
        self.body.setContentsMargins(12, 10, 12, 12)
        self.body.setSpacing(9)
        externo.addWidget(self._corpo)

        self._titulo = titulo
        self._corpo.setVisible(aberta)

    def _alternar(self, aberta: bool):
        self._corpo.setVisible(aberta)
        self._botao.setText(f"{'▾' if aberta else '▸'}  {self._titulo.upper()}")

    def add(self, w: QWidget, stretch: int = 0):
        self.body.addWidget(w, stretch)
        return w

    def add_layout(self, l):
        self.body.addLayout(l)
        return l


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


class ListaSelecao(QWidget):
    """Lista sempre visível que se comporta como um QComboBox.

    Numa tela de configuração de instrumento, esconder 31 modelos de
    receiver dentro de um menu suspenso obriga o operador a abrir a lista
    só para saber o que existe. Aqui os itens ficam à vista, com um campo
    de filtro em cima.

    Expõe a mesma API do QComboBox usada pelo resto do código
    (`addItem`, `clear`, `currentIndex`, `setCurrentIndex`, `findData`,
    `itemData`, `currentData`, `currentIndexChanged`), para poder ser
    trocada no lugar de um combo sem reescrever quem o usa.
    """

    currentIndexChanged = Signal(int)

    def __init__(self, com_filtro: bool = True, altura_min: int = 150, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self._filtro = None
        if com_filtro:
            self._filtro = QLineEdit()
            self._filtro.setPlaceholderText("filtrar…")
            self._filtro.setClearButtonEnabled(True)
            self._filtro.textChanged.connect(self._aplicar_filtro)
            lay.addWidget(self._filtro)

        self._lista = QListWidget()
        self._lista.setMinimumHeight(altura_min)
        # o minimo tem que valer para o widget inteiro, senao o layout
        # espreme a lista ate sobrar uma linha so
        self.setMinimumHeight(altura_min + (34 if com_filtro else 0))
        self._lista.setTextElideMode(Qt.ElideRight)
        self._lista.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._lista.currentRowChanged.connect(self._on_row)
        lay.addWidget(self._lista, 1)

    # ---- API compatível com QComboBox ----
    def addItem(self, texto: str, dado=None):
        item = QListWidgetItem(texto)
        item.setData(Qt.UserRole, dado)
        item.setToolTip(texto)
        self._lista.addItem(item)

    def clear(self):
        self._lista.clear()

    def count(self) -> int:
        return self._lista.count()

    def currentIndex(self) -> int:
        return self._lista.currentRow()

    def setCurrentIndex(self, i: int):
        self._lista.setCurrentRow(i)
        if 0 <= i < self._lista.count():
            self._lista.scrollToItem(self._lista.item(i))

    def itemData(self, i: int):
        item = self._lista.item(i)
        return item.data(Qt.UserRole) if item else None

    def currentData(self):
        return self.itemData(self.currentIndex())

    def currentText(self) -> str:
        item = self._lista.currentItem()
        return item.text() if item else ""

    def findData(self, dado) -> int:
        for i in range(self._lista.count()):
            if self.itemData(i) == dado:
                return i
        return -1

    def blockSignals(self, on: bool):
        self._lista.blockSignals(on)
        return super().blockSignals(on)

    # ---- interno ----
    def _on_row(self, linha: int):
        self.currentIndexChanged.emit(linha)

    def _aplicar_filtro(self, texto: str):
        alvo = texto.strip().lower()
        for i in range(self._lista.count()):
            item = self._lista.item(i)
            item.setHidden(bool(alvo) and alvo not in item.text().lower())


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
