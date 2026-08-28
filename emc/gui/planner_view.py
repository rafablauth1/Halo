import os
from pathlib import Path

from PySide6.QtCore import QDate, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emc.config import AUTOMATED_STANDARDS, STANDARDS
from emc.core import energy_registry, planner, project_files
from emc.core.planner import COMM_LINE_ELIGIBLE_STANDARDS, ORIGEM_DISPLAY, ORIGEM_SOFTWARE


class _FileSearchWorker(QThread):
    """Vasculha em background (pra não travar a tela) por arquivos .txt
    gerados por outro software com o padrão de nome '{protocolo}_...'.
    root_dirs: pasta(s) específica(s) onde procurar; None procura no PC
    todo (todas as unidades de disco)."""

    progress = Signal(str)
    finished_search = Signal(list)

    def __init__(self, protocolo: str, root_dirs: list[Path] | None = None, parent=None):
        super().__init__(parent)
        self.protocolo = protocolo
        self.root_dirs = root_dirs
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        results = project_files.find_matching_files(
            self.protocolo,
            root_dirs=self.root_dirs,
            stop_flag=lambda: self._stop,
            on_progress=lambda path: self.progress.emit(path),
        )
        self.finished_search.emit(results)

STATUS_OPTIONS = ["pendente", "andamento", "concluido"]
STATUS_LABELS = {"pendente": "Pendente", "andamento": "Em andamento", "concluido": "Concluído"}

HEADER_FIELD_LABELS = [
    ("fabricante", "Fabricante:"),
    ("modelo", "Modelo:"),
    ("classe", "Classe:"),
    ("serie", "Série:"),
    ("tensao_nominal", "Tensão Nom. (V):"),
    ("corrente_nominal", "Corrente Nom. (A):"),
    ("protocolo", "Protocolo:"),
    ("data_entrada", "Data de Entrada:"),
    ("previsao_saida", "Previsão de Saída:"),
]


class _CodeSelectionDialog(QDialog):
    """Escolher, dentre o catálogo de códigos de grandeza, quais esse medidor
    específico tem (ex.: os que aparecem no display) — usado depois em Registro
    de Energia pra gerar as linhas de leitura automaticamente."""

    def __init__(self, parent=None, selected: list[int] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Códigos aplicáveis a este medidor")
        self.resize(480, 520)
        selected_set = set(selected or [])
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Marque os códigos que esse medidor tem/mostra:"))

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["", "Código", "Legenda"])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        for entry in energy_registry.list_codes():
            row = self.table.rowCount()
            self.table.insertRow(row)
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(
                Qt.CheckState.Checked if entry["codigo"] in selected_set else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, check_item)
            self.table.setItem(row, 1, QTableWidgetItem(str(entry["codigo"])))
            self.table.setItem(row, 2, QTableWidgetItem(entry["legenda"]))

        btn_row = QHBoxLayout()
        all_btn = QPushButton("Marcar todos")
        all_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        btn_row.addWidget(all_btn)
        none_btn = QPushButton("Desmarcar todos")
        none_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        btn_row.addWidget(none_btn)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, state: Qt.CheckState) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def selected_codes(self) -> list[int]:
        codes = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked:
                codes.append(int(self.table.item(row, 1).text()))
        return codes


