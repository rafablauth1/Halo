"""
core/incerteza.py

Incerteza de medicao e REGRA DE DECISAO — como a incerteza entra (ou nao)
no veredito de conformidade.

Ate aqui o software comparava o nivel medido direto com o limite. Isso e
uma das regras possiveis (risco compartilhado), mas nao e a unica, e o
relatorio de ensaio precisa declarar qual foi usada (ISO/IEC 17025:2017,
item 7.8.6).

Tres regras implementadas:

1. `risco_compartilhado` — compara o valor medido com o limite, sem
   considerar a incerteza. E o que o relatorio de referência do laboratório
   faz (declara a incerteza numa tabela a parte, mas o veredito sai da
   comparacao direta). Padrao aqui.

2. `cispr_16_4_2` — a regra da CISPR 16-4-2: se a incerteza do
   laboratorio (U_lab) for MENOR OU IGUAL a incerteza de referencia da
   norma (U_cispr), compara-se direto com o limite; se for MAIOR, o
   limite e reduzido pela diferenca:

       limite_efetivo = limite - (U_lab - U_cispr)   [se U_lab > U_cispr]

   Ou seja, o laboratorio com incerteza pior que a de referencia paga a
   diferenca em banda de guarda.

3. `banda_de_guarda` — o caso conservador: so aprova se o valor medido
   mais a incerteza couber no limite (`medido + U <= limite`). Usado
   quando se quer garantir conformidade com alta confianca.

>>> ATENCAO: os valores de U_cispr da CISPR 16-4-2 NAO estao embutidos
aqui. A CISPR 16-4-2 nao esta disponivel neste ambiente e eu nao vou
inventar numero que decide aprovacao de ensaio. Cadastre os valores da
sua copia da norma, por faixa, na tela de incerteza. Enquanto U_cispr
for zero, a regra `cispr_16_4_2` se comporta como banda de guarda
completa (conservadora) e o software avisa. <<<
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import numpy as np

INCERTEZAS_DIR = Path(__file__).parent.parent / "dados" / "incertezas"

REGRAS = {
    "risco_compartilhado": "Risco compartilhado — compara o medido com o limite (incerteza declarada a parte)",
    "cispr_16_4_2": "CISPR 16-4-2 — reduz o limite se U do laboratorio exceder U de referencia",
    "banda_de_guarda": "Banda de guarda — so aprova se medido + U couber no limite",
}


@dataclass
class FaixaIncerteza:
    """Incerteza declarada para um trecho de frequencia, como na tabela
    'Incertezas de Medicao' do relatorio."""
    freq_min_hz: float
    freq_max_hz: float
    u_lab_db: float = 0.0        # incerteza expandida do laboratorio
    fator_k: float = 2.0
    u_cispr_db: float = 0.0      # incerteza de referencia da CISPR 16-4-2
    item_norma: str = ""         # ex.: "4.3.1"
    mensurando: str = ""         # ex.: "Disturbios conduzidos"

    def cobre(self, freq_hz: float) -> bool:
        return self.freq_min_hz <= freq_hz <= self.freq_max_hz


@dataclass
class ConfiguracaoIncerteza:
    """Conjunto de faixas de incerteza + regra de decisao, associado a uma
    norma (pelo id do metodo)."""
    metodo_id: str = ""
    regra: str = "risco_compartilhado"
    faixas: list[FaixaIncerteza] = field(default_factory=list)
    observacoes: str = ""

    def faixa_em(self, freq_hz: float) -> Optional[FaixaIncerteza]:
        for f in self.faixas:
            if f.cobre(freq_hz):
                return f
        return None

    def u_lab_em(self, freq_hz: float) -> float:
        f = self.faixa_em(freq_hz)
        return f.u_lab_db if f else 0.0

    def u_cispr_em(self, freq_hz: float) -> float:
        f = self.faixa_em(freq_hz)
        return f.u_cispr_db if f else 0.0

    # ---------------- aplicacao da regra ----------------
    def limite_efetivo(self, freq_hz: np.ndarray, limite: np.ndarray,
                        u_extra_db: Optional[np.ndarray] = None) -> np.ndarray:
        """Limite depois de aplicada a regra de decisao.

        `u_extra_db` e a incerteza vinda da cadeia de certificados (U
        expandida), somada em quadratura a incerteza declarada do
        laboratorio -- para nao contar duas vezes, use uma OU outra
        conforme o seu orcamento de incerteza."""
        freq_hz = np.asarray(freq_hz, dtype=float)
        limite = np.asarray(limite, dtype=float)

        u_lab = np.array([self.u_lab_em(f) for f in freq_hz])
        if u_extra_db is not None:
            u_lab = np.sqrt(u_lab ** 2 + np.asarray(u_extra_db, dtype=float) ** 2)

        if self.regra == "risco_compartilhado":
            return limite
        if self.regra == "banda_de_guarda":
            return limite - u_lab
        if self.regra == "cispr_16_4_2":
            u_cispr = np.array([self.u_cispr_em(f) for f in freq_hz])
            excesso = np.maximum(u_lab - u_cispr, 0.0)
            return limite - excesso
        return limite

    def descricao_regra(self) -> str:
        return REGRAS.get(self.regra, self.regra)

    def avisos(self) -> list[str]:
        msgs = []
        if not self.faixas:
            msgs.append("Nenhuma faixa de incerteza cadastrada — a incerteza nao entra no veredito.")
        if self.regra == "cispr_16_4_2":
            sem_ref = [f for f in self.faixas if f.u_cispr_db <= 0]
            if sem_ref:
                msgs.append(
                    f"{len(sem_ref)} faixa(s) sem U de referencia da CISPR 16-4-2 (U_cispr = 0): "
                    "nelas a regra vira banda de guarda completa, mais conservadora que a norma. "
                    "Preencha U_cispr com os valores da sua copia da CISPR 16-4-2.")
        for f in self.faixas:
            if f.u_lab_db <= 0:
                msgs.append(
                    f"Faixa {f.freq_min_hz/1e3:g} kHz–{f.freq_max_hz/1e6:g} MHz sem incerteza "
                    "do laboratorio declarada.")
        return msgs


# ---------------------------------------------------------------------------
# Preset a partir da tabela de incertezas do relatorio do laboratório
# ---------------------------------------------------------------------------

def preset_lab(metodo_id: str) -> ConfiguracaoIncerteza:
    """Incertezas declaradas no relatorio de referência do laboratório.

    U_cispr fica em zero de proposito: os valores de referencia da
    CISPR 16-4-2 tem que sair da sua copia da norma."""
    tabela = {
        "cispr15_mains_terminals": [
            FaixaIncerteza(9_000, 150_000, 4.5, 2.0, 0.0, "4.3.1", "Disturbios conduzidos"),
            FaixaIncerteza(150_000, 30_000_000, 4.4, 2.0, 0.0, "4.3.1", "Disturbios conduzidos"),
        ],
        "cispr15_load_terminals": [
            FaixaIncerteza(150_000, 30_000_000, 4.4, 2.0, 0.0, "4.3.2", "Disturbios conduzidos"),
        ],
        "cispr15_control_terminals": [
            FaixaIncerteza(150_000, 30_000_000, 4.4, 2.0, 0.0, "4.3.3", "Disturbios conduzidos"),
        ],
        "cispr15_loop_antenna": [
            FaixaIncerteza(9_000, 30_000_000, 4.8, 2.0, 0.0, "4.4.1", "Disturbios radiados"),
        ],
        "cispr15_radiated_30_300": [
            FaixaIncerteza(30_000_000, 300_000_000, 3.7, 2.0, 0.0, "4.4.2", "Disturbios radiados"),
        ],
    }
    return ConfiguracaoIncerteza(
        metodo_id=metodo_id,
        regra="risco_compartilhado",
        faixas=tabela.get(metodo_id, []),
        observacoes="Incertezas do relatorio de ensaio de referencia, k = 2,00. "
                    "U de referencia da CISPR 16-4-2 a preencher.",
    )


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def caminho_para(metodo_id: str) -> Path:
    return INCERTEZAS_DIR / f"{metodo_id}.json"


def salvar(cfg: ConfiguracaoIncerteza) -> Path:
    INCERTEZAS_DIR.mkdir(parents=True, exist_ok=True)
    path = caminho_para(cfg.metodo_id)
    path.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def carregar(metodo_id: str) -> ConfiguracaoIncerteza:
    """Carrega a configuracao da norma; se nao existir, cria a partir do
    preset do laboratório (ou vazia, para normas criadas pelo usuario)."""
    path = caminho_para(metodo_id)
    if not path.exists():
        cfg = preset_lab(metodo_id)
        cfg.metodo_id = metodo_id
        salvar(cfg)
        return cfg
    data = json.loads(path.read_text(encoding="utf-8"))
    faixas = [FaixaIncerteza(**{k: v for k, v in f.items()
                                 if k in FaixaIncerteza.__dataclass_fields__})
              for f in data.pop("faixas", [])]
    cfg = ConfiguracaoIncerteza(**{k: v for k, v in data.items()
                                    if k in ConfiguracaoIncerteza.__dataclass_fields__})
    cfg.faixas = faixas
    return cfg
