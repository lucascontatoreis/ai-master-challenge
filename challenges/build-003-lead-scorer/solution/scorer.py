"""
Lead Scoring Engine — Challenge 003
------------------------------------
Calcula um score de 0-100 para cada oportunidade ativa no pipeline,
com explicação de cada fator e probabilidade de fechamento estimada.

Fatores e pesos:
  Stage de Pipeline         25 pts  — Engaging > Prospecting
  Potencial do Deal         20 pts  — close_value ou preço do produto como proxy
  Velocidade + Urgência     20 pts  — dias no pipeline (vs. mediana DO MESMO stage) + boost por close_date
  Qualidade da Conta        20 pts  — setor estratégico + tamanho
  Performance do Vendedor   15 pts  — win rate com Wilson interval (penaliza pouca amostra)
  ---------
  Total                    100 pts

Win Probability:
  Score mapeado para P(win) via sigmoid calibrada:
  score 40 → ~11% · score 65 → ~50% · score 80 → ~74% · score 95 → ~92%

Risk Flags (alertas sem penalidade no score):
  📅 Data de fechamento vencida
  🧊 Deal parado há mais de 90 dias
  💰 Sem close_value — deal não qualificado
  💰 Produto premium sem valor confirmado
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

HIGH_VALUE_SECTORS = {
    "Technology", "Finance", "Healthcare", "Retail", "Manufacturing",
    "Telecommunications", "Energy", "Pharmaceuticals",
}

PREMIUM_SERIES = {"MG"}
STANDARD_SERIES = {"GTX"}

WEIGHT_STAGE    = 25
WEIGHT_POTENTIAL = 20
WEIGHT_VELOCITY  = 20
WEIGHT_ACCOUNT   = 20
WEIGHT_AGENT     = 15


# ---------------------------------------------------------------------------
# Win Probability
# ---------------------------------------------------------------------------

def score_to_win_prob(score: float) -> float:
    """
    Converte score 0-100 em probabilidade estimada de fechamento via sigmoid.

    Calibração:
      score 40  → ~11%
      score 55  → ~30%
      score 65  → ~50%   (mediana histórica do pipeline)
      score 75  → ~69%
      score 85  → ~83%
      score 95  → ~92%
    """
    x = (score - 65.0) / 12.0
    return round(1.0 / (1.0 + math.exp(-x)), 3)


# ---------------------------------------------------------------------------
# Wilson Confidence Interval (lower bound)
# ---------------------------------------------------------------------------

def wilson_lower(wins: int, total: int, z: float = 1.28) -> float:
    """
    Limite inferior do intervalo de Wilson a 80% de confiança.

    Penaliza agentes com poucos deals históricos — um agente com 2 wins
    em 2 deals não recebe win_rate = 1.0 mas sim ~0.45.
    z=1.28 → IC 80%  |  z=1.645 → IC 90%
    """
    if total == 0:
        return 0.0
    p = wins / total
    denom = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return max(0.0, (centre - margin) / denom)


# ---------------------------------------------------------------------------
# Estrutura de resultado
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    opportunity_id: str
    total_score: float
    win_probability: float
    stage_score: float
    potential_score: float
    velocity_score: float
    account_score: float
    agent_score: float
    explanations: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id":  self.opportunity_id,
            "total_score":     round(self.total_score, 1),
            "win_probability": self.win_probability,
            "score_stage":     round(self.stage_score, 1),
            "score_potential": round(self.potential_score, 1),
            "score_velocity":  round(self.velocity_score, 1),
            "score_account":   round(self.account_score, 1),
            "score_agent":     round(self.agent_score, 1),
            "explanations":    " | ".join(self.explanations),
            "risk_flags":      " | ".join(self.risk_flags) if self.risk_flags else "",
        }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class LeadScorer:
    """
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
        self.teams    = teams.copy()

        self._normalize_columns()
        self._precompute_globals()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _normalize_columns(self) -> None:
        for df_attr in ("pipeline", "accounts", "products", "teams"):
            df = getattr(self, df_attr)
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        if "close_value" in self.pipeline.columns:
            self.pipeline["close_value"] = pd.to_numeric(
                self.pipeline["close_value"], errors="coerce"
            ).fillna(0)

        for col in ("engage_date", "close_date"):
            if col in self.pipeline.columns:
                self.pipeline[col] = pd.to_datetime(self.pipeline[col], errors="coerce")

        if "sales_price" in self.products.columns:
            self.products["sales_price"] = pd.to_numeric(
                self.products["sales_price"], errors="coerce"
            ).fillna(0)

    def _precompute_globals(self) -> None:
        active = self.pipeline[
            self.pipeline["deal_stage"].isin(["Engaging", "Prospecting"])
        ]

        # ---- Produto ----
        self._product_price: dict[str, float] = {}
        self._product_series: dict[str, str] = {}
        if "product" in self.products.columns:
            for _, row in self.products.iterrows():
                name = str(row.get("product", "")).strip()
                self._product_price[name]  = float(row.get("sales_price", 0) or 0)
                self._product_series[name] = str(row.get("series", "")).strip()

        # ---- Potencial máximo ----
        if not active.empty:
            def _effective(r: pd.Series) -> float:
                cv = float(r.get("close_value", 0) or 0)
                return cv if cv > 0 else self._product_price.get(str(r.get("product", "")), 0)
            self._max_potential = active.apply(_effective, axis=1).max() or 1
        else:
            self._max_potential = 1

        # ---- Win rate por agente com Wilson interval ----
        closed = self.pipeline[self.pipeline["deal_stage"].isin(["Won", "Lost"])]
        self._agent_wilson: dict[str, float] = {}
        self._agent_raw_rate: dict[str, float] = {}
        self._agent_deal_count: dict[str, int] = {}
        self._avg_wilson: float = 0.5

        if not closed.empty and "sales_agent" in closed.columns:
            wins_s   = closed[closed["deal_stage"] == "Won"].groupby("sales_agent").size()
            totals_s = closed.groupby("sales_agent").size()

            for agent in totals_s.index:
                w = int(wins_s.get(agent, 0))
                t = int(totals_s[agent])
                self._agent_wilson[agent]     = wilson_lower(w, t)
                self._agent_raw_rate[agent]   = w / t if t > 0 else 0.0
                self._agent_deal_count[agent] = t

            if self._agent_wilson:
                self._avg_wilson = float(np.mean(list(self._agent_wilson.values())))

        # ---- Mediana de dias NO PIPELINE separada por stage ----
        #      Velocity é comparada dentro do mesmo stage → sem dupla contagem com Stage factor
        today = pd.Timestamp.today().normalize()
        self._avg_days_by_stage: dict[str, float] = {}

        for stage in ("Engaging", "Prospecting"):
            stage_df = active[active["deal_stage"] == stage].copy()
            if not stage_df.empty and "engage_date" in stage_df.columns:
                days = (today - stage_df["engage_date"]).dt.days.clip(lower=0).dropna()
                median = float(days.median()) if not days.empty else 30
                self._avg_days_by_stage[stage] = median if median > 0 else 30
            else:
                self._avg_days_by_stage[stage] = 30

        # ---- Dados de contas ----
        self._account_sector: dict[str, str] = {}
        self._account_employees: dict[str, float] = {}
        if "account" in self.accounts.columns:
            emp_col = next(
                (c for c in self.accounts.columns if "employ" in c or "employee" in c), None
            )
            for _, row in self.accounts.iterrows():
                key = str(row.get("account", "")).strip()
                self._account_sector[key]    = str(row.get("sector", "")).strip()
                self._account_employees[key] = float(row[emp_col]) if emp_col else 0.0

        self._max_employees = max(self._account_employees.values(), default=1) or 1

    # ------------------------------------------------------------------
    # Fatores
    # ------------------------------------------------------------------

    def _score_stage(self, row: pd.Series) -> tuple[float, str]:
        stage = str(row.get("deal_stage", "")).strip()
        pts   = float(STAGE_SCORES.get(stage, 0))
        if stage == "Engaging":
            msg = "Em Engaging — contato ativo, alta probabilidade de avanço (+25)"
        elif stage == "Prospecting":
            msg = "Em Prospecting — fase inicial de qualificação (+15)"
        else:
            msg = f"Stage '{stage}' não pontuado"
        return pts, msg

    def _score_potential(self, row: pd.Series) -> tuple[float, str]:
        close_value   = float(row.get("close_value", 0) or 0)
        product_name  = str(row.get("product", "")).strip()
        product_price = self._product_price.get(product_name, 0)
        product_series = self._product_series.get(product_name, "")
        is_premium    = product_series in PREMIUM_SERIES

        if close_value > 0:
            effective    = close_value
            value_source = f"R$ {close_value:,.0f} (qualificado)"
        elif product_price > 0:
            effective    = product_price * 0.7
            value_source = f"estimativa via {product_name} (tabela R$ {product_price:,.0f})"
        else:
            effective    = 0
            value_source = "sem valor e sem produto identificado"

        normalized = math.sqrt(effective) / math.sqrt(self._max_potential)
        pts = normalized * WEIGHT_POTENTIAL

        if is_premium and close_value == 0:
            pts = min(pts * 1.15, WEIGHT_POTENTIAL)
            series_note = f" | Série {product_series} (premium)"
        else:
            series_note = f" | Série {product_series}" if product_series else ""

        msg = f"Potencial: {value_source}{series_note} (+{pts:.0f})"
        return pts, msg

    def _score_velocity(self, row: pd.Series) -> tuple[float, str]:
        """
        Velocidade comparada contra a mediana DO MESMO stage (Engaging vs Engaging,
        Prospecting vs Prospecting) — evita dupla contagem com o fator de Stage.
        Urgência de close_date aplica para qualquer stage.
        """
        today      = pd.Timestamp.today().normalize()
        engage_date = row.get("engage_date")
        close_date  = row.get("close_date")
        stage       = str(row.get("deal_stage", ""))
        avg_days    = self._avg_days_by_stage.get(stage, 30)

        # ---- Urgência por close_date ----
        urgency_bonus = 0.0
        urgency_msg   = ""
        if pd.notna(close_date):
            days_to_close = (close_date - today).days
            if days_to_close < 0:
                urgency_msg = f"⚠️ Vence há {abs(days_to_close)}d"
            elif days_to_close <= 14:
                urgency_bonus = WEIGHT_VELOCITY * 0.5
                urgency_msg   = f"🔥 Fecha em {days_to_close}d — URGENTE"
            elif days_to_close <= 30:
                urgency_bonus = WEIGHT_VELOCITY * 0.3
                urgency_msg   = f"Fecha em {days_to_close}d — este mês"
            elif days_to_close <= 60:
                urgency_bonus = WEIGHT_VELOCITY * 0.15
                urgency_msg   = f"Fecha em {days_to_close}d"

        # ---- Velocidade base: dias no pipeline vs. mediana do mesmo stage ----
        if pd.isna(engage_date):
            base_pts = WEIGHT_VELOCITY * 0.2
            base_msg = "Sem data de engajamento"
        else:
            days_engaged = max(0, (today - engage_date).days)
            ratio        = days_engaged / avg_days

            if ratio <= 0.5:
                base_pts = WEIGHT_VELOCITY * 0.8
                base_msg = f"Recente ({days_engaged}d) — momentum positivo"
            elif ratio <= 1.0:
                base_pts = WEIGHT_VELOCITY * 0.6
                base_msg = f"Ritmo normal ({days_engaged}d, mediana {avg_days:.0f}d)"
            elif ratio <= 2.0:
                base_pts = WEIGHT_VELOCITY * 0.35
                base_msg = f"Desacelerando ({days_engaged}d = {ratio:.1f}× a mediana)"
            else:
                base_pts = WEIGHT_VELOCITY * 0.1
                base_msg = f"Parado ({days_engaged}d = {ratio:.1f}× a mediana) — risco de esfriar"

        total_pts = min(base_pts + urgency_bonus, WEIGHT_VELOCITY)
        parts     = [p for p in [base_msg, urgency_msg] if p]
        msg       = f"{' | '.join(parts)} (+{total_pts:.0f})"
        return total_pts, msg

    def _score_account(self, row: pd.Series) -> tuple[float, str]:
        account_name = str(row.get("account", "")).strip()
        sector       = self._account_sector.get(account_name, "")
        employees    = self._account_employees.get(account_name, 0.0)

        sector_pts = WEIGHT_ACCOUNT * 0.5 if sector in HIGH_VALUE_SECTORS else WEIGHT_ACCOUNT * 0.2
        size_pts   = WEIGHT_ACCOUNT * 0.5 * min(
            1.0, math.sqrt(employees) / math.sqrt(self._max_employees)
        )
        pts = sector_pts + size_pts

        sector_label = f"setor '{sector}'" if sector else "setor desconhecido"
        size_label   = f"{int(employees):,} funcionários" if employees > 0 else "tamanho desconhecido"
        msg = f"Conta: {sector_label}, {size_label} (+{pts:.0f})"
        return pts, msg

    def _score_agent(self, row: pd.Series) -> tuple[float, str]:
        """
        Win rate com Wilson lower bound (IC 80%).
        Penaliza agentes novos com poucos deals históricos.
        """
        agent       = str(row.get("sales_agent", "")).strip()
        wilson      = self._agent_wilson.get(agent, self._avg_wilson)
        raw_rate    = self._agent_raw_rate.get(agent, self._avg_wilson)
        deal_count  = self._agent_deal_count.get(agent, 0)
        pts         = wilson * WEIGHT_AGENT
        pct         = raw_rate * 100

        if deal_count == 0:
            msg = f"{agent}: sem histórico de fechamento (usando média) (+{pts:.0f})"
        elif deal_count < 10:
            msg = f"{agent}: win rate {pct:.0f}% ({deal_count} deals — amostra pequena) (+{pts:.0f})"
        elif wilson >= self._avg_wilson * 1.2:
            msg = f"{agent}: win rate {pct:.0f}% — acima da média (+{pts:.0f})"
        elif wilson >= self._avg_wilson * 0.8:
            msg = f"{agent}: win rate {pct:.0f}% — dentro da média (+{pts:.0f})"
        else:
            msg = f"{agent}: win rate {pct:.0f}% — abaixo da média (+{pts:.0f})"
        return pts, msg

    # ------------------------------------------------------------------
    # Risk Flags
    # ------------------------------------------------------------------

    def _get_risk_flags(self, row: pd.Series) -> list[str]:
        flags      = []
        today      = pd.Timestamp.today().normalize()
        close_date = row.get("close_date")
        engage_date = row.get("engage_date")
        close_value = float(row.get("close_value", 0) or 0)
        product_name = str(row.get("product", "")).strip()
        product_price = self._product_price.get(product_name, 0)
        product_series = self._product_series.get(product_name, "")

        if pd.notna(close_date) and (close_date - today).days < 0:
            flags.append(f"📅 Vencido há {abs((close_date - today).days)}d")

        if pd.notna(engage_date) and (today - engage_date).days > 90:
            flags.append(f"🧊 Inativo há {(today - engage_date).days}d")

        if close_value == 0:
            if product_price > 0 and product_series in PREMIUM_SERIES:
                flags.append(f"💰 Produto premium ({product_name}) sem valor confirmado")
            else:
                flags.append("💰 Sem close_value — qualificar ticket")

        if not product_series and product_name:
            flags.append("🔍 Série do produto desconhecida")

        return flags

    # ------------------------------------------------------------------
    # Score por linha
    # ------------------------------------------------------------------

    def _score_row(self, row: pd.Series) -> ScoreBreakdown:
        stage_pts,    stage_msg   = self._score_stage(row)
        potential_pts, pot_msg    = self._score_potential(row)
        vel_pts,      vel_msg     = self._score_velocity(row)
        acc_pts,      acc_msg     = self._score_account(row)
        agent_pts,    agent_msg   = self._score_agent(row)
        risk_flags = self._get_risk_flags(row)

        total    = stage_pts + potential_pts + vel_pts + acc_pts + agent_pts
        win_prob = score_to_win_prob(total)

        return ScoreBreakdown(
            opportunity_id  = str(row.get("opportunity_id", "")),
            total_score     = round(total, 1),
            win_probability = win_prob,
            stage_score     = round(stage_pts, 1),
            potential_score = round(potential_pts, 1),
            velocity_score  = round(vel_pts, 1),
            account_score   = round(acc_pts, 1),
            agent_score     = round(agent_pts, 1),
            explanations    = [stage_msg, pot_msg, vel_msg, acc_msg, agent_msg],
            risk_flags      = risk_flags,
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def score_all(self) -> pd.DataFrame:
        active = self.pipeline[
            self.pipeline["deal_stage"].isin(["Engaging", "Prospecting"])
        ].copy()

        if active.empty:
            return pd.DataFrame()

        breakdowns = [self._score_row(row) for _, row in active.iterrows()]
        scores_df  = pd.DataFrame([b.to_dict() for b in breakdowns])

        result = active.merge(scores_df, on="opportunity_id", how="left")

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
        result.index += 1
        result.index.name = "rank"
        return result

    def score_single(self, opportunity_id: str) -> ScoreBreakdown | None:
        rows = self.pipeline[self.pipeline["opportunity_id"] == opportunity_id]
        if rows.empty:
            return None
        return self._score_row(rows.iloc[0])
