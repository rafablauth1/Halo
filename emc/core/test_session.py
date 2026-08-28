import json
import threading
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QThread, Signal

from emc.core.db import db_cursor
from emc.instruments.agilent_53131a import Agilent53131ACounter
from emc.instruments.base import InstrumentDriver


class TestSessionWorker(QThread):
    """Roda um ensaio contra um driver de instrumento em thread separada,
    gravando progresso e resultado no banco a cada etapa.

    Opcionalmente, sincroniza com o contador de frequência (ligado no pulso
    de saída do medidor sob ensaio — "o relógio"): lê o pulso ATUAL antes de
    iniciar o driver do ensaio, roda o ensaio inteiro, e lê o próximo pulso
    novo assim que o ensaio termina. A diferença de tempo entre esses dois
    pulsos (marcações reais do próprio medidor, não só o cronômetro do PC)
    vira o "tempo do ensaio" registrado na sessão."""

    progress = Signal(str)
    paused = Signal(str)  # mensagem para o operador (ex.: trocar setup para próximo elemento)
    finished_session = Signal(int)  # session_id

    def __init__(
        self,
        driver: InstrumentDriver,
        project_id: int,
        standard_code: str,
        eut_name: str,
        eut_serial: str,
        operator: str,
        level_label: str,
        params: dict,
        counter: Optional[Agilent53131ACounter] = None,
        counter_recall_register: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.driver = driver
        self.project_id = project_id
        self.standard_code = standard_code
        self.eut_name = eut_name
        self.eut_serial = eut_serial
        self.operator = operator
        self.level_label = level_label
        self.params = params
        self.counter = counter
        self.counter_recall_register = counter_recall_register
        self._stop_requested = False
        self._pause_requested = False
        self.session_id: Optional[int] = None
        self._resume_event = threading.Event()

    def request_stop(self) -> None:
        self._stop_requested = True
        self._resume_event.set()  # destrava imediatamente se estiver pausado esperando o operador

    def request_pause(self) -> None:
        """Pede pausa na próxima oportunidade segura (o driver consulta should_stop()
        entre um pulso/ponto e outro). Retoma exatamente de onde parou."""
        self._pause_requested = True

    def resume(self) -> None:
        self._resume_event.set()

    def _should_stop(self) -> bool:
        if self._pause_requested and not self._stop_requested:
            self._pause_requested = False
            self._resume_event.clear()
            self.paused.emit("Ensaio pausado pelo operador. Clique em Continuar para retomar de onde parou.")
            self._resume_event.wait()
        return self._stop_requested

    def _wait_for_operator(self, message: str) -> bool:
        """Pausa a thread do ensaio até o operador chamar resume() (ou parar o ensaio).
        Retorna True se deve continuar, False se foi interrompido durante a pausa."""
        self._resume_event.clear()
        self.paused.emit(message)
        self._resume_event.wait()
        return not self._stop_requested

    def run(self) -> None:
        started_at = datetime.now(timezone.utc).isoformat()
        session_id = self._create_session(started_at)
        self.session_id = session_id

        def on_progress(message: str) -> None:
            self._log_event(session_id, message)
            self.progress.emit(message)

        counter_note = ""
        before_value: Optional[float] = None
        before_ts: Optional[str] = None
        if self.counter is not None:
            try:
                self.counter.connect()
                if self.counter_recall_register is not None:
                    self.counter.recall(self.counter_recall_register)
                before_value = self.counter.read_current_blocking()
                before_ts = datetime.now(timezone.utc).isoformat()
                on_progress(f"Contador (relógio) — pulso ANTES do ensaio: {before_value:g}")
            except Exception as exc:
                on_progress(f"Contador (relógio): erro ao ler o pulso inicial — {exc}")
                before_value = None
                before_ts = None

        result = None
        try:
            self.driver.connect()
            result = self.driver.run_test(
                self.standard_code, self.params, on_progress, self._should_stop, self._wait_for_operator
            )
        except Exception as exc:
            on_progress(f"ERRO: {exc}")
        finally:
            try:
                self.driver.disconnect()
            except Exception:
                pass

        if self.counter is not None and before_value is not None:
            try:
                after_value = self.counter.read_current_blocking()
                after_ts = datetime.now(timezone.utc).isoformat()
                elapsed_s = (
                    datetime.fromisoformat(after_ts) - datetime.fromisoformat(before_ts)
                ).total_seconds()
                pulses = after_value - before_value
                on_progress(
                    f"Contador (relógio) — pulso DEPOIS do ensaio: {after_value:g} "
                    f"(Δ={pulses:g} pulso(s), tempo do ensaio pelo contador: {elapsed_s:.3f}s)"
                )
                counter_note = (
                    f"Contador (relógio): {pulses:g} pulso(s) entre antes/depois do ensaio, "
                    f"tempo medido = {elapsed_s:.3f}s (pulso antes={before_value:g}, depois={after_value:g})."
                )
            except Exception as exc:
                on_progress(f"Contador (relógio): erro ao ler o pulso final — {exc}")
            finally:
                try:
                    self.counter.disconnect()
                except Exception:
                    pass

        finished_at = datetime.now(timezone.utc).isoformat()
        if result is None:
            outcome_note = "Ensaio abortado por erro de comunicação com o instrumento."
        elif not result.passed:
            outcome_note = "Ensaio interrompido pelo operador."
        else:
            outcome_note = ""
        notes = " ".join(n for n in (outcome_note, counter_note) if n)
        self._finish_session(session_id, finished_at, notes)
        self.finished_session.emit(session_id)

    def _create_session(self, started_at: str) -> int:
        with db_cursor() as cur:
            cur.execute(
                """INSERT INTO test_sessions
                (project_id, standard_code, eut_name, eut_serial, operator, level_label,
                 params_json, started_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')""",
                (
                    self.project_id,
                    self.standard_code,
                    self.eut_name,
                    self.eut_serial,
                    self.operator,
                    self.level_label,
                    json.dumps(self.params),
                    started_at,
                ),
            )
            return cur.lastrowid

    def _log_event(self, session_id: int, message: str) -> None:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO test_events (session_id, timestamp, message) VALUES (?, ?, ?)",
                (session_id, datetime.now(timezone.utc).isoformat(), message),
            )

    def _finish_session(self, session_id: int, finished_at: str, notes: str) -> None:
        with db_cursor() as cur:
            cur.execute(
                "UPDATE test_sessions SET finished_at = ?, notes = ? WHERE id = ?",
                (finished_at, notes, session_id),
            )


def set_session_result(session_id: int, result: str, notes: str = "") -> None:
    """result: 'aprovado' | 'reprovado'. Chamado pelo operador após inspecionar o EUT."""
    with db_cursor() as cur:
        if notes:
            cur.execute(
                "UPDATE test_sessions SET result = ?, notes = ? WHERE id = ?",
                (result, notes, session_id),
            )
        else:
            cur.execute(
                "UPDATE test_sessions SET result = ? WHERE id = ?", (result, session_id)
            )


def get_session(session_id: int) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM test_sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_sessions_for_project(project_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_sessions WHERE project_id = ? ORDER BY started_at DESC",
            (project_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def list_completed_sessions() -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            """
            SELECT test_sessions.*, projects.name AS project_name
            FROM test_sessions
            JOIN projects ON projects.id = test_sessions.project_id
            WHERE test_sessions.finished_at IS NOT NULL
            ORDER BY test_sessions.started_at DESC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def list_events(session_id: int) -> list[dict]:
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM test_events WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [dict(row) for row in cur.fetchall()]
