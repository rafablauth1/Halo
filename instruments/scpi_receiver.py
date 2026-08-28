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
        # (frequencia, detector) da medicao em curso -- so o modo
        # simulacao usa, para responder um nivel coerente ao marcador
        self._sim_ctx: tuple[float, str] | None = None
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
        try:
            self._inst = self._rm.open_resource(self.config.resource)
        except Exception as e:
            raise RuntimeError(self._explicar_falha(e)) from e
        self._inst.timeout = self.config.timeout_ms
        self._inst.write_termination = "\n"
        self._inst.read_termination = "\n"
        return self.idn()

    def _explicar_falha(self, erro: Exception) -> str:
        """Traduz a falha do VISA para o que precisa ser feito na maquina.

        Sem NI-VISA instalado, o pyvisa cai calado no pyvisa-py, que nao
        fala GPIB. O erro que ele devolve manda instalar gpib-ctypes, o que
        e uma pista falsa em PC de laboratorio: ali a placa e NI (ou
        Keysight) e o que falta e o driver VISA do fabricante."""
        recurso = self.config.resource
        try:
            backend_py = "py" in str(self._rm.visalib).lower()
        except Exception:
            backend_py = False

        if recurso.upper().startswith("GPIB") and backend_py:
            return (
                f"Nao foi possivel abrir {recurso}.\n\n"
                "Este PC nao tem uma implementacao VISA instalada — o "
                "programa caiu no pyvisa-py, que nao fala GPIB.\n\n"
                "Instale o NI-VISA (ou o R&S VISA) e reinicie o programa. "
                "Depois confira em NI MAX se a placa aparece como GPIB0 e "
                "se o endereco bate com o da ficha do dispositivo.\n\n"
                "Para trabalhar sem instrumento, marque Simulacao.\n\n"
                f"(erro original: {erro})")
        if recurso.upper().startswith("TCPIP"):
            return (
                f"Nao foi possivel abrir {recurso}.\n\n"
                "Confira se o aparelho esta ligado na rede e se o IP da "
                "ficha do dispositivo esta certo (no proprio aparelho: "
                "Setup > Network).\n\n"
                f"(erro original: {erro})")
        return (f"Nao foi possivel abrir {recurso}.\n\n{erro}")

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
        # nivel do marcador na medicao final simulada
        if "mark" in low and low.rstrip().endswith("?") and self._sim_ctx:
            f, det = self._sim_ctx
            return f"{self._simulated_level(f, det):.2f}"
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

    # ---------------- medicao final (pico a pico) ----------------
    def tune_fixed(self, freq_hz: float, *, rbw_hz: float | None = None,
                    detector: str = "QP", meas_time_s: float | None = None):
        """Sintoniza o receiver numa frequencia unica, em span zero.

        Span zero e o que transforma o instrumento de "varredura" em
        "medidor numa frequencia": ele fica parado ali pelo tempo de
        medicao, que e justamente o que o detector de quase-pico precisa
        para carregar e descarregar."""
        det = _DETECTOR_SCPI.get(detector.upper(), "QPE")
        self._send("freq_center", value=freq_hz)
        self._send("freq_span", value=0)
        if rbw_hz is not None:
            self._send("rbw", value=rbw_hz)
        self._send("detector", trace=1, value=det)
        if meas_time_s is not None:
            self._send("meas_time", value=meas_time_s)

    def read_level(self, freq_hz: float) -> float:
        """Le UM nivel na frequencia sintonizada.

        Tenta o marcador primeiro (`CALC:MARK1:Y?`), que e o caminho que
        funciona tanto em receiver quanto em analisador. Se o modelo nao
        declarar marcador, cai na leitura do traco e tira a media dos
        pontos -- em span zero o traco inteiro e a mesma frequencia."""
        if self._send("marker_on"):
            self._send("marker_freq", value=freq_hz)
        consulta = self._cmd("marker_level_query")
        if consulta:
            resposta = self._query(consulta)
            try:
                return float(resposta.split(",")[0])
            except ValueError:
                pass

        dados = self._cmd("trace_data_query", trace=1)
        if not dados:
            raise RuntimeError(
                f"O modelo {self.model.model if self.model else '?'} nao declara nem "
                "'marker_level_query' nem 'trace_data_query'. Preencha um dos dois "
                "em Receiver > Gerenciar modelos.")
        bruto = self._query(dados)
        valores = [float(v) for v in bruto.split(",") if v.strip() != ""]
        if not valores:
            raise RuntimeError("O instrumento devolveu um traco vazio na medicao final.")
        return sum(valores) / len(valores)

    def run_final_measurement(self, freqs_hz, detectores, *, tempos=None,
                               rbw_por_freq=None, unidade: str = "dBuV",
                               niveis_prescan=None, progresso=None,
                               settle_s: float = 0.0) -> "MedicaoFinal":
        """Remede cada frequencia de `freqs_hz` com cada detector.

        E o passo que o RadiMation chama de *final measurement* e que faz o
        ensaio "ficar calculando" depois do grafico: o prescan so aponta
        ONDE olhar; o valor que vai para o laudo sai daqui.

        `tempos` e {detector: (tempo_de_medicao_s, tempo_de_observacao_s)}.
        O tempo de medicao e o que o instrumento fica integrando; o de
        observacao e quanto tempo o operador acompanha para pegar emissao
        que varia (flutuante). Sem valor definido, usa 1 s.

        `progresso(i, total, freq, detector)` e chamado antes de cada
        medicao -- serve para a barra de progresso da tela nao travar.

        Devolve `MedicaoFinal`, nao um Trace: sao pontos soltos, nao curva.
        """
        from core.final_measurement import MedicaoFinal, PontoFinal

        freqs = list(freqs_hz)
        dets = [d.upper() for d in detectores]
        tempos = dict(tempos or {})
        niveis_prescan = dict(niveis_prescan or {})
        total = len(freqs) * len(dets)

        # o instrumento precisa estar parado para medir sob comando
        self._send("init_continuous_off")

        pontos: list[PontoFinal] = []
        feitos = 0
        for f in freqs:
            ponto = PontoFinal(freq_hz=float(f),
                                nivel_prescan=niveis_prescan.get(f))
            for det in dets:
                if progresso is not None:
                    progresso(feitos, total, float(f), det)
                t_med, t_obs = tempos.get(det, (1.0, 0.0))

                rbw = rbw_por_freq(f) if callable(rbw_por_freq) else rbw_por_freq
                self.tune_fixed(f, rbw_hz=rbw, detector=det, meas_time_s=t_med)

                # espera a sintonia assentar antes de disparar (preseletor
                # e atenuador levam alguns ms para comutar)
                if settle_s and not self.config.dry_run:
                    time.sleep(settle_s)

                # tempo de observacao: o instrumento mede varias vezes e a
                # gente fica com o maior valor visto na janela
                fim = time.monotonic() + max(0.0, t_obs)
                melhor = None
                while True:
                    self.run_scan(poll_timeout_s=max(30.0, t_med * 5 + 10))
                    # read_level roda tambem na simulacao, de proposito: so
                    # assim a sequencia registrada e a mesma que ira ao
                    # instrumento, marcador incluido
                    self._sim_ctx = (float(f), det)
                    nivel = self.read_level(f)
                    melhor = nivel if melhor is None else max(melhor, nivel)
                    if time.monotonic() >= fim:
                        break
                ponto.niveis[det] = float(melhor)
                feitos += 1
            pontos.append(ponto)

        if progresso is not None:
            progresso(total, total, 0.0, "")

        return MedicaoFinal(
            pontos=pontos, detectores=dets, unidade=unidade,
            instrumento=(self.model.model if self.model else ""),
            simulada=self.config.dry_run,
            tempos={d: tempos.get(d, (1.0, 0.0)) for d in dets},
        )

    def _simulated_level(self, freq_hz: float, detector: str) -> float:
        """Nivel plausivel para o modo simulacao.

        Respeita a ordem fisica dos detectores: pico >= quase-pico >= media.
        Sem isso a simulacao produziria tabelas impossiveis e esconderia
        erros de logica na hora de montar o relatorio."""
        base = float(self._simulated_trace(detector="PK", unit="dBuV").value_at(freq_hz))
        desconto = {"PK": 0.0, "QP": 3.5, "CAV": 8.0, "AV": 9.0,
                     "RMS": 5.0, "CRMS": 6.5}.get(detector.upper(), 4.0)
        return base - desconto

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
