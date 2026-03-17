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

SCORE_HOT = 70
SCORE_WARM = 50

# ---------------------------------------------------------------------------
# Carregamento e scoring
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Calculando scores do pipeline...")
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
            return pd.read_csv(io.BytesIO(b)) if b else fallback_fn()

        from sample_data import (
            generate_accounts, generate_products,
            generate_sales_teams, generate_pipeline,
        )
        accounts = read(accounts_bytes, generate_accounts)
        products = read(products_bytes, generate_products)
        teams = read(teams_bytes, generate_sales_teams)
        pipeline = read(pipeline_bytes, lambda: generate_pipeline(accounts, products, teams))

    scorer = LeadScorer(pipeline, accounts, products, teams)
    return scorer.score_all()


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🎯 Lead Scorer")
    st.markdown("**Challenge 003 — G4 AI Master**")
    st.divider()

    st.subheader("📂 Dados")
    use_sample = st.toggle("Usar dados de demonstração", value=True)

    pipeline_file = accounts_file = products_file = teams_file = None
    if not use_sample:
        pipeline_file = st.file_uploader("sales_pipeline.csv", type="csv")
        accounts_file = st.file_uploader("accounts.csv", type="csv")
        products_file = st.file_uploader("products.csv", type="csv")
        teams_file = st.file_uploader("sales_teams.csv", type="csv")

    st.divider()
    st.subheader("🔍 Filtros")


def _bytes(f) -> bytes | None:
    return f.read() if f else None


scored_df = load_and_score(
    _bytes(pipeline_file), _bytes(accounts_file),
    _bytes(products_file), _bytes(teams_file),
)

if scored_df.empty:
    st.error("Nenhum deal ativo encontrado.")
    st.stop()

# ---------------------------------------------------------------------------
# Filtros na sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    agents = sorted(scored_df["sales_agent"].dropna().unique()) if "sales_agent" in scored_df.columns else []
    managers = sorted(scored_df["manager"].dropna().unique()) if "manager" in scored_df.columns else []
    regions = sorted(scored_df["regional_office"].dropna().unique()) if "regional_office" in scored_df.columns else []
    stages = sorted(scored_df["deal_stage"].dropna().unique()) if "deal_stage" in scored_df.columns else []
    products_list = sorted(scored_df["product"].dropna().unique()) if "product" in scored_df.columns else []

    selected_manager = st.multiselect("Manager", managers, placeholder="Todos os managers")
    selected_agent = st.multiselect("Vendedor", agents, placeholder="Todos os vendedores")
    selected_region = st.multiselect("Região", regions, placeholder="Todas as regiões")
    selected_stage = st.multiselect(
        "Stage", stages, placeholder="Todos os stages",
        default=["Engaging", "Prospecting"] if "Engaging" in stages else [],
    )
    selected_product = st.multiselect("Produto", products_list, placeholder="Todos os produtos")
    min_score = st.slider("Score mínimo", 0, 100, 0)
    only_flagged = st.checkbox("Apenas deals com alertas ⚠️")

    st.divider()
    st.caption(
        "Scoring: stage 25pt · potencial 20pt\n"
        "velocidade+urgência 20pt · conta 20pt · agente 15pt"
    )

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
if only_flagged and "risk_flags" in filtered.columns:
    filtered = filtered[filtered["risk_flags"].str.len() > 0]

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------

st.title("🎯 Lead Scorer — Pipeline Priorizado")

col1, col2, col3, col4, col5 = st.columns(5)
hot_count = (filtered["total_score"] >= SCORE_HOT).sum()
warm_count = ((filtered["total_score"] >= SCORE_WARM) & (filtered["total_score"] < SCORE_HOT)).sum()
cold_count = (filtered["total_score"] < SCORE_WARM).sum()
flagged_count = (filtered["risk_flags"].str.len() > 0).sum() if "risk_flags" in filtered.columns else 0

with col1:
    st.metric("🔴 Quentes (≥70)", hot_count)
with col2:
    st.metric("🟠 Mornos (50–69)", warm_count)
with col3:
    st.metric("🔵 Frios (<50)", cold_count)
with col4:
    st.metric("⚠️ Com Alertas", flagged_count)
with col5:
    if "close_value" in filtered.columns:
        hot_warm_value = filtered[filtered["total_score"] >= SCORE_WARM]["close_value"].sum()
        st.metric("💰 Valor em Jogo", f"R$ {hot_warm_value:,.0f}")
    else:
        st.metric("Total", len(filtered))

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_pipeline, tab_focus, tab_manager, tab_charts, tab_detail = st.tabs([
    "📋 Pipeline Completo",
    "⚡ Meu Foco (Top 10)",
    "👔 Visão do Manager",
    "📊 Análises",
    "🔎 Detalhe do Deal",
])

