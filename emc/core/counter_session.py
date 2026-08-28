import time
from datetime import datetime

from PySide6.QtCore import QThread, Signal

from emc.instruments.agilent_53131a import Agilent53131ACounter


class CounterWorker(QThread):
    """Roda a leitura contínua do contador Agilent 53131A em thread separada,
    pra não travar a tela durante os gates longos (podem levar minutos).

    Três modos, com lógicas bem diferentes:
    - 'manual': o app configura o instrumento a cada leitura (:CONFigure:
      TOTalize:TIMed + INIT), espera gate_time_s e lê com FETCh?, repetindo
      a cada interval_s.
    - 'recall': carrega um registro salvo no instrumento (*RCL N) uma vez no
      início e depois só "escuta" — espera cada resultado ficar pronto e
      consulta com FETCh? (sem mandar INIT, respeitando o modo de disparo
      que já veio no registro, inclusive se for :INITiate:CONTinuous ON) —
      e só registra quando o valor lido muda, sem precisar configurar
      tempo/intervalo.
    - 'stopwatch': cronômetro manual — lê um valor inicial ao iniciar (emite
      stopwatch_started), fica esperando o operador pedir parada, e ao
      finalizar lê o valor final e emite (via reading) a DIFERENÇA entre os
      dois — usa a contagem do próprio instrumento como referência de tempo
      decorrido, não o relógio do PC."""

    reading = Signal(str, float)  # timestamp ISO, valor lido (ou diferença, no modo cronômetro)
    stopwatch_started = Signal(str, float)  # timestamp ISO, valor inicial capturado
    error = Signal(str)
    stopped = Signal()

    def __init__(
        self,
        counter: Agilent53131ACounter,
        gate_time_s: float | None = None,
        interval_s: float | None = None,
        mode: str = "manual",
        recall_register: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.counter = counter
        self.gate_time_s = gate_time_s
        self.interval_s = interval_s
        self.mode = mode
        self.recall_register = recall_register
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            self.counter.connect()
            if self.mode in ("recall", "stopwatch") and self.recall_register is not None:
                self.counter.recall(self.recall_register)
        except Exception as exc:
            self.error.emit(str(exc))
            self.stopped.emit()
            return

        try:
            if self.mode == "recall":
                self._run_recall_loop()
            elif self.mode == "stopwatch":
                self._run_stopwatch()
            else:
                self._run_manual_loop()
        finally:
            self.counter.disconnect()
            self.stopped.emit()

    def _run_manual_loop(self) -> None:
        while not self._stop_requested:
            try:
                value = self.counter.read_totalize(self.gate_time_s)
            except Exception as exc:
                self.error.emit(str(exc))
                break
            if self._stop_requested:
                break
            timestamp = datetime.now().isoformat(timespec="seconds")
            self.reading.emit(timestamp, value)

            waited = 0.0
            while waited < self.interval_s and not self._stop_requested:
                time.sleep(0.1)
                waited += 0.1

    def _run_recall_loop(self) -> None:
        last_value = None
        while not self._stop_requested:
            try:
                value = self.counter.read_current_blocking()
            except Exception as exc:
                self.error.emit(str(exc))
                break
            if self._stop_requested:
                break
            if value != last_value:
                last_value = value
                timestamp = datetime.now().isoformat(timespec="seconds")
                self.reading.emit(timestamp, value)
            # pequena pausa entre consultas — não afeta o tempo real de gate
            # (isso já é respeitado pelo FETCh? bloqueante), só evita
            # martelar o barramento sem necessidade entre uma tentativa e
            # outra quando o instrumento responde rápido.
            time.sleep(0.1)

    def _run_stopwatch(self) -> None:
        try:
            initial_value = self.counter.read_current_blocking()
        except Exception as exc:
            self.error.emit(str(exc))
            return
        start_timestamp = datetime.now().isoformat(timespec="seconds")
        self.stopwatch_started.emit(start_timestamp, initial_value)

        while not self._stop_requested:
            time.sleep(0.1)

        try:
            final_value = self.counter.read_current_blocking()
        except Exception as exc:
            self.error.emit(str(exc))
            return
        end_timestamp = datetime.now().isoformat(timespec="seconds")
        total = final_value - initial_value
        self.reading.emit(end_timestamp, total)


class RecallWorker(QThread):
    """Conecta no contador, carrega um registro de Recall salvo (*RCL N) e
    desconecta — em thread separada pra não travar a tela."""

    result = Signal(bool, str)

    def __init__(self, counter: Agilent53131ACounter, register: int, parent=None):
        super().__init__(parent)
        self.counter = counter
        self.register = register

    def run(self) -> None:
        try:
            self.counter.connect()
            self.counter.recall(self.register)
            self.result.emit(True, f"Recall {self.register} carregado.")
        except Exception as exc:
            self.result.emit(False, str(exc))
        finally:
            self.counter.disconnect()
