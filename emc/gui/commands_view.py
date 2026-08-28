from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from emc.core import command_overrides
from emc.instruments import agilent_53131a_commands, chroma_commands, ucs500n_commands
from emc.instruments.factory import (
    build_agilent_counter_driver,
    build_chroma_driver,
    build_ucs500n_driver,
)

INSTRUMENT_LABELS = {
    "ucs500n": "EM TEST UCS 500N",
    "chroma": "Chroma 61501/61504",
    "agilent_53131a": "Contador Agilent 53131A",
}

COMMAND_MODULES = {
    "ucs500n": ucs500n_commands,
    "chroma": chroma_commands,
    "agilent_53131a": agilent_53131a_commands,
}

COMMAND_FIELDS = {
    "ucs500n": [
        ("SELECT_BURST_MENU", "Selecionar menu Burst"),
        ("SELECT_SURGE_MENU", "Selecionar menu Surge"),
        ("TEST_ON", "TEST ON (ligar saída)"),
        ("TEST_OFF", "TEST OFF (desligar saída)"),
        ("SET_BURST_VOLTAGE", "Burst — tensão (use {voltage})"),
        ("SET_BURST_FREQUENCY", "Burst — frequência (use {frequency_hz})"),
        ("SET_BURST_COUPLING", "Burst — acoplamento (use {coupling})"),
        ("SET_BURST_POLARITY", "Burst — polaridade (use {polarity})"),
        ("SET_SURGE_VOLTAGE", "Surge — tensão (use {voltage})"),
        ("SET_SURGE_PHASE_ANGLE", "Surge — ângulo (use {angle_deg})"),
        ("SET_SURGE_COUPLING", "Surge — acoplamento (use {coupling})"),
        ("SET_SURGE_POLARITY", "Surge — polaridade (use {polarity})"),
        ("TRIGGER_SINGLE_EVENT", "Disparar pulso único"),
        ("STOP_TEST", "Parar ensaio"),
        ("QUERY_STATUS", "Consultar status"),
    ],
    "chroma": [
        ("IDN_QUERY", "Consultar identificação"),
        ("RESET", "Reset"),
        ("CLEAR_STATUS", "Limpar status"),
        ("OUTPUT_STATE", "Saída ON/OFF (use {state})"),
        ("VOLTAGE_RANGE", "Faixa de tensão (use {range}: LOW/HIGH/AUTO)"),
        ("SET_VOLTAGE_AC", "Tensão AC (use {voltage})"),
        ("SET_FREQUENCY", "Frequência (use {frequency_hz})"),
        ("ERROR_QUERY", "Consultar erro"),
    ],
    "agilent_53131a": [
        ("IDN_QUERY", "Consultar identificação"),
        ("RECALL", "Recall (use {register})"),
        ("CONFIGURE_TOTALIZE_TIMED", "Configurar totalize com gate (use {gate_time_s})"),
        ("INIT", "Disparar medição (INIT)"),
        ("FETCH", "Consultar resultado (FETCh?)"),
    ],
}

TERMINAL_FACTORIES = {
    "ucs500n": build_ucs500n_driver,
    "chroma": build_chroma_driver,
    "agilent_53131a": build_agilent_counter_driver,
}

CONFIRMED_HINT = (
    "Valores confirmados no manual oficial do fabricante — só edite se "
    "descobrir uma variação real (outro modelo/firmware)."
)
UNCONFIRMED_HINT = (
    "O dicionário de comandos oficial do fabricante não é público, então os "
    "valores abaixo são tentativas, não confirmados. Descubra os certos "
    "testando no Terminal GPIB acima e cole aqui embaixo."
)


