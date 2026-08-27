"""
gui/incerteza_dialog.py

Editor da tabela de incertezas de medicao de uma norma, no mesmo formato
da secao "Incertezas de Medicao" do relatorio de ensaio: item da norma,
mensurando, faixa, incerteza expandida e fator de abrangencia.

A coluna "U CISPR 16-4-2" e o valor de referencia da norma, usado pela
regra de decisao homonima. Deixada em branco (zero), a regra vira banda
de guarda completa -- mais conservadora que a norma manda.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                QPushButton, QTableWidget, QTableWidgetItem,
                                QComboBox, QMessageBox, QHeaderView, QTextEdit,
                                QFormLayout)
from PySide6.QtCore import Qt

from gui import theme

from core.incerteza import (ConfiguracaoIncerteza, FaixaIncerteza, REGRAS,
                             salvar, preset_lab)

COLS = ["Item da norma", "Mensurando", "Freq. inicial (Hz)", "Freq. final (Hz)",
        "U laboratorio (dB)", "Fator k", "U CISPR 16-4-2 (dB)"]


class IncertezaDialog(QDialog):
    def __init__(self, cfg: ConfiguracaoIncerteza, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle(f"Incertezas de medicao — {cfg.metodo_id}")
        self.resize(920, 480)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.regra_combo = QComboBox()
        for chave, desc in REGRAS.items():
            self.regra_combo.addItem(desc, chave)
        idx = self.regra_combo.findData(cfg.regra)
        self.regra_combo.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("Regra de decisao", self.regra_combo)
        layout.addLayout(form)

        layout.addWidget(QLabel(
            "Uma linha por faixa, como na tabela 'Incertezas de Medicao' do relatorio. "
            "A incerteza do laboratorio e a EXPANDIDA, no fator k declarado."))

        self.table = QTableWidget(0, len(COLS))
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table, 1)
        self._popular()

        btns = QHBoxLayout()
        add = QPushButton("Adicionar faixa")
        add.clicked.connect(self._add)
        rem = QPushButton("Remover faixa")
        rem.clicked.connect(self._del)
        preset = QPushButton("Restaurar tabela do relatorio laboratório")
        preset.clicked.connect(self._preset)
        btns.addWidget(add)
        btns.addWidget(rem)
        btns.addWidget(preset)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.obs = QTextEdit(cfg.observacoes)
        self.obs.setMaximumHeight(52)
        layout.addWidget(QLabel("Observacoes:"))
        layout.addWidget(self.obs)

        self.aviso = QLabel("")
        self.aviso.setWordWrap(True)
        self.aviso.setStyleSheet(theme.CSS_WARN)
        layout.addWidget(self.aviso)
        self._atualizar_avisos()
        self.regra_combo.currentIndexChanged.connect(self._atualizar_avisos)

        fim = QHBoxLayout()
        fim.addStretch(1)
        cancelar = QPushButton("Cancelar")
        cancelar.clicked.connect(self.reject)
        salvar_btn = QPushButton("Salvar")
        salvar_btn.clicked.connect(self._salvar)
        fim.addWidget(cancelar)
        fim.addWidget(salvar_btn)
        layout.addLayout(fim)

    # ---------------- tabela ----------------
    def _popular(self):
        self.table.setRowCount(0)
        for f in self.cfg.faixas:
            self._add_linha(f)

    def _add_linha(self, f: FaixaIncerteza):
        r = self.table.rowCount()
        self.table.insertRow(r)
        valores = [f.item_norma, f.mensurando, f"{f.freq_min_hz:g}", f"{f.freq_max_hz:g}",
                   f"{f.u_lab_db:g}", f"{f.fator_k:g}", f"{f.u_cispr_db:g}"]
        for c, v in enumerate(valores):
            item = QTableWidgetItem(v)
            if c >= 2:
                item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(r, c, item)

    def _add(self):
        self._add_linha(FaixaIncerteza(0, 0, 0, 2.0, 0))

    def _del(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def _preset(self):
        base = preset_lab(self.cfg.metodo_id)
        if not base.faixas:
            QMessageBox.information(
                self, "Sem preset",
                f"Nao ha tabela de incerteza de referencia para '{self.cfg.metodo_id}'.\n"
                "Este preset so existe para as normas transcritas do relatorio do laboratório.")
            return
        self.cfg.faixas = base.faixas
        self._popular()
        self._atualizar_avisos()

    def _ler(self) -> list[FaixaIncerteza]:
        faixas = []
        for r in range(self.table.rowCount()):
            def txt(c: int) -> str:
                item = self.table.item(r, c)
                return item.text().strip() if item else ""

            def num(c: int, padrao: float = 0.0) -> float:
                t = txt(c).replace(",", ".")
                return float(t) if t else padrao

            faixas.append(FaixaIncerteza(
                freq_min_hz=num(2), freq_max_hz=num(3), u_lab_db=num(4),
                fator_k=num(5, 2.0) or 2.0, u_cispr_db=num(6),
                item_norma=txt(0), mensurando=txt(1)))
        return faixas

    def _atualizar_avisos(self):
        try:
            cfg = ConfiguracaoIncerteza(metodo_id=self.cfg.metodo_id,
                                         regra=self.regra_combo.currentData(),
                                         faixas=self._ler())
        except ValueError:
            self.aviso.setText("")
            return
        self.aviso.setText(" · ".join(cfg.avisos()))

    def _salvar(self):
        try:
            faixas = self._ler()
        except ValueError as e:
            QMessageBox.warning(self, "Valor invalido",
                                 f"Ha um numero invalido na tabela: {e}")
            return
        for f in faixas:
            if f.freq_max_hz <= f.freq_min_hz:
                QMessageBox.warning(
                    self, "Faixa invalida",
                    f"A frequencia final ({f.freq_max_hz:g} Hz) deve ser maior que a "
                    f"inicial ({f.freq_min_hz:g} Hz).")
                return
        self.cfg.faixas = faixas
        self.cfg.regra = self.regra_combo.currentData()
        self.cfg.observacoes = self.obs.toPlainText()
        salvar(self.cfg)
        self.accept()
