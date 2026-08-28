from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emc.config import AUTOMATED_STANDARDS, STANDARDS
from emc.core import planner, project_files, templates
from emc.core.counter_session import CounterWorker
from emc.core.legacy_routines import burst_params_to_points, surge_params_to_points
from emc.core.runtime_settings import settings as runtime_settings
from emc.core.standards import (
    BURST_DEFAULT_DURATION_S,
    BURST_LEVELS,
    BURST_SPIKE_FREQUENCIES_HZ,
    DIPS_LEVELS,
    DIPS_PHASE_ANGLES_DEG,
    DIPS_SHORT_INTERRUPTION_CYCLES,
    SURGE_COUPLINGS,
    SURGE_DEFAULT_INTERVAL_S,
    SURGE_DEFAULT_PULSE_COUNT,
    SURGE_LEVELS,
    SURGE_METER_PHASE_COMBINATIONS,
)
from emc.core.test_session import TestSessionWorker, set_session_result
from emc.gui.routine_editor import RoutineEditorDialog, describe_point
from emc.instruments.factory import build_agilent_counter_driver, build_driver_for_standard

DEFAULT_PHASE_COMBINATIONS = ["L1-N"]


def _checkable_list(values: list[str]) -> QListWidget:
    widget = QListWidget()
    widget.setMaximumHeight(90)
    for value in values:
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        widget.addItem(item)
    return widget


def _checked_values(widget: QListWidget) -> list[str]:
    return [
        widget.item(i).text()
        for i in range(widget.count())
        if widget.item(i).checkState() == Qt.CheckState.Checked
    ]


def _set_checked_values(widget: QListWidget, values: list[str]) -> None:
    """Marca os itens existentes que estão em `values` e adiciona os que faltarem
    (necessário para restaurar ângulos personalizados salvos em um template)."""
    values_set = set(values)
    existing = set()
    for i in range(widget.count()):
        item = widget.item(i)
        existing.add(item.text())
        item.setCheckState(
            Qt.CheckState.Checked if item.text() in values_set else Qt.CheckState.Unchecked
        )
    for value in values_set - existing:
        item = QListWidgetItem(value)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked)
        widget.addItem(item)


