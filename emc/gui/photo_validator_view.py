import csv
import os
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional, Union

from PySide6.QtCore import QRect, Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from emc.core.photo_validator import (
    JsonResult,
    OcrEngine,
    PhotoResult,
    Roi,
    ScheduleEntry,
    find_json_files,
    list_photos,
    validate_json_file,
    validate_photo,
)

PHOTO_STATUS_LABELS = {
    "ok": "OK",
    "divergente": "DIVERGENTE",
    "erro_leitura": "ERRO DE LEITURA",
    "sem_horario": "SEM HORÁRIO NO CRONOGRAMA",
}
JSON_STATUS_LABELS = {
    "ok": "OK",
    "divergente": "DIVERGENTE",
    "erro": "ERRO",
}
STATUS_COLORS = {
    "ok": "#1e7d32",
    "divergente": "#b71c1c",
    "erro_leitura": "#e65100",
    "erro": "#e65100",
    "sem_horario": "#616161",
}

MODE_PHOTOS = "photos"
MODE_JSON = "json"


class _SortableItem(QTableWidgetItem):
    """QTableWidgetItem que ordena por um valor real (número/data), não pelo
    texto exibido — sem isso "10" viria antes de "9" na ordenação, e datas
    em dd/mm/aaaa não ordenariam cronologicamente."""

    def __init__(self, text: str, sort_key):
        super().__init__(text)
        self._sort_key = sort_key

    def __lt__(self, other) -> bool:
        if isinstance(other, _SortableItem):
            try:
                return self._sort_key < other._sort_key
            except TypeError:
                return str(self._sort_key) < str(other._sort_key)
        return super().__lt__(other)


def _sortable_time_item(timestamp: Optional[datetime]) -> _SortableItem:
    text = timestamp.strftime("%d/%m/%Y %H:%M:%S") if timestamp else "—"
    sort_key = timestamp or datetime.min
    return _SortableItem(text, sort_key)


def _sortable_numeric_item(value: Optional[str]) -> _SortableItem:
    text = value if value else "—"
    try:
        sort_key = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        sort_key = float("-inf")
    return _SortableItem(text, sort_key)