class _CadastroDialog(QDialog):
    """Cadastro completo do projeto/equipamento: identificação, cliente e quais
    ensaios se aplicam (com opção de linha de comunicação separada para os que
    fizerem sentido). Serve tanto pra criar um projeto novo quanto editar um já
    existente (passe project + existing_items)."""

    def __init__(self, parent=None, project: dict | None = None, existing_items: list[dict] | None = None):
        super().__init__(parent)
        self.setWindowTitle("Editar cadastro" if project else "Novo projeto")
        self.resize(460, 560)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.name_edit = QLineEdit(project["name"] if project else "")
        form.addRow("Nome do projeto:", self.name_edit)
        self.client_edit = QLineEdit(project["client"] if project else "")
        form.addRow("Cliente:", self.client_edit)
        self.header_edits: dict[str, QLineEdit] = {}
        for field, label in HEADER_FIELD_LABELS:
            edit = QLineEdit((project or {}).get(field, "") or "")
            form.addRow(label, edit)
            self.header_edits[field] = edit

        self.origem_combo = QComboBox()
        self.origem_combo.addItem("Display (leitura manual no mostrador)", ORIGEM_DISPLAY)
        self.origem_combo.addItem("Software (leitura via comunicação)", ORIGEM_SOFTWARE)
        origem_atual = (project or {}).get("origem_dados") or ORIGEM_DISPLAY
        index = self.origem_combo.findData(origem_atual)
        if index >= 0:
            self.origem_combo.setCurrentIndex(index)
        form.addRow("Dados via:", self.origem_combo)
        layout.addLayout(form)

        self._applicable_codes = planner.get_applicable_codes(project["id"]) if project else []
        codes_row = QHBoxLayout()
        self.codes_summary_label = QLabel()
        self._refresh_codes_summary()
        codes_row.addWidget(self.codes_summary_label, 1)
        codes_btn = QPushButton("Códigos aplicáveis...")
        codes_btn.clicked.connect(self._select_codes)
        codes_row.addWidget(codes_btn)
        layout.addLayout(codes_row)

        existing_keys = {(item["standard_code"], item["porta"]) for item in (existing_items or [])}
        is_new = project is None

        layout.addWidget(QLabel("Ensaios que se aplicam a este projeto:"))
        self.checkboxes: dict[str, QCheckBox] = {}
        self.alim_checkboxes: dict[str, QCheckBox] = {}
        self.comm_checkboxes: dict[str, QCheckBox] = {}
        self.tipo_comunicacao_edits: dict[str, QLineEdit] = {}
        for code, description in STANDARDS.items():
            row = QHBoxLayout()
            if code in COMM_LINE_ELIGIBLE_STANDARDS:
                row.addWidget(QLabel(f"{code} — {description}"))

                alim_checkbox = QCheckBox("Alimentação")
                alim_checkbox.setChecked(is_new or (code, "alimentação") in existing_keys)
                row.addWidget(alim_checkbox)
                self.alim_checkboxes[code] = alim_checkbox

                comm_checkbox = QCheckBox("Comunicação")
                comm_checkbox.setChecked((code, "comunicação") in existing_keys)
                row.addWidget(comm_checkbox)
                self.comm_checkboxes[code] = comm_checkbox

                tipo_edit = QLineEdit()
                tipo_edit.setPlaceholderText("Tipo de comunicação (ex.: RS-485, óptico)")
                existing_tipo = next(
                    (
                        item.get("tipo_comunicacao")
                        for item in (existing_items or [])
                        if item["standard_code"] == code and item["porta"] == "comunicação"
                    ),
                    "",
                )
                tipo_edit.setText(existing_tipo or "")
                tipo_edit.setEnabled(comm_checkbox.isChecked())
                comm_checkbox.toggled.connect(tipo_edit.setEnabled)
                row.addWidget(tipo_edit, 1)
                self.tipo_comunicacao_edits[code] = tipo_edit
            else:
                checkbox = QCheckBox(f"{code} — {description}")
                checkbox.setChecked(is_new or (code, "alimentação") in existing_keys)
                row.addWidget(checkbox)
                self.checkboxes[code] = checkbox
                row.addStretch(1)
            layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_codes_summary(self) -> None:
        n = len(self._applicable_codes)
        self.codes_summary_label.setText(
            f"{n} código(s) aplicável(is) selecionado(s)." if n else "Nenhum código selecionado ainda."
        )

    def _select_codes(self) -> None:
        dialog = _CodeSelectionDialog(self, selected=self._applicable_codes)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._applicable_codes = dialog.selected_codes()
            self._refresh_codes_summary()

    def header_values(self) -> dict:
        values = {field: edit.text().strip() for field, edit in self.header_edits.items()}
        values["origem_dados"] = self.origem_combo.currentData()
        return values

    def applicable_codes(self) -> list[int]:
        return list(self._applicable_codes)

    def selected_standards(self) -> list[str]:
        result = [code for code, checkbox in self.checkboxes.items() if checkbox.isChecked()]
        for code, alim_checkbox in self.alim_checkboxes.items():
            if alim_checkbox.isChecked() or self.comm_checkboxes[code].isChecked():
                result.append(code)
        return result

    def comm_line_config(self) -> dict[str, dict]:
        return {
            code: {
                "alimentacao": alim_checkbox.isChecked(),
                "comunicacao": self.comm_checkboxes[code].isChecked(),
                "tipo_comunicacao": self.tipo_comunicacao_edits[code].text().strip(),
            }
            for code, alim_checkbox in self.alim_checkboxes.items()
        }


