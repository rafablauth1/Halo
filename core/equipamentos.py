"""
core/equipamentos.py

Cadastro dos equipamentos da cadeia de medicao (cabo, LISN, antena,
atenuador, pre-amplificador...) e dos seus CERTIFICADOS DE CALIBRACAO.

A ideia central: um certificado de calibracao da, em algumas frequencias
discretas, o ERRO SISTEMATICO do equipamento (perda de insercao do cabo,
fator de divisao da LISN, fator de antena...) e a incerteza expandida U
daquele ponto. O ensaio, porem, mede em milhares de frequencias. Este
modulo INTERPOLA os pontos do certificado (linear em log da frequencia,
como manda a pratica de EMC) e devolve uma curva de correcao aplicavel a
qualquer trace.

Convencao de sinal (a mesma de core/corrections.py):

    nivel_corrigido = leitura_do_receiver + correcao_dB

Por isso perda de cabo, perda de insercao de LISN, atenuador e fator de
antena entram SOMANDO (`aplicar="somar"`), enquanto ganho de
pre-amplificador entra SUBTRAINDO (`aplicar="subtrair"`).

A incerteza dos certificados e combinada por RSS (raiz da soma dos
quadrados das incertezas padrao), conforme o GUM -- e o que alimenta a
declaracao de incerteza do relatorio.
"""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np

from core.corrections import CorrectionTable

EQUIPAMENTOS_DIR = Path(__file__).parent.parent / "dados" / "equipamentos"

_SAFE_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")

TIPOS_EQUIPAMENTO = [
    "cabo",
    "lisn",
    "antena",
    "atenuador",
    "pre-amplificador",
    "sonda-corrente",
    "adaptador",
    "outro",
]

# Grandeza tipica de cada tipo, so para rotular a tela/relatorio.
GRANDEZA_POR_TIPO = {
    "cabo": "Perda de insercao (dB)",
    "lisn": "Fator de divisao de tensao (dB)",
    "antena": "Fator de antena (dB/m)",
    "atenuador": "Atenuacao (dB)",
    "pre-amplificador": "Ganho (dB)",
    "sonda-corrente": "Impedancia de transferencia (dB)",
    "adaptador": "Perda de insercao (dB)",
    "outro": "Correcao (dB)",
}

# Como cada tipo entra na conta por padrao.
APLICACAO_PADRAO = {
    "pre-amplificador": "subtrair",
}


# ---------------------------------------------------------------------------
# Certificado
# ---------------------------------------------------------------------------

@dataclass
class PontoCertificado:
    """Um ponto de calibracao: frequencia, valor medido e incerteza."""
    freq_hz: float
    valor_db: float
    incerteza_db: float = 0.0   # incerteza EXPANDIDA U, no fator k abaixo


