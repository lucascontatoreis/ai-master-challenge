"""
Lead Scorer — Dashboard para Vendedores
Challenge 003 · G4 AI Master

Rode com:
    streamlit run app.py
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scorer import LeadScorer
from sample_data import generate_all

# ---------------------------------------------------------------------------
# Config da página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Lead Scorer | G4 AI Master",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------

SCORE_COLORS = {
    "hot": "#e74c3c",      # ≥ 70
    "warm": "#e67e22",     # 50–69
    "cold": "#3498db",     # < 50
}


def score_badge(score: float) -> str:
    if score >= 70:
        color, label = SCORE_COLORS["hot"], "🔴 QUENTE"
    elif score >= 50:
        color, label = SCORE_COLORS["warm"], "🟠 MORNO"
    else:
        color, label = SCORE_COLORS["cold"], "🔵 FRIO"
    return f'<span style="color:{color};font-weight:700">{label}</span>'


# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Calculando scores...")
def load_and_score(
    pipeline_bytes: bytes | None,
    accounts_bytes: bytes | None,
    products_bytes: bytes | None,
    teams_bytes: bytes | None,
) -> pd.DataFrame:
    if all(b is None for b in [pipeline_bytes, accounts_bytes, products_bytes, teams_bytes]):
        pipeline, accounts, products, teams = generate_all()
    else:
        def read(b: bytes | None, fallback_fn):
            if b:
                return pd.read_csv(io.BytesIO(b))
            return fallback_fn()

        from sample_data import (
            generate_accounts, generate_products,
            generate_sales_teams, generate_pipeline,
        )
        accounts = read(accounts_bytes, generate_accounts)
        products = read(products_bytes, generate_products)
        teams = read(teams_bytes, generate_sales_teams)

        if pipeline_bytes:
            pipeline = pd.read_csv(io.BytesIO(pipeline_bytes))
        else:
            pipeline = generate_pipeline(accounts, products, teams)

    scorer = LeadScorer(pipeline, accounts, products, teams)
    return scorer.score_all()


# ---------------------------------------------------------------------------
# Sidebar — Upload e Filtros
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🎯 Lead Scorer")
    st.markdown("**Challenge 003 — G4 AI Master**")
    st.divider()

    st.subheader("📂 Dados")
    st.markdown(
        "Faça upload dos CSVs do dataset ou use os dados de demonstração."
    )
    use_sample = st.toggle("Usar dados de demonstração", value=True)

    pipeline_file = accounts_file = products_file = teams_file = None
    if not use_sample:
        pipeline_file = st.file_uploader("sales_pipeline.csv", type="csv")
        accounts_file = st.file_uploader("accounts.csv", type="csv")
        products_file = st.file_uploader("products.csv", type="csv")
        teams_file = st.file_uploader("sales_teams.csv", type="csv")

    st.divider()
    st.subheader("🔍 Filtros")

# ---------------------------------------------------------------------------
# Carrega dados
# ---------------------------------------------------------------------------

def _bytes(f) -> bytes | None:
    return f.read() if f else None


scored_df = load_and_score(
    _bytes(pipeline_file),
    _bytes(accounts_file),
    _bytes(products_file),
    _bytes(teams_file),
)

if scored_df.empty:
    st.error("Nenhum deal ativo encontrado. Verifique os dados carregados.")
    st.stop()

# ---------------------------------------------------------------------------
# Filtros na sidebar (após dados carregados)
# ---------------------------------------------------------------------------

with st.sidebar:
    agents = sorted(scored_df["sales_agent"].dropna().unique().tolist()) if "sales_agent" in scored_df.columns else []
    managers = sorted(scored_df["manager"].dropna().unique().tolist()) if "manager" in scored_df.columns else []
    regions = sorted(scored_df["regional_office"].dropna().unique().tolist()) if "regional_office" in scored_df.columns else []
    stages = sorted(scored_df["deal_stage"].dropna().unique().tolist()) if "deal_stage" in scored_df.columns else []
    products_list = sorted(scored_df["product"].dropna().unique().tolist()) if "product" in scored_df.columns else []

    selected_manager = st.multiselect("Manager", managers, placeholder="Todos os managers")
    selected_agent = st.multiselect("Vendedor", agents, placeholder="Todos os vendedores")
    selected_region = st.multiselect("Região", regions, placeholder="Todas as regiões")
    selected_stage = st.multiselect("Stage", stages, placeholder="Todos os stages", default=["Engaging", "Prospecting"] if "Engaging" in stages else [])
    selected_product = st.multiselect("Produto", products_list, placeholder="Todos os produtos")
    min_score = st.slider("Score mínimo", 0, 100, 0)

    st.divider()
    st.caption("Scoring: stage 25pt · valor 20pt · velocidade 20pt · conta 20pt · agente 15pt")

# ---------------------------------------------------------------------------
# Aplica filtros
# ---------------------------------------------------------------------------

filtered = scored_df.copy()

if selected_manager and "manager" in filtered.columns:
    filtered = filtered[filtered["manager"].isin(selected_manager)]
if selected_agent and "sales_agent" in filtered.columns:
    filtered = filtered[filtered["sales_agent"].isin(selected_agent)]
if selected_region and "regional_office" in filtered.columns:
    filtered = filtered[filtered["regional_office"].isin(selected_region)]
if selected_stage and "deal_stage" in filtered.columns:
    filtered = filtered[filtered["deal_stage"].isin(selected_stage)]
if selected_product and "product" in filtered.columns:
    filtered = filtered[filtered["product"].isin(selected_product)]
filtered = filtered[filtered["total_score"] >= min_score]

# ---------------------------------------------------------------------------
# KPIs do topo
# ---------------------------------------------------------------------------

st.title("🎯 Lead Scorer — Dashboard de Priorização")
st.markdown(
    f"Exibindo **{len(filtered):,}** deals ativos | "
    f"Score médio: **{filtered['total_score'].mean():.1f}** | "
    f"Deals quentes (≥70): **{(filtered['total_score'] >= 70).sum():,}**"
)

col1, col2, col3, col4 = st.columns(4)

with col1:
    hot = (filtered["total_score"] >= 70).sum()
    st.metric("🔴 Quentes (≥70)", hot, help="Deals com alta probabilidade de fechamento")
with col2:
    warm = ((filtered["total_score"] >= 50) & (filtered["total_score"] < 70)).sum()
    st.metric("🟠 Mornos (50–69)", warm, help="Deals que precisam de atenção")
with col3:
    cold = (filtered["total_score"] < 50).sum()
    st.metric("🔵 Frios (<50)", cold, help="Deals com baixa prioridade no momento")
with col4:
    if "close_value" in filtered.columns:
        total_value = filtered[filtered["total_score"] >= 50]["close_value"].sum()
        st.metric("💰 Valor em Jogo (mornos+quentes)", f"R$ {total_value:,.0f}")
    else:
        st.metric("Total de Deals", len(filtered))

st.divider()

# ---------------------------------------------------------------------------
# Tabs principais
# ---------------------------------------------------------------------------

tab_pipeline, tab_charts, tab_detail = st.tabs(
    ["📋 Pipeline Priorizado", "📊 Análises", "🔎 Detalhe do Deal"]
)

# ===========================================================================
# TAB 1 — Pipeline Priorizado
# ===========================================================================

with tab_pipeline:
    st.subheader("Pipeline Ordenado por Score")
    st.markdown(
        "Os deals estão ordenados do mais prioritário ao menos prioritário. "
        "**Foque nos vermelhos primeiro.**"
    )

    display_cols = [
        "opportunity_id", "sales_agent", "account", "product",
        "deal_stage", "close_value", "total_score",
        "score_stage", "score_value", "score_velocity", "score_account", "score_agent",
        "explanations",
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]

    display_df = filtered[available_cols].copy().reset_index(drop=True)
    display_df.index += 1
    display_df.index.name = "Rank"

    # Renomear para exibição amigável
    rename_map = {
        "opportunity_id": "Deal ID",
        "sales_agent": "Vendedor",
        "account": "Conta",
        "product": "Produto",
        "deal_stage": "Stage",
        "close_value": "Valor (R$)",
        "total_score": "Score",
        "score_stage": "Pts Stage",
        "score_value": "Pts Valor",
        "score_velocity": "Pts Velocidade",
        "score_account": "Pts Conta",
        "score_agent": "Pts Agente",
        "explanations": "Explicação",
    }
    display_df = display_df.rename(columns=rename_map)

    # Formatação
    if "Valor (R$)" in display_df.columns:
        display_df["Valor (R$)"] = display_df["Valor (R$)"].apply(
            lambda x: f"R$ {x:,.0f}" if pd.notna(x) and x > 0 else "—"
        )

    # Highlight por score
    def highlight_score(val):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return ""
        if v >= 70:
            return "background-color:#fde8e8;color:#c0392b;font-weight:700"
        elif v >= 50:
            return "background-color:#fef3e2;color:#d35400;font-weight:600"
        return "background-color:#ebf5fb;color:#2980b9"

    styled = (
        display_df.style
        .applymap(highlight_score, subset=["Score"])
        .format({"Score": "{:.1f}", "Pts Stage": "{:.1f}", "Pts Valor": "{:.1f}",
                 "Pts Velocidade": "{:.1f}", "Pts Conta": "{:.1f}", "Pts Agente": "{:.1f}"},
                na_rep="—")
    )

    st.dataframe(styled, use_container_width=True, height=500)

    # Download
    csv_out = filtered[available_cols].to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Exportar CSV",
        data=csv_out,
        file_name="pipeline_priorizado.csv",
        mime="text/csv",
    )

# ===========================================================================
# TAB 2 — Análises
# ===========================================================================

with tab_charts:
    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Distribuição de Scores")
        fig_hist = px.histogram(
            filtered, x="total_score", nbins=20,
            color_discrete_sequence=["#3498db"],
            labels={"total_score": "Score", "count": "Qtd. Deals"},
            title="Quantos deals em cada faixa de score",
        )
        fig_hist.add_vline(x=70, line_dash="dash", line_color=SCORE_COLORS["hot"],
                           annotation_text="Quente (70)", annotation_position="top right")
        fig_hist.add_vline(x=50, line_dash="dash", line_color=SCORE_COLORS["warm"],
                           annotation_text="Morno (50)", annotation_position="top right")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_b:
        st.subheader("Contribuição de cada Fator no Score")
        score_cols = ["score_stage", "score_value", "score_velocity", "score_account", "score_agent"]
        available_score_cols = [c for c in score_cols if c in filtered.columns]
        if available_score_cols:
            means = filtered[available_score_cols].mean()
            labels = {
                "score_stage": "Stage",
                "score_value": "Valor",
                "score_velocity": "Velocidade",
                "score_account": "Conta",
                "score_agent": "Agente",
            }
            fig_bar = px.bar(
                x=[labels.get(c, c) for c in means.index],
                y=means.values,
                color=means.values,
                color_continuous_scale="Blues",
                labels={"x": "Fator", "y": "Média de Pontos"},
                title="Média de pontos por fator (indica onde há espaço para melhoria)",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        if "sales_agent" in filtered.columns:
            st.subheader("Top 10 Vendedores por Score Médio")
            agent_scores = (
                filtered.groupby("sales_agent")["total_score"]
                .agg(["mean", "count"])
                .rename(columns={"mean": "Score Médio", "count": "Deals Ativos"})
                .sort_values("Score Médio", ascending=False)
                .head(10)
                .reset_index()
            )
            fig_agents = px.bar(
                agent_scores, x="Score Médio", y="sales_agent",
                orientation="h", color="Score Médio",
                color_continuous_scale="RdYlGn",
                labels={"sales_agent": "Vendedor"},
                title="Quem tem o pipeline mais qualificado?",
                text="Deals Ativos",
            )
            fig_agents.update_layout(yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig_agents, use_container_width=True)

    with col_d:
        if "product" in filtered.columns:
            st.subheader("Score Médio por Produto")
            prod_scores = (
                filtered.groupby("product")["total_score"]
                .mean()
                .sort_values(ascending=True)
                .reset_index()
            )
            fig_prod = px.bar(
                prod_scores, x="total_score", y="product",
                orientation="h", color="total_score",
                color_continuous_scale="Blues",
                labels={"product": "Produto", "total_score": "Score Médio"},
                title="Quais produtos têm deals mais quentes?",
            )
            st.plotly_chart(fig_prod, use_container_width=True)

    # Scatter: valor × score
    if "close_value" in filtered.columns:
        st.subheader("Valor do Deal × Score (matriz de prioridade)")
        scatter_df = filtered[filtered["close_value"] > 0].copy() if "close_value" in filtered.columns else filtered.copy()
        hover_cols = [c for c in ["sales_agent", "account", "deal_stage", "product"] if c in scatter_df.columns]

        fig_scatter = px.scatter(
            scatter_df,
            x="total_score",
            y="close_value",
            color="deal_stage" if "deal_stage" in scatter_df.columns else None,
            hover_data=hover_cols,
            labels={"total_score": "Score", "close_value": "Valor do Deal (R$)"},
            title="Quadrante ideal: alto score + alto valor = foco máximo",
            opacity=0.7,
        )
        fig_scatter.add_vline(x=60, line_dash="dot", line_color="gray",
                              annotation_text="Score 60")
        st.plotly_chart(fig_scatter, use_container_width=True)

# ===========================================================================
# TAB 3 — Detalhe do Deal
# ===========================================================================

with tab_detail:
    st.subheader("Análise de um Deal Específico")
    st.markdown("Escolha um deal para ver exatamente **por que** ele tem esse score.")

    if "opportunity_id" in filtered.columns:
        deal_ids = filtered["opportunity_id"].tolist()
        selected_id = st.selectbox("Selecione o Deal ID", deal_ids)

        if selected_id:
            row = filtered[filtered["opportunity_id"] == selected_id].iloc[0]

            col1, col2, col3 = st.columns([1, 1, 2])
            with col1:
                score_val = float(row["total_score"])
                st.metric("Score Total", f"{score_val:.1f} / 100")
                if score_val >= 70:
                    st.success("🔴 Deal QUENTE — priorize agora!")
                elif score_val >= 50:
                    st.warning("🟠 Deal MORNO — fique de olho")
                else:
                    st.info("🔵 Deal FRIO — foco em outros primeiro")

            with col2:
                st.markdown("**Informações do Deal**")
                info = {
                    "Stage": row.get("deal_stage", "—"),
                    "Vendedor": row.get("sales_agent", "—"),
                    "Conta": row.get("account", "—"),
                    "Produto": row.get("product", "—"),
                    "Valor": f"R$ {row.get('close_value', 0):,.0f}" if row.get("close_value", 0) > 0 else "—",
                    "Manager": row.get("manager", "—"),
                    "Região": row.get("regional_office", "—"),
                }
                for k, v in info.items():
                    st.markdown(f"**{k}:** {v}")

            with col3:
                st.markdown("**Detalhamento do Score**")
                factor_data = {
                    "Fator": ["Stage", "Valor", "Velocidade", "Conta", "Agente"],
                    "Pontos": [
                        row.get("score_stage", 0),
                        row.get("score_value", 0),
                        row.get("score_velocity", 0),
                        row.get("score_account", 0),
                        row.get("score_agent", 0),
                    ],
                    "Máximo": [25, 20, 20, 20, 15],
                }
                factor_df = pd.DataFrame(factor_data)
                factor_df["% do Máximo"] = (factor_df["Pontos"] / factor_df["Máximo"] * 100).round(1)

                fig_detail = go.Figure(go.Bar(
                    x=factor_df["Pontos"],
                    y=factor_df["Fator"],
                    orientation="h",
                    marker_color=[
                        "#2ecc71" if p / m >= 0.7 else "#e67e22" if p / m >= 0.4 else "#e74c3c"
                        for p, m in zip(factor_df["Pontos"], factor_df["Máximo"])
                    ],
                    text=[f"{p:.1f}/{m}" for p, m in zip(factor_df["Pontos"], factor_df["Máximo"])],
                    textposition="outside",
                ))
                fig_detail.update_layout(
                    xaxis=dict(range=[0, 30], title="Pontos"),
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=0, r=0, t=10, b=0),
                    height=250,
                )
                st.plotly_chart(fig_detail, use_container_width=True)

            # Explicações
            st.markdown("**Por que este score?**")
            explanations = str(row.get("explanations", "")).split(" | ")
            for exp in explanations:
                if exp.strip():
                    st.markdown(f"- {exp.strip()}")

            # Recomendação de ação
            st.markdown("---")
            st.markdown("**Recomendação de Ação**")
            score_val = float(row["total_score"])
            stage = str(row.get("deal_stage", ""))
            vel_score = float(row.get("score_velocity", 0))

            if score_val >= 70:
                st.success("✅ **Prioridade máxima** — ligue hoje, agende reunião de fechamento.")
            elif score_val >= 50:
                if vel_score < 8:
                    st.warning("⚠️ **Atenção à velocidade** — deal está demorando. Crie urgência ou requalifique.")
                else:
                    st.info("📌 **Nutra com conteúdo** — está próximo do quente. Um push pode fechar.")
            else:
                st.info("💤 **Baixa prioridade** — deixe em automação ou requalifique em 30 dias.")
