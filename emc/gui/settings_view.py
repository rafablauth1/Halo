import shutil
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from emc import config
from emc.core.comm_test import CommTestWorker
from emc.core.counter_session import RecallWorker
from emc.core.runtime_settings import settings
from emc.instruments.factory import (
    build_agilent_counter_driver,
    build_chroma_driver,
    build_ucs500n_driver,
)


class SettingsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._comm_test_workers: dict[str, CommTestWorker] = {}
        self._recall_worker: RecallWorker | None = None
        layout = QVBoxLayout(self)

        layout.addWidget(self._build_data_dir_box())
        layout.addWidget(self._build_templates_mirror_box())

        self.sim_checkbox = QCheckBox("Modo simulado (sem hardware GPIB)")
        self.sim_checkbox.setChecked(settings.simulation_mode)
        self.sim_checkbox.toggled.connect(self._on_sim_toggled)
        layout.addWidget(self.sim_checkbox)
        sim_hint = QLabel(
            "Neste PC não há NI-VISA/NI-488.2 instalado — mantenha o modo simulado.\n"
            "No PC do laboratório, instale o driver NI-488.2 (ou NI-VISA) do adaptador\n"
            "GPIB-USB-HS e desmarque esta opção para controlar os equipamentos de verdade."
        )
        sim_hint.setWordWrap(True)
        layout.addWidget(sim_hint)

        self.buzzer_checkbox = QCheckBox("Buzzer nas pausas do ensaio (troca de ligação)")
        self.buzzer_checkbox.setChecked(settings.buzzer_enabled)
        self.buzzer_checkbox.toggled.connect(self._on_buzzer_toggled)
        layout.addWidget(self.buzzer_checkbox)
        buzzer_hint = QLabel(
            "Quando o ensaio pausa pedindo pra trocar a ligação do medidor, toca um "
            "buzzer além do aviso na tela. Desmarque para deixar só o aviso visual."
        )
        buzzer_hint.setWordWrap(True)
        layout.addWidget(buzzer_hint)

        form = QFormLayout()

        self.ucs_connection_combo = QComboBox()
        self.ucs_connection_combo.addItem("GPIB", "gpib")
        self.ucs_connection_combo.addItem("Serial (RS-232)", "serial")
        index = self.ucs_connection_combo.findData(settings.ucs500n_connection)
        if index >= 0:
            self.ucs_connection_combo.setCurrentIndex(index)
        self.ucs_connection_combo.currentIndexChanged.connect(self._on_ucs_connection_changed)
        form.addRow("Conexão — EM TEST UCS 500N:", self.ucs_connection_combo)

        self.ucs_addr_spin = QSpinBox()
        self.ucs_addr_spin.setRange(1, 31)
        self.ucs_addr_spin.setValue(settings.gpib_addresses["ucs500n"])
        self.ucs_addr_spin.valueChanged.connect(
            lambda v: settings.gpib_addresses.__setitem__("ucs500n", v)
        )
        form.addRow("Endereço GPIB — EM TEST UCS 500N:", self.ucs_addr_spin)
        self._ucs_addr_label = form.labelForField(self.ucs_addr_spin)

        self.ucs_serial_spin = QSpinBox()
        self.ucs_serial_spin.setRange(1, 99)
        self.ucs_serial_spin.setPrefix("COM")
        self.ucs_serial_spin.setValue(settings.serial_ports["ucs500n"])
        self.ucs_serial_spin.valueChanged.connect(
            lambda v: settings.serial_ports.__setitem__("ucs500n", v)
        )
        form.addRow("Porta serial — EM TEST UCS 500N:", self.ucs_serial_spin)
        self._ucs_serial_label = form.labelForField(self.ucs_serial_spin)

        self.chroma_connection_combo = QComboBox()
        self.chroma_connection_combo.addItem("GPIB", "gpib")
        self.chroma_connection_combo.addItem("Serial (RS-232)", "serial")
        index = self.chroma_connection_combo.findData(settings.chroma_connection)
        if index >= 0:
            self.chroma_connection_combo.setCurrentIndex(index)
        self.chroma_connection_combo.currentIndexChanged.connect(self._on_chroma_connection_changed)
        form.addRow("Conexão — Chroma 61501/61504:", self.chroma_connection_combo)

        self.chroma_addr_spin = QSpinBox()
        self.chroma_addr_spin.setRange(1, 30)
        self.chroma_addr_spin.setValue(settings.gpib_addresses["chroma"])
        self.chroma_addr_spin.valueChanged.connect(
            lambda v: settings.gpib_addresses.__setitem__("chroma", v)
        )
        form.addRow("Endereço GPIB — Chroma 61501/61504:", self.chroma_addr_spin)
        self._chroma_addr_label = form.labelForField(self.chroma_addr_spin)

        self.chroma_serial_spin = QSpinBox()
        self.chroma_serial_spin.setRange(1, 99)
        self.chroma_serial_spin.setPrefix("COM")
        self.chroma_serial_spin.setValue(settings.serial_ports["chroma"])
        self.chroma_serial_spin.valueChanged.connect(
            lambda v: settings.serial_ports.__setitem__("chroma", v)
        )
        form.addRow("Porta serial — Chroma 61501/61504:", self.chroma_serial_spin)
        self._chroma_serial_label = form.labelForField(self.chroma_serial_spin)

        self.counter_connection_combo = QComboBox()
        self.counter_connection_combo.addItem("GPIB", "gpib")
        self.counter_connection_combo.addItem("Serial (RS-232)", "serial")
        index = self.counter_connection_combo.findData(settings.counter_connection)
        if index >= 0:
            self.counter_connection_combo.setCurrentIndex(index)
        self.counter_connection_combo.currentIndexChanged.connect(self._on_counter_connection_changed)
        form.addRow("Conexão — Contador Agilent 53131A:", self.counter_connection_combo)

        self.counter_board_spin = QSpinBox()
        self.counter_board_spin.setRange(0, 15)
        self.counter_board_spin.setValue(settings.gpib_boards["agilent_53131a"])
        self.counter_board_spin.valueChanged.connect(
            lambda v: settings.gpib_boards.__setitem__("agilent_53131a", v)
        )
        form.addRow("Placa GPIB — Contador Agilent 53131A:", self.counter_board_spin)
        self._counter_board_label = form.labelForField(self.counter_board_spin)

        self.counter_addr_spin = QSpinBox()
        self.counter_addr_spin.setRange(0, 30)
        self.counter_addr_spin.setValue(settings.gpib_addresses["agilent_53131a"])
        self.counter_addr_spin.valueChanged.connect(
            lambda v: settings.gpib_addresses.__setitem__("agilent_53131a", v)
        )
        form.addRow("Endereço GPIB — Contador Agilent 53131A:", self.counter_addr_spin)
        self._counter_addr_label = form.labelForField(self.counter_addr_spin)

        self.counter_serial_spin = QSpinBox()
        self.counter_serial_spin.setRange(1, 99)
        self.counter_serial_spin.setPrefix("COM")
        self.counter_serial_spin.setValue(settings.serial_ports["agilent_53131a"])
        self.counter_serial_spin.valueChanged.connect(
            lambda v: settings.serial_ports.__setitem__("agilent_53131a", v)
        )
        form.addRow("Porta serial — Contador Agilent 53131A:", self.counter_serial_spin)
        self._counter_serial_label = form.labelForField(self.counter_serial_spin)

        layout.addLayout(form)
        self._on_ucs_connection_changed(self.ucs_connection_combo.currentIndex())
        self._on_chroma_connection_changed(self.chroma_connection_combo.currentIndex())
        self._on_counter_connection_changed(self.counter_connection_combo.currentIndex())

        layout.addWidget(
            QLabel(
                "Teste de comunicação (connect + *IDN?) — sempre tenta o hardware real,\n"
                "mesmo com o modo simulado marcado acima:"
            )
        )

        ucs_test_row = QHBoxLayout()
        ucs_test_btn = QPushButton("Testar comunicação — UCS 500N")
        ucs_test_btn.clicked.connect(
            lambda: self._test_comm("ucs500n", lambda: build_ucs500n_driver(force_real=True))
        )
        self.ucs_test_status = QLabel("")
        ucs_test_row.addWidget(ucs_test_btn)
        ucs_test_row.addWidget(self.ucs_test_status, 1)
        layout.addLayout(ucs_test_row)

        chroma_test_row = QHBoxLayout()
        chroma_test_btn = QPushButton("Testar comunicação — Chroma")
        chroma_test_btn.clicked.connect(
            lambda: self._test_comm("chroma", lambda: build_chroma_driver(force_real=True))
        )
        self.chroma_test_status = QLabel("")
        chroma_test_row.addWidget(chroma_test_btn)
        chroma_test_row.addWidget(self.chroma_test_status, 1)
        layout.addLayout(chroma_test_row)

        counter_test_row = QHBoxLayout()
        counter_test_btn = QPushButton("Testar comunicação — Contador Agilent 53131A")
        counter_test_btn.clicked.connect(
            lambda: self._test_comm(
                "agilent_53131a", lambda: build_agilent_counter_driver(force_real=True)
            )
        )
        self.counter_test_status = QLabel("")
        counter_test_row.addWidget(counter_test_btn)
        counter_test_row.addWidget(self.counter_test_status, 1)
        layout.addLayout(counter_test_row)

        recall_row = QHBoxLayout()
        recall_row.addWidget(QLabel("Recall do contador (Save/Recall > Recall N no painel):"))
        self.recall_register_spin = QSpinBox()
        self.recall_register_spin.setRange(0, 20)
        self.recall_register_spin.setValue(1)
        recall_row.addWidget(self.recall_register_spin)
        recall_btn = QPushButton("Carregar Recall")
        recall_btn.clicked.connect(self._load_recall)
        recall_row.addWidget(recall_btn)
        self.recall_status = QLabel("")
        recall_row.addWidget(self.recall_status, 1)
        layout.addLayout(recall_row)

        layout.addStretch()

    def _build_data_dir_box(self) -> QGroupBox:
        box = QGroupBox("Diretório de dados (banco de dados + arquivos de projetos)")
        box_layout = QVBoxLayout(box)
        data_dir_hint = QLabel(
            "Onde ficam o banco de dados (app.db) e os arquivos de projetos. Fica salvo "
            "num arquivo ao lado do .exe, então sobrevive a uma troca de versão do "
            "programa — não recomeça do zero só porque o .exe foi atualizado. Pode "
            "apontar pra uma pasta de rede, pra compartilhar entre vários PCs.\n"
            "Precisa reiniciar o app depois de trocar."
        )
        data_dir_hint.setWordWrap(True)
        box_layout.addWidget(data_dir_hint)
        self.data_dir_label = QLabel(str(config.DATA_DIR))
        self.data_dir_label.setWordWrap(True)
        self.data_dir_label.setStyleSheet("font-family: monospace;")
        box_layout.addWidget(self.data_dir_label)

        btn_row = QHBoxLayout()
        choose_btn = QPushButton("Escolher pasta...")
        choose_btn.clicked.connect(self._choose_data_dir)
        btn_row.addWidget(choose_btn)
        reset_btn = QPushButton("Usar pasta padrão (ao lado do .exe)")
        reset_btn.clicked.connect(self._reset_data_dir)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch(1)
        box_layout.addLayout(btn_row)

        return box

    def _choose_data_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta pros dados (pode ser de rede)")
        if not folder:
            return
        new_dir = Path(folder)

        if not (new_dir / "app.db").exists() and config.DATA_DIR.exists():
            confirm = QMessageBox.question(
                self,
                "Diretório de dados",
                f"A pasta escolhida ainda não tem dados.\n\n"
                f"Copiar os dados atuais de:\n{config.DATA_DIR}\n\npra lá agora, "
                f"pra não começar vazio? (os dados atuais NÃO são apagados, só copiados)",
            )
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    shutil.copytree(config.DATA_DIR, new_dir, dirs_exist_ok=True)
                except OSError as exc:
                    QMessageBox.warning(self, "Diretório de dados", f"Falha ao copiar os dados: {exc}")
                    return

        config.set_data_dir_override(new_dir)
        self.data_dir_label.setText(str(new_dir))
        QMessageBox.information(
            self, "Diretório de dados", "Salvo. Feche e abra o app de novo pra usar essa pasta."
        )

    def _reset_data_dir(self) -> None:
        config.set_data_dir_override(None)
        default_dir = config.BASE_DIR / "data"
        self.data_dir_label.setText(str(default_dir))
        QMessageBox.information(
            self, "Diretório de dados", "Salvo. Feche e abra o app de novo pra usar a pasta padrão."
        )

    def _build_templates_mirror_box(self) -> QGroupBox:
        box = QGroupBox("Pasta espelhada de roteiros (aba Execução)")
        box_layout = QVBoxLayout(box)
        mirror_hint = QLabel(
            "Os roteiros salvos em Execução (Templates) ficam sempre no banco local — "
            "funciona mesmo no portátil, sem rede. Se você marcar uma pasta aqui "
            "(tipicamente de rede), cada roteiro salvo/apagado também grava lá, e ao "
            "abrir a lista de roteiros, o app importa os que existem lá mas não "
            "localmente — assim o mesmo roteiro aparece no portátil e no PC normal, "
            "duplicado. Não precisa reiniciar o app."
        )
        mirror_hint.setWordWrap(True)
        box_layout.addWidget(mirror_hint)
        current = config.get_templates_mirror_dir()
        self.templates_mirror_label = QLabel(str(current) if current else "Nenhuma (só salva localmente)")
        self.templates_mirror_label.setWordWrap(True)
        self.templates_mirror_label.setStyleSheet("font-family: monospace;")
        box_layout.addWidget(self.templates_mirror_label)

        btn_row = QHBoxLayout()
        choose_btn = QPushButton("Escolher pasta espelhada...")
        choose_btn.clicked.connect(self._choose_templates_mirror_dir)
        btn_row.addWidget(choose_btn)
        clear_btn = QPushButton("Remover (só local)")
        clear_btn.clicked.connect(self._clear_templates_mirror_dir)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        box_layout.addLayout(btn_row)

        return box

    def _choose_templates_mirror_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta espelhada pros roteiros (de rede)")
        if not folder:
            return
        config.set_templates_mirror_dir(Path(folder))
        self.templates_mirror_label.setText(folder)

    def _clear_templates_mirror_dir(self) -> None:
        config.set_templates_mirror_dir(None)
        self.templates_mirror_label.setText("Nenhuma (só salva localmente)")

    def _on_sim_toggled(self, checked: bool) -> None:
        settings.simulation_mode = checked

    def _on_buzzer_toggled(self, checked: bool) -> None:
        settings.buzzer_enabled = checked

    def _on_ucs_connection_changed(self, _index: int) -> None:
        connection = self.ucs_connection_combo.currentData()
        settings.ucs500n_connection = connection
        is_serial = connection == "serial"
        self.ucs_addr_spin.setVisible(not is_serial)
        self._ucs_addr_label.setVisible(not is_serial)
        self.ucs_serial_spin.setVisible(is_serial)
        self._ucs_serial_label.setVisible(is_serial)

    def _on_chroma_connection_changed(self, _index: int) -> None:
        connection = self.chroma_connection_combo.currentData()
        settings.chroma_connection = connection
        is_serial = connection == "serial"
        self.chroma_addr_spin.setVisible(not is_serial)
        self._chroma_addr_label.setVisible(not is_serial)
        self.chroma_serial_spin.setVisible(is_serial)
        self._chroma_serial_label.setVisible(is_serial)

    def _on_counter_connection_changed(self, _index: int) -> None:
        connection = self.counter_connection_combo.currentData()
        settings.counter_connection = connection
        is_serial = connection == "serial"
        self.counter_board_spin.setVisible(not is_serial)
        self._counter_board_label.setVisible(not is_serial)
        self.counter_addr_spin.setVisible(not is_serial)
        self._counter_addr_label.setVisible(not is_serial)
        self.counter_serial_spin.setVisible(is_serial)
        self._counter_serial_label.setVisible(is_serial)

    def _test_comm(self, instrument: str, driver_factory) -> None:
        status_labels = {
            "ucs500n": self.ucs_test_status,
            "chroma": self.chroma_test_status,
            "agilent_53131a": self.counter_test_status,
        }
        status_label = status_labels[instrument]
        status_label.setStyleSheet("")
        status_label.setText("Testando...")
        worker = CommTestWorker(driver_factory)
        worker.result.connect(lambda ok, msg: self._on_comm_test_result(status_label, ok, msg))
        self._comm_test_workers[instrument] = worker
        worker.start()

    def _on_comm_test_result(self, status_label: QLabel, ok: bool, message: str) -> None:
        if ok:
            status_label.setStyleSheet("color: green;")
            status_label.setText(f"OK — {message}")
        else:
            status_label.setStyleSheet("color: red;")
            status_label.setText(f"Falhou — {message}")

    # ---- recall do contador Agilent 53131A ----

    def _load_recall(self) -> None:
        self.recall_status.setStyleSheet("")
        self.recall_status.setText("Carregando...")
        counter = build_agilent_counter_driver()
        worker = RecallWorker(counter, self.recall_register_spin.value(), self)
        worker.result.connect(self._on_recall_result)
        self._recall_worker = worker
        worker.start()

    def _on_recall_result(self, ok: bool, message: str) -> None:
        self._recall_worker = None
        if ok:
            self.recall_status.setStyleSheet("color: green;")
            self.recall_status.setText(message)
        else:
            self.recall_status.setStyleSheet("color: red;")
            self.recall_status.setText(f"Falhou — {message}")
