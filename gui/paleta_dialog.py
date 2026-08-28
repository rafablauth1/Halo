"""
gui/paleta_dialog.py

Editor da paleta: troca as cores da interface e grava a escolha.

As cores ficam em `dados/aparencia.json`. O arquivo so guarda o que foi
MUDADO -- as demais continuam vindo do tema padrao, entao acrescentar
uma cor nova ao programa nao invalida a personalizacao de ninguem.

O que NAO entra aqui, de proposito:
  * as cores do grafico do laudo. Elas foram conferidas contra o
    relatorio impresso e mudar por engano geraria um PDF diferente do
    que ja foi emitido;
  * as cores de estado (aprovado/reprovado). Verde e vermelho tem
    significado normativo na leitura do resultado; deixar o operador
    trocar por duas cores parecidas seria um convite a erro de leitura.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QDialog, QDialogButtonBox, QFrame,
                                QHBoxLayout, QLabel, QMessageBox, QPushButton,
                                QScrollArea, QVBoxLayout, QWidget)

from gui import theme

ARQUIVO = Path(__file__).parent.parent / "dados" / "aparencia.json"

# (atributo em theme, rotulo, explicacao do papel da cor)
EDITAVEIS = [
    ("ACCENT",     "Cor de ação",        "Seleção, foco, botão principal e aba ativa."),
    ("BG",         "Fundo da janela",    "A superfície mais baixa, atrás de tudo."),
    ("SURFACE",    "Cartões",            "Fundo das caixas e painéis."),
    ("SURFACE_2",  "Botões e campos",    "Um degrau acima dos cartões."),
    ("SURFACE_3",  "Realce ao passar",   "Fundo do item sob o cursor."),
    ("FIELD",      "Campos e tabelas",   "Fundo de entrada de texto e de tabela."),
    ("BORDER",     "Linhas de estrutura", "Borda de cartão, moldura e grade de tabela."),
    ("BORDER_2",   "Contorno de campo",  "Borda de caixa de texto e combo."),
    ("TEXT",       "Texto principal",    "Cor do texto normal."),
    ("TEXT_MUTED", "Texto secundário",   "Legendas e informação de apoio."),
    ("TEXT_DIM",   "Texto apagado",      "Rótulos miúdos e itens desabilitados."),
    ("GLOW",       "Cor da marca",       "O halo do logotipo."),
]

PRESETS = {
    "Grafite (padrão)": {},
    "Azul-ardósia": {"BG": "#0d1117", "SURFACE": "#151b23", "SURFACE_2": "#1c242e",
                      "SURFACE_3": "#243040", "FIELD": "#0f151c",
                      "BORDER": "#2a3441", "BORDER_2": "#3d4a5a",
                      "ACCENT": "#4d9fff"},
    "Verde-bancada": {"BG": "#101512", "SURFACE": "#161c18", "SURFACE_2": "#1d251f",
                       "SURFACE_3": "#26302a", "FIELD": "#0c100d",
                       "BORDER": "#2b352e", "BORDER_2": "#3d4a41",
                       "ACCENT": "#5fc98a"},
    "Âmbar-instrumento": {"BG": "#141210", "SURFACE": "#1c1916", "SURFACE_2": "#24201c",
                           "SURFACE_3": "#2f2a24", "FIELD": "#100e0c",
                           "BORDER": "#39332b", "BORDER_2": "#4d453a",
                           "ACCENT": "#e0a33c"},
}


# ---------------------------------------------------------------- persistencia
def carregar() -> dict:
    try:
        return json.loads(ARQUIVO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def salvar(cores: dict) -> None:
    ARQUIVO.parent.mkdir(parents=True, exist_ok=True)
    ARQUIVO.write_text(json.dumps(cores, indent=2, ensure_ascii=False),
                        encoding="utf-8")


def aplicar_salvas(app) -> int:
    """Sobrescreve no modulo `theme` as cores gravadas e reconstroi o QSS.

    Chamado no arranque, ANTES da janela existir. Devolve quantas cores
    foram trocadas."""
    cores = carregar()
    n = 0
    for nome, valor in cores.items():
        if hasattr(theme, nome) and isinstance(getattr(theme, nome), str):
            setattr(theme, nome, valor)
            n += 1
    if n:
        theme.sincronizar_apelidos()
        app.setStyleSheet(theme.build_qss())
    return n


# ------------------------------------------------------------------- interface
class _LinhaCor(QWidget):
    """Uma cor: amostra clicavel, nome, papel e o codigo hexadecimal."""

    def __init__(self, nome: str, rotulo: str, ajuda: str, valor: str, parent=None):
        super().__init__(parent)
        self.nome = nome
        self.valor = valor
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.amostra = QFrame()
        self.amostra.setFixedSize(34, 24)
        self.amostra.setCursor(Qt.PointingHandCursor)
        self.amostra.mousePressEvent = lambda _e: self.escolher()
        lay.addWidget(self.amostra)

        col = QVBoxLayout()
        col.setSpacing(0)
        t = QLabel(rotulo)
        t.setStyleSheet(f"color:{theme.TEXT}; font-size:12px; font-weight:600;")
        d = QLabel(ajuda)
        d.setStyleSheet(theme.CSS_DIM)
        d.setWordWrap(True)
        col.addWidget(t)
        col.addWidget(d)
        lay.addLayout(col, 1)

        self.hexa = QLabel(valor.upper())
        self.hexa.setFont(theme.mono_font(9))
        self.hexa.setStyleSheet(theme.CSS_MUTED)
        lay.addWidget(self.hexa)

        b = QPushButton("Escolher…")
        b.clicked.connect(self.escolher)
        lay.addWidget(b)
        self._pintar()

    def _pintar(self):
        self.amostra.setStyleSheet(
            f"background-color:{self.valor}; border:1px solid {theme.BORDER_2}; "
            f"border-radius:4px;")
        self.hexa.setText(self.valor.upper())

    def escolher(self):
        c = QColorDialog.getColor(QColor(self.valor), self,
                                   "Escolha a cor", QColorDialog.DontUseNativeDialog)
        if c.isValid():
            self.valor = c.name()
            self._pintar()

    def set_valor(self, v: str):
        self.valor = v
        self._pintar()


class PaletaDialog(QDialog):
    """Editor da paleta. Aplica sem fechar, para dar para comparar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aparência e cores")
        self.resize(680, 620)
        self._original = {n: getattr(theme, n) for n, _, _ in EDITAVEIS}

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        cab = QLabel(
            "As cores do <b>gráfico do laudo</b> e as de <b>aprovado/reprovado</b> "
            "não entram aqui: o gráfico foi conferido contra o relatório impresso, "
            "e verde/vermelho têm significado na leitura do resultado.")
        cab.setWordWrap(True)
        cab.setStyleSheet(theme.CSS_MUTED)
        lay.addWidget(cab)

        linha_preset = QHBoxLayout()
        linha_preset.addWidget(QLabel("Conjuntos prontos:"))
        for nome in PRESETS:
            b = QPushButton(nome)
            b.clicked.connect(lambda _=False, k=nome: self._usar_preset(k))
            linha_preset.addWidget(b)
        linha_preset.addStretch(1)
        lay.addLayout(linha_preset)

        interior = QWidget()
        col = QVBoxLayout(interior)
        col.setSpacing(9)
        self.linhas: list[_LinhaCor] = []
        salvas = carregar()
        for nome, rotulo, ajuda in EDITAVEIS:
            ln = _LinhaCor(nome, rotulo, ajuda,
                            salvas.get(nome, getattr(theme, nome)))
            self.linhas.append(ln)
            col.addWidget(ln)
        col.addStretch(1)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(interior)
        lay.addWidget(area, 1)

        botoes = QDialogButtonBox()
        b_aplicar = botoes.addButton("Aplicar", QDialogButtonBox.ApplyRole)
        b_aplicar.clicked.connect(self._aplicar)
        b_padrao = botoes.addButton("Restaurar padrão", QDialogButtonBox.ResetRole)
        b_padrao.clicked.connect(self._restaurar)
        botoes.addButton(QDialogButtonBox.Save).clicked.connect(self._salvar_e_sair)
        botoes.addButton(QDialogButtonBox.Cancel).clicked.connect(self._cancelar)
        lay.addWidget(botoes)

    # ---- acoes ----
    def _coletar(self) -> dict:
        return {ln.nome: ln.valor for ln in self.linhas}

    def _usar_preset(self, nome: str):
        preset = PRESETS.get(nome, {})
        for ln in self.linhas:
            ln.set_valor(preset.get(ln.nome, theme.PADRAO.get(ln.nome, ln.valor)))
        self._aplicar()

    def _aplicar(self):
        from PySide6.QtWidgets import QApplication
        for nome, valor in self._coletar().items():
            setattr(theme, nome, valor)
        theme.sincronizar_apelidos()
        QApplication.instance().setStyleSheet(theme.build_qss())

    def _restaurar(self):
        for ln in self.linhas:
            ln.set_valor(theme.PADRAO.get(ln.nome, ln.valor))
        self._aplicar()

    def _salvar_e_sair(self):
        cores = {n: v for n, v in self._coletar().items()
                 if v.lower() != theme.PADRAO.get(n, "").lower()}
        salvar(cores)
        self._aplicar()
        QMessageBox.information(
            self, "Aparência salva",
            f"{len(cores)} cor(es) personalizada(s) gravada(s) em\n{ARQUIVO}\n\n"
            "Algumas partes só assumem a cor nova depois de reabrir o programa.")
        self.accept()

    def _cancelar(self):
        from PySide6.QtWidgets import QApplication
        for nome, valor in self._original.items():
            setattr(theme, nome, valor)
        theme.sincronizar_apelidos()
        QApplication.instance().setStyleSheet(theme.build_qss())
        self.reject()