@dataclass
class Certificado:
    numero: str = ""
    laboratorio: str = ""
    data_calibracao: str = ""      # ISO 8601 (AAAA-MM-DD)
    data_validade: str = ""        # ISO 8601
    fator_k: float = 2.0           # fator de abrangencia da incerteza expandida
    grandeza: str = ""             # ex.: "Perda de insercao (dB)"
    pontos: list[PontoCertificado] = field(default_factory=list)
    observacoes: str = ""

    # -------- validade --------
    def vencido_em(self, quando: Optional[date] = None) -> Optional[bool]:
        """True se vencido, False se valido, None se sem data de validade."""
        if not self.data_validade:
            return None
        try:
            venc = datetime.fromisoformat(self.data_validade).date()
        except ValueError:
            return None
        return (quando or date.today()) > venc

    def dias_para_vencer(self, quando: Optional[date] = None) -> Optional[int]:
        if not self.data_validade:
            return None
        try:
            venc = datetime.fromisoformat(self.data_validade).date()
        except ValueError:
            return None
        return (venc - (quando or date.today())).days

    # -------- interpolacao --------
    def _ordenados(self) -> list[PontoCertificado]:
        return sorted(self.pontos, key=lambda p: p.freq_hz)

    def valor_em(self, freq_hz: float) -> Optional[float]:
        """Erro sistematico interpolado nesta frequencia (linear em log f).
        Fora da faixa calibrada, mantem o valor da extremidade (nao
        extrapola) -- extrapolar certificado nao tem respaldo metrologico."""
        pts = self._ordenados()
        if not pts:
            return None
        if len(pts) == 1:
            return pts[0].valor_db
        freqs = np.array([p.freq_hz for p in pts], dtype=float)
        vals = np.array([p.valor_db for p in pts], dtype=float)
        if freq_hz <= freqs[0]:
            return float(vals[0])
        if freq_hz >= freqs[-1]:
            return float(vals[-1])
        return float(np.interp(math.log10(freq_hz), np.log10(freqs), vals))

    def incerteza_em(self, freq_hz: float) -> Optional[float]:
        """Incerteza expandida U interpolada. Entre dois pontos de
        incertezas diferentes, usa a MAIOR das duas (conservador -- nao se
        deve 'ganhar' exatidao interpolando)."""
        pts = self._ordenados()
        if not pts:
            return None
        if len(pts) == 1:
            return pts[0].incerteza_db
        freqs = [p.freq_hz for p in pts]
        if freq_hz <= freqs[0]:
            return pts[0].incerteza_db
        if freq_hz >= freqs[-1]:
            return pts[-1].incerteza_db
        for i in range(len(pts) - 1):
            if freqs[i] <= freq_hz <= freqs[i + 1]:
                return max(pts[i].incerteza_db, pts[i + 1].incerteza_db)
        return pts[-1].incerteza_db

    def faixa_hz(self) -> Optional[tuple[float, float]]:
        pts = self._ordenados()
        if not pts:
            return None
        return (pts[0].freq_hz, pts[-1].freq_hz)

    def cobre(self, freq_min_hz: float, freq_max_hz: float,
               tol_relativa: float = 1e-6) -> bool:
        """A faixa calibrada cobre a faixa pedida? Usa tolerancia relativa
        porque os extremos costumam vir de np.logspace e trazem erro de
        ponto flutuante (30 MHz virando 30000000.000000004) -- sem isso o
        aviso de 'fora da faixa' dispararia mesmo com faixas identicas."""
        faixa = self.faixa_hz()
        if not faixa:
            return False
        ini = faixa[0] * (1.0 - tol_relativa)
        fim = faixa[1] * (1.0 + tol_relativa)
        return ini <= freq_min_hz and fim >= freq_max_hz

    # -------- import de CSV --------
    @staticmethod
    def from_csv(path: str | Path, *, freq_unit: str = "hz") -> "Certificado":
        """Le um CSV do certificado: frequencia, valor, [incerteza]."""
        escala = {"hz": 1.0, "khz": 1e3, "mhz": 1e6, "ghz": 1e9}.get(freq_unit.lower(), 1.0)
        pontos: list[PontoCertificado] = []
        path = Path(path)
        with open(path, "r", encoding="utf-8-sig") as f:
            amostra = f.read(2000)
            f.seek(0)
            delim = ";" if amostra.count(";") >= amostra.count(",") else ","
            for linha in csv.reader(f, delimiter=delim):
                if len(linha) < 2:
                    continue
                try:
                    freq = float(linha[0].replace(",", ".")) * escala
                    valor = float(linha[1].replace(",", "."))
                except ValueError:
                    continue  # cabecalho ou linha nao numerica
                inc = 0.0
                if len(linha) >= 3:
                    try:
                        inc = float(linha[2].replace(",", "."))
                    except ValueError:
                        inc = 0.0
                pontos.append(PontoCertificado(freq, valor, inc))
        if not pontos:
            raise ValueError("Nao encontrei pares (frequencia, valor) numericos neste CSV.")
        return Certificado(numero=path.stem, pontos=pontos)


# ---------------------------------------------------------------------------
# Equipamento
# ---------------------------------------------------------------------------