class PlannerView(QWidget):
    run_test_requested = Signal(int, str)  # project_id, standard_code

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_project_id: int | None = None

        layout = QVBoxLayout(self)

        overview_box = QGroupBox("Projetos em execução")
        overview_layout = QVBoxLayout(overview_box)
        overview_btn_row = QHBoxLayout()
        overview_btn_row.addStretch(1)
        expand_overview_btn = QPushButton("Expandir visualização (lado a lado)")
        expand_overview_btn.clicked.connect(self._expand_overview)
        overview_btn_row.addWidget(expand_overview_btn)
        overview_layout.addLayout(overview_btn_row)
        self.overview_table = QTableWidget(0, 4)
        self.overview_table.setHorizontalHeaderLabels(["Projeto", "Cliente", "Progresso", ""])
        self.overview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.overview_table.setAlternatingRowColors(True)
        self.overview_table.verticalHeader().setDefaultSectionSize(28)
        self.overview_table.setMaximumHeight(160)
        overview_layout.addWidget(self.overview_table)
        layout.addWidget(overview_box)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Projeto:"))
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_selected)
        top_bar.addWidget(self.project_combo, 1)
        new_project_btn = QPushButton("Novo projeto")
        new_project_btn.clicked.connect(self._create_project)
        top_bar.addWidget(new_project_btn)
        edit_cadastro_btn = QPushButton("Editar cadastro")
        edit_cadastro_btn.clicked.connect(self._edit_cadastro)
        top_bar.addWidget(edit_cadastro_btn)
        delete_project_btn = QPushButton("Excluir projeto")
        delete_project_btn.clicked.connect(self._delete_project)
        top_bar.addWidget(delete_project_btn)
        layout.addLayout(top_bar)

        status_box = QGroupBox("Status do projeto")
        status_layout = QHBoxLayout(status_box)
        status_layout.addWidget(QLabel("Situação:"))
        self.project_status_label = QLabel("—")
        status_layout.addWidget(self.project_status_label)
        status_layout.addStretch(1)
        self.finalize_btn = QPushButton("Finalizar projeto")
        self.finalize_btn.clicked.connect(self._finalize_project)
        status_layout.addWidget(self.finalize_btn)
        self.reopen_btn = QPushButton("Reabrir projeto")
        self.reopen_btn.clicked.connect(self._reopen_project)
        status_layout.addWidget(self.reopen_btn)
        layout.addWidget(status_box)

        cadastro_box = QGroupBox("Cadastro")
        cadastro_layout = QFormLayout(cadastro_box)
        self.cadastro_labels: dict[str, QLabel] = {}
        for field, label in [("client", "Cliente:")] + HEADER_FIELD_LABELS:
            value_label = QLabel("—")
            cadastro_layout.addRow(label, value_label)
            self.cadastro_labels[field] = value_label
        layout.addWidget(cadastro_box)

        files_box = QGroupBox("Arquivos do projeto (gerados pelo protocolo)")
        files_layout = QVBoxLayout(files_box)
        files_btn_row = QHBoxLayout()
        open_folder_btn = QPushButton("Abrir pasta do projeto")
        open_folder_btn.clicked.connect(self._open_project_folder)
        files_btn_row.addWidget(open_folder_btn)
        import_files_btn = QPushButton("Importar arquivos (buscar no PC)")
        import_files_btn.clicked.connect(self._import_files)
        files_btn_row.addWidget(import_files_btn)
        import_folder_btn = QPushButton("Importar de uma pasta...")
        import_folder_btn.clicked.connect(self._import_files_from_folder)
        files_btn_row.addWidget(import_folder_btn)
        files_btn_row.addStretch(1)
        files_layout.addLayout(files_btn_row)
        self.files_table = QTableWidget(0, 1)
        self.files_table.setHorizontalHeaderLabels(["Arquivo"])
        self.files_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.files_table.setMaximumHeight(120)
        files_layout.addWidget(self.files_table)
        layout.addWidget(files_box)

        checklist_box = QGroupBox("Checklist de ensaios")
        checklist_layout = QVBoxLayout(checklist_box)
        self.checklist_table = QTableWidget(0, 6)
        self.checklist_table.setHorizontalHeaderLabels(
            ["Norma", "Linha", "Descrição", "Status", "Data agendada", ""]
        )
        self.checklist_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.checklist_table.setAlternatingRowColors(True)
        self.checklist_table.setMinimumHeight(220)
        checklist_layout.addWidget(self.checklist_table)
        layout.addWidget(checklist_box, 1)

        schedule_box = QGroupBox("Cronograma (todos os projetos) — editável")
        schedule_layout = QVBoxLayout(schedule_box)
        self.schedule_table = QTableWidget(0, 6)
        self.schedule_table.setHorizontalHeaderLabels(
            ["Data", "Projeto", "Norma", "Linha", "Status", ""]
        )
        self.schedule_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.schedule_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.schedule_table.setAlternatingRowColors(True)
        self.schedule_table.verticalHeader().setDefaultSectionSize(32)
        self.schedule_table.setMinimumHeight(280)
        schedule_layout.addWidget(self.schedule_table)
        layout.addWidget(schedule_box, 3)

        self.refresh_projects()
        self.refresh_schedule()

    def refresh_projects(self, select_project_id: int | None = None) -> None:
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = planner.list_projects()
        for project in projects:
            label = project["name"]
            if (project.get("status") or "ativo") == "finalizado":
                label += " (finalizado)"
            self.project_combo.addItem(label, project["id"])
        self.project_combo.blockSignals(False)
        self.refresh_overview()
        if select_project_id is not None:
            index = self.project_combo.findData(select_project_id)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
                self._on_project_selected(index)
                return
        if projects:
            self.project_combo.setCurrentIndex(0)
            self._on_project_selected(0)
        else:
            self.current_project_id = None
            self._load_cadastro_summary()
            self._load_checklist()
            self._load_project_status()
            self._load_project_files()

    def refresh_overview(self) -> None:
        projects = planner.list_active_projects()
        self.overview_table.setRowCount(len(projects))
        for row, project in enumerate(projects):
            items = planner.list_test_items(project["id"])
            total = len(items)
            done = sum(1 for item in items if item["status"] == "concluido")
            self.overview_table.setItem(row, 0, QTableWidgetItem(project["name"]))
            self.overview_table.setItem(row, 1, QTableWidgetItem(project["client"] or ""))
            self.overview_table.setItem(row, 2, QTableWidgetItem(f"{done}/{total} ensaios concluídos"))
            open_btn = QPushButton("Abrir")
            open_btn.clicked.connect(lambda _checked=False, pid=project["id"]: self._open_from_overview(pid))
            self.overview_table.setCellWidget(row, 3, open_btn)
        if not projects:
            self.overview_table.setRowCount(1)
            empty_item = QTableWidgetItem("Nenhum projeto em execução no momento.")
            empty_item.setFlags(empty_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.overview_table.setItem(0, 0, empty_item)
            self.overview_table.setSpan(0, 0, 1, 4)

    def _open_from_overview(self, project_id: int) -> None:
        index = self.project_combo.findData(project_id)
        if index >= 0:
            self.project_combo.setCurrentIndex(index)

    def _expand_overview(self) -> None:
        """Visão lado a lado de todos os projetos em execução, um painel por
        projeto com o checklist completo — pra comparar o andamento de vários
        projetos sem precisar trocar no combo um de cada vez."""
        projects = planner.list_active_projects()
        dialog = QDialog(self)
        dialog.setWindowTitle("Projetos em execução — lado a lado")
        dialog.resize(1400, 800)
        outer_layout = QVBoxLayout(dialog)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        row_layout = QHBoxLayout(container)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        order = {code: i for i, code in enumerate(STANDARDS)}
        if not projects:
            row_layout.addWidget(QLabel("Nenhum projeto em execução no momento."))
        for project in projects:
            panel = QGroupBox(project["name"])
            panel.setMinimumWidth(320)
            panel.setMaximumWidth(380)
            panel_layout = QVBoxLayout(panel)
            panel_layout.addWidget(QLabel(f"Cliente: {project['client'] or '—'}"))

            items = planner.list_test_items(project["id"])
            items.sort(key=lambda item: (order.get(item["standard_code"], 999), item["porta"]))
            table = QTableWidget(len(items), 3)
            table.setHorizontalHeaderLabels(["Norma", "Linha", "Status"])
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            for row, item in enumerate(items):
                table.setItem(row, 0, QTableWidgetItem(item["standard_code"]))
                porta_label = item["porta"]
                if item.get("tipo_comunicacao"):
                    porta_label += f" ({item['tipo_comunicacao']})"
                table.setItem(row, 1, QTableWidgetItem(porta_label))
                table.setItem(row, 2, QTableWidgetItem(STATUS_LABELS.get(item["status"], item["status"])))
            panel_layout.addWidget(table)

            open_btn = QPushButton("Abrir este projeto")
            open_btn.clicked.connect(
                lambda _checked=False, pid=project["id"], dlg=dialog: self._open_from_dialog(pid, dlg)
            )
            panel_layout.addWidget(open_btn)

            row_layout.addWidget(panel)

        scroll.setWidget(container)
        outer_layout.addWidget(scroll)
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(dialog.accept)
        outer_layout.addWidget(close_btn)
        dialog.exec()

    def _open_from_dialog(self, project_id: int, dialog: QDialog) -> None:
        self._open_from_overview(project_id)
        dialog.accept()

    def _create_project(self) -> None:
        dialog = _CadastroDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name_edit.text().strip()
        if not name:
            return
        project_id = planner.create_project(
            name,
            dialog.client_edit.text().strip(),
            dialog.selected_standards(),
            dialog.header_values(),
            dialog.comm_line_config(),
            dialog.applicable_codes(),
        )
        self.refresh_projects(select_project_id=project_id)
        self.refresh_schedule()

    def _edit_cadastro(self) -> None:
        if self.current_project_id is None:
            QMessageBox.warning(self, "Cadastro", "Selecione ou crie um projeto primeiro.")
            return
        project = planner.get_project(self.current_project_id)
        existing_items = planner.list_test_items(self.current_project_id)
        dialog = _CadastroDialog(self, project=project, existing_items=existing_items)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name_edit.text().strip()
        if not name:
            return
        planner.update_project(
            self.current_project_id,
            name,
            dialog.client_edit.text().strip(),
            dialog.header_values(),
            dialog.applicable_codes(),
        )
        planner.set_project_standards(
            self.current_project_id, dialog.selected_standards(), dialog.comm_line_config()
        )
        self.refresh_projects(select_project_id=self.current_project_id)
        self.refresh_schedule()

    def _on_project_selected(self, _index: int) -> None:
        project_id = self.project_combo.currentData()
        self.current_project_id = project_id
        self._load_cadastro_summary()
        self._load_checklist()
        self._load_project_status()
        self._load_project_files()

    def _load_project_status(self) -> None:
        project = planner.get_project(self.current_project_id) if self.current_project_id else None
        if not project:
            self.project_status_label.setText("—")
            self.finalize_btn.setEnabled(False)
            self.reopen_btn.setEnabled(False)
            self.finalize_btn.setVisible(True)
            self.reopen_btn.setVisible(False)
            return
        status = project.get("status") or "ativo"
        finalizado = status == "finalizado"
        self.project_status_label.setText("Finalizado" if finalizado else "Ativo")
        self.finalize_btn.setVisible(not finalizado)
        self.reopen_btn.setVisible(finalizado)
        self.finalize_btn.setEnabled(True)
        self.reopen_btn.setEnabled(True)

    def _finalize_project(self) -> None:
        if self.current_project_id is None:
            return
        confirm = QMessageBox.question(
            self, "Finalizar projeto", "Marcar este projeto como finalizado?"
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        planner.finalize_project(self.current_project_id)
        self.refresh_projects(select_project_id=self.current_project_id)

    def _reopen_project(self) -> None:
        if self.current_project_id is None:
            return
        planner.reopen_project(self.current_project_id)
        self.refresh_projects(select_project_id=self.current_project_id)

    def _load_cadastro_summary(self) -> None:
        project = planner.get_project(self.current_project_id) if self.current_project_id else None
        for field, label_widget in self.cadastro_labels.items():
            value = (project or {}).get(field, "") or "—"
            label_widget.setText(value)

    def _load_project_files(self) -> None:
        self.files_table.setRowCount(0)
        if self.current_project_id is None:
            return
        files = project_files.list_project_files(self.current_project_id)
        self.files_table.setRowCount(len(files))
        for row, path in enumerate(files):
            item = QTableWidgetItem(path.name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.files_table.setItem(row, 0, item)

    def _open_project_folder(self) -> None:
        if self.current_project_id is None:
            QMessageBox.warning(self, "Pasta do projeto", "Selecione um projeto primeiro.")
            return
        folder = project_files.get_project_folder(self.current_project_id)
        os.startfile(str(folder))

    def _current_protocolo(self) -> str | None:
        if self.current_project_id is None:
            QMessageBox.warning(self, "Importar arquivos", "Selecione um projeto primeiro.")
            return None
        project = planner.get_project(self.current_project_id)
        protocolo = (project.get("protocolo") or "").strip() if project else ""
        if not protocolo:
            QMessageBox.warning(
                self,
                "Importar arquivos",
                "Preencha o campo \"Protocolo\" no Cadastro deste projeto antes de importar — "
                "é ele que identifica quais arquivos (ex.: PROTOCOLO_4-19_120V.txt) pertencem a este projeto.",
            )
            return None
        return protocolo

    def _import_files(self) -> None:
        protocolo = self._current_protocolo()
        if protocolo is None:
            return
        self._run_file_search(protocolo, root_dirs=None, label="Buscando arquivos no PC...")

    def _import_files_from_folder(self) -> None:
        protocolo = self._current_protocolo()
        if protocolo is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta pra buscar arquivos")
        if not folder:
            return
        self._run_file_search(
            protocolo, root_dirs=[Path(folder)], label=f"Buscando arquivos em {folder}..."
        )

    def _run_file_search(self, protocolo: str, root_dirs: list[Path] | None, label: str) -> None:
        progress = QProgressDialog(label, "Cancelar", 0, 0, self)
        progress.setWindowTitle("Importar arquivos")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker = _FileSearchWorker(protocolo, root_dirs=root_dirs, parent=self)
        worker.progress.connect(lambda path: progress.setLabelText(f"Buscando...\n{path}"))

        def on_finished(results: list) -> None:
            progress.close()
            self._file_search_worker = None
            self._show_import_results(results)

        worker.finished_search.connect(on_finished)
        progress.canceled.connect(worker.stop)
        self._file_search_worker = worker  # mantém referência viva enquanto a busca roda
        worker.start()
        progress.show()

    def _show_import_results(self, results: list[Path]) -> None:
        if not results:
            QMessageBox.information(
                self, "Importar arquivos", "Nenhum arquivo encontrado no PC com esse protocolo."
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{len(results)} arquivo(s) encontrado(s)")
        dialog.resize(720, 420)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.addWidget(QLabel("Selecione os arquivos que devem ser MOVIDOS pra pasta do projeto:"))

        table = QTableWidget(len(results), 2)
        table.setHorizontalHeaderLabels(["", "Caminho encontrado"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for row, path in enumerate(results):
            check_item = QTableWidgetItem()
            check_item.setFlags(check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(Qt.CheckState.Checked)
            table.setItem(row, 0, check_item)
            path_item = QTableWidgetItem(str(path))
            path_item.setFlags(path_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 1, path_item)
        dlg_layout.addWidget(table, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Mover arquivos selecionados")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dlg_layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_paths = [
            Path(table.item(row, 1).text())
            for row in range(table.rowCount())
            if table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        if not selected_paths:
            return
        moved, skipped = project_files.move_files_to_project(self.current_project_id, selected_paths)
        self._load_project_files()
        message = f"{moved} arquivo(s) movido(s) pra pasta do projeto."
        if skipped:
            message += f"\n{skipped} ignorado(s) (já existia arquivo igual no destino, ou não encontrado)."
        QMessageBox.information(self, "Importar arquivos", message)

    def _load_checklist(self) -> None:
        self.checklist_table.setRowCount(0)
        if self.current_project_id is None:
            return
        items = planner.list_test_items(self.current_project_id)
        # ordena pela ordem natural de STANDARDS (4-2..4-19), não pela ordem alfabética do banco
        order = {code: i for i, code in enumerate(STANDARDS)}
        items.sort(key=lambda item: (order.get(item["standard_code"], 999), item["porta"]))
        self.checklist_table.setRowCount(len(items))
        for row, item in enumerate(items):
            standard_code = item["standard_code"]
            self.checklist_table.setItem(row, 0, QTableWidgetItem(standard_code))
            porta_label = item["porta"]
            if item.get("tipo_comunicacao"):
                porta_label += f" ({item['tipo_comunicacao']})"
            self.checklist_table.setItem(row, 1, QTableWidgetItem(porta_label))
            self.checklist_table.setItem(
                row, 2, QTableWidgetItem(STANDARDS.get(standard_code, ""))
            )

            status_combo = QComboBox()
            for status in STATUS_OPTIONS:
                status_combo.addItem(STATUS_LABELS[status], status)
            status_combo.setCurrentIndex(STATUS_OPTIONS.index(item["status"]))
            status_combo.currentIndexChanged.connect(
                lambda _i, item_id=item["id"], combo=status_combo: self._on_status_changed(
                    item_id, combo
                )
            )
            self.checklist_table.setCellWidget(row, 3, status_combo)

            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setSpecialValueText(" ")
            date_edit.setMinimumDate(QDate(2000, 1, 1))
            if item["scheduled_date"]:
                date_edit.setDate(QDate.fromString(item["scheduled_date"], "yyyy-MM-dd"))
            else:
                date_edit.setDate(date_edit.minimumDate())
            date_edit.dateChanged.connect(
                lambda date, item_id=item["id"]: self._on_date_changed(item_id, date)
            )
            self.checklist_table.setCellWidget(row, 4, date_edit)

            if standard_code in AUTOMATED_STANDARDS:
                run_btn = QPushButton("Executar")
                run_btn.clicked.connect(
                    lambda _checked=False, code=standard_code: self._request_run(code)
                )
                self.checklist_table.setCellWidget(row, 5, run_btn)

    def _request_run(self, standard_code: str) -> None:
        if self.current_project_id is not None:
            self.run_test_requested.emit(self.current_project_id, standard_code)

    def _delete_project(self) -> None:
        if self.current_project_id is None:
            QMessageBox.warning(self, "Excluir projeto", "Selecione um projeto primeiro.")
            return
        project = planner.get_project(self.current_project_id)
        name = project["name"] if project else ""
        confirm = QMessageBox.question(
            self,
            "Excluir projeto",
            f"Excluir o projeto '{name}'? Isso apaga também o checklist, ensaios executados, "
            "laudos e registro de energia desse projeto — não pode ser desfeito.",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        planner.delete_project(self.current_project_id)
        self.current_project_id = None
        self.refresh_projects()
        self.refresh_schedule()

    def _on_status_changed(self, item_id: int, combo: QComboBox) -> None:
        planner.update_item_status(item_id, combo.currentData())
        self._load_checklist()
        self.refresh_schedule()

    def _on_date_changed(self, item_id: int, date: QDate) -> None:
        value = None if date == QDate(2000, 1, 1) else date.toString("yyyy-MM-dd")
        planner.update_item_schedule(item_id, value)
        self._load_checklist()
        self.refresh_schedule()

    def _remove_from_schedule(self, item_id: int) -> None:
        planner.update_item_schedule(item_id, None)
        self._load_checklist()
        self.refresh_schedule()

    def refresh_schedule(self) -> None:
        items = planner.list_scheduled_items()
        self.schedule_table.setRowCount(len(items))
        for row, item in enumerate(items):
            item_id = item["id"]
            self.schedule_table.setItem(row, 1, QTableWidgetItem(item["project_name"]))
            self.schedule_table.setItem(row, 2, QTableWidgetItem(item["standard_code"]))
            self.schedule_table.setItem(row, 3, QTableWidgetItem(item["porta"]))

            date_edit = QDateEdit()
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("yyyy-MM-dd")
            date_edit.setSpecialValueText(" ")
            date_edit.setMinimumDate(QDate(2000, 1, 1))
            date_edit.setDate(QDate.fromString(item["scheduled_date"], "yyyy-MM-dd"))
            date_edit.dateChanged.connect(
                lambda date, iid=item_id: self._on_date_changed(iid, date)
            )
            self.schedule_table.setCellWidget(row, 0, date_edit)

            status_combo = QComboBox()
            for status in STATUS_OPTIONS:
                status_combo.addItem(STATUS_LABELS[status], status)
            status_combo.setCurrentIndex(STATUS_OPTIONS.index(item["status"]))
            status_combo.currentIndexChanged.connect(
                lambda _i, iid=item_id, combo=status_combo: self._on_status_changed(iid, combo)
            )
            self.schedule_table.setCellWidget(row, 4, status_combo)

            remove_btn = QPushButton("Remover do cronograma")
            remove_btn.clicked.connect(lambda _checked=False, iid=item_id: self._remove_from_schedule(iid))
            self.schedule_table.setCellWidget(row, 5, remove_btn)
