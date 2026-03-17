"""
Lead Scoring Engine — Challenge 003
------------------------------------
Calcula um score de 0-100 para cada oportunidade ativa no pipeline,
com explicação de cada fator para o vendedor entender o resultado.

Fatores e pesos:
  Stage de Pipeline         25 pts  — Engaging vale mais que Prospecting
  Valor do Deal             20 pts  — Normalizado pelo máximo do pipeline
  Velocidade no Pipeline    20 pts  — Deals com bom ritmo > deals parados
  Qualidade da Conta        20 pts  — Setor estratégico + tamanho da empresa
  Performance do Vendedor   15 pts  — Taxa histórica de fechamento do agente
  ---------
  Total                    100 pts
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Constantes de configuração
# ---------------------------------------------------------------------------

STAGE_SCORES: dict[str, int] = {
    "Engaging": 25,
    "Prospecting": 15,
    "Won": 0,
    "Lost": 0,
}

# Setores com maior potencial de receita/expansão recorrente
HIGH_VALUE_SECTORS = {
    "Technology", "Finance", "Healthcare", "Retail", "Manufacturing",
    "Telecommunications", "Energy", "Pharmaceuticals",
}

WEIGHT_STAGE = 25
WEIGHT_VALUE = 20
WEIGHT_VELOCITY = 20
WEIGHT_ACCOUNT = 20
WEIGHT_AGENT = 15


# ---------------------------------------------------------------------------
# Estrutura de resultado
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """Score detalhado de um deal, com explicação por fator."""
    opportunity_id: str
    total_score: float
    stage_score: float
    value_score: float
    velocity_score: float
    account_score: float
    agent_score: float
    explanations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "total_score": round(self.total_score, 1),
            "score_stage": round(self.stage_score, 1),
            "score_value": round(self.value_score, 1),
            "score_velocity": round(self.velocity_score, 1),
            "score_account": round(self.account_score, 1),
            "score_agent": round(self.agent_score, 1),
            "explanations": " | ".join(self.explanations),
        }


# ---------------------------------------------------------------------------
# Engine principal
# ---------------------------------------------------------------------------

class LeadScorer:
    """
    Calcula scores para todas as oportunidades ativas (Engaging / Prospecting).

    Uso:
        scorer = LeadScorer(pipeline_df, accounts_df, products_df, teams_df)
        scored_df = scorer.score_all()
    """

    def __init__(
        self,
        pipeline: pd.DataFrame,
        accounts: pd.DataFrame,
        products: pd.DataFrame,
        teams: pd.DataFrame,
    ) -> None:
        self.pipeline = pipeline.copy()
        self.accounts = accounts.copy()
        self.products = products.copy()
        self.teams = teams.copy()

        self._normalize_columns()
        self._precompute_globals()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _normalize_columns(self) -> None:
        """Padroniza nomes de colunas para lowercase sem espaços."""
        for df_attr in ("pipeline", "accounts", "products", "teams"):
            df = getattr(self, df_attr)
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        # Garante que close_value é numérico
        if "close_value" in self.pipeline.columns:
            self.pipeline["close_value"] = pd.to_numeric(
                self.pipeline["close_value"], errors="coerce"
            ).fillna(0)

        # Converte datas
        for col in ("engage_date", "close_date"):
            if col in self.pipeline.columns:
                self.pipeline[col] = pd.to_datetime(
                    self.pipeline[col], errors="coerce"
                )

    def _precompute_globals(self) -> None:
        """Pré-computa métricas globais usadas na normalização."""
        active = self.pipeline[
            self.pipeline["deal_stage"].isin(["Engaging", "Prospecting"])
        ]

        # Máximo de valor para normalização
        self._max_value = active["close_value"].max() if not active.empty else 1
        if self._max_value == 0:
            self._max_value = 1

        # Taxa histórica de win por agente (usando todos os deals fechados)
        closed = self.pipeline[self.pipeline["deal_stage"].isin(["Won", "Lost"])]
        if not closed.empty and "sales_agent" in closed.columns:
            wins = (
                closed[closed["deal_stage"] == "Won"]
                .groupby("sales_agent")
                .size()
                .rename("wins")
            )
            totals = closed.groupby("sales_agent").size().rename("totals")
            rates = (wins / totals).fillna(0)
            self._agent_win_rate: pd.Series = rates
            self._avg_win_rate: float = float(rates.mean()) if not rates.empty else 0.5
        else:
            self._agent_win_rate = pd.Series(dtype=float)
            self._avg_win_rate = 0.5

        # Dias médios de pipeline (Engaging) para referência de velocidade
        engaging = active[active["deal_stage"] == "Engaging"].copy()
        today = pd.Timestamp.today().normalize()
        if not engaging.empty and "engage_date" in engaging.columns:
            engaging["days_in_pipeline"] = (
                today - engaging["engage_date"]
            ).dt.days.clip(lower=0)
            self._avg_pipeline_days = float(engaging["days_in_pipeline"].median())
            if self._avg_pipeline_days == 0:
                self._avg_pipeline_days = 30
        else:
            self._avg_pipeline_days = 30

        # Mapa sector → booleano high_value
        self._account_sector: dict[str, str] = {}
        self._account_employees: dict[str, float] = {}
        if "account" in self.accounts.columns:
            for _, row in self.accounts.iterrows():
                key = str(row.get("account", "")).strip()
                self._account_sector[key] = str(row.get("sector", "")).strip()
                emp_col = next(
                    (c for c in self.accounts.columns if "employ" in c or "employee" in c),
                    None,
                )
                self._account_employees[key] = float(row[emp_col]) if emp_col else 0.0

        self._max_employees = max(self._account_employees.values(), default=1) or 1

    # ------------------------------------------------------------------
    # Fatores individuais
    # ------------------------------------------------------------------

    def _score_stage(self, row: pd.Series) -> tuple[float, str]:
        stage = str(row.get("deal_stage", "")).strip()
        pts = float(STAGE_SCORES.get(stage, 0))
        if stage == "Engaging":
            msg = "Em Engaging — alta probabilidade de avanço (+25)"
        elif stage == "Prospecting":
            msg = "Em Prospecting — ainda em fase inicial (+15)"
        else:
            msg = f"Stage {stage!r} não pontuado"
        return pts, msg

    def _score_value(self, row: pd.Series) -> tuple[float, str]:
        value = float(row.get("close_value", 0) or 0)
        # Raiz quadrada suaviza o efeito de outliers
        normalized = math.sqrt(value) / math.sqrt(self._max_value)
        pts = normalized * WEIGHT_VALUE
        if value == 0:
            msg = "Sem valor de fechamento registrado (+0)"
        elif normalized >= 0.75:
            msg = f"Deal de alto valor (R$ {value:,.0f}) — top quartil do pipeline (+{pts:.0f})"
        elif normalized >= 0.40:
            msg = f"Valor intermediário (R$ {value:,.0f}) (+{pts:.0f})"
        else:
            msg = f"Valor baixo vs. média do pipeline (R$ {value:,.0f}) (+{pts:.0f})"
        return pts, msg

    def _score_velocity(self, row: pd.Series) -> tuple[float, str]:
        today = pd.Timestamp.today().normalize()
        engage_date = row.get("engage_date")
        stage = str(row.get("deal_stage", ""))

        if stage == "Prospecting":
            # Prospecting: velocidade baseada em ter ou não data de engajamento próxima
            close_date = row.get("close_date")
            if pd.notna(close_date):
                days_to_close = (close_date - today).days
                if 0 < days_to_close <= 30:
                    return WEIGHT_VELOCITY * 0.8, f"Fecha em {days_to_close} dias — urgente (+{WEIGHT_VELOCITY*0.8:.0f})"
                elif 0 < days_to_close <= 90:
                    return WEIGHT_VELOCITY * 0.5, f"Fecha em {days_to_close} dias (+{WEIGHT_VELOCITY*0.5:.0f})"
            return WEIGHT_VELOCITY * 0.3, "Prospecting sem data urgente (+6)"

        if pd.isna(engage_date):
            return WEIGHT_VELOCITY * 0.2, "Sem data de engajamento (+4)"

        days_engaged = max(0, (today - engage_date).days)

        # Score alto: deal novo (< metade da média) → momentum
        # Score baixo: deal muito antigo (> 2x a média) → estagnado
        ratio = days_engaged / self._avg_pipeline_days
        if ratio <= 0.5:
            pts = WEIGHT_VELOCITY * 1.0
            msg = f"Deal recente ({days_engaged}d) — momentum positivo (+{pts:.0f})"
        elif ratio <= 1.0:
            pts = WEIGHT_VELOCITY * 0.75
            msg = f"Velocidade normal ({days_engaged}d no pipeline) (+{pts:.0f})"
        elif ratio <= 1.75:
            pts = WEIGHT_VELOCITY * 0.45
            msg = f"Pipeline desacelerando ({days_engaged}d, média {self._avg_pipeline_days:.0f}d) (+{pts:.0f})"
        else:
            pts = WEIGHT_VELOCITY * 0.15
            msg = (
                f"Deal parado há {days_engaged}d "
                f"(média {self._avg_pipeline_days:.0f}d) — risco de esfriar (+{pts:.0f})"
            )
        return pts, msg

    def _score_account(self, row: pd.Series) -> tuple[float, str]:
        account_name = str(row.get("account", "")).strip()
        sector = self._account_sector.get(account_name, "")
        employees = self._account_employees.get(account_name, 0.0)

        sector_pts = WEIGHT_ACCOUNT * 0.5 if sector in HIGH_VALUE_SECTORS else WEIGHT_ACCOUNT * 0.2
        size_pts = WEIGHT_ACCOUNT * 0.5 * min(1.0, math.sqrt(employees) / math.sqrt(self._max_employees))

        pts = sector_pts + size_pts
        sector_label = f"setor {sector!r}" if sector else "setor desconhecido"
        size_label = f"{int(employees):,} funcionários" if employees > 0 else "tamanho desconhecido"
        msg = f"Conta: {sector_label}, {size_label} (+{pts:.0f})"
        return pts, msg

    def _score_agent(self, row: pd.Series) -> tuple[float, str]:
        agent = str(row.get("sales_agent", "")).strip()
        win_rate = self._agent_win_rate.get(agent, self._avg_win_rate)
        pts = float(win_rate) * WEIGHT_AGENT
        pct = win_rate * 100
        if win_rate >= self._avg_win_rate * 1.2:
            msg = f"{agent}: taxa de fechamento {pct:.0f}% (acima da média) (+{pts:.0f})"
        elif win_rate >= self._avg_win_rate * 0.8:
            msg = f"{agent}: taxa de fechamento {pct:.0f}% (média) (+{pts:.0f})"
        else:
            msg = f"{agent}: taxa de fechamento {pct:.0f}% (abaixo da média) (+{pts:.0f})"
        return pts, msg

    # ------------------------------------------------------------------
    # Score completo por linha
    # ------------------------------------------------------------------

    def _score_row(self, row: pd.Series) -> ScoreBreakdown:
        stage_pts, stage_msg = self._score_stage(row)
        value_pts, value_msg = self._score_value(row)
        vel_pts, vel_msg = self._score_velocity(row)
        acc_pts, acc_msg = self._score_account(row)
        agent_pts, agent_msg = self._score_agent(row)

        total = stage_pts + value_pts + vel_pts + acc_pts + agent_pts

        return ScoreBreakdown(
            opportunity_id=str(row.get("opportunity_id", "")),
            total_score=round(total, 1),
            stage_score=round(stage_pts, 1),
            value_score=round(value_pts, 1),
            velocity_score=round(vel_pts, 1),
            account_score=round(acc_pts, 1),
            agent_score=round(agent_pts, 1),
            explanations=[stage_msg, value_msg, vel_msg, acc_msg, agent_msg],
        )

    # ------------------------------------------------------------------
    # Público
    # ------------------------------------------------------------------

    def score_all(self) -> pd.DataFrame:
        """
        Retorna DataFrame com todos os deals ativos + scores, ordenado por score desc.
        """
        active = self.pipeline[
            self.pipeline["deal_stage"].isin(["Engaging", "Prospecting"])
        ].copy()

        if active.empty:
            return pd.DataFrame()

        breakdowns = [self._score_row(row) for _, row in active.iterrows()]
        scores_df = pd.DataFrame([b.to_dict() for b in breakdowns])

        # Merge com dados originais
        result = active.merge(scores_df, on="opportunity_id", how="left")

        # Enrichment: join com accounts, teams
        if "account" in result.columns and "account" in self.accounts.columns:
            acc_cols = ["account"] + [
                c for c in self.accounts.columns
                if c not in result.columns and c != "account"
            ]
            result = result.merge(self.accounts[acc_cols], on="account", how="left")

        if "sales_agent" in result.columns and "sales_agent" in self.teams.columns:
            team_cols = ["sales_agent"] + [
                c for c in self.teams.columns
                if c not in result.columns and c != "sales_agent"
            ]
            result = result.merge(self.teams[team_cols], on="sales_agent", how="left")

        if "product" in result.columns and "product" in self.products.columns:
            prod_cols = ["product"] + [
                c for c in self.products.columns
                if c not in result.columns and c != "product"
            ]
            result = result.merge(self.products[prod_cols], on="product", how="left")

        result = result.sort_values("total_score", ascending=False).reset_index(drop=True)
        result.index += 1  # rank começa em 1
        result.index.name = "rank"

        return result

    def score_single(self, opportunity_id: str) -> ScoreBreakdown | None:
        """Score detalhado de uma oportunidade específica."""
        rows = self.pipeline[self.pipeline["opportunity_id"] == opportunity_id]
        if rows.empty:
            return None
        return self._score_row(rows.iloc[0])
