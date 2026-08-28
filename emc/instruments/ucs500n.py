import time
from typing import Callable, Optional

from emc.core.command_overrides import load_overrides
from emc.core.legacy_routines import burst_params_to_points, surge_params_to_points
from emc.instruments import ucs500n_commands as cmd
from emc.instruments.base import InstrumentDriver, TestResult

STEP_DELAY_S = 0.3
SLEEP_POLL_S = 0.2
DEFAULT_PHASE_COMBINATIONS = ["L1-N"]


def _interruptible_sleep(duration_s: float, should_stop: Optional[Callable[[], bool]]) -> bool:
    """Dorme por duration_s em pequenos passos, checando should_stop. Retorna True se foi
    interrompido no meio do caminho (para o chamador poder abortar o ensaio prontamente)."""
    elapsed = 0.0
    while elapsed < duration_s:
        if should_stop and should_stop():
            return True
        step = min(SLEEP_POLL_S, duration_s - elapsed)
        time.sleep(step)
        elapsed += step
    return False


class UCS500NDriver(InstrumentDriver):
    """EM TEST UCS 500N — Burst (IEC 61000-4-4) e Surge (IEC 61000-4-5)."""

    def _cmd(self, name: str, **kwargs) -> str:
        """Monta a string de comando, usando o valor salvo em Configurações >
        Comandos do UCS 500N se o operador já tiver descoberto/confirmado um, senão
        cai no placeholder padrão de app/instruments/ucs500n_commands.py."""
        overrides = load_overrides("ucs500n")
        template = overrides.get(name) or getattr(cmd, name)
        return template.format(**kwargs) if kwargs else template

    def set_test_on(self, state: bool) -> None:
        self._transport.write(self._cmd("TEST_ON" if state else "TEST_OFF"))

    def run_test(
        self,
        standard_code: str,
        params: dict,
        on_progress: Optional[Callable[[str], None]] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        wait_for_operator: Optional[Callable[[str], bool]] = None,
    ) -> TestResult:
        if standard_code == "4-4":
            return self._run_burst(params, on_progress, should_stop)
        if standard_code == "4-5":
            return self._run_surge(params, on_progress, should_stop, wait_for_operator)
        raise ValueError(f"UCS500NDriver não suporta a norma {standard_code}")

    def _emit(self, on_progress, message: str) -> None:
        if on_progress:
            on_progress(message)

    def _run_burst(self, params, on_progress, should_stop) -> TestResult:
        points = burst_params_to_points(params)
        if not points:
            raise ValueError("Roteiro de burst sem pontos.")

        self._transport.write(self._cmd("SELECT_BURST_MENU"))
        self._emit(on_progress, f"Burst — roteiro com {len(points)} ponto(s)")

        applied = 0
        for index, point in enumerate(points):
            if should_stop and should_stop():
                self._emit(on_progress, "Ensaio interrompido pelo operador")
                return TestResult(passed=False, applied_events=applied)

            voltage = point["voltage"]
            frequency_hz = point.get("frequency_hz", 5000)
            coupling = point.get("coupling", "COM")
            polarity = point.get("polarity", "+")
            duration_s = point.get("duration_s", STEP_DELAY_S)

            self._transport.write(self._cmd("SET_BURST_VOLTAGE", voltage=voltage))
            self._transport.write(self._cmd("SET_BURST_FREQUENCY", frequency_hz=frequency_hz))
            self._transport.write(self._cmd("SET_BURST_COUPLING", coupling=coupling))
            self._transport.write(self._cmd("SET_BURST_POLARITY", polarity=polarity))
            self._transport.query(self._cmd("TRIGGER_SINGLE_EVENT"))
            applied += 1
            self._emit(
                on_progress,
                f"Ponto {index + 1}/{len(points)} — {voltage}V, {frequency_hz}Hz, "
                f"{coupling}, polaridade {polarity} ({duration_s:.1f}s)",
            )
            if _interruptible_sleep(duration_s, should_stop):
                self._transport.write(self._cmd("STOP_TEST"))
                self._emit(on_progress, "Ensaio interrompido pelo operador")
                return TestResult(passed=False, applied_events=applied)

        self._transport.write(self._cmd("STOP_TEST"))
        return TestResult(passed=True, applied_events=applied)

    def _run_surge(self, params, on_progress, should_stop, wait_for_operator=None) -> TestResult:
        points = surge_params_to_points(params)
        if not points:
            raise ValueError("Roteiro de surge sem pontos.")
        combinations = params.get("phase_combinations") or DEFAULT_PHASE_COMBINATIONS
        if not combinations:
            raise ValueError("Selecione ao menos uma combinação de fase para o surge.")

        self._transport.write(self._cmd("SELECT_SURGE_MENU"))
        applied = 0

        for combo_index, combination in enumerate(combinations):
            if combo_index > 0:
                message = (
                    f"Pausa — altere o setup do medidor para {combination} "
                    "e clique em Continuar."
                )
                self._emit(on_progress, message)
                if wait_for_operator is not None:
                    if not wait_for_operator(message):
                        self._emit(on_progress, "Ensaio interrompido pelo operador")
                        return TestResult(passed=False, applied_events=applied)
                if should_stop and should_stop():
                    self._emit(on_progress, "Ensaio interrompido pelo operador")
                    return TestResult(passed=False, applied_events=applied)

            self._emit(
                on_progress,
                f"Surge — combinação {combination} ({combo_index + 1}/{len(combinations)}), "
                f"roteiro com {len(points)} ponto(s)",
            )

            for index, point in enumerate(points):
                voltage = point["voltage"]
                coupling = point.get("coupling", "L-N")
                polarity = point.get("polarity", "+")
                angle = point.get("phase_angle", 0)
                pulse_count = point.get("pulse_count", 1)
                interval_s = point.get("interval_s", STEP_DELAY_S)

                self._transport.write(self._cmd("SET_SURGE_VOLTAGE", voltage=voltage))
                self._transport.write(self._cmd("SET_SURGE_COUPLING", coupling=coupling))
                self._transport.write(self._cmd("SET_SURGE_POLARITY", polarity=polarity))
                self._transport.write(self._cmd("SET_SURGE_PHASE_ANGLE", angle_deg=angle))

                for rep in range(pulse_count):
                    if should_stop and should_stop():
                        self._emit(on_progress, "Ensaio interrompido pelo operador")
                        return TestResult(passed=False, applied_events=applied)
                    self._transport.query(self._cmd("TRIGGER_SINGLE_EVENT"))
                    applied += 1
                    self._emit(
                        on_progress,
                        f"{combination} — ponto {index + 1}/{len(points)} — "
                        f"{voltage}V, {coupling}, {polarity}, {angle}° (pulso {rep + 1}/{pulse_count})",
                    )
                    if rep < pulse_count - 1:
                        if _interruptible_sleep(interval_s, should_stop):
                            self._emit(on_progress, "Ensaio interrompido pelo operador")
                            return TestResult(passed=False, applied_events=applied)

        self._transport.write(self._cmd("STOP_TEST"))
        return TestResult(passed=True, applied_events=applied)