# ===========================================================================
# TAB 1 — Pipeline completo
# ===========================================================================

with tab_pipeline:
    st.subheader(f"Pipeline Priorizado — {len(filtered):,} deals ativos")
    st.caption("Ordenado por score. Vermelho = foco imediato.")

    DISPLAY_COLS = [
        "opportunity_id", "sales_agent", "account", "product", "deal_stage",
        "close_value", "total_score",
        "score_stage", "score_potential", "score_velocity", "score_account", "score_agent",
        "risk_flags", "explanations",
    ]
    avail = [c for c in DISPLAY_COLS if c in filtered.columns]
    display_df = filtered[avail].copy().reset_index(drop=True)
    display_df.index += 1
    display_df.index.name = "Rank"

    RENAME = {
        "opportunity_id": "Deal ID", "sales_agent": "Vendedor", "account": "Conta",
        "product": "Produto", "deal_stage": "Stage", "close_value": "Valor (R$)",
        "total_score": "Score", "score_stage": "Pts Stage",
        "score_potential": "Pts Potencial", "score_velocity": "Pts Velocidade",
        "score_account": "Pts Conta", "score_agent": "Pts Agente",
        "risk_flags": "Alertas", "explanations": "Explicação",
    }
    display_df = display_df.rename(columns=RENAME)

    if "Valor (R$)" in display_df.columns:
        display_df["Valor (R$)"] = display_df["Valor (R$)"].apply(
            lambda x: f"R$ {x:,.0f}" if pd.notna(x) and float(x) > 0 else "—"
        )

    def _hl_score(val):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return ""
        if v >= SCORE_HOT:
            return "background-color:#fde8e8;color:#c0392b;font-weight:700"
        elif v >= SCORE_WARM:
            return "background-color:#fef3e2;color:#d35400;font-weight:600"
        return "background-color:#ebf5fb;color:#2980b9"

    fmt_cols = {k: "{:.1f}" for k in ["Score", "Pts Stage", "Pts Potencial",
                                        "Pts Velocidade", "Pts Conta", "Pts Agente"]
                if k in display_df.columns}

    styled = (
        display_df.style
        .applymap(_hl_score, subset=["Score"])
        .format(fmt_cols, na_rep="—")
    )
    st.dataframe(styled, use_container_width=True, height=520)

    csv_out = filtered[avail].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv_out,
                       file_name="pipeline_priorizado.csv", mime="text/csv")

# ===========================================================================
# TAB 2 — Meu Foco (Top 10)
# ===========================================================================

with tab_focus:
    st.subheader("⚡ Meu Foco — Segunda-feira de Manhã")
    st.markdown(
        "Selecione seu nome para ver sua lista de prioridades. "
        "**Foque nestas 10 oportunidades esta semana.**"
    )

    if agents:
        selected_my_agent = st.selectbox("Sou o vendedor:", ["— selecione —"] + list(agents))

        if selected_my_agent != "— selecione —" and "sales_agent" in filtered.columns:
            my_deals = (
                filtered[filtered["sales_agent"] == selected_my_agent]
                .sort_values("total_score", ascending=False)
                .head(10)
                .reset_index(drop=True)
            )
            my_deals.index += 1
            my_deals.index.name = "Prioridade"

            if my_deals.empty:
                st.info("Nenhum deal ativo para este vendedor com os filtros atuais.")
            else:
                for i, (_, row) in enumerate(my_deals.iterrows(), 1):
                    score = float(row["total_score"])
                    if score >= SCORE_HOT:
                        color = "🔴"
                        label = "QUENTE"
                        border = "#e74c3c"
                    elif score >= SCORE_WARM:
                        color = "🟠"
                        label = "MORNO"
                        border = "#e67e22"
                    else:
                        color = "🔵"
                        label = "FRIO"
                        border = "#3498db"

                    deal_id = row.get("opportunity_id", "—")
                    account = row.get("account", "—")
                    product = row.get("product", "—")
                    stage = row.get("deal_stage", "—")
                    value = row.get("close_value", 0)
                    flags = str(row.get("risk_flags", ""))

                    value_str = f"R$ {float(value):,.0f}" if pd.notna(value) and float(value) > 0 else "sem valor"

                    with st.expander(
                        f"{color} #{i} — {deal_id} | {account} | Score {score:.0f} {label}",
                        expanded=(i <= 3),
                    ):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**Produto:** {product}")
                            st.markdown(f"**Stage:** {stage}")
                            st.markdown(f"**Valor:** {value_str}")
                        with c2:
                            # Barra de score
                            fig_mini = go.Figure(go.Bar(
                                x=[score], y=["Score"],
                                orientation="h",
                                marker_color=border,
                                text=[f"{score:.0f}/100"],
                                textposition="outside",
                            ))
                            fig_mini.update_layout(
                                xaxis=dict(range=[0, 100]),
                                margin=dict(l=0, r=40, t=0, b=0),
                                height=60,
                                showlegend=False,
                            )
                            st.plotly_chart(fig_mini, use_container_width=True)

                        # Explicação
                        explanations = str(row.get("explanations", "")).split(" | ")
                        st.markdown("**Por que este score:**")
                        for exp in explanations:
                            if exp.strip():
                                st.markdown(f"  - {exp.strip()}")

                        if flags:
                            st.warning(f"**Alertas:** {flags}")

                        # Ação recomendada
                        st.markdown("---")
                        if score >= SCORE_HOT:
                            action = "✅ **Ação:** Ligue hoje. Agende reunião de fechamento esta semana."
                        elif score >= SCORE_WARM:
                            vel = float(row.get("score_velocity", 0))
                            if vel < 7:
                                action = "⚠️ **Ação:** Deal esfriando — crie urgência ou requalifique."
                            else:
                                action = "📌 **Ação:** Um push pode fechar. Envie proposta ou case de sucesso."
                        else:
                            action = "💤 **Ação:** Baixa prioridade agora. Retome em 30 dias ou coloque em nurture."
                        st.markdown(action)
    else:
        st.info("Nenhum vendedor identificado nos dados.")