class ExecutionView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker: TestSessionWorker | None = None
        self.template_combos: dict[str, QComboBox] = {}
        self._manual_driver = None  # driver conectado manualmente via botão TEST ON
        self._manual_driver_standard: str | None = None
        self._counter_worker: CounterWorker | None = None
        self._counter_project_id: int | None = None
        self._counter_log_path = None

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.project_combo = QComboBox()
        form.addRow("Projeto:", self.project_combo)

        self.standard_combo = QComboBox()
        for code in AUTOMATED_STANDARDS:
            self.standard_combo.addItem(f"{code} — {STANDARDS[code]}", code)
        self.standard_combo.currentIndexChanged.connect(self._on_standard_changed)
        form.addRow("Norma:", self.standard_combo)

        self.eut_name_edit = QLineEdit()
        form.addRow("EUT (nome/modelo):", self.eut_name_edit)
        self.eut_serial_edit = QLineEdit()
        form.addRow("Número de série:", self.eut_serial_edit)
        self.operator_edit = QLineEdit()
        form.addRow("Operador:", self.operator_edit)
        layout.addLayout(form)

        self.params_stack = QStackedWidget()
        self.params_stack.addWidget(self._build_burst_page())
        self.params_stack.addWidget(self._build_surge_page())
        self.params_stack.addWidget(self._build_dips_page())
        layout.addWidget(self.params_stack)

        self.test_on_widget = QWidget()
        test_on_row = QHBoxLayout(self.test_on_widget)
        test_on_row.setContentsMargins(0, 0, 0, 0)
        self.test_on_btn = QPushButton("TEST ON (ligar saída do UCS 500N)")
        self.test_on_btn.setCheckable(True)
        self.test_on_btn.toggled.connect(self._toggle_test_on)
        test_on_row.addWidget(self.test_on_btn)
        test_on_row.addWidget(
            QLabel("Liga/desliga a saída do gerador manualmente, fora de um ensaio automatizado.")
        )
        test_on_row.addStretch(1)
        layout.addWidget(self.test_on_widget)
        self._on_standard_changed(self.standard_combo.currentIndex())

        button_row = QHBoxLayout()
        self.start_btn = QPushButton("Iniciar ensaio")
        self.start_btn.clicked.connect(self._start_test)
        button_row.addWidget(self.start_btn)
        self.pause_btn = QPushButton("Pausar ensaio")
        self.pause_btn.setEnabled(False)
        self.pause_btn.clicked.connect(self._pause_test)
        button_row.addWidget(self.pause_btn)
        self.stop_btn = QPushButton("Parar (aborta)")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_test)
        button_row.addWidget(self.stop_btn)
        layout.addLayout(button_row)

        layout.addWidget(QLabel("Log do ensaio:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(260)
        layout.addWidget(self.log_view, 1)

        layout.addWidget(self._build_counter_box())

        self.refresh_projects()

    def _build_counter_box(self) -> QGroupBox:
        box = QGroupBox("Contador de Frequência — RTC/Timer (Agilent 53131A)")
        box_layout = QVBoxLayout(box)

        counter_box_hint = QLabel(
            "Placa/endereço GPIB configurados em Configurações. Aqui só o tempo de "
            "gate e o intervalo entre leituras, que são específicos de cada sessão."
        )
        counter_box_hint.setWordWrap(True)
        box_layout.addWidget(counter_box_hint)

        counter_form = QFormLayout()
        self.counter_mode_combo = QComboBox()
        self.counter_mode_combo.addItem("Configuração manual (app configura o gate)", "manual")
        self.counter_mode_combo.addItem("Via Recall (usa config. já salva no instrumento)", "recall")
        self.counter_mode_combo.addItem("Cronômetro (Iniciar/Finalizar, registra a diferença)", "stopwatch")
        self.counter_mode_combo.currentIndexChanged.connect(self._on_counter_mode_changed)
        counter_form.addRow("Modo:", self.counter_mode_combo)

        self.counter_recall_spin = QSpinBox()
        self.counter_recall_spin.setRange(0, 20)
        self.counter_recall_spin.setValue(1)
        self.counter_recall_spin.setVisible(False)
        counter_form.addRow("Registro de Recall:", self.counter_recall_spin)
        self._counter_recall_label = counter_form.labelForField(self.counter_recall_spin)
        self._counter_recall_label.setVisible(False)

        self.counter_gate_spin = QDoubleSpinBox()
        self.counter_gate_spin.setRange(0.1, 3600)
        self.counter_gate_spin.setValue(30)
        self.counter_gate_spin.setSuffix(" s")
        counter_form.addRow("Tempo de gate:", self.counter_gate_spin)
        self._counter_gate_label = counter_form.labelForField(self.counter_gate_spin)

        self.counter_interval_spin = QDoubleSpinBox()
        self.counter_interval_spin.setRange(0, 3600)
        self.counter_interval_spin.setValue(30)
        self.counter_interval_spin.setSuffix(" s")
        counter_form.addRow("Intervalo entre leituras:", self.counter_interval_spin)
        self._counter_interval_label = counter_form.labelForField(self.counter_interval_spin)

        self.counter_decimals_spin = QSpinBox()
        self.counter_decimals_spin.setRange(0, 9)
        self.counter_decimals_spin.setValue(0)
        self.counter_decimals_spin.setToolTip(
            "Ajusta onde entra a vírgula no valor bruto do contador — ex.: valor "
            "299998739 com 7 casas decimais vira 29,9998739. Não muda o valor "
            "real medido, só como ele é exibido/salvo."
        )
        counter_form.addRow("Casas decimais:", self.counter_decimals_spin)
        box_layout.addLayout(counter_form)

        self.counter_recall_hint = QLabel(
            "No modo Recall não precisa configurar tempo nem intervalo — o app "
            "escuta o instrumento continuamente e registra sozinho toda vez que "
            "o valor mudar."
        )
        self.counter_recall_hint.setWordWrap(True)
        self.counter_recall_hint.setVisible(False)
        box_layout.addWidget(self.counter_recall_hint)

        self.counter_stopwatch_status = QLabel("")
        self.counter_stopwatch_status.setWordWrap(True)
        self.counter_stopwatch_status.setVisible(False)
        box_layout.addWidget(self.counter_stopwatch_status)

        counter_btn_row = QHBoxLayout()
        self.counter_start_btn = QPushButton("Iniciar leitura contínua")
        self.counter_start_btn.clicked.connect(self._start_counter)
        counter_btn_row.addWidget(self.counter_start_btn)
        self.counter_stop_btn = QPushButton("Parar")
        self.counter_stop_btn.setEnabled(False)
        self.counter_stop_btn.clicked.connect(self._stop_counter)
        counter_btn_row.addWidget(self.counter_stop_btn)
        counter_btn_row.addStretch(1)
        box_layout.addLayout(counter_btn_row)

        self.counter_table = QTableWidget(0, 2)
        self.counter_table.setHorizontalHeaderLabels(["Data/Hora", "Contagem (RTC)"])
        self.counter_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.counter_table.setMaximumHeight(180)
        box_layout.addWidget(self.counter_table)

        self.counter_file_label = QLabel("Nenhuma leitura salva ainda nesta sessão.")
        box_layout.addWidget(self.counter_file_label)

        return box

    # ---- templates (roteiros salvos) ----

    def _add_template_controls(self, form: QFormLayout, standard_code: str) -> None:
        row = QHBoxLayout()
        combo = QComboBox()
        row.addWidget(combo, 1)
        new_btn = QPushButton("Novo roteiro em branco")
        new_btn.clicked.connect(lambda: self._new_routine(standard_code))
        row.addWidget(new_btn)
        load_btn = QPushButton("Carregar")
        load_btn.clicked.connect(lambda: self._load_template(standard_code))
        row.addWidget(load_btn)
        save_btn = QPushButton("Salvar como template...")
        save_btn.clicked.connect(lambda: self._save_template(standard_code))
        row.addWidget(save_btn)
        delete_btn = QPushButton("Excluir")
        delete_btn.clicked.connect(lambda: self._delete_template(standard_code))
        row.addWidget(delete_btn)
        form.addRow("Template:", row)
        self.template_combos[standard_code] = combo
        self._refresh_templates(standard_code)

    def _new_routine(self, standard_code: str) -> None:
        """Limpa o formulário da norma para valores padrão, pronto para montar um roteiro novo do zero."""
        combo = self.template_combos.get(standard_code)
        if combo is not None:
            combo.setCurrentIndex(-1)

        if standard_code == "4-4":
            self.burst_points = self._default_burst_points()
            self._refresh_points_summary("4-4")
        elif standard_code == "4-5":
            self.surge_points = self._default_surge_points()
            self._refresh_points_summary("4-5")
            _set_checked_values(self.surge_phase_combo_list, DEFAULT_PHASE_COMBINATIONS)
        elif standard_code == "4-11":
            self.dips_nominal_spin.setValue(230)
            self.dips_freq_spin.setValue(50)
            _set_checked_values(self.dips_phase_list, [str(a) for a in DIPS_PHASE_ANGLES_DEG])
            self.dips_events_table.setRowCount(0)
            self._add_dips_preset_event()

    def _refresh_templates(self, standard_code: str) -> None:
        combo = self.template_combos[standard_code]
        combo.blockSignals(True)
        combo.clear()
        for tpl in templates.list_templates(standard_code):
            combo.addItem(tpl["name"], tpl)
        combo.blockSignals(False)

    def _save_template(self, standard_code: str) -> None:
        try:
            params, level_label = self._collect_params(standard_code)
        except ValueError as exc:
            QMessageBox.warning(self, "Template", str(exc))
            return
        name, ok = QInputDialog.getText(self, "Salvar template", "Nome do roteiro:")
        if not ok or not name.strip():
            return
        templates.save_template(standard_code, name.strip(), level_label, params)
        self._refresh_templates(standard_code)

    def _load_template(self, standard_code: str) -> None:
        combo = self.template_combos[standard_code]
        tpl = combo.currentData()
        if tpl is None:
            QMessageBox.information(self, "Template", "Nenhum template salvo para esta norma.")
            return
        self._apply_params(standard_code, tpl["params"])

    def _delete_template(self, standard_code: str) -> None:
        combo = self.template_combos[standard_code]
        tpl = combo.currentData()
        if tpl is None:
            return
        confirm = QMessageBox.question(
            self, "Excluir template", f"Excluir o template '{tpl['name']}'?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        templates.delete_template(tpl["id"])
        self._refresh_templates(standard_code)

    # ---- utilitários genéricos de tabela (usados pelo roteiro de dips) ----

    def _move_table_row(self, table: QTableWidget, delta: int) -> None:
        row = table.currentRow()
        if row < 0:
            return
        new_row = row + delta
        if new_row < 0 or new_row >= table.rowCount():
            return
        for col in range(table.columnCount()):
            item_a = table.takeItem(row, col)
            item_b = table.takeItem(new_row, col)
            table.setItem(row, col, item_b)
            table.setItem(new_row, col, item_a)
        table.setCurrentCell(new_row, 0)

    def _remove_table_row(self, table: QTableWidget) -> None:
        row = table.currentRow()
        if row >= 0:
            table.removeRow(row)

    # ---- roteiro (sequência de pontos) de burst/surge — editado em sub-tela dedicada ----

    def _refresh_points_summary(self, standard_code: str) -> None:
        if standard_code == "4-4":
            list_widget, points = self.burst_summary_list, self.burst_points
        else:
            list_widget, points = self.surge_summary_list, self.surge_points
        list_widget.clear()
        for i, point in enumerate(points):
            list_widget.addItem(f"{i + 1}. {describe_point(standard_code, point)}")

    def _open_routine_editor(self, standard_code: str) -> None:
        points = self.burst_points if standard_code == "4-4" else self.surge_points
        dialog = RoutineEditorDialog(standard_code, points, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if standard_code == "4-4":
                self.burst_points = dialog.get_points()
            else:
                self.surge_points = dialog.get_points()
            self._refresh_points_summary(standard_code)

    def _default_burst_points(self) -> list[dict]:
        return [
            {
                "voltage": BURST_LEVELS[0].voltage,
                "frequency_hz": BURST_SPIKE_FREQUENCIES_HZ[0],
                "coupling": "COM",
                "polarity": "+",
                "duration_s": BURST_DEFAULT_DURATION_S,
            }
        ]

    def _default_surge_points(self) -> list[dict]:
        return [
            {
                "voltage": SURGE_LEVELS[0].voltage,
                "coupling": SURGE_COUPLINGS[0],
                "polarity": "+",
                "phase_angle": 0,
                "pulse_count": SURGE_DEFAULT_PULSE_COUNT,
                "interval_s": SURGE_DEFAULT_INTERVAL_S,
            }
        ]

    # ---- páginas de parâmetros por norma ----

    def _build_burst_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(
            QLabel(
                "Roteiro de burst (IEC 61000-4-4) — sequência de pontos, executados na ordem abaixo.\n"
                "Clique em \"Editar roteiro...\" para montar a sequência (sempre dá para adicionar o "
                "polo + e o polo − juntos, de uma vez)."
            )
        )
        self.burst_summary_list = QListWidget()
        self.burst_summary_list.setMinimumHeight(160)
        layout.addWidget(self.burst_summary_list, 1)

        edit_row = QHBoxLayout()
        edit_btn = QPushButton("Editar roteiro...")
        edit_btn.clicked.connect(lambda: self._open_routine_editor("4-4"))
        edit_row.addWidget(edit_btn)
        layout.addLayout(edit_row)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-4")
        layout.addLayout(template_form)

        self.burst_points = self._default_burst_points()
        self._refresh_points_summary("4-4")
        return page

    def _build_surge_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        surge_phase_hint = QLabel(
            "Combinações de fase a testar (medidor bi/trifásico) — marque as que se aplicam "
            "ao seu medidor. O mesmo roteiro roda uma vez por combinação marcada; o ensaio "
            "pausa entre uma e outra e avisa no log para trocar o setup."
        )
        surge_phase_hint.setWordWrap(True)
        layout.addWidget(surge_phase_hint)
        self.surge_phase_combo_list = _checkable_list(list(SURGE_METER_PHASE_COMBINATIONS))
        self.surge_phase_combo_list.setMaximumHeight(190)
        _set_checked_values(self.surge_phase_combo_list, DEFAULT_PHASE_COMBINATIONS)
        layout.addWidget(self.surge_phase_combo_list)

        surge_routine_hint = QLabel(
            "Roteiro de surge (IEC 61000-4-5) — sequência de pontos, executados na ordem abaixo.\n"
            "Clique em \"Editar roteiro...\" para montar a sequência (sempre dá para adicionar o "
            "polo + e o polo − juntos, de uma vez, ou a grade completa de ângulos × polos)."
        )
        surge_routine_hint.setWordWrap(True)
        layout.addWidget(surge_routine_hint)
        self.surge_summary_list = QListWidget()
        self.surge_summary_list.setMinimumHeight(160)
        layout.addWidget(self.surge_summary_list, 1)

        edit_row = QHBoxLayout()
        edit_btn = QPushButton("Editar roteiro...")
        edit_btn.clicked.connect(lambda: self._open_routine_editor("4-5"))
        edit_row.addWidget(edit_btn)
        layout.addLayout(edit_row)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-5")
        layout.addLayout(template_form)

        self.surge_points = self._default_surge_points()
        self._refresh_points_summary("4-5")
        return page

    def _build_dips_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.dips_nominal_spin = QDoubleSpinBox()
        self.dips_nominal_spin.setRange(1, 300)
        self.dips_nominal_spin.setValue(230)
        self.dips_nominal_spin.setSuffix(" V")
        form.addRow("Tensão nominal (Un):", self.dips_nominal_spin)

        self.dips_freq_spin = QDoubleSpinBox()
        self.dips_freq_spin.setRange(15, 1000)
        self.dips_freq_spin.setValue(50)
        self.dips_freq_spin.setSuffix(" Hz")
        form.addRow("Frequência:", self.dips_freq_spin)

        self.dips_phase_list = _checkable_list([str(a) for a in DIPS_PHASE_ANGLES_DEG])
        form.addRow("Ângulos de fase (°):", self.dips_phase_list)

        layout.addLayout(form)

        dips_hint_label = QLabel(
            "Roteiro de eventos (dips/interrupções) — editável, na ordem de execução: o app "
            "passa por TODAS as linhas uma vez (repetição 1 de cada), depois volta pra "
            "primeira linha e repete (repetição 2 de cada), e assim por diante até completar "
            "as Repetições de cada linha — uma linha que já completou suas repetições é "
            "pulada nas voltas seguintes. Ciclos é quanto tempo dura a queda em si; "
            "Intervalo é a pausa em tensão nominal antes de cada repetição dessa linha. "
            "Ângulos em branco usam os ângulos marcados acima; ângulo 0/padrão aplica "
            "direto (VOLT); qualquer outro ângulo dispara sincronizado via modo LIST do "
            "equipamento."
        )
        dips_hint_label.setWordWrap(True)
        layout.addWidget(dips_hint_label)
        self.dips_events_table = QTableWidget(0, 5)
        self.dips_events_table.setHorizontalHeaderLabels(
            ["% de queda (100 = interrupção)", "Ciclos", "Repetições", "Intervalo (ciclos)", "Ângulos (°)"]
        )
        self.dips_events_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.dips_events_table.setMinimumHeight(260)
        layout.addWidget(self.dips_events_table)

        preset_row = QHBoxLayout()
        self.dips_preset_combo = QComboBox()
        for level in DIPS_LEVELS:
            self.dips_preset_combo.addItem(
                f"Nível {level.level} — {level.percent_un}% de queda, {level.cycles:g} ciclo(s)",
                (level.percent_un, level.cycles),
            )
        self.dips_preset_combo.addItem(
            f"Interrupção curta — {DIPS_SHORT_INTERRUPTION_CYCLES:g} ciclo(s)",
            (100, DIPS_SHORT_INTERRUPTION_CYCLES),
        )
        add_preset_btn = QPushButton("Adicionar nível padrão ao roteiro")
        add_preset_btn.clicked.connect(self._add_dips_preset_event)
        preset_row.addWidget(self.dips_preset_combo, 1)
        preset_row.addWidget(add_preset_btn)
        layout.addLayout(preset_row)

        events_btn_row = QHBoxLayout()
        add_row_btn = QPushButton("Adicionar linha em branco")
        add_row_btn.clicked.connect(self._add_dips_blank_event)
        remove_row_btn = QPushButton("Remover linha selecionada")
        remove_row_btn.clicked.connect(lambda: self._remove_table_row(self.dips_events_table))
        up_btn = QPushButton("▲ Mover para cima")
        up_btn.clicked.connect(lambda: self._move_table_row(self.dips_events_table, -1))
        down_btn = QPushButton("▼ Mover para baixo")
        down_btn.clicked.connect(lambda: self._move_table_row(self.dips_events_table, 1))
        events_btn_row.addWidget(add_row_btn)
        events_btn_row.addWidget(remove_row_btn)
        events_btn_row.addWidget(up_btn)
        events_btn_row.addWidget(down_btn)
        layout.addLayout(events_btn_row)

        template_form = QFormLayout()
        self._add_template_controls(template_form, "4-11")
        layout.addLayout(template_form)

        self.dips_counter_sync_checkbox = QCheckBox("Sincronizar com o contador (relógio)")
        layout.addWidget(self.dips_counter_sync_checkbox)
        counter_sync_hint = QLabel(
            "Lê o pulso do medidor antes de iniciar e o próximo pulso assim que o "
            "ensaio terminar, e registra o tempo do ensaio medido por esse intervalo."
        )
        counter_sync_hint.setWordWrap(True)
        layout.addWidget(counter_sync_hint)

        self._add_dips_preset_event()
        return page

    def _add_dips_preset_event(self) -> None:
        percent_un, cycles = self.dips_preset_combo.currentData()
        self._append_dips_row(percent_un, cycles)

    def _add_dips_blank_event(self) -> None:
        self._append_dips_row(40, 12)

    def _append_dips_row(
        self,
        percent_un: float,
        cycles: float,
        count: int = 1,
        interval_cycles: float = 0,
        phase_angles: str = "",
    ) -> None:
        row = self.dips_events_table.rowCount()
        self.dips_events_table.insertRow(row)
        self.dips_events_table.setItem(row, 0, QTableWidgetItem(str(percent_un)))
        self.dips_events_table.setItem(row, 1, QTableWidgetItem(str(cycles)))
        self.dips_events_table.setItem(row, 2, QTableWidgetItem(str(count)))
        self.dips_events_table.setItem(row, 3, QTableWidgetItem(str(interval_cycles) if interval_cycles else ""))
        self.dips_events_table.setItem(row, 4, QTableWidgetItem(phase_angles))

    def _on_standard_changed(self, index: int) -> None:
        self.params_stack.setCurrentIndex(index)
        standard_code = self.standard_combo.itemData(index)
        supports_test_on = standard_code in ("4-4", "4-5")
        self.test_on_widget.setVisible(supports_test_on)
        if self._manual_driver is not None and self._manual_driver_standard != standard_code:
            self._disconnect_manual_driver()

    # ---- projeto ----

    def refresh_projects(self) -> None:
        current = self.project_combo.currentData()
        self.project_combo.clear()
        for project in planner.list_projects():
            self.project_combo.addItem(project["name"], project["id"])
        if current is not None:
            index = self.project_combo.findData(current)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)

    def preselect(self, project_id: int, standard_code: str) -> None:
        self.refresh_projects()
        p_index = self.project_combo.findData(project_id)
        if p_index >= 0:
            self.project_combo.setCurrentIndex(p_index)
        s_index = self.standard_combo.findData(standard_code)
        if s_index >= 0:
            self.standard_combo.setCurrentIndex(s_index)

    # ---- montagem / restauração de parâmetros ----

    def _collect_params(self, standard_code: str) -> tuple[dict, str]:
        if standard_code == "4-4":
            if not self.burst_points:
                raise ValueError("Adicione ao menos um ponto ao roteiro de burst antes de continuar.")
            params = {"points": self.burst_points}
            voltages = {p["voltage"] for p in self.burst_points}
            voltage_desc = f"{self.burst_points[0]['voltage']:.0f} V" if len(voltages) == 1 else "tensões variadas"
            label = f"Roteiro com {len(self.burst_points)} ponto(s), {voltage_desc}"
            return params, label

        if standard_code == "4-5":
            if not self.surge_points:
                raise ValueError("Adicione ao menos um ponto ao roteiro de surge antes de continuar.")
            combinations = [
                combo
                for combo in SURGE_METER_PHASE_COMBINATIONS
                if combo in _checked_values(self.surge_phase_combo_list)
            ]
            if not combinations:
                raise ValueError("Marque ao menos uma combinação de fase (ex: L1-N) antes de continuar.")
            params = {"points": self.surge_points, "phase_combinations": combinations}
            voltages = {p["voltage"] for p in self.surge_points}
            voltage_desc = f"{self.surge_points[0]['voltage']:.0f} V" if len(voltages) == 1 else "tensões variadas"
            label = (
                f"Roteiro com {len(self.surge_points)} ponto(s), {voltage_desc}, "
                f"{len(combinations)} combinação(ões) de fase ({', '.join(combinations)})"
            )
            return params, label

        if standard_code == "4-11":
            nominal = self.dips_nominal_spin.value()
            events = []
            for row in range(self.dips_events_table.rowCount()):
                percent_item = self.dips_events_table.item(row, 0)
                cycles_item = self.dips_events_table.item(row, 1)
                count_item = self.dips_events_table.item(row, 2)
                interval_item = self.dips_events_table.item(row, 3)
                angles_item = self.dips_events_table.item(row, 4)
                if percent_item is None or cycles_item is None:
                    continue
                percent_un = float(percent_item.text())
                cycles = float(cycles_item.text())
                event = {"percent_un": percent_un, "cycles": cycles}
                count_text = count_item.text().strip() if count_item else ""
                event["count"] = int(count_text) if count_text else 1
                interval_text = interval_item.text().strip() if interval_item else ""
                if interval_text:
                    event["interval_cycles"] = float(interval_text)
                angles_text = angles_item.text().strip() if angles_item else ""
                if angles_text:
                    event["phase_angles"] = [int(a.strip()) for a in angles_text.split(",") if a.strip()]
                events.append(event)
            if not events:
                raise ValueError("Adicione ao menos um evento ao roteiro de dips antes de continuar.")
            default_angles = [int(a) for a in _checked_values(self.dips_phase_list)] or [0]
            params = {
                "nominal_voltage": nominal,
                "frequency_hz": self.dips_freq_spin.value(),
                "phase_angles": default_angles,
                "events": events,
            }
            total_pulses = sum(
                event.get("count", 1) * len(event.get("phase_angles") or default_angles) for event in events
            )
            label = f"Roteiro com {len(events)} linha(s), {total_pulses} pulso(s), Un={nominal:.0f} V"
            return params, label

        raise ValueError(standard_code)

    def _apply_params(self, standard_code: str, params: dict) -> None:
        if standard_code == "4-4":
            self.burst_points = burst_params_to_points(params)
            self._refresh_points_summary("4-4")

        elif standard_code == "4-5":
            self.surge_points = surge_params_to_points(params)
            self._refresh_points_summary("4-5")
            combinations = params.get("phase_combinations")
            if not combinations:
                # compatibilidade com o formato anterior (meter_elements: int, sem escolha de fase)
                meter_elements = params.get("meter_elements", 1)
                combinations = list(SURGE_METER_PHASE_COMBINATIONS[:meter_elements]) or DEFAULT_PHASE_COMBINATIONS
            _set_checked_values(self.surge_phase_combo_list, combinations)

        elif standard_code == "4-11":
            self.dips_nominal_spin.setValue(params["nominal_voltage"])
            self.dips_freq_spin.setValue(params["frequency_hz"])
            _set_checked_values(self.dips_phase_list, [str(a) for a in params["phase_angles"]])
            self.dips_events_table.setRowCount(0)
            for event in params["events"]:
                percent_un = 100 if event.get("interruption") else event["percent_un"]
                count = event.get("count", 1)
                interval_cycles = event.get("interval_cycles", 0)
                angles = ",".join(str(a) for a in event["phase_angles"]) if event.get("phase_angles") else ""
                self._append_dips_row(percent_un, event["cycles"], count, interval_cycles, angles)

    # ---- execução ----

    def _start_test(self) -> None:
        project_id = self.project_combo.currentData()
        if project_id is None:
            QMessageBox.warning(self, "Ensaio", "Selecione um projeto antes de iniciar.")
            return
        standard_code = self.standard_combo.currentData()
        try:
            params, level_label = self._collect_params(standard_code)
        except ValueError as exc:
            QMessageBox.warning(self, "Ensaio", str(exc))
            return
        if not self.eut_name_edit.text().strip():
            QMessageBox.warning(self, "Ensaio", "Informe o EUT antes de iniciar.")
            return

        self._disconnect_manual_driver()

        counter = None
        counter_recall_register = None
        if standard_code == "4-11" and self.dips_counter_sync_checkbox.isChecked():
            counter = build_agilent_counter_driver()
            counter_recall_register = self.counter_recall_spin.value()

        driver = build_driver_for_standard(standard_code)
        self.worker = TestSessionWorker(
            driver=driver,
            project_id=project_id,
            standard_code=standard_code,
            eut_name=self.eut_name_edit.text().strip(),
            eut_serial=self.eut_serial_edit.text().strip(),
            operator=self.operator_edit.text().strip(),
            level_label=level_label,
            params=params,
            counter=counter,
            counter_recall_register=counter_recall_register,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.paused.connect(self._on_paused)
        self.worker.finished_session.connect(self._on_finished)
        self.log_view.clear()
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(True)
        self.stop_btn.setEnabled(True)
        self.test_on_btn.setEnabled(False)
        self.worker.start()

    # ---- TEST ON manual (fora de um ensaio automatizado) ----

    def _toggle_test_on(self, checked: bool) -> None:
        standard_code = self.standard_combo.currentData()
        if checked:
            try:
                if self._manual_driver is None or self._manual_driver_standard != standard_code:
                    self._close_manual_driver()
                    driver = build_driver_for_standard(standard_code)
                    driver.connect()
                    self._manual_driver = driver
                    self._manual_driver_standard = standard_code
                self._manual_driver.set_test_on(True)
                self.test_on_btn.setText("TEST ON (ligado) — clique para desligar")
            except Exception as exc:
                QMessageBox.warning(self, "TEST ON", f"Não foi possível ligar o TEST ON: {exc}")
                self._close_manual_driver()
                self.test_on_btn.blockSignals(True)
                self.test_on_btn.setChecked(False)
                self.test_on_btn.blockSignals(False)
        else:
            self._close_manual_driver()
            self.test_on_btn.setText("TEST ON (ligar saída do UCS 500N)")

    def _close_manual_driver(self) -> None:
        """Fecha a conexão manual do TEST ON, sem mexer no estado visual do botão
        (usado tanto ao desligar de propósito quanto antes de reconectar em outra norma)."""
        if self._manual_driver is not None:
            try:
                self._manual_driver.set_test_on(False)
            except Exception:
                pass
            try:
                self._manual_driver.disconnect()
            except Exception:
                pass
            self._manual_driver = None
            self._manual_driver_standard = None

    def _disconnect_manual_driver(self) -> None:
        """Fecha a conexão manual do TEST ON e reseta o botão pro estado desligado."""
        self._close_manual_driver()
        self.test_on_btn.blockSignals(True)
        self.test_on_btn.setChecked(False)
        self.test_on_btn.setText("TEST ON (ligar saída do UCS 500N)")
        self.test_on_btn.blockSignals(False)

    def _pause_test(self) -> None:
        if self.worker is not None:
            self.worker.request_pause()

    def _stop_test(self) -> None:
        if self.worker is not None:
            self.worker.request_stop()

    def _on_progress(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {message}")

    def _on_paused(self, message: str) -> None:
        self.log_view.appendPlainText(f"*** PAUSA: {message} ***")
        self._alert_operator()
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Pausa no ensaio")
        box.setText(f"ATENÇÃO:\n\n{message}")
        continue_btn = box.addButton("Continuar ensaio", QMessageBox.ButtonRole.AcceptRole)
        abort_btn = box.addButton("Abortar ensaio", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(continue_btn)
        box.exec()
        if self.worker is None:
            return
        if box.clickedButton() == abort_btn:
            self.worker.request_stop()
        else:
            self.worker.resume()

    def _alert_operator(self) -> None:
        """Chama a atenção do operador para uma pausa que exige troca física de ligação:
        buzzer (beeps, se habilitado nas configurações) + piscar a janela na barra de
        tarefas + trazer a janela pra frente."""
        if runtime_settings.buzzer_enabled:
            try:
                import winsound

                for _ in range(3):
                    winsound.Beep(1200, 250)
            except Exception:
                pass
        window = self.window()
        QApplication.alert(window)
        window.raise_()
        window.activateWindow()

    def _on_finished(self, session_id: int) -> None:
        self.start_btn.setEnabled(True)
        self.pause_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        self.test_on_btn.setEnabled(True)
        self.log_view.appendPlainText("--- Ensaio finalizado ---")

        result, ok = QInputDialog.getItem(
            self, "Resultado do ensaio", "Resultado:", ["aprovado", "reprovado"], 0, False
        )
        if ok:
            set_session_result(session_id, result)

        project_id = self.project_combo.currentData()
        standard_code = self.standard_combo.currentData()
        item = planner.find_item(project_id, standard_code)
        if item is not None:
            planner.link_item_session(item["id"], session_id)

    # ---- contador de frequência RTC/Timer (Agilent 53131A) ----

    def _start_counter(self) -> None:
        if self._counter_worker is not None:
            return
        project_id = self.project_combo.currentData()
        if project_id is None:
            QMessageBox.warning(self, "Contador RTC", "Selecione um projeto antes de iniciar.")
            return

        counter = build_agilent_counter_driver()
        self.counter_table.setRowCount(0)
        self._counter_project_id = project_id
        self._counter_log_path = None

        mode = self.counter_mode_combo.currentData()
        needs_gate = mode == "manual"
        uses_recall_register = mode in ("recall", "stopwatch")
        recall_register = self.counter_recall_spin.value() if uses_recall_register else None
        gate_time = self.counter_gate_spin.value() if needs_gate else None
        interval = self.counter_interval_spin.value() if needs_gate else None

        if mode == "stopwatch":
            self.counter_file_label.setText("")
            self.counter_stopwatch_status.setText("Conectando e capturando o valor inicial...")
            self.counter_stopwatch_status.setVisible(True)
        else:
            self.counter_stopwatch_status.setVisible(False)
            self.counter_file_label.setText("Aguardando a primeira leitura...")

        self._counter_worker = CounterWorker(
            counter,
            gate_time,
            interval,
            mode=mode,
            recall_register=recall_register,
            parent=self,
        )
        self._counter_worker.reading.connect(self._on_counter_reading)
        self._counter_worker.stopwatch_started.connect(self._on_counter_stopwatch_started)
        self._counter_worker.error.connect(self._on_counter_error)
        self._counter_worker.stopped.connect(self._on_counter_stopped)
        self.counter_start_btn.setEnabled(False)
        self.counter_stop_btn.setEnabled(True)
        self.counter_mode_combo.setEnabled(False)
        self.counter_recall_spin.setEnabled(False)
        self.counter_gate_spin.setEnabled(False)
        self.counter_interval_spin.setEnabled(False)
        self.counter_decimals_spin.setEnabled(False)
        self._counter_worker.start()

    def _on_counter_mode_changed(self, _index: int) -> None:
        mode = self.counter_mode_combo.currentData()
        is_recall = mode == "recall"
        is_stopwatch = mode == "stopwatch"
        needs_gate = mode == "manual"
        self.counter_recall_spin.setVisible(is_recall or is_stopwatch)
        self._counter_recall_label.setVisible(is_recall or is_stopwatch)
        self.counter_gate_spin.setVisible(needs_gate)
        self._counter_gate_label.setVisible(needs_gate)
        self.counter_interval_spin.setVisible(needs_gate)
        self._counter_interval_label.setVisible(needs_gate)
        self.counter_recall_hint.setVisible(is_recall)
        self.counter_start_btn.setText(
            "Iniciar cronômetro" if is_stopwatch else "Iniciar leitura contínua"
        )
        self.counter_stop_btn.setText("Finalizar cronômetro" if is_stopwatch else "Parar")

    def _stop_counter(self) -> None:
        if self._counter_worker is not None:
            self.counter_stop_btn.setEnabled(False)
            self._counter_worker.request_stop()

    def _format_counter_value(self, value: float) -> str:
        """Ajusta onde entra a vírgula no valor bruto (o contador manda um
        inteiro sem separador — ex.: 299998739 — e o operador informa quantas
        casas decimais contar da direita pra chegar no valor real, ex.:
        29,9998739 com 7 casas). Não altera o valor medido, só a exibição."""
        decimals = self.counter_decimals_spin.value()
        if decimals <= 0:
            return f"{value:.0f}"
        return f"{value / (10 ** decimals):.{decimals}f}"

    def _on_counter_reading(self, timestamp: str, value: float) -> None:
        formatted = self._format_counter_value(value)
        row = self.counter_table.rowCount()
        self.counter_table.insertRow(row)
        self.counter_table.setItem(row, 0, QTableWidgetItem(timestamp))
        self.counter_table.setItem(row, 1, QTableWidgetItem(formatted))
        self.counter_table.scrollToBottom()

        if self._counter_project_id is None:
            return
        folder = project_files.get_project_folder(self._counter_project_id)
        if self._counter_log_path is None:
            name = datetime.now().strftime("contador_rtc_%Y%m%d_%H%M%S.txt")
            self._counter_log_path = folder / name
        with open(self._counter_log_path, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} | {formatted}\n")
        self.counter_file_label.setText(f"Salvando em: {self._counter_log_path.name}")

    def _on_counter_stopwatch_started(self, timestamp: str, value: float) -> None:
        formatted = self._format_counter_value(value)
        self.counter_stopwatch_status.setText(
            f"Cronômetro iniciado às {timestamp} — valor inicial: {formatted}. "
            "Clique em \"Finalizar cronômetro\" quando quiser encerrar."
        )

    def _on_counter_error(self, message: str) -> None:
        QMessageBox.warning(self, "Contador RTC", f"Erro na leitura do contador: {message}")

    def _on_counter_stopped(self) -> None:
        self._counter_worker = None
        if self._counter_log_path is not None:
            self.counter_file_label.setText(f"Salvo em: {self._counter_log_path.name}")
        self.counter_start_btn.setEnabled(True)
        self.counter_stop_btn.setEnabled(False)
        self.counter_mode_combo.setEnabled(True)
        self.counter_recall_spin.setEnabled(True)
        self.counter_gate_spin.setEnabled(True)
        self.counter_interval_spin.setEnabled(True)
        self.counter_decimals_spin.setEnabled(True)
