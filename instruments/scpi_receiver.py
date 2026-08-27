"""
instruments/scpi_receiver.py

Driver SCPI/VISA para receivers de EMI Rohde & Schwarz.

IMPORTANTE: este driver NAO tem comandos chumbados. Todos os comandos vem
do MODELO escolhido no catalogo (instruments/receivers/*.json, ver
instruments/receiver_models.py) -- assim o que a aba Receiver mostra em
"Comandos SCPI" e exatamente o que o driver envia, inclusive na varredura.
Se o modelo nao declarar um comando, ele simplesmente nao e enviado.

Modo simulacao (`dry_run=True`): nao abre VISA, so registra a sequencia de
comandos em `sent_commands` e devolve um trace sintetico. Serve para
validar o fluxo inteiro sem instrumento -- e para revisar, antes de ir ao
laboratorio, exatamente o que sera enviado.

Validacao com hardware real: ver instrucoes/03_validacao_receiver_scpi.md.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

try:
    import pyvisa
except ImportError:  # pragma: no cover - so falta no sandbox de dev
    pyvisa = None

from core.trace import Trace
from instruments.receiver_models import ReceiverModel, BASE_COMMANDS

# Detector -> sufixo SCPI. Igual ao usado em receiver_settings.py.
_DETECTOR_SCPI = {
    "PK": "POS",
    "QP": "QPE",
    "AV": "AVER",
    "RMS": "RMS",
    "CAV": "CAV",
    "CRMS": "CRMS",
}


@dataclass
class ReceiverConfig:
    resource: str = "GPIB0::20::INSTR"
    timeout_ms: int = 20000
    model: Optional[ReceiverModel] = None
    dry_run: bool = False


class RohdeSchwarzEMIReceiver:
    def __init__(self, config: ReceiverConfig):
        if pyvisa is None and not config.dry_run:
            raise RuntimeError(
                "pyvisa nao instalado. No PC do laboratorio: pip install pyvisa "
                "(e o VISA do fabricante -- NI-VISA ou R&S VISA -- para falar GPIB).")
        self.config = config
        self.model = config.model
        self.sent_commands: list[str] = []
        self._rm = None
        self._inst = None

    # ---------------- comandos vindos do modelo ----------------
    def _template(self, key: str) -> Optional[str]:
        if self.model is not None:
            return self.model.command(key)
        tpl = BASE_COMMANDS.get(key, "")
        return tpl or None

    def _cmd(self, key: str, **kwargs) -> Optional[str]:
        """Monta o comando do modelo para `key`, ou None se o modelo nao
        declarar esse comando (nesse caso nada e enviado)."""
        tpl = self._template(key)
        if not tpl:
            return None
        try:
            return tpl.format(**kwargs)
        except (KeyError, IndexError):
            return tpl

    def _send(self, key: str, **kwargs) -> bool:
        cmd = self._cmd(key, **kwargs)
        if cmd is None:
            return False
        self._write(cmd)
        return True

    # ---------------- conexao ----------------
    def connect(self) -> str:
        if self.config.dry_run:
            self.sent_commands.clear()
            return f"[SIMULACAO] {self.model.model if self.model else 'receiver generico'}"
        self._rm = pyvisa.ResourceManager()
        self._inst = self._rm.open_resource(self.config.resource)
        self._inst.timeout = self.config.timeout_ms
        self._inst.write_termination = "\n"
        self._inst.read_termination = "\n"
        return self.idn()

    def disconnect(self):
        if self._inst is not None:
            self._inst.close()
            self._inst = None

    def _write(self, cmd: str):
        self.sent_commands.append(cmd)
        if self.config.dry_run:
            return
        if self._inst is None:
            raise RuntimeError("Instrumento nao conectado.")
        self._inst.write(cmd)

    def _query(self, cmd: str) -> str:
        self.sent_commands.append(cmd)
        if self.config.dry_run:
            return self._simulated_response(cmd)
        if self._inst is None:
            raise RuntimeError("Instrumento nao conectado.")
        return self._inst.query(cmd).strip()

    def _simulated_response(self, cmd: str) -> str:
        low = cmd.lower()
        if low.startswith("*idn"):
            m = self.model
            return (f"Rohde&Schwarz,{m.model},100000/000,1.00" if m
                    else "Rohde&Schwarz,SIMULADO,0,0")
        if "err" in low:
            return '0,"No error"'
        if low.startswith("*opc"):
            return "1"
        return "0"

    # ---------------- basicos ----------------
    def idn(self) -> str:
        cmd = self._cmd("idn") or "*IDN?"
        return self._query(cmd)

    def reset(self):
        self._send("reset")
        self._send("clear_status")

    def check_errors(self) -> list[str]:
        tpl = self._cmd("error_query")
        if tpl is None:
            return []
        errors = []
        while True:
            resp = self._query(tpl)
            if resp.startswith("0,") or resp.lower().startswith('0,"no error"'):
                break
            errors.append(resp)
            if len(errors) > 20:
                break
        return errors

    # ---------------- configuracao de varredura ----------------
    def configure_scan(self, *, start_hz: float, stop_hz: float, rbw_hz: float,
                        detector: str = "QP", sweep_time_s: float | None = None,
                        trace: int = 1):
        """Configura UMA faixa de varredura usando os comandos do modelo.

        Se o modelo tiver tabela de scan (`scan_*`), usa a faixa 1 dela;
        senao cai nos comandos de frequencia direta (`freq_start`/`freq_stop`)."""
        det = _DETECTOR_SCPI.get(detector.upper(), "QPE")
        use_scan_table = bool(self.model and self.model.has_scan_table
                              and self._template("scan_start"))

        if use_scan_table:
            self._send("scan_ranges", value=1)
            self._send("scan_start", range=1, value=start_hz)
            self._send("scan_stop", range=1, value=stop_hz)
            self._send("scan_rbw", range=1, value=rbw_hz)
            if sweep_time_s is not None:
                self._send("scan_meas_time", range=1, value=sweep_time_s)
        else:
            self._send("freq_start", value=start_hz)
            self._send("freq_stop", value=stop_hz)
            self._send("rbw", value=rbw_hz)
            if sweep_time_s is not None:
                self._send("sweep_time", value=sweep_time_s)

        self._send("detector", trace=trace, value=det)
        self._send("init_continuous_off")

    def run_scan(self, *, wait_s: float = 0.0, poll_timeout_s: float = 300.0) -> None:
        self._send("init_immediate")
        opc = self._cmd("opc_query")
        if opc:
            if not self.config.dry_run and self._inst is not None:
                old = self._inst.timeout
                self._inst.timeout = int(poll_timeout_s * 1000)
                self._query(opc)
                self._inst.timeout = old
            else:
                self._query(opc)
        if wait_s:
            time.sleep(wait_s)

    def read_trace(self, trace_num: int = 1, detector: str = "QP",
                    unit: str = "dBuV") -> Trace:
        data_cmd = self._cmd("trace_data_query", trace=trace_num)
        if data_cmd is None:
            raise RuntimeError(
                f"O modelo {self.model.model if self.model else '?'} nao declara o comando "
                "'trace_data_query'. Preencha-o na aba Receiver > Gerenciar modelos.")

        if self.config.dry_run:
            # registra as mesmas consultas que a leitura real faria, para a
            # sequencia simulada refletir o que vai ao instrumento
            self.sent_commands.append(data_cmd)
            for key in ("query_freq_start", "query_freq_stop", "query_sweep_points"):
                c = self._cmd(key)
                if c:
                    self.sent_commands.append(c)
            return self._simulated_trace(detector=detector, unit=unit)

        raw = self._query(data_cmd)
        values = np.array([float(v) for v in raw.split(",") if v.strip() != ""])

        start = float(self._query(self._cmd("query_freq_start") or "FREQ:STAR?"))
        stop = float(self._query(self._cmd("query_freq_stop") or "FREQ:STOP?"))
        pts_cmd = self._cmd("query_sweep_points")
        n_points = len(values)
        if pts_cmd:
            try:
                declared = int(float(self._query(pts_cmd)))
                if declared == len(values):
                    n_points = declared
            except ValueError:
                pass
        freq_hz = np.linspace(start, stop, n_points)

        return Trace(freq_hz=freq_hz, level=values, unit=unit, detector=detector,
                     label=f"Live scan ({detector})",
                     meta={"idn": self.idn(), "resource": self.config.resource})

    def _simulated_trace(self, *, detector: str, unit: str,
                          start_hz: float = 9e3, stop_hz: float = 30e6,
                          n: int = 2000) -> Trace:
        """Trace sintetico para o modo simulacao -- so para exercitar o fluxo."""
        rng = np.random.default_rng(0)
        freq = np.logspace(np.log10(start_hz), np.log10(stop_hz), n)
        level = np.clip(45 - 8 * np.log10(freq / start_hz), 18, 45)
        level = level + rng.normal(0, 1.0, n)
        return Trace(freq_hz=freq, level=level, unit=unit, detector=detector,
                     label=f"[SIMULACAO] {detector}",
                     meta={"simulado": "true"})


def list_visa_resources() -> list[str]:
    if pyvisa is None:
        return []
    rm = pyvisa.ResourceManager()
    return list(rm.list_resources())
