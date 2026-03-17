"""
Lead Scoring Engine — Challenge 003
------------------------------------
Calcula um score de 0-100 para cada oportunidade ativa no pipeline,
com explicação de cada fator para o vendedor entender o resultado.

Fatores e pesos:
  Stage de Pipeline         25 pts  — Engaging vale mais que Prospecting
  Potencial do Deal         20 pts  — close_value (ou preço do produto se $0)
  Velocidade + Urgência     20 pts  — dias no pipeline + proximidade da data de fechamento
  Qualidade da Conta        20 pts  — setor estratégico + tamanho da empresa
  Performance do Vendedor   15 pts  — taxa histórica de fechamento do agente
  ---------
  Total                    100 pts

Risk Flags (não subtraem pontos — são alertas de ação):
  ⚠️ Data de fechamento vencida
  ⚠️ Deal parado há mais de 90 dias
  ⚠️ Nenhum valor de fechamento registrado
  ⚠️ Produto de alto ticket sem close_value (não qualificado)
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

# Séries de produto — MG é a linha premium, GTX é a linha de entrada
PREMIUM_SERIES = {"MG"}
STANDARD_SERIES = {"GTX"}

WEIGHT_STAGE = 25
WEIGHT_POTENTIAL = 20   # antes era só "value"; agora inclui produto como proxy
WEIGHT_VELOCITY = 20
WEIGHT_ACCOUNT = 20
WEIGHT_AGENT = 15


# ---------------------------------------------------------------------------
# Estrutura de resultado
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    """Score detalhado de um deal, com explicação por fator e risk flags."""
    opportunity_id: str
    total_score: float
    stage_score: float
    potential_score: float
    velocity_score: float
    account_score: float
    agent_score: float
    explanations: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "total_score": round(self.total_score, 1),
            "score_stage": round(self.stage_score, 1),
            "score_potential": round(self.potential_score, 1),
            "score_velocity": round(self.velocity_score, 1),
            "score_account": round(self.account_score, 1),
            "score_agent": round(self.agent_score, 1),
            "explanations": " | ".join(self.explanations),
            "risk_flags": " | ".join(self.risk_flags) if self.risk_flags else "",
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

        if "close_value" in self.pipeline.columns:
            self.pipeline["close_value"] = pd.to_numeric(
                self.pipeline["close_value"], errors="coerce"
            ).fillna(0)

        for col in ("engage_date", "close_date"):
            if col in self.pipeline.columns:
                self.pipeline[col] = pd.to_datetime(
                    self.pipeline[col], errors="coerce"
                )

        if "sales_price" in self.products.columns:
            self.products["sales_price"] = pd.to_numeric(
                self.products["sales_price"], errors="coerce"
            ).fillna(0)

    def _precompute_globals(self) -> None:
        """Pré-computa métricas globais usadas na normalização."""
        active = self.pipeline[
            self.pipeline["deal_stage"].isin(["Engaging", "Prospecting"])
        ]

        # ------------------------------------------------------------------
        # Potencial máximo: usa close_value ou preço do produto como fallback
        # ------------------------------------------------------------------
        self._product_price: dict[str, float] = {}
        self._product_series: dict[str, str] = {}
        if "product" in self.products.columns:
            for _, row in self.products.iterrows():
                name = str(row.get("product", "")).strip()
                self._product_price[name] = float(row.get("sales_price", 0) or 0)
                self._product_series[name] = str(row.get("series", "")).strip()

        # Para normalizar potencial: considera close_value se > 0,
        # senão usa o preço do produto como proxy de potencial
        if not active.empty:
            def _effective_value(r: pd.Series) -> float:
                cv = float(r.get("close_value", 0) or 0)
                if cv > 0:
                    return cv
                return self._product_price.get(str(r.get("product", "")), 0)

            effective_values = active.apply(_effective_value, axis=1)
            self._max_potential = effective_values.max()
        else:
            self._max_potential = 1

        if self._max_potential == 0:
            self._max_potential = 1

        # ------------------------------------------------------------------
        # Taxa histórica de win por agente
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Mediana de dias no pipeline para Engaging (referência de velocidade)
        # ------------------------------------------------------------------
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

        # ------------------------------------------------------------------
        # Dados de contas
        # ------------------------------------------------------------------
        self._account_sector: dict[str, str] = {}
        self._account_employees: dict[str, float] = {}
        if "account" in self.accounts.columns:
            emp_col = next(
                (c for c in self.accounts.columns if "employ" in c or "employee" in c),
                None,
            )
            for _, row in self.accounts.iterrows():
                key = str(row.get("account", "")).strip()
                self._account_sector[key] = str(row.get("sector", "")).strip()
                self._account_employees[key] = float(row[emp_col]) if emp_col else 0.0

        self._max_employees = max(self._account_employees.values(), default=1) or 1

    # ------------------------------------------------------------------
    # Fatores individuais
    # ------------------------------------------------------------------

    def _score_stage(self, row: pd.Series) -> tuple[float, str]:
        stage = str(row.get("deal_stage", "")).strip()
        pts = float(STAGE_SCORES.get(stage, 0))
        if stage == "Engaging":
            msg = "Em Engaging — contato ativo, alta probabilidade de avanço (+25)"
        elif stage == "Prospecting":
            msg = "Em Prospecting — ainda em fase inicial de qualificação (+15)"
        else:
            msg = f"Stage '{stage}' não pontuado"
        return pts, msg

    def _score_potential(self, row: pd.Series) -> tuple[float, str]:
        """
        Pontuação de potencial financeiro.
        Usa close_value se disponível, caso contrário usa o preço de tabela
        do produto como proxy de potencial máximo do deal.
        """
        close_value = float(row.get("close_value", 0) or 0)
        product_name = str(row.get("product", "")).strip()
        product_price = self._product_price.get(product_name, 0)
        product_series = self._product_series.get(product_name, "")
        is_premium = product_series in PREMIUM_SERIES

        if close_value > 0:
            effective = close_value
            value_source = f"R$ {close_value:,.0f} (valor qualificado)"
        elif product_price > 0:
            # Usa preço do produto como potencial, mas com desconto
            # pois é uma estimativa, não valor confirmado
            effective = product_price * 0.7
            value_source = f"sem valor confirmado — estimativa via produto {product_name} (R$ {product_price:,.0f} tabela)"
        else:
            effective = 0
            value_source = "sem valor e sem produto identificado"

        normalized = math.sqrt(effective) / math.sqrt(self._max_potential)
        pts = normalized * WEIGHT_POTENTIAL

        # Bônus de série: produto premium sinaliza deal de maior ticket
        if is_premium and close_value == 0:
            pts = min(pts * 1.15, WEIGHT_POTENTIAL)  # +15% para premium sem valor confirmado
            series_note = f" | Série {product_series} (premium)"
        elif is_premium:
            series_note = f" | Série {product_series} (premium)"
        else:
            series_note = f" | Série {product_series}" if product_series else ""

        msg = f"Potencial: {value_source}{series_note} (+{pts:.0f})"
        return pts, msg

    def _score_velocity(self, row: pd.Series) -> tuple[float, str]:
        """
        Velocidade no pipeline + urgência de data de fechamento.
        Aplica para ambos Engaging e Prospecting.
        """
        today = pd.Timestamp.today().normalize()
        engage_date = row.get("engage_date")
        close_date = row.get("close_date")
        stage = str(row.get("deal_stage", ""))

        # ---- Urgência por close_date (válida para qualquer stage) ----
        urgency_bonus = 0.0
        urgency_msg = ""
        if pd.notna(close_date):
            days_to_close = (close_date - today).days
            if days_to_close < 0:
                # Data já passou — deal atrasado, mas ainda ativo
                urgency_bonus = 0.0
                urgency_msg = f"⚠️ Fecha há {abs(days_to_close)}d"
            elif days_to_close <= 14:
                urgency_bonus = WEIGHT_VELOCITY * 0.5
                urgency_msg = f"🔥 Fecha em {days_to_close}d — URGENTE"
            elif days_to_close <= 30:
                urgency_bonus = WEIGHT_VELOCITY * 0.3
                urgency_msg = f"Fecha em {days_to_close}d — este mês"
            elif days_to_close <= 60:
                urgency_bonus = WEIGHT_VELOCITY * 0.15
                urgency_msg = f"Fecha em {days_to_close}d"

        # ---- Velocidade base por dias no pipeline ----
        if pd.isna(engage_date):
            base_pts = WEIGHT_VELOCITY * 0.2
            base_msg = "Sem data de engajamento registrada"
        else:
            days_engaged = max(0, (today - engage_date).days)
            ratio = days_engaged / self._avg_pipeline_days

            if stage == "Prospecting":
                # Prospecting: sem referência histórica — só close_date conta
                base_pts = WEIGHT_VELOCITY * 0.3
                base_msg = "Prospecting — velocidade avaliada pela data de fechamento"
            elif ratio <= 0.5:
                base_pts = WEIGHT_VELOCITY * 0.8
                base_msg = f"Deal recente ({days_engaged}d) — momentum positivo"
            elif ratio <= 1.0:
                base_pts = WEIGHT_VELOCITY * 0.6
                base_msg = f"Velocidade normal ({days_engaged}d no pipeline, média {self._avg_pipeline_days:.0f}d)"
            elif ratio <= 2.0:
                base_pts = WEIGHT_VELOCITY * 0.35
                base_msg = f"Desacelerando ({days_engaged}d, {ratio:.1f}x a média)"
            else:
                base_pts = WEIGHT_VELOCITY * 0.1
                base_msg = f"Deal parado ({days_engaged}d, {ratio:.1f}x a média) — risco de esfriar"

        # Combina base + urgência (cap em WEIGHT_VELOCITY)
        total_pts = min(base_pts + urgency_bonus, WEIGHT_VELOCITY)
        parts = [p for p in [base_msg, urgency_msg] if p]
        msg = f"{' | '.join(parts)} (+{total_pts:.0f})"
        return total_pts, msg

    def _score_account(self, row: pd.Series) -> tuple[float, str]:
        account_name = str(row.get("account", "")).strip()
        sector = self._account_sector.get(account_name, "")
        employees = self._account_employees.get(account_name, 0.0)

        sector_pts = WEIGHT_ACCOUNT * 0.5 if sector in HIGH_VALUE_SECTORS else WEIGHT_ACCOUNT * 0.2
        size_pts = WEIGHT_ACCOUNT * 0.5 * min(
            1.0, math.sqrt(employees) / math.sqrt(self._max_employees)
        )

        pts = sector_pts + size_pts
        sector_label = f"setor {sector!r}" if sector else "setor desconhecido"
        size_label = f"{int(employees):,} funcionários" if employees > 0 else "tamanho desconhecido"
        msg = f"Conta: {sector_label}, {size_label} (+{pts:.0f})"
        return pts, msg

    def _score_agent(self, row: pd.Series) -> tuple[float, str]:
        agent = str(row.get("sales_agent", "")).strip()
        win_rate = float(self._agent_win_rate.get(agent, self._avg_win_rate))
        pts = win_rate * WEIGHT_AGENT
        pct = win_rate * 100
        if win_rate >= self._avg_win_rate * 1.2:
            msg = f"{agent}: win rate {pct:.0f}% — acima da média (+{pts:.0f})"
        elif win_rate >= self._avg_win_rate * 0.8:
            msg = f"{agent}: win rate {pct:.0f}% — dentro da média (+{pts:.0f})"
        else:
            msg = f"{agent}: win rate {pct:.0f}% — abaixo da média (+{pts:.0f})"
        return pts, msg

    # ------------------------------------------------------------------
    # Risk flags — alertas sem penalidade no score
    # ------------------------------------------------------------------

    def _get_risk_flags(self, row: pd.Series) -> list[str]:
        flags = []
        today = pd.Timestamp.today().normalize()

        close_date = row.get("close_date")
        engage_date = row.get("engage_date")
        close_value = float(row.get("close_value", 0) or 0)
        product_name = str(row.get("product", "")).strip()
        product_price = self._product_price.get(product_name, 0)
        product_series = self._product_series.get(product_name, "")

        # Data de fechamento vencida
        if pd.notna(close_date) and (close_date - today).days < 0:
            flags.append(f"📅 Vencido há {abs((close_date - today).days)}d")

        # Deal parado por muito tempo
        if pd.notna(engage_date):
            days_engaged = (today - engage_date).days
            if days_engaged > 90:
                flags.append(f"🧊 Inativo há {days_engaged}d")

        # Sem valor confirmado
        if close_value == 0:
            if product_price > 0 and product_series in PREMIUM_SERIES:
                flags.append(f"💰 Produto premium ({product_name}) sem valor confirmado")
            else:
                flags.append("💰 Sem close_value — qualificar ticket")

        # Produto sem série identificada (dado sujo)
        if not product_series and product_name:
            flags.append("🔍 Série do produto desconhecida")

        return flags

    # ------------------------------------------------------------------
    # Score completo por linha
    # ------------------------------------------------------------------

    def _score_row(self, row: pd.Series) -> ScoreBreakdown:
        stage_pts, stage_msg = self._score_stage(row)
        potential_pts, potential_msg = self._score_potential(row)
        vel_pts, vel_msg = self._score_velocity(row)
        acc_pts, acc_msg = self._score_account(row)
        agent_pts, agent_msg = self._score_agent(row)
        risk_flags = self._get_risk_flags(row)

        total = stage_pts + potential_pts + vel_pts + acc_pts + agent_pts

        return ScoreBreakdown(
            opportunity_id=str(row.get("opportunity_id", "")),
            total_score=round(total, 1),
            stage_score=round(stage_pts, 1),
            potential_score=round(potential_pts, 1),
            velocity_score=round(vel_pts, 1),
            account_score=round(acc_pts, 1),
            agent_score=round(agent_pts, 1),
            explanations=[stage_msg, potential_msg, vel_msg, acc_msg, agent_msg],
            risk_flags=risk_flags,
        )

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def score_all(self) -> pd.DataFrame:
        """
        Retorna DataFrame com todos os deals ativos + scores, ordenado por score desc.
        Inclui colunas enriquecidas de accounts, teams e products.
        """
        active = self.pipeline[
            self.pipeline["deal_stage"].isin(["Engaging", "Prospecting"])
        ].copy()

        if active.empty:
            return pd.DataFrame()

        breakdowns = [self._score_row(row) for _, row in active.iterrows()]
        scores_df = pd.DataFrame([b.to_dict() for b in breakdowns])

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
        """Score detalhado de uma oportunidade específica."""
        rows = self.pipeline[self.pipeline["opportunity_id"] == opportunity_id]
        if rows.empty:
            return None
        return self._score_row(rows.iloc[0])