class _RoiSelectLabel(QLabel):
    """Mostra a primeira foto e deixa arrastar um retângulo com o mouse pra
    marcar onde fica o mostrador — o recorte é guardado como fração da
    imagem (0..1), então vale pra qualquer foto com o mesmo enquadramento."""

    roi_changed = Signal(object)  # Roi | None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: Optional[QPixmap] = None
        self._drag_start = None
        self._drag_rect: Optional[QRect] = None
        self.setMinimumHeight(300)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #111; border: 1px solid #444;")
        self.setText("Importe as fotos e clique e arraste aqui pra marcar a área do mostrador")

    def set_photo(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self._pixmap = pixmap.scaled(
            self.width() or 600, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        self._drag_rect = None
        self._update_display()

    def _update_display(self) -> None:
        if self._pixmap is None:
            return
        canvas = QPixmap(self._pixmap)
        if self._drag_rect is not None:
            painter = QPainter(canvas)
            pen = QPen(Qt.GlobalColor.red)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self._drag_rect)
            painter.end()
        self.setPixmap(canvas)

    def mousePressEvent(self, event) -> None:
        if self._pixmap is None:
            return
        self._drag_start = event.position().toPoint()
        self._drag_rect = QRect(self._drag_start, self._drag_start)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None:
            return
        self._drag_rect = QRect(self._drag_start, event.position().toPoint()).normalized()
        self._update_display()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_start is None or self._pixmap is None:
            return
        self._drag_rect = QRect(self._drag_start, event.position().toPoint()).normalized()
        self._drag_start = None
        self._update_display()

        # Converte o retângulo desenhado (em pixels do QLabel) pra fração da
        # imagem exibida — o QPixmap escalado ocupa o canto superior esquerdo
        # do QLabel (sem esticar), então o cálculo é direto por cima dele.
        pw, ph = self._pixmap.width(), self._pixmap.height()
        if pw == 0 or ph == 0 or self._drag_rect.width() < 5 or self._drag_rect.height() < 5:
            self.roi_changed.emit(None)
            return
        roi = Roi(
            left=max(0.0, self._drag_rect.left() / pw),
            top=max(0.0, self._drag_rect.top() / ph),
            right=min(1.0, self._drag_rect.right() / pw),
            bottom=min(1.0, self._drag_rect.bottom() / ph),
        )
        self.roi_changed.emit(roi)


class _PhotoValidationWorker(QThread):
    progress = Signal(int, int, str)  # feito, total, nome do arquivo atual
    finished_all = Signal(list)  # list[PhotoResult]
    error = Signal(str)

    def __init__(self, photos: list[Path], schedule: list[ScheduleEntry], roi: Optional[Roi], parent=None):
        super().__init__(parent)
        self.photos = photos
        self.schedule = schedule
        self.roi = roi
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            engine = OcrEngine()
        except Exception as exc:
            self.error.emit(f"Não foi possível carregar o motor de OCR: {exc}")
            return

        results: list[PhotoResult] = []
        total = len(self.photos)
        for i, path in enumerate(self.photos, start=1):
            if self._stop_requested:
                break
            result = validate_photo(engine, path, self.schedule, self.roi)
            results.append(result)
            self.progress.emit(i, total, path.name)
        self.finished_all.emit(results)


class _JsonValidationWorker(QThread):
    progress = Signal(int, int, str)
    finished_all = Signal(list)  # list[JsonResult]

    def __init__(self, json_paths: list[Path], key: str, expected_value: str, parent=None):
        super().__init__(parent)
        self.json_paths = json_paths
        self.key = key
        self.expected_value = expected_value
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        results: list[JsonResult] = []
        total = len(self.json_paths)
        for i, path in enumerate(self.json_paths, start=1):
            if self._stop_requested:
                break
            results.append(validate_json_file(path, self.key, self.expected_value))
            self.progress.emit(i, total, path.name)
        self.finished_all.emit(results)


def _parse_time(edit: QTimeEdit) -> dt_time:
    qt = edit.time()
    return dt_time(qt.hour(), qt.minute(), qt.second())


class PhotoValidatorView(QWidget):
    """Aba de validação automática de resultados de ensaio contra um valor
    esperado — dois modos:
    - Fotos (OCR): lê por OCR o valor mostrado no display de um equipamento
      (ex.: velocidade num radar) em cada foto de uma sequência, contra uma
      velocidade esperada que pode mudar por faixa de horário.
    - Pastas com JSON: cada subpasta de uma pasta-raiz tem um .json de
      resultado; confere um campo dele (ex.: "Speed") contra um valor fixo
      esperado — sem foto, sem horário envolvido."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.photos: list[Path] = []
        self.roi: Optional[Roi] = None
        self.photo_results: list[PhotoResult] = []
        self.json_paths: list[Path] = []
        self.json_results: list[JsonResult] = []
        self.mode = MODE_PHOTOS
        self._worker: Union[_PhotoValidationWorker, _JsonValidationWorker, None] = None

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("<b>Validador de resultados de ensaio</b>"))

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Modo:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Fotos (OCR do display)", MODE_PHOTOS)
        self.mode_combo.addItem("Pastas com JSON (compara um campo)", MODE_JSON)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_photo_mode_widget())
        self.mode_stack.addWidget(self._build_json_mode_widget())
        layout.addWidget(self.mode_stack)

        # ---- validar (comum aos dois modos) ----
        validate_row = QHBoxLayout()
        self.validate_btn = QPushButton("Validar")
        self.validate_btn.clicked.connect(self._start_validation)
        validate_row.addWidget(self.validate_btn)
        self.only_problems_checkbox = QCheckBox("Mostrar só erros/divergências")
        self.only_problems_checkbox.toggled.connect(self._refresh_results_table)
        validate_row.addWidget(self.only_problems_checkbox)
        validate_row.addStretch(1)
        export_btn = QPushButton("Exportar resultados (CSV)")
        export_btn.clicked.connect(self._export_csv)
        validate_row.addWidget(export_btn)
        layout.addLayout(validate_row)

        self.summary_label = QLabel("")
        layout.addWidget(self.summary_label)

        # ---- resultados (comum aos dois modos) ----
        self.results_table = QTableWidget(0, 6)
        self.results_table.setHorizontalHeaderLabels(["Item", "Arquivo", "Horário", "Esperado", "Lido", "Status"])
        header = self.results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)  # a última coluna (Status) preenche o espaço sobrando
        self.results_table.setColumnWidth(0, 65)  # Item — mais fino, o nome completo já está em "Arquivo"
        self.results_table.setColumnWidth(1, 120)
        self.results_table.setColumnWidth(2, 110)
        self.results_table.setColumnWidth(3, 60)
        self.results_table.setColumnWidth(4, 60)
        self.results_table.setSortingEnabled(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.results_table.setMinimumHeight(300)
        self.results_table.doubleClicked.connect(self._open_selected_row)
        layout.addWidget(self.results_table, 1)
        self.open_hint_label = QLabel("Dica: dê duplo clique numa linha pra abrir a foto correspondente.")
        layout.addWidget(self.open_hint_label)

    # ---- modo Fotos (OCR) ----

    def _build_photo_mode_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        photo_mode_hint = QLabel(
            "Confere o valor lido no display em cada foto de uma sequência contra uma "
            "velocidade esperada, que pode mudar por faixa de horário durante o ensaio."
        )
        photo_mode_hint.setWordWrap(True)
        layout.addWidget(photo_mode_hint)

        import_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("Nenhuma pasta selecionada")
        import_row.addWidget(self.folder_edit, 1)
        browse_btn = QPushButton("Escolher pasta com as fotos...")
        browse_btn.clicked.connect(self._choose_photo_folder)
        import_row.addWidget(browse_btn)
        layout.addLayout(import_row)

        self.photos_count_label = QLabel("0 foto(s) importada(s).")
        layout.addWidget(self.photos_count_label)

        roi_box = QGroupBox("Área do mostrador na foto (opcional, mas melhora muito a precisão)")
        roi_layout = QVBoxLayout(roi_box)
        roi_hint = QLabel("Clique e arraste na foto abaixo pra marcar só a área do display. Deixe em branco pra ler a foto inteira.")
        roi_hint.setWordWrap(True)
        roi_layout.addWidget(roi_hint)
        self.roi_label = _RoiSelectLabel()
        self.roi_label.roi_changed.connect(self._on_roi_changed)
        roi_layout.addWidget(self.roi_label)
        roi_btn_row = QHBoxLayout()
        self.roi_status_label = QLabel("Nenhuma área marcada — vai ler a foto inteira.")
        roi_btn_row.addWidget(self.roi_status_label, 1)
        clear_roi_btn = QPushButton("Limpar área marcada")
        clear_roi_btn.clicked.connect(self._clear_roi)
        roi_btn_row.addWidget(clear_roi_btn)
        roi_layout.addLayout(roi_btn_row)
        layout.addWidget(roi_box)

        schedule_box = QGroupBox("Cronograma — velocidade esperada por faixa de horário")
        schedule_layout = QVBoxLayout(schedule_box)
        self.schedule_table = QTableWidget(0, 3)
        self.schedule_table.setHorizontalHeaderLabels(["De (HH:MM:SS)", "Até (HH:MM:SS)", "Velocidade esperada"])
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.schedule_table.setMinimumHeight(150)
        schedule_layout.addWidget(self.schedule_table)
        schedule_btn_row = QHBoxLayout()
        add_row_btn = QPushButton("Adicionar faixa")
        add_row_btn.clicked.connect(self._add_schedule_row)
        schedule_btn_row.addWidget(add_row_btn)
        remove_row_btn = QPushButton("Remover faixa selecionada")
        remove_row_btn.clicked.connect(self._remove_schedule_row)
        schedule_btn_row.addWidget(remove_row_btn)
        schedule_btn_row.addStretch(1)
        schedule_layout.addLayout(schedule_btn_row)
        layout.addWidget(schedule_box)
        self._add_schedule_row()

        return widget

    def _choose_photo_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta com as fotos")
        if not folder:
            return
        folder_path = Path(folder)
        self.photos = list_photos(folder_path)
        self.folder_edit.setText(folder)
        self.photos_count_label.setText(f"{len(self.photos)} foto(s) importada(s).")
        if self.photos:
            self.roi_label.set_photo(self.photos[0])

    def _on_roi_changed(self, roi: Optional[Roi]) -> None:
        self.roi = roi
        if roi is None:
            self.roi_status_label.setText("Nenhuma área marcada — vai ler a foto inteira.")
        else:
            self.roi_status_label.setText(
                f"Área marcada: {roi.left:.0%}–{roi.right:.0%} horizontal, "
                f"{roi.top:.0%}–{roi.bottom:.0%} vertical."
            )

    def _clear_roi(self) -> None:
        self.roi = None
        self.roi_label._drag_rect = None
        self.roi_label._update_display()
        self.roi_status_label.setText("Nenhuma área marcada — vai ler a foto inteira.")

    def _add_schedule_row(self) -> None:
        row = self.schedule_table.rowCount()
        self.schedule_table.insertRow(row)
        start_edit = QTimeEdit()
        start_edit.setDisplayFormat("HH:mm:ss")
        end_edit = QTimeEdit()
        end_edit.setDisplayFormat("HH:mm:ss")
        end_edit.setTime(end_edit.time().addSecs(3600))
        self.schedule_table.setCellWidget(row, 0, start_edit)
        self.schedule_table.setCellWidget(row, 1, end_edit)
        self.schedule_table.setItem(row, 2, QTableWidgetItem(""))

    def _remove_schedule_row(self) -> None:
        row = self.schedule_table.currentRow()
        if row >= 0:
            self.schedule_table.removeRow(row)

    def _collect_schedule(self) -> list[ScheduleEntry]:
        entries = []
        for row in range(self.schedule_table.rowCount()):
            start_edit = self.schedule_table.cellWidget(row, 0)
            end_edit = self.schedule_table.cellWidget(row, 1)
            value_item = self.schedule_table.item(row, 2)
            if start_edit is None or end_edit is None:
                continue
            value_text = value_item.text().strip() if value_item else ""
            if not value_text:
                continue
            entries.append(
                ScheduleEntry(start=_parse_time(start_edit), end=_parse_time(end_edit), expected_value=value_text)
            )
        return entries

    # ---- modo Pastas com JSON ----

    def _build_json_mode_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        json_mode_hint = QLabel(
            "Pasta-raiz com várias subpastas, cada uma com um .json de resultado — "
            "confere um campo desse json (ex.: \"Speed\": 60) contra um valor fixo "
            "esperado, igual pra todas as subpastas. Não depende de foto; o horário "
            "mostrado vem do campo \"Timestamp\" do próprio json."
        )
        json_mode_hint.setWordWrap(True)
        layout.addWidget(json_mode_hint)

        import_row = QHBoxLayout()
        self.json_folder_edit = QLineEdit()
        self.json_folder_edit.setReadOnly(True)
        self.json_folder_edit.setPlaceholderText("Nenhuma pasta selecionada")
        import_row.addWidget(self.json_folder_edit, 1)
        browse_btn = QPushButton("Escolher pasta-raiz...")
        browse_btn.clicked.connect(self._choose_json_folder)
        import_row.addWidget(browse_btn)
        layout.addLayout(import_row)

        self.json_count_label = QLabel("0 arquivo(s) json encontrado(s).")
        layout.addWidget(self.json_count_label)

        field_row = QHBoxLayout()
        field_row.addWidget(QLabel("Campo a comparar:"))
        self.json_key_edit = QLineEdit("Speed")
        field_row.addWidget(self.json_key_edit)
        field_row.addWidget(QLabel("Valor esperado:"))
        self.json_expected_edit = QLineEdit("60")
        field_row.addWidget(self.json_expected_edit)
        field_row.addStretch(1)
        layout.addLayout(field_row)
        layout.addStretch(1)

        return widget

    def _choose_json_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta-raiz (com as subpastas de resultado)")
        if not folder:
            return
        folder_path = Path(folder)
        self.json_paths = find_json_files(folder_path)
        self.json_folder_edit.setText(folder)
        self.json_count_label.setText(f"{len(self.json_paths)} arquivo(s) json encontrado(s).")

    # ---- alternar modo ----

    def _on_mode_changed(self, index: int) -> None:
        self.mode = self.mode_combo.itemData(index)
        self.mode_stack.setCurrentIndex(index)
        self.validate_btn.setText("Validar fotos" if self.mode == MODE_PHOTOS else "Validar JSONs")
        self.open_hint_label.setText(
            "Dica: dê duplo clique numa linha pra abrir a foto correspondente."
            if self.mode == MODE_PHOTOS
            else "Dica: dê duplo clique numa linha pra abrir a pasta do json correspondente."
        )
        self._refresh_results_table()

    # ---- validação ----

    def _start_validation(self) -> None:
        if self.mode == MODE_PHOTOS:
            self._start_photo_validation()
        else:
            self._start_json_validation()

    def _start_photo_validation(self) -> None:
        if not self.photos:
            QMessageBox.warning(self, "Validador", "Escolha uma pasta com fotos antes de validar.")
            return
        schedule = self._collect_schedule()
        if not schedule:
            QMessageBox.warning(self, "Validador", "Adicione ao menos uma faixa de horário com velocidade esperada.")
            return

        progress = QProgressDialog("Rodando OCR nas fotos...", "Cancelar", 0, len(self.photos), self)
        progress.setWindowTitle("Validador de fotos")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        worker = _PhotoValidationWorker(self.photos, schedule, self.roi, parent=self)
        worker.progress.connect(
            lambda done, total, name: (progress.setValue(done), progress.setLabelText(f"{done}/{total} — {name}"))
        )
        worker.error.connect(lambda msg: QMessageBox.critical(self, "Validador", msg))
        worker.finished_all.connect(lambda results: self._on_photo_validation_finished(results, progress))
        progress.canceled.connect(worker.request_stop)
        self._worker = worker
        self.validate_btn.setEnabled(False)
        worker.start()

    def _start_json_validation(self) -> None:
        if not self.json_paths:
            QMessageBox.warning(self, "Validador", "Escolha uma pasta-raiz com subpastas de json antes de validar.")
            return
        key = self.json_key_edit.text().strip()
        expected = self.json_expected_edit.text().strip()
        if not key or not expected:
            QMessageBox.warning(self, "Validador", "Informe o campo e o valor esperado.")
            return

        progress = QProgressDialog("Comparando os jsons...", "Cancelar", 0, len(self.json_paths), self)
        progress.setWindowTitle("Validador de JSONs")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        worker = _JsonValidationWorker(self.json_paths, key, expected, parent=self)
        worker.progress.connect(
            lambda done, total, name: (progress.setValue(done), progress.setLabelText(f"{done}/{total} — {name}"))
        )
        worker.finished_all.connect(lambda results: self._on_json_validation_finished(results, progress))
        progress.canceled.connect(worker.request_stop)
        self._worker = worker
        self.validate_btn.setEnabled(False)
        worker.start()

    def _on_photo_validation_finished(self, results: list[PhotoResult], progress: QProgressDialog) -> None:
        progress.close()
        self.validate_btn.setEnabled(True)
        self._worker = None
        self.photo_results = results
        self._refresh_results_table()

        ok = sum(1 for r in results if r.status == "ok")
        divergente = sum(1 for r in results if r.status == "divergente")
        erro = sum(1 for r in results if r.status == "erro_leitura")
        sem_horario = sum(1 for r in results if r.status == "sem_horario")
        self.summary_label.setText(
            f"{len(results)} foto(s) analisada(s) — {ok} OK, {divergente} divergente(s), "
            f"{erro} erro(s) de leitura, {sem_horario} sem horário no cronograma."
        )

    def _on_json_validation_finished(self, results: list[JsonResult], progress: QProgressDialog) -> None:
        progress.close()
        self.validate_btn.setEnabled(True)
        self._worker = None
        self.json_results = results
        self._refresh_results_table()

        ok = sum(1 for r in results if r.status == "ok")
        divergente = sum(1 for r in results if r.status == "divergente")
        erro = sum(1 for r in results if r.status == "erro")
        self.summary_label.setText(
            f"{len(results)} json(s) analisado(s) — {ok} OK, {divergente} divergente(s), {erro} erro(s)."
        )

    # ---- resultados (tabela genérica pros dois modos) ----

    def _refresh_results_table(self) -> None:
        only_problems = self.only_problems_checkbox.isChecked()
        self.results_table.setSortingEnabled(False)  # evita reordenar a cada linha inserida
        self.results_table.setRowCount(0)

        if self.mode == MODE_PHOTOS:
            rows = [r for r in self.photo_results if not only_problems or r.status != "ok"]
            for r in rows:
                row = self.results_table.rowCount()
                self.results_table.insertRow(row)
                item_col = QTableWidgetItem(r.path.name)
                item_col.setData(Qt.ItemDataRole.UserRole, str(r.path))
                self.results_table.setItem(row, 0, item_col)
                self.results_table.setItem(row, 1, QTableWidgetItem(r.path.name))
                self.results_table.setItem(row, 2, _sortable_time_item(r.timestamp))
                self.results_table.setItem(row, 3, _sortable_numeric_item(r.expected_value))
                self.results_table.setItem(row, 4, _sortable_numeric_item(r.read_value))
                self._set_status_item(row, r.status, PHOTO_STATUS_LABELS)
        else:
            rows = [r for r in self.json_results if not only_problems or r.status != "ok"]
            expected_text = self.json_expected_edit.text().strip() if hasattr(self, "json_expected_edit") else ""
            for r in rows:
                row = self.results_table.rowCount()
                self.results_table.insertRow(row)
                item_col = QTableWidgetItem(r.folder_name)
                item_col.setData(Qt.ItemDataRole.UserRole, str(r.path.parent))
                self.results_table.setItem(row, 0, item_col)
                self.results_table.setItem(row, 1, QTableWidgetItem(r.path.name))
                self.results_table.setItem(row, 2, _sortable_time_item(r.timestamp))
                self.results_table.setItem(row, 3, _sortable_numeric_item(expected_text))
                found_text = str(r.found_value) if r.found_value is not None else (r.error_message or "—")
                self.results_table.setItem(row, 4, _sortable_numeric_item(found_text))
                self._set_status_item(row, r.status, JSON_STATUS_LABELS)

        self.results_table.setSortingEnabled(True)

    def _set_status_item(self, row: int, status: str, labels: dict) -> None:
        status_item = QTableWidgetItem(labels.get(status, status))
        status_item.setForeground(Qt.GlobalColor.white)
        status_item.setBackground(QColor(STATUS_COLORS.get(status, "#333")))
        self.results_table.setItem(row, 5, status_item)

    def _open_selected_row(self) -> None:
        row = self.results_table.currentRow()
        if row < 0:
            return
        item_col = self.results_table.item(row, 0)
        target = item_col.data(Qt.ItemDataRole.UserRole) if item_col else None
        if not target:
            return

        try:
            os.startfile(target)  # noqa: S606 — abrir no Explorer/visualizador padrão do Windows
        except Exception as exc:
            QMessageBox.warning(self, "Validador", f"Não foi possível abrir: {exc}")

    # ---- exportar ----

    def _export_csv(self) -> None:
        if self.mode == MODE_PHOTOS:
            self._export_photo_csv()
        else:
            self._export_json_csv()

    def _export_photo_csv(self) -> None:
        if not self.photo_results:
            QMessageBox.information(self, "Validador", "Nenhum resultado pra exportar ainda.")
            return
        path_str, _ = QFileDialog.getSaveFileName(self, "Exportar resultados", "validacao_fotos.csv", "CSV (*.csv)")
        if not path_str:
            return
        with open(path_str, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Foto", "Horário", "Esperado", "Lido", "Status"])
            for r in self.photo_results:
                ts_text = r.timestamp.strftime("%d/%m/%Y %H:%M:%S") if r.timestamp else ""
                writer.writerow(
                    [
                        r.path.name,
                        ts_text,
                        r.expected_value or "",
                        r.read_value or "",
                        PHOTO_STATUS_LABELS.get(r.status, r.status),
                    ]
                )
        QMessageBox.information(self, "Validador", f"Resultados exportados para:\n{path_str}")

    def _export_json_csv(self) -> None:
        if not self.json_results:
            QMessageBox.information(self, "Validador", "Nenhum resultado pra exportar ainda.")
            return
        path_str, _ = QFileDialog.getSaveFileName(self, "Exportar resultados", "validacao_json.csv", "CSV (*.csv)")
        if not path_str:
            return
        expected_text = self.json_expected_edit.text().strip()
        with open(path_str, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Pasta", "Arquivo", "Horário", "Esperado", "Lido", "Status"])
            for r in self.json_results:
                found_text = str(r.found_value) if r.found_value is not None else r.error_message
                ts_text = r.timestamp.strftime("%d/%m/%Y %H:%M:%S") if r.timestamp else ""
                writer.writerow(
                    [
                        r.folder_name,
                        r.path.name,
                        ts_text,
                        expected_text,
                        found_text,
                        JSON_STATUS_LABELS.get(r.status, r.status),
                    ]
                )
        QMessageBox.information(self, "Validador", f"Resultados exportados para:\n{path_str}")
