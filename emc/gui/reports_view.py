import os
import subprocess
import sys

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emc.core.report_generator import generate_report
from emc.core.test_session import list_completed_sessions


class ReportsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        top_bar = QHBoxLayout()
        top_bar.addWidget(QLabel("Sessões de ensaio concluídas"))
        refresh_btn = QPushButton("Atualizar")
        refresh_btn.clicked.connect(self.refresh)
        top_bar.addStretch()
        top_bar.addWidget(refresh_btn)
        layout.addLayout(top_bar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["Projeto", "Norma", "EUT", "Nível", "Resultado", "Data", ""]
        )
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.refresh()

    def refresh(self) -> None:
        sessions = list_completed_sessions()
        self.table.setRowCount(len(sessions))
        for row, session in enumerate(sessions):
            self.table.setItem(row, 0, QTableWidgetItem(session["project_name"]))
            self.table.setItem(row, 1, QTableWidgetItem(session["standard_code"]))
            self.table.setItem(row, 2, QTableWidgetItem(session["eut_name"] or "-"))
            self.table.setItem(row, 3, QTableWidgetItem(session["level_label"] or "-"))
            self.table.setItem(
                row, 4, QTableWidgetItem((session["result"] or "pendente").upper())
            )
            self.table.setItem(row, 5, QTableWidgetItem(session["started_at"] or "-"))

            generate_btn = QPushButton("Gerar laudo")
            generate_btn.clicked.connect(
                lambda _checked=False, session_id=session["id"]: self._generate(session_id)
            )
            self.table.setCellWidget(row, 6, generate_btn)

    def _generate(self, session_id: int) -> None:
        try:
            file_path = generate_report(session_id)
        except Exception as exc:
            QMessageBox.critical(self, "Erro ao gerar laudo", str(exc))
            return
        QMessageBox.information(self, "Laudo gerado", f"Laudo salvo em:\n{file_path}")
        self._open_containing_folder(file_path)

    def _open_containing_folder(self, file_path: str) -> None:
        folder = os.path.dirname(file_path)
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            pass