class CommandsView(QWidget):
    """Terminal GPIB (comando bruto) + editor de comandos por equipamento —
    separado de Configurações porque cresceu e é sobre outra coisa (o que
    mandar pro instrumento, não como conectar nele)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._terminal_driver = None
        self.command_edits: dict[str, QLineEdit] = {}
        layout = QVBoxLayout(self)

        terminal_hint = QLabel(
            "Terminal GPIB (comando bruto) — pra descobrir/testar os comandos reais de um "
            "instrumento na mão, digitando direto (ex: enquanto não se tem o dicionário de "
            "comandos do UCS 500N)."
        )
        terminal_hint.setWordWrap(True)
        layout.addWidget(terminal_hint)
        terminal_top_row = QHBoxLayout()
        self.terminal_instrument_combo = QComboBox()
        for key, label in INSTRUMENT_LABELS.items():
            self.terminal_instrument_combo.addItem(label, key)
        terminal_top_row.addWidget(self.terminal_instrument_combo)
        self.terminal_connect_btn = QPushButton("Conectar")
        self.terminal_connect_btn.setCheckable(True)
        self.terminal_connect_btn.toggled.connect(self._toggle_terminal_connection)
        terminal_top_row.addWidget(self.terminal_connect_btn)
        terminal_top_row.addStretch(1)
        layout.addLayout(terminal_top_row)

        self.terminal_log = QPlainTextEdit()
        self.terminal_log.setReadOnly(True)
        self.terminal_log.setMaximumHeight(160)
        layout.addWidget(self.terminal_log)

        terminal_input_row = QHBoxLayout()
        self.terminal_command_edit = QLineEdit()
        self.terminal_command_edit.setPlaceholderText(
            "Digite um comando (ex: *IDN?, TEST ON, OUTP ON...) e Enter consulta"
        )
        self.terminal_command_edit.returnPressed.connect(self._terminal_query)
        terminal_input_row.addWidget(self.terminal_command_edit, 1)
        terminal_write_btn = QPushButton("Enviar (write)")
        terminal_write_btn.clicked.connect(self._terminal_write)
        terminal_input_row.addWidget(terminal_write_btn)
        terminal_query_btn = QPushButton("Consultar (query)")
        terminal_query_btn.clicked.connect(self._terminal_query)
        terminal_input_row.addWidget(terminal_query_btn)
        layout.addLayout(terminal_input_row)

        cmd_top_row = QHBoxLayout()
        cmd_top_row.addWidget(QLabel("Comandos (editável) do equipamento:"))
        self.commands_instrument_combo = QComboBox()
        for key, label in INSTRUMENT_LABELS.items():
            self.commands_instrument_combo.addItem(label, key)
        self.commands_instrument_combo.currentIndexChanged.connect(self._rebuild_command_fields)
        cmd_top_row.addWidget(self.commands_instrument_combo, 1)
        layout.addLayout(cmd_top_row)

        self.commands_hint = QLabel("")
        self.commands_hint.setWordWrap(True)
        layout.addWidget(self.commands_hint)

        self.cmd_form_container = QWidget()
        self.cmd_form = QFormLayout(self.cmd_form_container)
        layout.addWidget(self.cmd_form_container)

        cmd_btn_row = QHBoxLayout()
        save_cmd_btn = QPushButton("Salvar comandos")
        save_cmd_btn.clicked.connect(self._save_commands)
        cmd_btn_row.addWidget(save_cmd_btn)
        restore_cmd_btn = QPushButton("Restaurar tentativas padrão")
        restore_cmd_btn.clicked.connect(self._restore_commands)
        cmd_btn_row.addWidget(restore_cmd_btn)
        self.commands_status = QLabel("")
        cmd_btn_row.addWidget(self.commands_status, 1)
        layout.addLayout(cmd_btn_row)

        layout.addStretch()

        self._rebuild_command_fields(0)

    # ---- terminal GPIB (comando bruto) ----

    def _terminal_log_line(self, text: str) -> None:
        self.terminal_log.appendPlainText(text)

    def _toggle_terminal_connection(self, checked: bool) -> None:
        if checked:
            instrument = self.terminal_instrument_combo.currentData()
            factory = TERMINAL_FACTORIES[instrument]
            try:
                driver = factory()
                driver.connect()
                self._terminal_driver = driver
                self.terminal_connect_btn.setText("Desconectar")
                self.terminal_instrument_combo.setEnabled(False)
                self._terminal_log_line(
                    f"-- conectado ({self.terminal_instrument_combo.currentText()}) --"
                )
            except Exception as exc:
                self._terminal_log_line(f"-- erro ao conectar: {exc} --")
                self.terminal_connect_btn.blockSignals(True)
                self.terminal_connect_btn.setChecked(False)
                self.terminal_connect_btn.blockSignals(False)
        else:
            if self._terminal_driver is not None:
                try:
                    self._terminal_driver.disconnect()
                except Exception:
                    pass
                self._terminal_driver = None
            self.terminal_connect_btn.setText("Conectar")
            self.terminal_instrument_combo.setEnabled(True)
            self._terminal_log_line("-- desconectado --")

    def _terminal_write(self) -> None:
        command = self.terminal_command_edit.text().strip()
        if not command:
            return
        if self._terminal_driver is None:
            self._terminal_log_line("-- conecte antes de enviar um comando --")
            return
        try:
            self._terminal_driver.write(command)
            self._terminal_log_line(f"> {command}")
        except Exception as exc:
            self._terminal_log_line(f"-- erro: {exc} --")

    def _terminal_query(self) -> None:
        command = self.terminal_command_edit.text().strip()
        if not command:
            return
        if self._terminal_driver is None:
            self._terminal_log_line("-- conecte antes de consultar um comando --")
            return
        try:
            response = self._terminal_driver.query(command)
            self._terminal_log_line(f"> {command}")
            self._terminal_log_line(f"< {response}")
        except Exception as exc:
            self._terminal_log_line(f"-- erro: {exc} --")

    # ---- comandos editáveis (sobrescrita salva em disco, por equipamento) ----

    def _rebuild_command_fields(self, _index: int) -> None:
        while self.cmd_form.rowCount():
            self.cmd_form.removeRow(0)
        self.command_edits.clear()

        instrument = self.commands_instrument_combo.currentData()
        module = COMMAND_MODULES[instrument]
        overrides = command_overrides.load_overrides(instrument)
        for key, label in COMMAND_FIELDS[instrument]:
            edit = QLineEdit(overrides.get(key, getattr(module, key)))
            self.cmd_form.addRow(f"{label}:", edit)
            self.command_edits[key] = edit

        self.commands_hint.setText(CONFIRMED_HINT if instrument != "ucs500n" else UNCONFIRMED_HINT)
        self.commands_status.setText("")

    def _save_commands(self) -> None:
        instrument = self.commands_instrument_combo.currentData()
        overrides = {key: edit.text() for key, edit in self.command_edits.items()}
        command_overrides.save_overrides(instrument, overrides)
        self.commands_status.setStyleSheet("color: green;")
        self.commands_status.setText("Salvo — já vale pro próximo uso desse equipamento.")

    def _restore_commands(self) -> None:
        instrument = self.commands_instrument_combo.currentData()
        module = COMMAND_MODULES[instrument]
        for key, edit in self.command_edits.items():
            edit.setText(getattr(module, key))
        self.commands_status.setStyleSheet("")
        self.commands_status.setText("Restaurado para os valores padrão (não salvo ainda).")