# ===========================================================================
# TAB 3 — Visão do Manager
# ===========================================================================

with tab_manager:
    st.subheader("👔 Saúde do Pipeline por Manager / Região")

    if "manager" in filtered.columns and "regional_office" in filtered.columns:
        col_a, col_b = st.columns(2)

        with col_a:
            # Heatmap: manager × stage → score médio
            if not filtered.empty:
                heatmap_data = (
                    filtered.groupby(["manager", "deal_stage"])["total_score"]
                    .mean()
                    .reset_index()
                    .pivot(index="manager", columns="deal_stage", values="total_score")
                    .fillna(0)
                )
                fig_heat = px.imshow(
                    heatmap_data,
                    color_continuous_scale="RdYlGn",
                    title="Score médio por Manager × Stage",
                    labels={"color": "Score Médio"},
                    aspect="auto",
                )
                st.plotly_chart(fig_heat, use_container_width=True)

        with col_b:
            # Pipeline value por manager
            manager_summary = (
                filtered.groupby("manager")
                .agg(
                    deals=("total_score", "count"),
                    score_medio=("total_score", "mean"),
                    quentes=("total_score", lambda x: (x >= SCORE_HOT).sum()),
                    valor_total=("close_value", "sum"),
                )
                .sort_values("score_medio", ascending=False)
                .reset_index()
            )
            manager_summary["valor_total"] = manager_summary["valor_total"].apply(
                lambda x: f"R$ {x:,.0f}"
            )
            manager_summary.columns = [
                "Manager", "Deals Ativos", "Score Médio", "Quentes (≥70)", "Valor Total"
            ]

            def _hl_manager(val):
                try:
                    v = float(val)
                except (ValueError, TypeError):
                    return ""
                if v >= 60:
                    return "background-color:#d5f5e3"
                elif v >= 45:
                    return "background-color:#fef9e7"
                return "background-color:#fdf2f8"

            st.dataframe(
                manager_summary.style
                .applymap(_hl_manager, subset=["Score Médio"])
                .format({"Score Médio": "{:.1f}"}),
                use_container_width=True,
                height=300,
            )

        # Scatter: score médio × total de deals por agente
        if "sales_agent" in filtered.columns:
            agent_summary = (
                filtered.groupby(["sales_agent", "manager"])
                .agg(
                    deals=("total_score", "count"),
                    score_medio=("total_score", "mean"),
                    quentes=("total_score", lambda x: (x >= SCORE_HOT).sum()),
                )
                .reset_index()
            )
            fig_bubble = px.scatter(
                agent_summary,
                x="score_medio",
                y="deals",
                size="quentes",
                color="manager",
                hover_name="sales_agent",
                labels={
                    "score_medio": "Score Médio do Pipeline",
                    "deals": "Deals Ativos",
                    "quentes": "Deals Quentes",
                },
                title="Vendedores: volume × qualidade de pipeline (tamanho = deals quentes)",
                size_max=40,
            )
            fig_bubble.add_vline(x=60, line_dash="dot", line_color="gray",
                                  annotation_text="Score 60")
            st.plotly_chart(fig_bubble, use_container_width=True)
    else:
        st.info("Dados de manager/região não disponíveis.")

