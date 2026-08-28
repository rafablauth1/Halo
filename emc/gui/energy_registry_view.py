from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emc.config import STANDARDS
from emc.core import energy_registry, planner

COL_ENSAIO = 0
COL_METROLOGISTA = 1
COL_TENSAO_LABEL = 2
COL_CODIGO = 3
COL_LEGENDA = 4
COL_DATA_INI = 5
COL_REG_INI = 6
COL_DATA_FIM = 7
COL_REG_FIM = 8
COL_OBS = 9

COLUMN_LABELS = [
    "Ensaio", "Metrologista", "Tensão",
    "Código", "Legenda", "Data Inicial", "Registro Inicial",
    "Data Final", "Registro Final", "Observações",
]


class EnergyRegistryView(QWidget):
    """Registro de leituras de energia por ensaio/tensão — equivalente à
    planilha 'Registro de Energia' usada no laboratório: acompanha se o
    medidor mantém a leitura correta antes/depois de cada evento EMC."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_project_id: int | None = None
        self._project_standard_codes: list[str] = list(STANDARDS)
        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Projeto:"))
        self.project_combo = QComboBox()
        self.project_combo.currentIndexChanged.connect(self._on_project_selected)
        top_row.addWidget(self.project_combo, 1)
        manage_codes_btn = QPushButton("Gerenciar códigos...")
        manage_codes_btn.clicked.connect(self._open_code_manager)
        top_row.addWidget(manage_codes_btn)
        layout.addLayout(top_row)

        summary_form = QFormLayout()
        self.cliente_label = QLabel("—")
        summary_form.addRow("Cliente:", self.cliente_label)
        self.protocolo_label = QLabel("—")
        summary_form.addRow("Protocolo:", self.protocolo_label)
        layout.addLayout(summary_form)
        equipment_hint = QLabel(
            "Identificação completa do equipamento (fabricante, modelo, série...) fica "
            "no Cadastro, na aba Planner — aqui só cliente/protocolo pra referência."
        )
        equipment_hint.setWordWrap(True)
        layout.addWidget(equipment_hint)

        generator_box = QGroupBox("Gerar leituras (ensaio + tensão)")
        generator_form = QFormLayout(generator_box)
        self.gen_ensaio_combo = QComboBox()
        generator_form.addRow("Ensaio:", self.gen_ensaio_combo)
        self.gen_metrologista_edit = QLineEdit()
        generator_form.addRow("Metrologista:", self.gen_metrologista_edit)
        self.gen_tensao_edit = QLineEdit()
        self.gen_tensao_edit.setPlaceholderText("ex.: 220V ou TENSÃO 1")
        generator_form.addRow("Tensão:", self.gen_tensao_edit)
        self.gen_data_inicial_edit = QLineEdit()
        self.gen_data_inicial_edit.setPlaceholderText("mesma data pra todos os códigos gerados")
        generator_form.addRow("Data Inicial:", self.gen_data_inicial_edit)
        self.gen_data_final_edit = QLineEdit()
        self.gen_data_final_edit.setPlaceholderText("mesma data pra todos os códigos gerados")
        generator_form.addRow("Data Final:", self.gen_data_final_edit)
        self.gen_clock_mode_checkbox = QCheckBox(
            "Modo relógio (1 leitura só, com a duração total do ensaio)"
        )
        generator_form.addRow("", self.gen_clock_mode_checkbox)
        gen_btn_row = QHBoxLayout()
        gen_btn = QPushButton("Gerar leituras (códigos do cadastro)")
        gen_btn.clicked.connect(self._generate_readings)
        gen_btn_row.addWidget(gen_btn)
        generator_form.addRow("", gen_btn_row)
        layout.addWidget(generator_box)

        readings_hint = QLabel(
            "Leituras — uma linha por código de grandeza registrado em cada tensão de "
            "cada ensaio. A Legenda é preenchida sozinha ao digitar o Código."
        )
        readings_hint.setWordWrap(True)
        layout.addWidget(readings_hint)

        filter_box = QGroupBox("Filtrar leituras")
        filter_layout = QHBoxLayout(filter_box)
        filter_layout.addWidget(QLabel("Ensaio:"))
        self.filter_ensaio_combo = QComboBox()
        self.filter_ensaio_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.filter_ensaio_combo.setMinimumContentsLength(18)
        self.filter_ensaio_combo.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.filter_ensaio_combo)
        filter_layout.addWidget(QLabel("Código:"))
        self.filter_codigo_combo = QComboBox()
        self.filter_codigo_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.filter_codigo_combo.setMinimumContentsLength(18)
        self.filter_codigo_combo.currentIndexChanged.connect(self._apply_filters)
        filter_layout.addWidget(self.filter_codigo_combo)
        refresh_filters_btn = QPushButton("Atualizar filtros")
        refresh_filters_btn.clicked.connect(self._refresh_filter_options)
        filter_layout.addWidget(refresh_filters_btn)
        clear_filters_btn = QPushButton("Limpar filtros")
        clear_filters_btn.clicked.connect(self._clear_filters)
        filter_layout.addWidget(clear_filters_btn)
        filter_layout.addStretch(1)
        expand_btn = QPushButton("Expandir tabela")
        expand_btn.clicked.connect(self._expand_table)
        filter_layout.addWidget(expand_btn)
        layout.addWidget(filter_box)

        self.table = QTableWidget(0, len(COLUMN_LABELS))
        self.table.setHorizontalHeaderLabels(COLUMN_LABELS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellChanged.connect(self._on_cell_changed)
        # Sem altura mínima, a tabela ficava espremida — o "stretch" sozinho não
        # garante espaço quando várias caixas acima dela (Gerar/Filtrar leituras)
        # já ocupam bastante altura. Garante que sempre dá pra ver várias linhas
        # de leitura de uma vez, mesmo com pouco espaço sobrando.
        self.table.setMinimumHeight(320)
        layout.addWidget(self.table, 1)
        self._table_layout = layout
        self._table_index = layout.indexOf(self.table)

        btn_row = QHBoxLayout()
        remove_btn = QPushButton("Remover linha selecionada")
        remove_btn.clicked.connect(self._remove_selected_row)
        btn_row.addWidget(remove_btn)
        layout.addLayout(btn_row)

        btn_row2 = QHBoxLayout()
        sort_btn = QPushButton("Ordenar por consumo de energia")
        sort_btn.clicked.connect(self._sort_by_consumption)
        btn_row2.addWidget(sort_btn)
        chain_btn = QPushButton("Encadear ensaios (final → inicial)...")
        chain_btn.clicked.connect(self._open_chain_dialog)
        btn_row2.addWidget(chain_btn)
        layout.addLayout(btn_row2)

        save_row = QHBoxLayout()
        save_btn = QPushButton("Salvar registro")
        save_btn.clicked.connect(self._save)
        save_row.addWidget(save_btn)
        self.save_status = QLabel("")
        save_row.addWidget(self.save_status, 1)
        layout.addLayout(save_row)

        self.refresh_projects()

    # ---- projeto ----

    def refresh_projects(self) -> None:
        current = self.project_combo.currentData()
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for project in planner.list_projects():
            self.project_combo.addItem(project["name"], project["id"])
        self.project_combo.blockSignals(False)
        if current is not None:
            index = self.project_combo.findData(current)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
                return
        if self.project_combo.count():
            self.project_combo.setCurrentIndex(0)
            self._on_project_selected(0)

    def _on_project_selected(self, _index: int) -> None:
        self.current_project_id = self.project_combo.currentData()
        self._load()

    # ---- carregar / salvar ----

    def _load(self) -> None:
        self.save_status.setText("")
        if self.current_project_id is None:
            self.cliente_label.setText("—")
            self.protocolo_label.setText("—")
            self.table.setRowCount(0)
            return
        project = planner.get_project(self.current_project_id) or {}
        self.cliente_label.setText(project.get("client") or "—")
        self.protocolo_label.setText(project.get("protocolo") or "—")

        project_codes = {item["standard_code"] for item in planner.list_test_items(self.current_project_id)}
        # ordena pela ordem natural de STANDARDS (4-2..4-19), não pela ordem alfabética do banco
        self._project_standard_codes = [code for code in STANDARDS if code in project_codes] or list(STANDARDS)

        self.gen_ensaio_combo.clear()
        for code in self._project_standard_codes:
            self.gen_ensaio_combo.addItem(f"{code} — {STANDARDS.get(code, '')}", code)

        leituras = energy_registry.get_leituras(self.current_project_id)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for leitura in leituras:
            self._append_row(leitura)
        self.table.blockSignals(False)
        self._refresh_filter_options()

    def _combo_codes(self, current: str = "") -> list[str]:
        """Ensaios do projeto atual (só os que foram marcados na criação do
        projeto); inclui o código da leitura mesmo que não esteja mais na
        lista do projeto, pra não perder/esconder dado já gravado."""
        codes = list(self._project_standard_codes)
        if current and current not in codes:
            codes.append(current)
        return codes

    def _save(self) -> None:
        if self.current_project_id is None:
            QMessageBox.warning(self, "Registro de energia", "Selecione um projeto antes de salvar.")
            return
        leituras = [self._row_to_dict(row) for row in range(self.table.rowCount())]
        energy_registry.save_leituras(self.current_project_id, leituras)
        self.save_status.setStyleSheet("color: green;")
        self.save_status.setText("Salvo.")

    # ---- linhas da tabela ----

    def _append_row(self, leitura: dict | None = None) -> int:
        leitura = leitura or {}
        row = self.table.rowCount()
        self.table.insertRow(row)

        combo = QComboBox()
        for code in self._combo_codes(leitura.get("standard_code", "")):
            combo.addItem(code, code)
        index = combo.findData(leitura.get("standard_code", ""))
        if index >= 0:
            combo.setCurrentIndex(index)
        self.table.setCellWidget(row, COL_ENSAIO, combo)

        self.table.setItem(row, COL_METROLOGISTA, QTableWidgetItem(leitura.get("metrologista", "")))
        self.table.setItem(row, COL_TENSAO_LABEL, QTableWidgetItem(leitura.get("tensao_label", "")))

        codigo = leitura.get("codigo", "")
        self.table.setItem(row, COL_CODIGO, QTableWidgetItem(str(codigo) if codigo != "" else ""))
        legenda_item = QTableWidgetItem(leitura.get("legenda", ""))
        legenda_item.setFlags(legenda_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, COL_LEGENDA, legenda_item)

        self.table.setItem(row, COL_DATA_INI, QTableWidgetItem(leitura.get("data_inicial", "")))
        self.table.setItem(row, COL_REG_INI, QTableWidgetItem(leitura.get("registro_inicial", "")))
        self.table.setItem(row, COL_DATA_FIM, QTableWidgetItem(leitura.get("data_final", "")))
        self.table.setItem(row, COL_REG_FIM, QTableWidgetItem(leitura.get("registro_final", "")))
        self.table.setItem(row, COL_OBS, QTableWidgetItem(leitura.get("observacoes", "")))
        return row

    def _row_to_dict(self, row: int) -> dict:
        combo = self.table.cellWidget(row, COL_ENSAIO)
        item = lambda col: self.table.item(row, col)
        text = lambda col: item(col).text() if item(col) else ""
        return {
            "standard_code": combo.currentData() if combo else "",
            "metrologista": text(COL_METROLOGISTA),
            "tensao_label": text(COL_TENSAO_LABEL),
            "codigo": text(COL_CODIGO),
            "legenda": text(COL_LEGENDA),
            "data_inicial": text(COL_DATA_INI),
            "registro_inicial": text(COL_REG_INI),
            "data_final": text(COL_DATA_FIM),
            "registro_final": text(COL_REG_FIM),
            "observacoes": text(COL_OBS),
        }

    def _generate_readings(self) -> None:
        """Gera as linhas de leitura pro ensaio/tensão escolhidos acima, de duas
        formas: normal (uma linha por código aplicável do Cadastro — cobre 'dados
        via Display', onde os códigos aplicáveis são os que o display mostra) ou
        'modo relógio' (uma única leitura, colocada só no final do ensaio, com a
        duração total do ensaio em segundos). Data Inicial/Final são as mesmas pra
        todos os códigos gerados juntos (é assim que se lê no display: tudo no
        mesmo momento)."""
        if self.current_project_id is None:
            QMessageBox.warning(self, "Gerar leituras", "Selecione um projeto antes de gerar leituras.")
            return
        standard_code = self.gen_ensaio_combo.currentData()
        if not standard_code:
            QMessageBox.warning(self, "Gerar leituras", "Este projeto não tem ensaios cadastrados.")
            return
        tensao_label = self.gen_tensao_edit.text().strip() or "TENSÃO 1"
        base = {
            "standard_code": standard_code,
            "metrologista": self.gen_metrologista_edit.text().strip(),
            "tensao_label": tensao_label,
            "data_inicial": self.gen_data_inicial_edit.text().strip(),
            "data_final": self.gen_data_final_edit.text().strip(),
        }

        if self.gen_clock_mode_checkbox.isChecked():
            self._append_row(
                {
                    **base,
                    "codigo": "",
                    "legenda": "Duração total do ensaio (s) — modo relógio",
                    "observacoes": "Preencher Registro Final com o tempo total do ensaio, em segundos.",
                }
            )
            self._refresh_filter_options()
            return

        codes = planner.get_applicable_codes(self.current_project_id)
        if not codes:
            QMessageBox.warning(
                self,
                "Gerar leituras",
                "Nenhum código aplicável cadastrado para este projeto ainda. "
                "Defina em Planner > Editar cadastro > Códigos aplicáveis.",
            )
            return
        for codigo in codes:
            self._append_row({**base, "codigo": str(codigo), "legenda": energy_registry.get_legend(codigo)})
        self._refresh_filter_options()

    def _sort_by_consumption(self) -> None:
        """Reordena os blocos (mesmo ensaio + mesma tensão) do menor pro maior
        consumo total registrado (Registro Final − Registro Inicial), preservando
        a ordem das linhas dentro de cada bloco — equivalente à macro
        OrdenarPorEnsaio da planilha original."""
        rows = [self._row_to_dict(r) for r in range(self.table.rowCount())]
        if len(rows) < 2:
            return

        def consumo(row: dict) -> float:
            try:
                return float(row["registro_final"]) - float(row["registro_inicial"])
            except (ValueError, TypeError):
                return 0.0

        groups: dict[tuple[str, str], list[dict]] = {}
        order: list[tuple[str, str]] = []
        for row in rows:
            key = (row["standard_code"], row["tensao_label"])
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(row)

        order.sort(key=lambda key: sum(consumo(r) for r in groups[key]))

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for key in order:
            for row in groups[key]:
                self._append_row(row)
        self.table.blockSignals(False)
        self._apply_filters()  # a reconstrução acima recria as linhas todas visíveis — reaplica o filtro ativo

    def _remove_selected_row(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _expand_table(self) -> None:
        """Reparenta temporariamente a tabela de leituras pra um diálogo maior,
        pra facilitar a leitura/edição com muitas linhas. Ao fechar, a tabela
        volta pro lugar original na aba."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Leituras — visão expandida")
        dialog.resize(1300, 750)
        dlg_layout = QVBoxLayout(dialog)
        dlg_layout.addWidget(self.table)
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(dialog.accept)
        dlg_layout.addWidget(close_btn)
        dialog.exec()
        self._table_layout.insertWidget(self._table_index, self.table, 1)

    def _on_cell_changed(self, row: int, column: int) -> None:
        if column != COL_CODIGO:
            return
        item = self.table.item(row, COL_CODIGO)
        text = item.text().strip() if item else ""
        legenda = ""
        if text.isdigit():
            legenda = energy_registry.get_legend(int(text))
        legenda_item = self.table.item(row, COL_LEGENDA)
        self.table.blockSignals(True)
        if legenda_item is None:
            legenda_item = QTableWidgetItem()
            legenda_item.setFlags(legenda_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, COL_LEGENDA, legenda_item)
        legenda_item.setText(legenda)
        self.table.blockSignals(False)

    # ---- filtrar leituras (por ensaio e por código) ----

    def _refresh_filter_options(self) -> None:
        current_ensaio = self.filter_ensaio_combo.currentData() if self.filter_ensaio_combo.count() else None
        current_codigo = self.filter_codigo_combo.currentData() if self.filter_codigo_combo.count() else None

        self.filter_ensaio_combo.blockSignals(True)
        self.filter_ensaio_combo.clear()
        self.filter_ensaio_combo.addItem("Todos", None)
        for code in self._project_standard_codes:
            self.filter_ensaio_combo.addItem(f"{code} — {STANDARDS.get(code, '')}", code)
        index = self.filter_ensaio_combo.findData(current_ensaio)
        self.filter_ensaio_combo.setCurrentIndex(index if index >= 0 else 0)
        self.filter_ensaio_combo.blockSignals(False)

        codigos_na_tabela = sorted(
            {self._row_to_dict(r)["codigo"] for r in range(self.table.rowCount()) if self._row_to_dict(r)["codigo"]},
            key=lambda c: (len(c), c),
        )
        self.filter_codigo_combo.blockSignals(True)
        self.filter_codigo_combo.clear()
        self.filter_codigo_combo.addItem("Todos", None)
        for codigo in codigos_na_tabela:
            legenda = energy_registry.get_legend(int(codigo)) if codigo.isdigit() else ""
            label = f"{codigo} — {legenda}" if legenda else codigo
            self.filter_codigo_combo.addItem(label, codigo)
        index2 = self.filter_codigo_combo.findData(current_codigo)
        self.filter_codigo_combo.setCurrentIndex(index2 if index2 >= 0 else 0)
        self.filter_codigo_combo.blockSignals(False)

        self._apply_filters()

    def _apply_filters(self) -> None:
        ensaio_filter = self.filter_ensaio_combo.currentData() if self.filter_ensaio_combo.count() else None
        codigo_filter = self.filter_codigo_combo.currentData() if self.filter_codigo_combo.count() else None
        for r in range(self.table.rowCount()):
            d = self._row_to_dict(r)
            match = True
            if ensaio_filter and d["standard_code"] != ensaio_filter:
                match = False
            if codigo_filter and d["codigo"] != codigo_filter:
                match = False
            self.table.setRowHidden(r, not match)

    def _clear_filters(self) -> None:
        self.filter_ensaio_combo.setCurrentIndex(0)
        self.filter_codigo_combo.setCurrentIndex(0)

    # ---- encadear ensaios (registro final de um vira o inicial do outro) ----

    def _open_chain_dialog(self) -> None:
        blocks = sorted(
            {(self._row_to_dict(r)["standard_code"], self._row_to_dict(r)["tensao_label"])
             for r in range(self.table.rowCount())}
        )
        blocks = [b for b in blocks if b[0] and b[1]]
        if len(blocks) < 2:
            QMessageBox.warning(
                self,
                "Encadear ensaios",
                "Precisa ter pelo menos 2 blocos (ensaio + tensão) com leituras geradas.",
            )
            return
        dialog = _ChainReadingsDialog(self, blocks)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        from_key, to_key = dialog.selection()
        if from_key == to_key:
            QMessageBox.warning(self, "Encadear ensaios", "Escolha dois blocos diferentes.")
            return
        self._chain_blocks(from_key, to_key)

    def _chain_blocks(self, from_key: tuple[str, str], to_key: tuple[str, str]) -> None:
        source_map = {}
        for r in range(self.table.rowCount()):
            d = self._row_to_dict(r)
            if (d["standard_code"], d["tensao_label"]) == from_key and d["codigo"]:
                source_map[d["codigo"]] = (d["data_final"], d["registro_final"])

        applied = 0
        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            d = self._row_to_dict(r)
            if (d["standard_code"], d["tensao_label"]) == to_key and d["codigo"] in source_map:
                data_final, registro_final = source_map[d["codigo"]]
                self.table.item(r, COL_DATA_INI).setText(data_final)
                self.table.item(r, COL_REG_INI).setText(registro_final)
                applied += 1
        self.table.blockSignals(False)
        QMessageBox.information(
            self, "Encadear ensaios", f"{applied} leitura(s) atualizada(s) por código correspondente."
        )

    # ---- catálogo de códigos ----

    def _open_code_manager(self) -> None:
        dialog = _CodeManagerDialog(self)
        dialog.exec()


