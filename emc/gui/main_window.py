from PySide6.QtWidgets import QMainWindow, QScrollArea, QTabWidget, QWidget

from emc.gui.commands_view import CommandsView
from emc.gui.energy_registry_view import EnergyRegistryView
from emc.gui.execution_view import ExecutionView
from emc.gui.photo_validator_view import PhotoValidatorView
from emc.gui.planner_view import PlannerView
from emc.gui.reports_view import ReportsView
from emc.gui.settings_view import SettingsView


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Automatizador de Ensaios EMC")
        self.resize(1100, 750)

        self.planner_view = PlannerView()
        self.execution_view = ExecutionView()
        self.energy_registry_view = EnergyRegistryView()
        self.reports_view = ReportsView()
        self.settings_view = SettingsView()
        self.commands_view = CommandsView()
        self.photo_validator_view = PhotoValidatorView()

        self.planner_view.run_test_requested.connect(self._go_to_execution)

        # Cada aba fica dentro de um QScrollArea: em telas menores (notebook),
        # o conteúdo das abas (várias caixas empilhadas) não cabe todo de uma
        # vez — sem rolagem, o Qt força tudo a caber espremendo o layout, o
        # que corrompe visualmente o texto. Com scroll, o conteúdo mantém o
        # tamanho natural e rola em vez de espremer.
        self._execution_tab = self._scrollable(self.execution_view)
        tabs = QTabWidget()
        tabs.addTab(self._scrollable(self.planner_view), "Planner")
        tabs.addTab(self._execution_tab, "Execução")
        tabs.addTab(self._scrollable(self.energy_registry_view), "Registro de Energia")
        tabs.addTab(self._scrollable(self.reports_view), "Relatórios")
        tabs.addTab(self._scrollable(self.settings_view), "Configurações")
        tabs.addTab(self._scrollable(self.commands_view), "Comandos")
        tabs.addTab(self._scrollable(self.photo_validator_view), "Validador de Fotos (OCR)")
        tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs = tabs
        self.setCentralWidget(tabs)

    @staticmethod
    def _scrollable(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _go_to_execution(self, project_id: int, standard_code: str) -> None:
        self.execution_view.preselect(project_id, standard_code)
        self.tabs.setCurrentWidget(self._execution_tab)

    def _on_tab_changed(self, index: int) -> None:
        container = self.tabs.widget(index)
        widget = container.widget() if isinstance(container, QScrollArea) else container
        if widget is self.execution_view:
            self.execution_view.refresh_projects()
        elif widget is self.energy_registry_view:
            self.energy_registry_view.refresh_projects()
        elif widget is self.reports_view:
            self.reports_view.refresh()
        elif widget is self.planner_view:
            self.planner_view.refresh_schedule()
