"""
gui/emc_section.py

Secao EMC do HALO: as telas do Automatizador de Ensaios (imunidade
IEC 61000-4-4 / 4-5 / 4-11) reunidas num painel unico.

Por que existe este arquivo em vez de reaproveitar a MainWindow original
--------------------------------------------------------------------
O Automatizador era um programa proprio, com a sua QMainWindow. Aqui ele
vira uma SECAO dentro do HALO, e uma QMainWindow nao pode ser aninhada.
Este modulo refaz apenas a casca -- as abas e a ligacao entre elas --
sem tocar em nenhuma das views: `PlannerView`, `ExecutionView` e as
demais sao importadas de `emc.gui` exatamente como estavam.

A fiacao original e reproduzida por inteiro:
  * `run_test_requested` do Planner leva para a aba de Execucao, ja com
    o projeto e a norma pre-selecionados;
  * a troca de aba dispara o refresh da view que entrou em foco -- sem
    isso, um projeto criado no Planner nao aparece na Execucao.

Cada aba fica dentro de uma area rolavel pelo mesmo motivo documentado
no programa original: em tela de notebook o conteudo nao cabe, e sem
rolagem o Qt espreme o layout ate o texto corromper.
"""

from __future__ import annotations

from PySide6.QtWidgets import QScrollArea, QTabWidget, QVBoxLayout, QWidget

from emc.gui.commands_view import CommandsView
from emc.gui.energy_registry_view import EnergyRegistryView
from emc.gui.execution_view import ExecutionView
from emc.gui.photo_validator_view import PhotoValidatorView
from emc.gui.planner_view import PlannerView
from emc.gui.reports_view import ReportsView
from emc.gui.settings_view import SettingsView


class EmcSection(QWidget):
    """Todas as telas de imunidade EMC, como um painel de abas."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.planner_view = PlannerView()
        self.execution_view = ExecutionView()
        self.energy_registry_view = EnergyRegistryView()
        self.reports_view = ReportsView()
        self.settings_view = SettingsView()
        self.commands_view = CommandsView()
        self.photo_validator_view = PhotoValidatorView()

        self.planner_view.run_test_requested.connect(self._ir_para_execucao)

        self._aba_execucao = self._rolavel(self.execution_view)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._rolavel(self.planner_view), "Planejamento")
        self.tabs.addTab(self._aba_execucao, "Execução")
        self.tabs.addTab(self._rolavel(self.energy_registry_view), "Registro de energia")
        self.tabs.addTab(self._rolavel(self.reports_view), "Relatórios")
        self.tabs.addTab(self._rolavel(self.settings_view), "Configurações")
        self.tabs.addTab(self._rolavel(self.commands_view), "Comandos")
        self.tabs.addTab(self._rolavel(self.photo_validator_view), "Validador de fotos (OCR)")
        self.tabs.currentChanged.connect(self._ao_trocar_aba)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.tabs)

    # ---- nomes das abas, para o menu poder saltar direto para uma delas ----
    ABAS = ("Planejamento", "Execução", "Registro de energia", "Relatórios",
            "Configurações", "Comandos", "Validador de fotos (OCR)")

    def ir_para(self, nome: str) -> bool:
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == nome:
                self.tabs.setCurrentIndex(i)
                return True
        return False

    @staticmethod
    def _rolavel(widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setWidget(widget)
        area.setFrameShape(QScrollArea.NoFrame)
        return area

    def _ir_para_execucao(self, project_id: int, standard_code: str) -> None:
        self.execution_view.preselect(project_id, standard_code)
        self.tabs.setCurrentWidget(self._aba_execucao)

    def _ao_trocar_aba(self, index: int) -> None:
        recipiente = self.tabs.widget(index)
        view = recipiente.widget() if isinstance(recipiente, QScrollArea) else recipiente
        if view is self.execution_view:
            self.execution_view.refresh_projects()
        elif view is self.energy_registry_view:
            self.energy_registry_view.refresh_projects()
        elif view is self.reports_view:
            self.reports_view.refresh()
        elif view is self.planner_view:
            self.planner_view.refresh_schedule()
