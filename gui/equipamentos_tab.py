"""
gui/equipamentos_tab.py

Aba "Equipamentos / Certificados": cadastro dos itens da cadeia de medicao
(cabo, LISN, antena, atenuador, pre-amplificador...) e dos seus
certificados de calibracao.

Cada certificado traz os pontos (frequencia, valor, incerteza) medidos
pelo laboratorio de calibracao. O software INTERPOLA esses pontos em log
da frequencia e aplica a correcao ao trace do ensaio -- e o grafico de
pre-visualizacao mostra exatamente a curva que sera somada.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
                                QFormLayout, QComboBox, QLabel, QPushButton,
                                QLineEdit, QCheckBox, QTableWidget, QTableWidgetItem,
                                QListWidget, QListWidgetItem, QMessageBox,
                                QInputDialog, QSplitter, QFileDialog, QTextEdit,
                                QDoubleSpinBox, QHeaderView, QDateEdit, QTabWidget)
from PySide6.QtCore import Qt, QDate, Signal

from gui import theme
from gui.widgets import area_rolavel

from core.equipamentos import (Equipamento, Certificado, PontoCertificado,
                                TIPOS_EQUIPAMENTO, GRANDEZA_POR_TIPO, APLICACAO_PADRAO,
                                listar_equipamentos, carregar_equipamento,
                                salvar_equipamento, novo_equipamento,
                                duplicar_equipamento, renomear_equipamento,
                                excluir_equipamento, EQUIPAMENTOS_DIR)
from gui.plot_canvas import PlotCanvas

PONTO_COLS = ["Frequência (Hz)", "Valor (dB)", "Incerteza U (dB)"]


class EquipamentosTab(QWidget):
    """Cadastro de equipamentos e certificados de calibracao."""

    catalogo_mudou = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path: Path | None = None
        self._equip: Equipamento | None = None

        root = QVBoxLayout(self)
        splitter = QSplitter()
        root.addWidget(splitter, 1)

        # ---------------- lista de equipamentos ----------------
        left = QWidget()
        left_l = QVBoxLayout(left)
        titulo_lista = QLabel("EQUIPAMENTOS CADASTRADOS")
        titulo_lista.setObjectName("cardTitle")
        left_l.addWidget(titulo_lista)
        self.list = QListWidget()
        # nome de equipamento e comprido; elide em vez de criar barra
        # horizontal (o texto completo fica no tooltip do item)
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentItemChanged.connect(self._on_select)
        left_l.addWidget(self.list, 1)
        btns = QHBoxLayout()
        for texto, slot in (("Novo", self._novo), ("Duplicar", self._duplicar),
                             ("Renomear", self._renomear), ("Excluir", self._excluir)):
            b = QPushButton(texto)
            b.clicked.connect(slot)
            btns.addWidget(b)
        left_l.addLayout(btns)
        splitter.addWidget(left)

        # ---------------- editor ----------------
        right = QWidget()
        right_l = QVBoxLayout(right)

        ident = QGroupBox("Identificação")
        form = QFormLayout(ident)
        self.tipo_combo = QComboBox()
        self.tipo_combo.addItems(TIPOS_EQUIPAMENTO)
        self.tipo_combo.currentTextChanged.connect(self._on_tipo_changed)
        form.addRow("Tipo", self.tipo_combo)
        self.fabricante_edit = QLineEdit()
        form.addRow("Fabricante", self.fabricante_edit)
        self.modelo_edit = QLineEdit()
        form.addRow("Modelo", self.modelo_edit)
        self.serie_edit = QLineEdit()
        form.addRow("Número de série", self.serie_edit)
        self.patrimonio_edit = QLineEdit()
        form.addRow("Patrimônio", self.patrimonio_edit)
        self.descricao_edit = QLineEdit()
        form.addRow("Descrição", self.descricao_edit)
        self.aplicar_combo = QComboBox()
        self.aplicar_combo.addItems(["somar", "subtrair"])
        self.aplicar_combo.setToolTip(
            "Como a correcao entra na conta: nivel_corrigido = leitura + correcao.\n"
            "Perdas (cabo, LISN, atenuador) e fator de antena SOMAM.\n"
            "Ganho de pré-amplificador SUBTRAI.")
        form.addRow("Aplicar como", self.aplicar_combo)
        self.ativo_chk = QCheckBox("Disponível para uso na cadeia de medição")
        self.ativo_chk.setChecked(True)
        form.addRow(self.ativo_chk)
        right_l.addWidget(ident)

        # ---------------- certificado ----------------
        cert_box = QGroupBox("Certificado de calibração")
        cert_l = QVBoxLayout(cert_box)

        cert_top = QHBoxLayout()
        cert_top.addWidget(QLabel("Certificado:"))
        self.cert_combo = QComboBox()
        self.cert_combo.currentIndexChanged.connect(self._on_cert_changed)
        cert_top.addWidget(self.cert_combo, 1)
        add_cert = QPushButton("Novo certificado")
        add_cert.clicked.connect(self._novo_certificado)
        cert_top.addWidget(add_cert)
        del_cert = QPushButton("Excluir certificado")
        del_cert.clicked.connect(self._excluir_certificado)
        cert_top.addWidget(del_cert)
        cert_l.addLayout(cert_top)

        cert_form = QFormLayout()
        self.cert_numero_edit = QLineEdit()
        cert_form.addRow("Número", self.cert_numero_edit)
        self.cert_lab_edit = QLineEdit()
        cert_form.addRow("Laboratório", self.cert_lab_edit)
        datas = QHBoxLayout()
        self.cert_data_edit = QDateEdit()
        self.cert_data_edit.setCalendarPopup(True)
        self.cert_data_edit.setDisplayFormat("dd/MM/yyyy")
        self.cert_validade_edit = QDateEdit()
        self.cert_validade_edit.setCalendarPopup(True)
        self.cert_validade_edit.setDisplayFormat("dd/MM/yyyy")
        datas.addWidget(QLabel("Calibração"))
        datas.addWidget(self.cert_data_edit)
        datas.addWidget(QLabel("Validade"))
        datas.addWidget(self.cert_validade_edit)
        self.validade_label = QLabel("-")
        datas.addWidget(self.validade_label, 1)
        cert_form.addRow("Datas", datas)
        self.cert_k_spin = QDoubleSpinBox()
        self.cert_k_spin.setRange(1.0, 5.0)
        self.cert_k_spin.setSingleStep(0.1)
        self.cert_k_spin.setValue(2.0)
        cert_form.addRow("Fator k da incerteza", self.cert_k_spin)
        self.cert_grandeza_edit = QLineEdit()
        cert_form.addRow("Grandeza", self.cert_grandeza_edit)
        cert_l.addLayout(cert_form)

        cert_l.addWidget(QLabel(
            "Pontos do certificado — o valor entre eles é interpolado em log da frequência; "
            "fora da faixa calibrada o valor da extremidade é mantido (não há extrapolação):"))
        self.pontos_table = QTableWidget(0, len(PONTO_COLS))
        self.pontos_table.setAlternatingRowColors(True)
        self.pontos_table.verticalHeader().setDefaultSectionSize(26)
        self.pontos_table.setHorizontalHeaderLabels(PONTO_COLS)
        self.pontos_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.pontos_table.setMinimumHeight(170)
        cert_l.addWidget(self.pontos_table, 1)

        p_btns = QHBoxLayout()
        add_p = QPushButton("Adicionar ponto")
        add_p.clicked.connect(self._add_ponto)
        del_p = QPushButton("Remover ponto")
        del_p.clicked.connect(self._del_ponto)
        imp_p = QPushButton("Importar CSV…")
        imp_p.clicked.connect(self._importar_csv)
        prev_p = QPushButton("Ver curva")
        prev_p.clicked.connect(self._preview)
        p_btns.addWidget(add_p)
        p_btns.addWidget(del_p)
        p_btns.addWidget(imp_p)
        p_btns.addWidget(prev_p)
        p_btns.addStretch(1)
        cert_l.addLayout(p_btns)
        right_l.addWidget(cert_box, 1)

        self.obs_edit = QTextEdit()
        self.obs_edit.setMinimumHeight(52)
        self.obs_edit.setMaximumHeight(80)
        obs_box = QGroupBox("Observações")
        obs_l = QVBoxLayout(obs_box)
        obs_l.addWidget(self.obs_edit)
        right_l.addWidget(obs_box)

        right_l.addStretch(0)

        # O editor e alto: identificacao + certificado + pontos + observacoes.
        # Numa janela baixa, sem area rolavel, o Qt espreme as linhas do
        # formulario ate elas se SOBREPOREM. Dentro da area, o excedente
        # vira rolagem e cada campo mantem a altura certa.
        editor_scroll = area_rolavel(right)
        editor_scroll.setMinimumWidth(560)

        direita = QWidget()
        dir_l = QVBoxLayout(direita)
        dir_l.setContentsMargins(0, 0, 0, 0)
        dir_l.setSpacing(8)
        dir_l.addWidget(editor_scroll, 1)
        salvar = QPushButton("Salvar equipamento")
        salvar.setObjectName("primary")     # e a acao principal desta aba
        salvar.setMinimumHeight(38)
        salvar.clicked.connect(self._salvar)
        dir_l.addWidget(salvar)

        splitter.addWidget(direita)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])

        self._set_enabled(False)
        self._refresh()

    # ---------------------------------------------------------------- helpers
    def _set_enabled(self, on: bool):
        for w in (self.tipo_combo, self.fabricante_edit, self.modelo_edit,
                  self.serie_edit, self.patrimonio_edit, self.descricao_edit,
                  self.aplicar_combo, self.ativo_chk, self.cert_combo,
                  self.cert_numero_edit, self.cert_lab_edit, self.cert_data_edit,
                  self.cert_validade_edit, self.cert_k_spin, self.cert_grandeza_edit,
                  self.pontos_table, self.obs_edit):
            w.setEnabled(on)

    def _refresh(self, selecionar: Path | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        for p in listar_equipamentos():
            try:
                eq = carregar_equipamento(p)
                rotulo = f"[{eq.tipo}] {eq.rotulo()}"
                cert = eq.certificado()
                if cert is not None and cert.vencido_em():
                    rotulo += "  ⚠ vencido"
            except Exception:
                rotulo = p.stem
            item = QListWidgetItem(rotulo)
            item.setData(Qt.UserRole, str(p))
            item.setToolTip(rotulo)     # o rotulo e elidido na lista estreita
            self.list.addItem(item)
        self.list.blockSignals(False)
        if selecionar is not None:
            for i in range(self.list.count()):
                if Path(self.list.item(i).data(Qt.UserRole)) == selecionar:
                    self.list.setCurrentRow(i)
                    return
        if self.list.count() == 0:
            self.current_path = None
            self._equip = None
            self._set_enabled(False)

    def _on_tipo_changed(self, tipo: str):
        if not self.cert_grandeza_edit.text().strip():
            self.cert_grandeza_edit.setPlaceholderText(
                GRANDEZA_POR_TIPO.get(tipo, "Correcao (dB)"))
        if self._equip is not None and not self._equip.certificados:
            self.aplicar_combo.setCurrentText(APLICACAO_PADRAO.get(tipo, "somar"))

    # ---------------------------------------------------------------- selecao
    def _on_select(self, item: QListWidgetItem | None):
        if item is None:
            return
        self.current_path = Path(item.data(Qt.UserRole))
        self._equip = carregar_equipamento(self.current_path)
        eq = self._equip
        self._set_enabled(True)
        self.tipo_combo.setCurrentText(eq.tipo)
        self.fabricante_edit.setText(eq.fabricante)
        self.modelo_edit.setText(eq.modelo)
        self.serie_edit.setText(eq.numero_serie)
        self.patrimonio_edit.setText(eq.patrimonio)
        self.descricao_edit.setText(eq.descricao)
        self.aplicar_combo.setCurrentText(eq.aplicar)
        self.ativo_chk.setChecked(eq.ativo)
        self.obs_edit.setPlainText(eq.observacoes)

        self.cert_combo.blockSignals(True)
        self.cert_combo.clear()
        for i, c in enumerate(eq.certificados):
            self.cert_combo.addItem(
                f"{c.numero or '(sem numero)'} — {c.data_calibracao or 's/ data'}", i)
        self.cert_combo.setCurrentIndex(
            min(eq.certificado_ativo, max(0, len(eq.certificados) - 1)))
        self.cert_combo.blockSignals(False)
        self._carregar_certificado()

    def _carregar_certificado(self):
        eq = self._equip
        self.pontos_table.setRowCount(0)
        if eq is None or not eq.certificados:
            self.cert_numero_edit.clear()
            self.cert_lab_edit.clear()
            self.cert_grandeza_edit.clear()
            self.validade_label.setText("(sem certificado)")
            return
        idx = max(0, self.cert_combo.currentIndex())
        cert = eq.certificados[idx]
        self.cert_numero_edit.setText(cert.numero)
        self.cert_lab_edit.setText(cert.laboratorio)
        self.cert_grandeza_edit.setText(cert.grandeza)
        self.cert_k_spin.setValue(cert.fator_k or 2.0)
        for edit, txt in ((self.cert_data_edit, cert.data_calibracao),
                           (self.cert_validade_edit, cert.data_validade)):
            d = QDate.fromString(txt, "yyyy-MM-dd") if txt else QDate.currentDate()
            edit.setDate(d if d.isValid() else QDate.currentDate())
        for p in sorted(cert.pontos, key=lambda x: x.freq_hz):
            r = self.pontos_table.rowCount()
            self.pontos_table.insertRow(r)
            for c, v in enumerate((p.freq_hz, p.valor_db, p.incerteza_db)):
                self.pontos_table.setItem(r, c, QTableWidgetItem(f"{v:g}"))
        self._atualizar_validade(cert)

    def _atualizar_validade(self, cert: Certificado):
        dias = cert.dias_para_vencer()
        if dias is None:
            self.validade_label.setText("sem validade")
            self.validade_label.setStyleSheet(theme.CSS_WARN)
        elif dias < 0:
            self.validade_label.setText(f"VENCIDO há {-dias} dias")
            self.validade_label.setStyleSheet(theme.CSS_FAIL)
        elif dias < 60:
            self.validade_label.setText(f"vence em {dias} dias")
            self.validade_label.setStyleSheet(theme.CSS_WARN + " font-weight:700;")
        else:
            self.validade_label.setText(f"válido ({dias} dias)")
            self.validade_label.setStyleSheet(theme.CSS_OK)

    def _on_cert_changed(self):
        self._carregar_certificado()

    # ---------------------------------------------------------------- pontos
    def _add_ponto(self):
        r = self.pontos_table.rowCount()
        self.pontos_table.insertRow(r)
        for c, v in enumerate(("0", "0", "0")):
            self.pontos_table.setItem(r, c, QTableWidgetItem(v))

    def _del_ponto(self):
        for r in sorted({i.row() for i in self.pontos_table.selectedIndexes()}, reverse=True):
            self.pontos_table.removeRow(r)

    def _ler_pontos(self) -> list[PontoCertificado]:
        pontos = []
        for r in range(self.pontos_table.rowCount()):
            def val(c: int) -> float:
                item = self.pontos_table.item(r, c)
                if item is None or not item.text().strip():
                    return 0.0
                return float(item.text().replace(",", "."))
            pontos.append(PontoCertificado(val(0), val(1), val(2)))
        return sorted(pontos, key=lambda p: p.freq_hz)

    def _importar_csv(self):
        if self._equip is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Importar pontos do certificado", "", "CSV (*.csv *.txt);;Todos (*.*)")
        if not path:
            return
        unidade, ok = QInputDialog.getItem(
            self, "Unidade de frequencia",
            "Em que unidade esta a coluna de frequencia do arquivo?",
            ["Hz", "kHz", "MHz", "GHz"], 0, False)
        if not ok:
            return
        try:
            cert = Certificado.from_csv(path, freq_unit=unidade.lower())
        except Exception as e:
            QMessageBox.warning(self, "Erro ao importar", str(e))
            return
        self.pontos_table.setRowCount(0)
        for p in cert.pontos:
            r = self.pontos_table.rowCount()
            self.pontos_table.insertRow(r)
            for c, v in enumerate((p.freq_hz, p.valor_db, p.incerteza_db)):
                self.pontos_table.setItem(r, c, QTableWidgetItem(f"{v:g}"))
        QMessageBox.information(
            self, "Importado",
            f"{len(cert.pontos)} pontos importados. Confira e clique em "
            "'Salvar equipamento'.\n\nColunas esperadas: frequencia, valor, incerteza "
            "(a terceira e opcional).")

    def _preview(self):
        """Mostra a curva interpolada que sera aplicada ao ensaio."""
        try:
            pontos = self._ler_pontos()
        except ValueError as e:
            QMessageBox.warning(self, "Valor invalido", str(e))
            return
        if len(pontos) < 1:
            QMessageBox.information(self, "Sem pontos", "Cadastre ao menos um ponto.")
            return

        import numpy as np
        from matplotlib.figure import Figure

        cert = Certificado(pontos=pontos, fator_k=self.cert_k_spin.value())
        sinal = -1.0 if self.aplicar_combo.currentText() == "subtrair" else 1.0
        f0, f1 = pontos[0].freq_hz, pontos[-1].freq_hz
        if f1 <= f0:
            f1 = f0 * 10
        freq = np.logspace(np.log10(max(f0, 1.0)), np.log10(f1), 600)
        vals = np.array([(cert.valor_em(f) or 0.0) * sinal for f in freq])
        incs = np.array([cert.incerteza_em(f) or 0.0 for f in freq])

        fig = Figure(figsize=(8, 4.2), dpi=110)
        ax = fig.add_subplot(111)
        ax.fill_between(freq, vals - incs, vals + incs, color="#1f4e96", alpha=0.15,
                        label=f"Incerteza U (k={cert.fator_k:g})")
        ax.plot(freq, vals, "-", color="#1f4e96", linewidth=1.2, label="Correcao interpolada")
        ax.plot([p.freq_hz for p in pontos], [p.valor_db * sinal for p in pontos],
                "o", color="#c0392b", markersize=5, label="Pontos do certificado")
        ax.set_xscale("log")
        ax.set_xlabel("Frequencia (Hz)", fontsize=9)
        ax.set_ylabel(self.cert_grandeza_edit.text() or "Correcao (dB)", fontsize=9)
        ax.grid(True, which="both", linestyle="-", linewidth=0.4, color="#999999")
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=8)
        titulo = self.modelo_edit.text() or (self._equip.id if self._equip else "")
        ax.set_title(f"Curva de correcao — {titulo}", fontsize=10)
        fig.tight_layout()

        dlg = QWidget(self, Qt.Window)
        dlg.setWindowTitle("Curva de correcao interpolada")
        dlg.resize(880, 480)
        lay = QVBoxLayout(dlg)
        canvas = PlotCanvas(dlg)
        canvas.show_figure(fig)
        lay.addWidget(canvas)
        lay.addWidget(QLabel(
            "A faixa sombreada e a incerteza do certificado. Fora dos pontos calibrados "
            "o valor da extremidade e mantido — o software nao extrapola certificado."))
        dlg.show()
        self._preview_win = dlg  # mantem referencia viva

    # ---------------------------------------------------------------- CRUD
    def _novo(self):
        equip_id, ok = QInputDialog.getText(self, "Novo equipamento",
                                             "Id (ex.: cabo_rg214_3m):")
        if not ok or not equip_id.strip():
            return
        tipo, ok = QInputDialog.getItem(self, "Tipo", "Tipo do equipamento:",
                                         TIPOS_EQUIPAMENTO, 0, False)
        if not ok:
            return
        try:
            path = novo_equipamento(equip_id, tipo)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.catalogo_mudou.emit()
        self._refresh(selecionar=path)

    def _duplicar(self):
        if self.current_path is None:
            return
        novo_id, ok = QInputDialog.getText(self, "Duplicar", "Id da copia:",
                                            text=f"{self.current_path.stem}_copia")
        if not ok or not novo_id.strip():
            return
        try:
            path = duplicar_equipamento(self.current_path, novo_id)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.catalogo_mudou.emit()
        self._refresh(selecionar=path)

    def _renomear(self):
        if self.current_path is None:
            return
        novo_id, ok = QInputDialog.getText(self, "Renomear", "Novo id:",
                                            text=self.current_path.stem)
        if not ok or not novo_id.strip() or novo_id.strip() == self.current_path.stem:
            return
        try:
            path = renomear_equipamento(self.current_path, novo_id)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.current_path = path
        self.catalogo_mudou.emit()
        self._refresh(selecionar=path)

    def _excluir(self):
        if self.current_path is None:
            return
        if QMessageBox.question(
                self, "Confirmar exclusao",
                f"Excluir o equipamento '{self.current_path.stem}' e todos os seus "
                "certificados?") != QMessageBox.Yes:
            return
        excluir_equipamento(self.current_path)
        self.current_path = None
        self._equip = None
        self.catalogo_mudou.emit()
        self._refresh()

    def _novo_certificado(self):
        if self._equip is None:
            return
        numero, ok = QInputDialog.getText(self, "Novo certificado", "Numero do certificado:")
        if not ok:
            return
        cert = Certificado(numero=numero.strip(),
                            grandeza=GRANDEZA_POR_TIPO.get(self._equip.tipo, ""),
                            data_calibracao=date.today().isoformat())
        self._equip.certificados.append(cert)
        self._equip.certificado_ativo = len(self._equip.certificados) - 1
        salvar_equipamento(self._equip, self.current_path)
        self._on_select(self.list.currentItem())
        self.cert_combo.setCurrentIndex(len(self._equip.certificados) - 1)

    def _excluir_certificado(self):
        if self._equip is None or not self._equip.certificados:
            return
        idx = self.cert_combo.currentIndex()
        cert = self._equip.certificados[idx]
        if QMessageBox.question(
                self, "Confirmar",
                f"Excluir o certificado '{cert.numero or '(sem numero)'}'?") != QMessageBox.Yes:
            return
        self._equip.certificados.pop(idx)
        self._equip.certificado_ativo = 0
        salvar_equipamento(self._equip, self.current_path)
        self._on_select(self.list.currentItem())

    def _salvar(self):
        if self._equip is None or self.current_path is None:
            return
        eq = self._equip
        eq.tipo = self.tipo_combo.currentText()
        eq.fabricante = self.fabricante_edit.text().strip()
        eq.modelo = self.modelo_edit.text().strip()
        eq.numero_serie = self.serie_edit.text().strip()
        eq.patrimonio = self.patrimonio_edit.text().strip()
        eq.descricao = self.descricao_edit.text().strip()
        eq.aplicar = self.aplicar_combo.currentText()
        eq.ativo = self.ativo_chk.isChecked()
        eq.observacoes = self.obs_edit.toPlainText()

        if eq.certificados:
            idx = max(0, self.cert_combo.currentIndex())
            cert = eq.certificados[idx]
            cert.numero = self.cert_numero_edit.text().strip()
            cert.laboratorio = self.cert_lab_edit.text().strip()
            cert.data_calibracao = self.cert_data_edit.date().toString("yyyy-MM-dd")
            cert.data_validade = self.cert_validade_edit.date().toString("yyyy-MM-dd")
            cert.fator_k = self.cert_k_spin.value()
            cert.grandeza = self.cert_grandeza_edit.text().strip()
            try:
                cert.pontos = self._ler_pontos()
            except ValueError as e:
                QMessageBox.warning(self, "Valor invalido",
                                     f"Ha um numero invalido na tabela de pontos: {e}")
                return
            eq.certificado_ativo = idx

        salvar_equipamento(eq, self.current_path)
        self.catalogo_mudou.emit()
        QMessageBox.information(self, "Salvo", f"Equipamento salvo em {self.current_path.name}")
        self._refresh(selecionar=self.current_path)