@dataclass
class Equipamento:
    id: str
    tipo: str = "cabo"
    fabricante: str = ""
    modelo: str = ""
    numero_serie: str = ""
    patrimonio: str = ""
    descricao: str = ""
    aplicar: str = "somar"          # "somar" ou "subtrair"
    ativo: bool = True
    certificados: list[Certificado] = field(default_factory=list)
    certificado_ativo: int = 0      # indice em `certificados`
    observacoes: str = ""

    # -------- certificado em uso --------
    def certificado(self) -> Optional[Certificado]:
        if not self.certificados:
            return None
        idx = max(0, min(self.certificado_ativo, len(self.certificados) - 1))
        return self.certificados[idx]

    def grandeza(self) -> str:
        cert = self.certificado()
        if cert and cert.grandeza:
            return cert.grandeza
        return GRANDEZA_POR_TIPO.get(self.tipo, "Correcao (dB)")

    def rotulo(self) -> str:
        partes = [p for p in (self.fabricante, self.modelo) if p]
        nome = " ".join(partes) or self.id
        if self.numero_serie:
            nome += f" (s/n {self.numero_serie})"
        return nome

    # -------- correcao --------
    def _sinal(self) -> float:
        return -1.0 if self.aplicar == "subtrair" else 1.0

    def correcao_em(self, freq_hz: float) -> Optional[float]:
        cert = self.certificado()
        if cert is None:
            return None
        valor = cert.valor_em(freq_hz)
        return None if valor is None else valor * self._sinal()

    def tabela_correcao(self) -> Optional[CorrectionTable]:
        """Converte o certificado ativo numa CorrectionTable, ja com o sinal
        de aplicacao resolvido -- pronta para somar ao trace."""
        cert = self.certificado()
        if cert is None or not cert.pontos:
            return None
        sinal = self._sinal()
        pontos = [(p.freq_hz, p.valor_db * sinal) for p in cert._ordenados()]
        return CorrectionTable(
            name=self.rotulo(),
            unit_note=f"{self.grandeza()} · certificado {cert.numero or '(sem numero)'}",
            points=pontos,
        )


# ---------------------------------------------------------------------------
# Cadeia de medicao (varios equipamentos aplicados juntos)
# ---------------------------------------------------------------------------

@dataclass
class ResultadoCadeia:
    correcao_db: np.ndarray
    incerteza_expandida_db: np.ndarray
    fator_k: float
    equipamentos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def aplicar_cadeia(freq_hz: np.ndarray, equipamentos: list[Equipamento],
                    *, fator_k: float = 2.0,
                    quando: Optional[date] = None) -> ResultadoCadeia:
    """Soma as correcoes de todos os equipamentos da cadeia e combina as
    incertezas por RSS, ponto a ponto.

    Avisa (sem impedir) quando: o certificado esta vencido, falta
    certificado, ou a faixa do ensaio extrapola a faixa calibrada."""
    freq_hz = np.asarray(freq_hz, dtype=float)
    correcao = np.zeros_like(freq_hz)
    var_padrao = np.zeros_like(freq_hz)   # soma dos u^2 (incerteza PADRAO)
    usados: list[str] = []
    avisos: list[str] = []

    if freq_hz.size:
        f_min, f_max = float(freq_hz.min()), float(freq_hz.max())
    else:
        f_min = f_max = 0.0

    for eq in equipamentos:
        if not eq.ativo:
            continue
        cert = eq.certificado()
        if cert is None or not cert.pontos:
            avisos.append(f"{eq.rotulo()}: sem certificado cadastrado — correcao nao aplicada.")
            continue

        vencido = cert.vencido_em(quando)
        if vencido:
            avisos.append(
                f"{eq.rotulo()}: certificado {cert.numero or '(sem numero)'} VENCIDO "
                f"em {cert.data_validade}.")
        elif vencido is None:
            avisos.append(f"{eq.rotulo()}: certificado sem data de validade.")

        if freq_hz.size and not cert.cobre(f_min, f_max):
            faixa = cert.faixa_hz()
            avisos.append(
                f"{eq.rotulo()}: certificado cobre "
                f"{faixa[0]/1e3:.1f} kHz–{faixa[1]/1e6:.3f} MHz, menor que a faixa do ensaio "
                f"({f_min/1e3:.1f} kHz–{f_max/1e6:.3f} MHz). Fora da faixa o valor da "
                "extremidade e mantido (nao ha extrapolacao).")

        sinal = eq._sinal()
        correcao += np.array([(cert.valor_em(f) or 0.0) * sinal for f in freq_hz])
        # U -> u (incerteza padrao) dividindo pelo k do proprio certificado
        k_cert = cert.fator_k or 2.0
        u = np.array([(cert.incerteza_em(f) or 0.0) / k_cert for f in freq_hz])
        var_padrao += u ** 2
        usados.append(eq.rotulo())

    return ResultadoCadeia(
        correcao_db=correcao,
        incerteza_expandida_db=fator_k * np.sqrt(var_padrao),
        fator_k=fator_k,
        equipamentos=usados,
        avisos=avisos,
    )