# ===========================================================================
# TAB 4 — Análises
# ===========================================================================

with tab_charts:
    col_a, col_b = st.columns(2)

    with col_a:
        fig_hist = px.histogram(
            filtered, x="total_score", nbins=20,
            color_discrete_sequence=["#3498db"],
            labels={"total_score": "Score"},
            title="Distribuição de Scores",
        )
        fig_hist.add_vline(x=SCORE_HOT, line_dash="dash", line_color="#e74c3c",
                           annotation_text="Quente (70)")
        fig_hist.add_vline(x=SCORE_WARM, line_dash="dash", line_color="#e67e22",
                           annotation_text="Morno (50)")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_b:
        score_cols = ["score_stage", "score_potential", "score_velocity", "score_account", "score_agent"]
        avail_scores = [c for c in score_cols if c in filtered.columns]
        if avail_scores:
            means = filtered[avail_scores].mean()
            max_pts = {"score_stage": 25, "score_potential": 20, "score_velocity": 20,
                       "score_account": 20, "score_agent": 15}
            labels = {"score_stage": "Stage", "score_potential": "Potencial",
                      "score_velocity": "Velocidade", "score_account": "Conta",
                      "score_agent": "Agente"}
            pct_used = [means[c] / max_pts[c] * 100 for c in avail_scores]
            fig_factors = px.bar(
                x=[labels[c] for c in avail_scores],
                y=pct_used,
                color=pct_used,
                color_continuous_scale="RdYlGn",
                range_y=[0, 100],
                labels={"x": "Fator", "y": "% do máximo atingido"},
                title="Aproveitamento médio por fator (100% = todos no máximo)",
            )
            st.plotly_chart(fig_factors, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        if "product" in filtered.columns and "series" in filtered.columns:
            prod_scores = (
                filtered.groupby(["product", "series"])["total_score"]
                .mean()
                .sort_values()
                .reset_index()
            )
            fig_prod = px.bar(
                prod_scores, x="total_score", y="product", color="series",
                orientation="h",
                labels={"product": "Produto", "total_score": "Score Médio", "series": "Série"},
                title="Score médio por Produto e Série",
            )
            st.plotly_chart(fig_prod, use_container_width=True)
        elif "product" in filtered.columns:
            prod_scores = (
                filtered.groupby("product")["total_score"]
                .mean().sort_values().reset_index()
            )
            fig_prod = px.bar(
                prod_scores, x="total_score", y="product", orientation="h",
                color="total_score", color_continuous_scale="Blues",
                labels={"product": "Produto", "total_score": "Score Médio"},
                title="Score médio por Produto",
            )
            st.plotly_chart(fig_prod, use_container_width=True)

    with col_d:
        if "risk_flags" in filtered.columns:
            # Frequência de cada tipo de alerta
            all_flags = []
            for flags_str in filtered["risk_flags"].dropna():
                if flags_str:
                    all_flags.extend([f.strip() for f in flags_str.split("|") if f.strip()])

            if all_flags:
                from collections import Counter
                flag_counts = Counter(all_flags)
                flag_df = pd.DataFrame(flag_counts.most_common(8), columns=["Alerta", "Qtd"])
                fig_flags = px.bar(
                    flag_df, x="Qtd", y="Alerta", orientation="h",
                    color="Qtd", color_continuous_scale="Reds",
                    title="Alertas mais frequentes no pipeline",
                )
                st.plotly_chart(fig_flags, use_container_width=True)
            else:
                st.info("Nenhum alerta identificado nos deals filtrados.")

    # Scatter valor × score
    if "close_value" in filtered.columns:
        scatter_df = filtered[filtered["close_value"] > 0].copy()
        if not scatter_df.empty:
            hover = [c for c in ["sales_agent", "account", "deal_stage", "product", "risk_flags"]
                     if c in scatter_df.columns]
            fig_scatter = px.scatter(
                scatter_df, x="total_score", y="close_value",
                color="deal_stage" if "deal_stage" in scatter_df.columns else None,
                hover_data=hover,
                labels={"total_score": "Score", "close_value": "Valor (R$)"},
                title="Quadrante de Prioridade: alto score + alto valor = foco máximo",
                opacity=0.65,
            )
            fig_scatter.add_vline(x=60, line_dash="dot", line_color="gray")
            st.plotly_chart(fig_scatter, use_container_width=True)

# ===========================================================================
# TAB 5 — Detalhe do Deal
# ===========================================================================

with tab_detail:
    st.subheader("🔎 Análise Detalhada de um Deal")

    if "opportunity_id" in filtered.columns:
        deal_ids = filtered["opportunity_id"].tolist()
        selected_id = st.selectbox("Selecione o Deal ID", deal_ids)

        if selected_id:
            row = filtered[filtered["opportunity_id"] == selected_id].iloc[0]
            score_val = float(row["total_score"])
            flags = str(row.get("risk_flags", ""))

            # Header com score e status
            col_score, col_info, col_breakdown = st.columns([1, 1, 2])

            with col_score:
                st.metric("Score Total", f"{score_val:.1f} / 100")
                if score_val >= SCORE_HOT:
                    st.success("🔴 QUENTE — priorize agora!")
                elif score_val >= SCORE_WARM:
                    st.warning("🟠 MORNO — fique de olho")
                else:
                    st.info("🔵 FRIO — foco em outros primeiro")

                if flags:
                    st.markdown("**Alertas:**")
                    for flag in flags.split("|"):
                        if flag.strip():
                            st.warning(flag.strip())

            with col_info:
                st.markdown("**Dados do Deal**")
                for label, key in [
                    ("Stage", "deal_stage"), ("Vendedor", "sales_agent"),
                    ("Conta", "account"), ("Produto", "product"),
                    ("Série", "series"), ("Manager", "manager"),
                    ("Região", "regional_office"),
                ]:
                    val = row.get(key, "—")
                    if pd.notna(val) and str(val).strip():
                        st.markdown(f"**{label}:** {val}")

                cv = row.get("close_value", 0)
                cv_str = f"R$ {float(cv):,.0f}" if pd.notna(cv) and float(cv) > 0 else "Não confirmado"
                st.markdown(f"**Valor:** {cv_str}")

                sp = row.get("sales_price", None)
                if pd.notna(sp) and float(sp) > 0:
                    st.markdown(f"**Preço tabela:** R$ {float(sp):,.0f}")

            with col_breakdown:
                st.markdown("**Detalhamento do Score**")
                factor_data = {
                    "Fator": ["Stage", "Potencial", "Velocidade", "Conta", "Agente"],
                    "Pontos": [
                        row.get("score_stage", 0), row.get("score_potential", 0),
                        row.get("score_velocity", 0), row.get("score_account", 0),
                        row.get("score_agent", 0),
                    ],
                    "Máximo": [25, 20, 20, 20, 15],
                }
                fdf = pd.DataFrame(factor_data)
                bar_colors = [
                    "#2ecc71" if p / m >= 0.7 else "#f39c12" if p / m >= 0.4 else "#e74c3c"
                    for p, m in zip(fdf["Pontos"], fdf["Máximo"])
                ]
                fig_detail = go.Figure(go.Bar(
                    x=fdf["Pontos"], y=fdf["Fator"], orientation="h",
                    marker_color=bar_colors,
                    text=[f"{p:.1f}/{m}" for p, m in zip(fdf["Pontos"], fdf["Máximo"])],
                    textposition="outside",
                ))
                fig_detail.update_layout(
                    xaxis=dict(range=[0, 28], title="Pontos"),
                    yaxis=dict(autorange="reversed"),
                    margin=dict(l=0, r=40, t=10, b=0),
                    height=260,
                )
                st.plotly_chart(fig_detail, use_container_width=True)

            # Por que este score
            st.markdown("**Por que este score?**")
            for exp in str(row.get("explanations", "")).split(" | "):
                if exp.strip():
                    st.markdown(f"- {exp.strip()}")

            # Ação recomendada
            st.markdown("---")
            st.markdown("**Ação recomendada para esta semana**")
            vel = float(row.get("score_velocity", 0))
            if score_val >= SCORE_HOT:
                st.success("✅ Ligue hoje. Agende reunião de fechamento. Este deal está pronto.")
            elif score_val >= SCORE_WARM:
                if vel < 7:
                    st.warning("⚠️ Deal esfriando. Crie urgência: desconto por prazo, case de sucesso, demo ao vivo.")
                else:
                    st.info("📌 Envie proposta formal ou próximo passo claro. Está próximo do quente.")
            else:
                st.info("💤 Não foque aqui agora. Coloque em sequência de nurture e reveja em 30 dias.")
