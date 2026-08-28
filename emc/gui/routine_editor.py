"""Sub-tela dedicada para montar o roteiro (sequência de pontos) de burst/surge,
com atalhos para o caso mais comum: adicionar o mesmo ponto nos polos + e -."""

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from emc.core.standards import (
    BURST_LEVELS,
    BURST_SPIKE_FREQUENCIES_HZ,
    SURGE_COUPLINGS,
    SURGE_LEVELS,
)


def describe_point(standard_code: str, point: dict) -> str:
    polarity = point.get("polarity", "+")
    if standard_code == "4-4":
        freq = point.get("frequency_hz", 5000)
        return (
            f"{point['voltage']:.0f} V · {freq / 1000:.0f} kHz · {point.get('coupling', 'COM')} · "
            f"polo {polarity} · {point.get('duration_s', 60):.0f} s"
        )
    return (
        f"{point['voltage']:.0f} V · {point.get('coupling', 'L-N')} · polo {polarity} · "
        f"{point.get('phase_angle', 0)}° · {point.get('pulse_count', 1)} pulso(s) · "
        f"{point.get('interval_s', 1):.0f}s entre pulsos"
    )


class RoutineEditorDialog(QDialog):
    """Editor de roteiro para 4-4 (burst) ou 4-5 (surge): monta uma lista de pontos
    executados em sequência. `points` de entrada não é modificado — o resultado só
    é aplicado pelo chamador se o diálogo for aceito (`exec() == Accepted`)."""

    def __init__(self, standard_code: str, points: list[dict], parent=None):
        super().__init__(parent)
        self.standard_code = standard_code
        self.points = [dict(p) for p in points]
        self._editing_index: int | None = None

        title = "Editar roteiro de Burst (IEC 61000-4-4)" if standard_code == "4-4" else "Editar roteiro de Surge (IEC 61000-4-5)"
        self.setWindowTitle(title)
        self.resize(640, 560)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #b06000;")
        layout.addWidget(self.status_label)

        form = QFormLayout()
        if standard_code == "4-4":
            self._build_burst_fields(form)
        else:
            self._build_surge_fields(form)
        layout.addLayout(form)

        add_row = QHBoxLayout()
        plus_btn = QPushButton("+ Adicionar ponto (polo +)")
        plus_btn.clicked.connect(lambda: self._add_point("+"))
        minus_btn = QPushButton("− Adicionar ponto (polo −)")
        minus_btn.clicked.connect(lambda: self._add_point("-"))
        add_row.addWidget(plus_btn)
        add_row.addWidget(minus_btn)
        layout.addLayout(add_row)

        sequence_row = QHBoxLayout()
        sequence_row.addWidget(QLabel("Gerar sequência — pulsos por polo:"))
        self.polarity_count_spin = QSpinBox()
        self.polarity_count_spin.setRange(1, 200)
        self.polarity_count_spin.setValue(1)
        sequence_row.addWidget(self.polarity_count_spin)
        self.polarity_pattern_combo = QComboBox()
        self.polarity_pattern_combo.addItem("Alternado (+ − + − ...)", "alternate")
        self.polarity_pattern_combo.addItem("Em blocos (todos + depois todos −)", "block")
        sequence_row.addWidget(self.polarity_pattern_combo)
        generate_btn = QPushButton("Gerar sequência de polos")
        generate_btn.clicked.connect(self._add_polarity_sequence)
        sequence_row.addWidget(generate_btn)
        layout.addLayout(sequence_row)

        if standard_code == "4-5":
            grid_row = QHBoxLayout()
            grid_btn = QPushButton("Adicionar todos os ângulos padrão (0/90/180/270) × polos")
            grid_btn.clicked.connect(self._add_full_angle_grid)
            grid_row.addWidget(grid_btn)
            layout.addLayout(grid_row)

        layout.addWidget(QLabel("Sequência do roteiro (ordem de execução):"))
        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        list_btn_row = QHBoxLayout()
        up_btn = QPushButton("▲ Mover para cima")
        up_btn.clicked.connect(lambda: self._move_selected(-1))
        down_btn = QPushButton("▼ Mover para baixo")
        down_btn.clicked.connect(lambda: self._move_selected(1))
        edit_btn = QPushButton("Editar selecionado")
        edit_btn.clicked.connect(self._edit_selected)
        duplicate_btn = QPushButton("Duplicar selecionado")
        duplicate_btn.clicked.connect(self._duplicate_selected)
        remove_btn = QPushButton("Remover selecionado")
        remove_btn.clicked.connect(self._remove_selected)
        clear_btn = QPushButton("Limpar tudo")
        clear_btn.clicked.connect(self._clear_all)
        for btn in (up_btn, down_btn, edit_btn, duplicate_btn, remove_btn, clear_btn):
            list_btn_row.addWidget(btn)
        layout.addLayout(list_btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_list()

    # ---- construção dos campos por norma ----

    def _build_burst_fields(self, form: QFormLayout) -> None:
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        for level in BURST_LEVELS:
            self.preset_combo.addItem(f"Nível {level.level} — {level.voltage} V", level.voltage)
        apply_btn = QPushButton("Aplicar")
        apply_btn.clicked.connect(lambda: self.voltage_spin.setValue(self.preset_combo.currentData()))
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(apply_btn)
        form.addRow("Nível padrão:", preset_row)

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(0, 6000)
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setValue(BURST_LEVELS[0].voltage)
        form.addRow("Tensão:", self.voltage_spin)

        self.freq_combo = QComboBox()
        for freq in BURST_SPIKE_FREQUENCIES_HZ:
            self.freq_combo.addItem(f"{freq / 1000:.0f} kHz", freq)
        form.addRow("Frequência de repetição:", self.freq_combo)

        self.coupling_combo = QComboBox()
        self.coupling_combo.addItems(["COM", "ALL", "CCC"])
        form.addRow("Acoplamento:", self.coupling_combo)

        self.duration_spin = QDoubleSpinBox()
        self.duration_spin.setRange(0.1, 600)
        self.duration_spin.setSuffix(" s")
        self.duration_spin.setValue(60)
        form.addRow("Duração:", self.duration_spin)

    def _build_surge_fields(self, form: QFormLayout) -> None:
        preset_row = QHBoxLayout()
        self.preset_combo = QComboBox()
        for level in SURGE_LEVELS:
            self.preset_combo.addItem(f"Nível {level.level} — {level.voltage} V", level.voltage)
        apply_btn = QPushButton("Aplicar")
        apply_btn.clicked.connect(lambda: self.voltage_spin.setValue(self.preset_combo.currentData()))
        preset_row.addWidget(self.preset_combo, 1)
        preset_row.addWidget(apply_btn)
        form.addRow("Nível padrão:", preset_row)

        self.voltage_spin = QDoubleSpinBox()
        self.voltage_spin.setRange(0, 7000)
        self.voltage_spin.setSuffix(" V")
        self.voltage_spin.setValue(SURGE_LEVELS[0].voltage)
        form.addRow("Tensão:", self.voltage_spin)

        self.coupling_combo = QComboBox()
        self.coupling_combo.addItems(list(SURGE_COUPLINGS))
        form.addRow("Acoplamento:", self.coupling_combo)

        angle_row = QHBoxLayout()
        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(0, 359)
        angle_row.addWidget(self.angle_spin)
        for angle in (0, 90, 180, 270):
            angle_btn = QPushButton(f"{angle}°")
            angle_btn.setMaximumWidth(50)
            angle_btn.clicked.connect(lambda checked=False, a=angle: self.angle_spin.setValue(a))
            angle_row.addWidget(angle_btn)
        form.addRow("Ângulo de fase:", angle_row)

        self.pulse_count_spin = QSpinBox()
        self.pulse_count_spin.setRange(1, 100)
        self.pulse_count_spin.setValue(1)
        form.addRow("Pulsos neste ponto:", self.pulse_count_spin)

        self.interval_spin = QDoubleSpinBox()
        self.interval_spin.setRange(0, 600)
        self.interval_spin.setSuffix(" s")
        self.interval_spin.setValue(1.0)
        form.addRow("Intervalo entre pulsos:", self.interval_spin)

    # ---- valores atuais dos campos (sem polaridade) ----

    def _current_field_values(self) -> dict:
        if self.standard_code == "4-4":
            return {
                "voltage": self.voltage_spin.value(),
                "frequency_hz": self.freq_combo.currentData(),
                "coupling": self.coupling_combo.currentText(),
                "duration_s": self.duration_spin.value(),
            }
        return {
            "voltage": self.voltage_spin.value(),
            "coupling": self.coupling_combo.currentText(),
            "phase_angle": self.angle_spin.value(),
            "pulse_count": self.pulse_count_spin.value(),
            "interval_s": self.interval_spin.value(),
        }

    def _load_fields(self, point: dict) -> None:
        if self.standard_code == "4-4":
            self.voltage_spin.setValue(point.get("voltage", BURST_LEVELS[0].voltage))
            freq_index = self.freq_combo.findData(point.get("frequency_hz", 5000))
            if freq_index >= 0:
                self.freq_combo.setCurrentIndex(freq_index)
            coupling_index = self.coupling_combo.findText(point.get("coupling", "COM"))
            if coupling_index >= 0:
                self.coupling_combo.setCurrentIndex(coupling_index)
            self.duration_spin.setValue(point.get("duration_s", 60))
        else:
            self.voltage_spin.setValue(point.get("voltage", SURGE_LEVELS[0].voltage))
            coupling_index = self.coupling_combo.findText(point.get("coupling", "L-N"))
            if coupling_index >= 0:
                self.coupling_combo.setCurrentIndex(coupling_index)
            self.angle_spin.setValue(point.get("phase_angle", 0))
            self.pulse_count_spin.setValue(point.get("pulse_count", 1))
            self.interval_spin.setValue(point.get("interval_s", 1.0))

    def _refresh_list(self) -> None:
        selected = self.list_widget.currentRow()
        self.list_widget.clear()
        for i, point in enumerate(self.points):
            self.list_widget.addItem(f"{i + 1}. {describe_point(self.standard_code, point)}")
        if 0 <= selected < self.list_widget.count():
            self.list_widget.setCurrentRow(selected)

    def _clear_status(self) -> None:
        self._editing_index = None
        self.status_label.setText("")

    # ---- ações ----

    def _add_point(self, polarity: str) -> None:
        self._clear_status()
        point = self._current_field_values()
        point["polarity"] = polarity
        self.points.append(point)
        self._refresh_list()

    def _add_polarity_sequence(self) -> None:
        """Gera N pulsos de cada polo usando os valores atuais dos campos, alternados
        (+ − + − ...) ou em blocos (todos + depois todos −), conforme escolhido."""
        self._clear_status()
        base = self._current_field_values()
        count = self.polarity_count_spin.value()
        pattern = self.polarity_pattern_combo.currentData()
        if pattern == "block":
            for _ in range(count):
                self.points.append({**base, "polarity": "+"})
            for _ in range(count):
                self.points.append({**base, "polarity": "-"})
        else:
            for _ in range(count):
                self.points.append({**base, "polarity": "+"})
                self.points.append({**base, "polarity": "-"})
        self._refresh_list()

    def _add_full_angle_grid(self) -> None:
        self._clear_status()
        base = self._current_field_values()
        base.pop("phase_angle", None)
        for angle in (0, 90, 180, 270):
            for polarity in ("+", "-"):
                self.points.append({**base, "phase_angle": angle, "polarity": polarity})
        self._refresh_list()

    def _move_selected(self, delta: int) -> None:
        row = self.list_widget.currentRow()
        new_row = row + delta
        if row < 0 or new_row < 0 or new_row >= len(self.points):
            return
        self.points[row], self.points[new_row] = self.points[new_row], self.points[row]
        self._refresh_list()
        self.list_widget.setCurrentRow(new_row)

    def _edit_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        point = self.points.pop(row)
        self._load_fields(point)
        self._editing_index = row
        polarity = point.get("polarity", "+")
        self.status_label.setText(
            f"Editando o ponto {row + 1} (polo {polarity}) — ajuste os campos acima e clique em "
            "'Adicionar ponto' com o polo desejado para salvar."
        )
        self._refresh_list()

    def _duplicate_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            return
        self._clear_status()
        self.points.insert(row + 1, dict(self.points[row]))
        self._refresh_list()
        self.list_widget.setCurrentRow(row + 1)

    def _remove_selected(self) -> None:
        row = self.list_widget.currentRow()
        if row >= 0:
            self._clear_status()
            del self.points[row]
            self._refresh_list()

    def _clear_all(self) -> None:
        self._clear_status()
        self.points = []
        self._refresh_list()

    def get_points(self) -> list[dict]:
        return self.points