# ---------------------------------------------------------------------------
# Persistencia / CRUD
# ---------------------------------------------------------------------------

def validar_id(equip_id: str) -> str:
    equip_id = equip_id.strip()
    if not equip_id:
        raise ValueError("O id do equipamento nao pode ser vazio.")
    if not set(equip_id) <= _SAFE_ID_CHARS:
        raise ValueError("Use apenas letras, numeros, '_' e '-' no id do equipamento.")
    return equip_id


def salvar_equipamento(eq: Equipamento, path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(asdict(eq), indent=2, ensure_ascii=False),
                          encoding="utf-8")


def carregar_equipamento(path: str | Path) -> Equipamento:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    certs = []
    for c in data.pop("certificados", []):
        pontos = [PontoCertificado(**{k: v for k, v in p.items()
                                       if k in PontoCertificado.__dataclass_fields__})
                  for p in c.pop("pontos", [])]
        cert = Certificado(**{k: v for k, v in c.items()
                              if k in Certificado.__dataclass_fields__})
        cert.pontos = pontos
        certs.append(cert)
    eq = Equipamento(**{k: v for k, v in data.items()
                        if k in Equipamento.__dataclass_fields__})
    eq.certificados = certs
    return eq


def listar_equipamentos() -> list[Path]:
    EQUIPAMENTOS_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(EQUIPAMENTOS_DIR.glob("*.json"))


def novo_equipamento(equip_id: str, tipo: str = "cabo") -> Path:
    equip_id = validar_id(equip_id)
    EQUIPAMENTOS_DIR.mkdir(parents=True, exist_ok=True)
    path = EQUIPAMENTOS_DIR / f"{equip_id}.json"
    if path.exists():
        raise FileExistsError(f"Ja existe um equipamento com id '{equip_id}'.")
    eq = Equipamento(id=equip_id, tipo=tipo,
                     aplicar=APLICACAO_PADRAO.get(tipo, "somar"))
    salvar_equipamento(eq, path)
    return path


def duplicar_equipamento(origem: str | Path, novo_id: str) -> Path:
    novo_id = validar_id(novo_id)
    destino = EQUIPAMENTOS_DIR / f"{novo_id}.json"
    if destino.exists():
        raise FileExistsError(f"Ja existe um equipamento com id '{novo_id}'.")
    eq = carregar_equipamento(origem)
    eq.id = novo_id
    eq.numero_serie = ""   # copia nao herda o numero de serie
    salvar_equipamento(eq, destino)
    return destino


def renomear_equipamento(path: str | Path, novo_id: str) -> Path:
    novo_id = validar_id(novo_id)
    path = Path(path)
    destino = EQUIPAMENTOS_DIR / f"{novo_id}.json"
    if destino != path and destino.exists():
        raise FileExistsError(f"Ja existe um equipamento com id '{novo_id}'.")
    eq = carregar_equipamento(path)
    eq.id = novo_id
    salvar_equipamento(eq, destino)
    if destino != path:
        path.unlink()
    return destino


def excluir_equipamento(path: str | Path) -> None:
    Path(path).unlink()
