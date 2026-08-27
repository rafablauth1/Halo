"""
gui/receiver_models_manager.py

Gerenciador do catalogo de receivers: criar/duplicar/renomear/excluir um
modelo e -- o mais importante -- EDITAR OS COMANDOS SCPI de cada modelo,
linha a linha, direto na tela.

E aqui que voce corrige um comando que o manual do SEU instrumento
descreve diferente do que veio pre-setado, sem mexer em codigo Python.
Um comando deixado em branco simplesmente nao e enviado.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QLabel, QMessageBox,
                                QInputDialog, QLineEdit, QFormLayout, QTableWidget,
                                QTableWidgetItem, QSplitter, QWidget, QDoubleSpinBox,
                                QSpinBox, QCheckBox, QTextEdit, QTabWidget, QHeaderView)
from PySide6.QtCore import Qt

from instruments.receiver_models import (ReceiverModel, list_available_receivers,
                                          load_receiver, save_receiver, new_receiver,
                                          duplicate_receiver, rename_receiver,
                                          delete_receiver)

# Descricao em portugues de cada chave de comando, para o usuario saber o
# que esta editando sem precisar decorar a chave interna.
COMMAND_HELP = {
    "idn": "Identificacao do instrumento (*IDN?)",
    "reset": "Reset geral",
    "clear_status": "Limpa registrador de status",
    "opc_query": "Espera fim da operacao (*OPC?)",
    "error_query": "Le a fila de erros",
    "remote_display_on": "Mantem a tela ligada em controle remoto",
    "select_receiver_mode": "Entra no modo Receiver (scan EMI)",
    "select_analyzer_mode": "Entra no modo Analisador de espectro",
    "freq_start": "Frequencia inicial",
    "freq_stop": "Frequencia final",
    "freq_center": "Frequencia central",
    "freq_span": "Span",
    "rbw": "Banda de resolucao (RBW)",
    "rbw_filter_cispr": "Seleciona filtro CISPR (6 dB)",
    "rbw_filter_normal": "Seleciona filtro normal (3 dB)",
    "vbw": "Banda de video (VBW)",
    "detector": "Detector do trace ({trace} = numero do trace)",
    "meas_time": "Tempo de medicao por ponto",
    "sweep_time": "Tempo de varredura",
    "sweep_time_auto": "Tempo de varredura automatico",
    "sweep_points": "Pontos por varredura",
    "sweep_count": "Numero de varreduras",
    "ref_level": "Nivel de referencia",
    "ref_level_offset": "Offset do nivel de referencia",
    "attenuation": "Atenuacao RF manual",
    "attenuation_auto": "Atenuacao RF automatica",
    "preamp_state": "Liga/desliga pre-amplificador",
    "preamp_level": "Ganho do pre-amplificador",
    "preselector_state": "Liga/desliga pre-seletor",
    "unit_level": "Unidade de nivel (dBuV, dBuA...)",
    "input_impedance": "Impedancia de entrada (50/75 ohm)",
    "input_coupling": "Acoplamento de entrada (AC/DC)",
    "noise_limiter": "Limitador de pulso / protecao de entrada",
    "trace_mode": "Modo do trace (Clear/Write, Max Hold...)",
    "trace_data_query": "Le os dados do trace",
    "transducer_select": "Seleciona fator de transdutor",
    "transducer_state": "Ativa/desativa transdutor",
    "init_continuous_off": "Modo single sweep",
    "init_continuous_on": "Modo varredura continua",
    "init_immediate": "Dispara a varredura",
    "abort": "Aborta a varredura",
    "query_sweep_points": "Consulta pontos por varredura",
    "query_freq_start": "Consulta frequencia inicial",
    "query_freq_stop": "Consulta frequencia final",
    "scan_start": "Tabela de scan: inicio da faixa ({range} = n. da faixa)",
    "scan_stop": "Tabela de scan: fim da faixa",
    "scan_step": "Tabela de scan: passo de frequencia",
    "scan_rbw": "Tabela de scan: RBW da faixa",
    "scan_meas_time": "Tabela de scan: tempo de medicao da faixa",
    "scan_attenuation": "Tabela de scan: atenuacao da faixa",
    "scan_preamp": "Tabela de scan: pre-amplificador da faixa",
    "scan_count": "Numero de scans",
    "scan_ranges": "Quantidade de sub-faixas da tabela de scan",
    "final_meas_margin": "Medicao final: margem abaixo do limite",
    "final_meas_peaks": "Medicao final: quantidade de picos",
    "final_meas_run": "Medicao final: executa",
    "final_meas_query": "Medicao final: le resultados",
    "lisn_type": "LISN: tipo (ENV216, ESH2-Z5...)",
    "lisn_phase": "LISN: fase medida (L1/L2/L3/N)",
    "lisn_pe": "LISN: terra de protecao",
    "lisn_highpass": "LISN: filtro passa-alta 150 kHz",
}


class ReceiverModelsManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gerenciar modelos de receiver (R&S)")
        self.resize(1080, 660)
        self.changed = False
        self.current_path: Path | None = None

        layout = QVBoxLayout(self)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        # ---- lista de modelos ----
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.addWidget(QLabel("Modelos (instruments/receivers/*.json):"))
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        left_l.addWidget(self.list)
        btn_row = QHBoxLayout()
        for text, slot in (("Novo", self._new), ("Duplicar", self._duplicate),
                            ("Renomear", self._rename), ("Excluir", self._delete)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        left_l.addLayout(btn_row)
        splitter.addWidget(left)

        # ---- editor do modelo ----
        right = QWidget()
        right_l = QVBoxLayout(right)
        self.tabs = QTabWidget()
        right_l.addWidget(self.tabs, 1)

        # aba: caracteristicas
        specs = QWidget()
        form = QFormLayout(specs)
        self.model_edit = QLineEdit()
        form.addRow("Modelo", self.model_edit)
        self.family_edit = QLineEdit()
        form.addRow("Familia", self.family_edit)
        self.desc_edit = QLineEdit()
        form.addRow("Descricao", self.desc_edit)
        self.fmin_spin = QDoubleSpinBox()
        self.fmin_spin.setRange(0, 1e12)
        self.fmin_spin.setDecimals(0)
        self.fmin_spin.setGroupSeparatorShown(True)
        form.addRow("Freq. minima (Hz)", self.fmin_spin)
        self.fmax_spin = QDoubleSpinBox()
        self.fmax_spin.setRange(0, 1e12)
        self.fmax_spin.setDecimals(0)
        self.fmax_spin.setGroupSeparatorShown(True)
        form.addRow("Freq. maxima (Hz)", self.fmax_spin)
        self.detectors_edit = QLineEdit()
        self.detectors_edit.setPlaceholderText("PK, QP, AV, RMS, CAV, CRMS")
        form.addRow("Detectores", self.detectors_edit)
        self.rbw_edit = QLineEdit()
        self.rbw_edit.setPlaceholderText("200, 9000, 120000, 1000000")
        form.addRow("RBW CISPR (Hz)", self.rbw_edit)
        self.gpib_spin = QSpinBox()
        self.gpib_spin.setRange(0, 30)
        form.addRow("Endereco GPIB padrao", self.gpib_spin)
        self.preamp_chk = QCheckBox("Tem pre-amplificador")
        form.addRow(self.preamp_chk)
        self.presel_chk = QCheckBox("Tem pre-seletor")
        form.addRow(self.presel_chk)
        self.recmode_chk = QCheckBox("Tem modo Receiver (scan EMI)")
        form.addRow(self.recmode_chk)
        self.lisn_chk = QCheckBox("Controla LISN pelo receiver")
        form.addRow(self.lisn_chk)
        self.scantable_chk = QCheckBox("Tem tabela de scan multi-banda")
        form.addRow(self.scantable_chk)
        self.verified_chk = QCheckBox("Comandos ja conferidos no manual deste instrumento")
        form.addRow(self.verified_chk)
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(70)
        form.addRow("Notas", self.notes_edit)
        self.tabs.addTab(specs, "Caracteristicas")

        # aba: comandos SCPI
        cmds = QWidget()
        cmds_l = QVBoxLayout(cmds)
        cmds_l.addWidget(QLabel(
            "Comandos SCPI deste modelo. {value} e substituido pelo valor, {trace} pelo numero "
            "do trace e {range} pelo numero da faixa de scan. Deixe em branco para NAO enviar."))
        self.cmd_table = QTableWidget(0, 3)
        self.cmd_table.setAlternatingRowColors(True)
        self.cmd_table.verticalHeader().setDefaultSectionSize(26)
        self.cmd_table.setHorizontalHeaderLabels(["Funcao", "Comando SCPI", "O que faz"])
        self.cmd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        cmds_l.addWidget(self.cmd_table)
        cmd_btns = QHBoxLayout()
        add_cmd = QPushButton("Adicionar comando")
        add_cmd.clicked.connect(self._add_command_row)
        del_cmd = QPushButton("Remover selecionado")
        del_cmd.clicked.connect(self._del_command_row)
        cmd_btns.addWidget(add_cmd)
        cmd_btns.addWidget(del_cmd)
        cmd_btns.addStretch(1)
        cmds_l.addLayout(cmd_btns)
        self.tabs.addTab(cmds, "Comandos SCPI")

        save_btn = QPushButton("Salvar modelo")
        save_btn.clicked.connect(self._save)
        right_l.addWidget(save_btn)
        splitter.addWidget(right)
        splitter.setSizes([260, 820])

        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self._set_enabled(False)
        self._refresh()

    # ---------------- helpers ----------------
    def _set_enabled(self, enabled: bool):
        self.tabs.setEnabled(enabled)

    def _refresh(self, select_path: Path | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        for p in list_available_receivers():
            try:
                m = load_receiver(p)
                label = f"{m.model or p.stem}  [{m.family}]"
            except Exception:
                label = p.stem
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(p))
            self.list.addItem(item)
        self.list.blockSignals(False)
        if select_path is not None:
            for i in range(self.list.count()):
                if Path(self.list.item(i).data(Qt.UserRole)) == select_path:
                    self.list.setCurrentRow(i)
                    return
        if self.list.count() and self.current_path is None:
            self.list.setCurrentRow(0)

    def _on_select(self, item: QListWidgetItem | None):
        if item is None:
            return
        self.current_path = Path(item.data(Qt.UserRole))
        m = load_receiver(self.current_path)
        self._set_enabled(True)
        self.model_edit.setText(m.model)
        self.family_edit.setText(m.family)
        self.desc_edit.setText(m.description)
        self.fmin_spin.setValue(m.freq_min_hz)
        self.fmax_spin.setValue(m.freq_max_hz)
        self.detectors_edit.setText(", ".join(m.detectors))
        self.rbw_edit.setText(", ".join(f"{v:g}" for v in m.rbw_cispr_hz))
        self.gpib_spin.setValue(m.default_gpib_address)
        self.preamp_chk.setChecked(m.has_preamp)
        self.presel_chk.setChecked(m.has_preselector)
        self.recmode_chk.setChecked(m.has_receiver_mode)
        self.lisn_chk.setChecked(m.has_lisn_control)
        self.scantable_chk.setChecked(m.has_scan_table)
        self.verified_chk.setChecked(m.verified)
        self.notes_edit.setPlainText(m.notes)

        self.cmd_table.setRowCount(0)
        for key in sorted(m.commands):
            row = self.cmd_table.rowCount()
            self.cmd_table.insertRow(row)
            key_item = QTableWidgetItem(key)
            self.cmd_table.setItem(row, 0, key_item)
            self.cmd_table.setItem(row, 1, QTableWidgetItem(m.commands[key]))
            help_item = QTableWidgetItem(COMMAND_HELP.get(key, ""))
            help_item.setFlags(help_item.flags() & ~Qt.ItemIsEditable)
            self.cmd_table.setItem(row, 2, help_item)

    def _add_command_row(self):
        row = self.cmd_table.rowCount()
        self.cmd_table.insertRow(row)
        self.cmd_table.setItem(row, 0, QTableWidgetItem("nova_chave"))
        self.cmd_table.setItem(row, 1, QTableWidgetItem(""))
        self.cmd_table.setItem(row, 2, QTableWidgetItem(""))

    def _del_command_row(self):
        rows = sorted({i.row() for i in self.cmd_table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.cmd_table.removeRow(r)

    # ---------------- CRUD ----------------
    def _new(self):
        rid, ok = QInputDialog.getText(self, "Novo receiver", "Id (ex.: meu_esr3):")
        if not ok or not rid.strip():
            return
        try:
            path = new_receiver(rid)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self._refresh(select_path=path)

    def _duplicate(self):
        if self.current_path is None:
            QMessageBox.information(self, "Selecione", "Selecione um modelo para duplicar.")
            return
        base = self.current_path.stem
        rid, ok = QInputDialog.getText(self, "Duplicar receiver", "Id da copia:", text=f"{base}_copia")
        if not ok or not rid.strip():
            return
        try:
            path = duplicate_receiver(self.current_path, rid)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self._refresh(select_path=path)

    def _rename(self):
        if self.current_path is None:
            QMessageBox.information(self, "Selecione", "Selecione um modelo para renomear.")
            return
        rid, ok = QInputDialog.getText(self, "Renomear id", "Novo id:", text=self.current_path.stem)
        if not ok or not rid.strip() or rid.strip() == self.current_path.stem:
            return
        try:
            path = rename_receiver(self.current_path, rid)
        except (ValueError, FileExistsError) as e:
            QMessageBox.warning(self, "Erro", str(e))
            return
        self.changed = True
        self.current_path = path
        self._refresh(select_path=path)

    def _delete(self):
        if self.current_path is None:
            QMessageBox.information(self, "Selecione", "Selecione um modelo para excluir.")
            return
        if QMessageBox.question(self, "Confirmar exclusao",
                                 f"Excluir permanentemente '{self.current_path.stem}'?") != QMessageBox.Yes:
            return
        delete_receiver(self.current_path)
        self.changed = True
        self.current_path = None
        self._set_enabled(False)
        self._refresh()

    def _save(self):
        if self.current_path is None:
            return
        m = load_receiver(self.current_path)
        m.model = self.model_edit.text().strip()
        m.family = self.family_edit.text().strip()
        m.description = self.desc_edit.text().strip()
        m.freq_min_hz = self.fmin_spin.value()
        m.freq_max_hz = self.fmax_spin.value()
        m.detectors = [d.strip().upper() for d in self.detectors_edit.text().split(",") if d.strip()]
        try:
            m.rbw_cispr_hz = [float(v.strip()) for v in self.rbw_edit.text().split(",") if v.strip()]
        except ValueError:
            QMessageBox.warning(self, "Erro", "RBW CISPR deve ser uma lista de numeros separados por virgula.")
            return
        m.default_gpib_address = self.gpib_spin.value()
        m.has_preamp = self.preamp_chk.isChecked()
        m.has_preselector = self.presel_chk.isChecked()
        m.has_receiver_mode = self.recmode_chk.isChecked()
        m.has_lisn_control = self.lisn_chk.isChecked()
        m.has_scan_table = self.scantable_chk.isChecked()
        m.verified = self.verified_chk.isChecked()
        m.notes = self.notes_edit.toPlainText()

        commands: dict[str, str] = {}
        for row in range(self.cmd_table.rowCount()):
            key_item = self.cmd_table.item(row, 0)
            cmd_item = self.cmd_table.item(row, 1)
            if key_item is None:
                continue
            key = key_item.text().strip()
            if not key:
                continue
            commands[key] = cmd_item.text().strip() if cmd_item else ""
        m.commands = commands

        save_receiver(m, self.current_path)
        self.changed = True
        QMessageBox.information(self, "Salvo", f"Modelo salvo em {self.current_path.name}")
        self._refresh(select_path=self.current_path)