class _ChainReadingsDialog(QDialog):
    """Escolhe dois blocos (ensaio+tensão) já com leituras geradas: o Registro
    Final de cada código do primeiro vira o Registro Inicial do mesmo código no
    segundo — pra quando um ensaio foi feito logo em seguida do outro sem
    resetar o medidor. É sempre uma escolha manual do operador, não uma dedução
    automática do app."""

    def __init__(self, parent, blocks: list[tuple[str, str]]):
        super().__init__(parent)
        self.setWindowTitle("Encadear ensaios")
        self.resize(420, 200)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "Escolha o ensaio/tensão que TERMINOU e o que COMEÇOU em seguida, sem "
                "resetar o medidor entre um e outro."
            )
        )
        form = QFormLayout()
        self.from_combo = QComboBox()
        self.to_combo = QComboBox()
        for code, label in blocks:
            text = f"{code} — {label}"
            self.from_combo.addItem(text, (code, label))
            self.to_combo.addItem(text, (code, label))
        form.addRow("Ensaio que terminou:", self.from_combo)
        form.addRow("Ensaio que começou depois:", self.to_combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selection(self) -> tuple[tuple[str, str], tuple[str, str]]:
        return self.from_combo.currentData(), self.to_combo.currentData()


class _CodeManagerDialog(QDialog):
    """Ver/editar o catálogo de códigos de grandezas (aba 'Codigos' da planilha)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Catálogo de códigos de grandezas")
        self.resize(520, 500)
        layout = QVBoxLayout(self)

        layout.addWidget(
            QLabel(
                "Códigos padrão de grandezas usadas por medidores eletrônicos no Brasil. "
                "Nem todo medidor implementa todos — apague os que não existirem no seu."
            )
        )
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Código", "Legenda"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        for entry in energy_registry.list_codes():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(entry["codigo"])))
            self.table.setItem(row, 1, QTableWidgetItem(entry["legenda"]))

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Adicionar código")
        add_btn.clicked.connect(self._add_code)
        btn_row.addWidget(add_btn)
        remove_btn = QPushButton("Remover selecionado")
        remove_btn.clicked.connect(self._remove_code)
        btn_row.addWidget(remove_btn)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_code(self) -> None:
        codigo, ok = QInputDialog.getInt(self, "Novo código", "Código:", 0, 0, 9999)
        if not ok:
            return
        legenda, ok2 = QInputDialog.getText(self, "Novo código", "Legenda:")
        if not ok2 or not legenda.strip():
            return
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(codigo)))
        self.table.setItem(row, 1, QTableWidgetItem(legenda.strip()))

    def _remove_code(self) -> None:
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)

    def _save_and_close(self) -> None:
        with_conn_codes = []
        for row in range(self.table.rowCount()):
            codigo_item = self.table.item(row, 0)
            legenda_item = self.table.item(row, 1)
            if not codigo_item or not codigo_item.text().strip().isdigit():
                continue
            with_conn_codes.append((int(codigo_item.text().strip()), legenda_item.text().strip() if legenda_item else ""))
        energy_registry.replace_codes(with_conn_codes)
        self.accept()
