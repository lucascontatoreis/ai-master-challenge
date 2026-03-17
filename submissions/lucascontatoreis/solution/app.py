"""
Lead Scorer — Dashboard para Vendedores
Challenge 003 · G4 AI Master

Rode com:
    streamlit run app.py
"""

from __future__ import annotations

import io
from collections import Counter

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from scorer import LeadScorer, score_to_win_prob
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
# Helpers de threshold percentual
# ---------------------------------------------------------------------------

def compute_thresholds(scores: pd.Series) -> tuple[float, float]:
    """
    Retorna (hot_threshold, warm_threshold) baseado na distribuição real.
    Hot  = top 15% do pipeline  (P85)
    Warm = P60 – P85
    Cold = abaixo de P60

    Isso garante que sempre ~15% dos deals sejam "quentes",
    independente da escala absoluta dos scores.
    """
    if scores.empty:
        return 70.0, 50.0
    return float(scores.quantile(0.85)), float(scores.quantile(0.60))


def tier_label(score: float, hot: float, warm: float) -> str:
    if score >= hot:
        return "🔴 QUENTE"
    if score >= warm:
        return "🟠 MORNO"
    return "🔵 FRIO"


def tier_color(score: float, hot: float, warm: float) -> str:
    if score >= hot:
        return "#e74c3c"
    if score >= warm:
        return "#e67e22"
    return "#3498db"


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
        def read(b, fallback_fn):
            return pd.read_csv(io.BytesIO(b)) if b else fallback_fn()

        from sample_data import (
            generate_accounts, generate_products,
            generate_sales_teams, generate_pipeline,
        )
        accounts = read(accounts_bytes, generate_accounts)
        products = read(products_bytes, generate_products)
        teams    = read(teams_bytes, generate_sales_teams)
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
        teams_file    = st.file_uploader("sales_teams.csv", type="csv")

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
    agents   = sorted(scored_df["sales_agent"].dropna().unique())    if "sales_agent"      in scored_df.columns else []
    managers = sorted(scored_df["manager"].dropna().unique())        if "manager"          in scored_df.columns else []
    regions  = sorted(scored_df["regional_office"].dropna().unique()) if "regional_office" in scored_df.columns else []
    stages   = sorted(scored_df["deal_stage"].dropna().unique())     if "deal_stage"       in scored_df.columns else []
    prods    = sorted(scored_df["product"].dropna().unique())        if "product"          in scored_df.columns else []

    selected_manager = st.multiselect("Manager",  managers, placeholder="Todos")
    selected_agent   = st.multiselect("Vendedor", agents,   placeholder="Todos")
    selected_region  = st.multiselect("Região",   regions,  placeholder="Todas")
    selected_stage   = st.multiselect(
        "Stage", stages, placeholder="Todos",
        default=["Engaging", "Prospecting"] if "Engaging" in stages else [],
    )
    selected_product = st.multiselect("Produto", prods, placeholder="Todos")
    min_score        = st.slider("Score mínimo", 0, 100, 0)
    only_flagged     = st.checkbox("Apenas deals com alertas ⚠️")

    st.divider()
    st.caption(
        "Scoring: stage 25pt · potencial 20pt\n"
        "velocidade 20pt · conta 20pt · agente 15pt\n\n"
        "Thresholds: percentil 85 (quente) / 60 (morno)"
    )

# ---------------------------------------------------------------------------
# Aplica filtros
# ---------------------------------------------------------------------------

filtered = scored_df.copy()
if selected_manager and "manager"          in filtered.columns: filtered = filtered[filtered["manager"].isin(selected_manager)]
if selected_agent   and "sales_agent"      in filtered.columns: filtered = filtered[filtered["sales_agent"].isin(selected_agent)]
if selected_region  and "regional_office"  in filtered.columns: filtered = filtered[filtered["regional_office"].isin(selected_region)]
if selected_stage   and "deal_stage"       in filtered.columns: filtered = filtered[filtered["deal_stage"].isin(selected_stage)]
if selected_product and "product"          in filtered.columns: filtered = filtered[filtered["product"].isin(selected_product)]
filtered = filtered[filtered["total_score"] >= min_score]
if only_flagged and "risk_flags" in filtered.columns:
    filtered = filtered[filtered["risk_flags"].str.len() > 0]

# Thresholds baseados na distribuição filtrada
HOT_THR, WARM_THR = compute_thresholds(filtered["total_score"])

# ---------------------------------------------------------------------------
# Header + KPIs
# ---------------------------------------------------------------------------

st.title("🎯 Lead Scorer — Pipeline Priorizado")

col1, col2, col3, col4, col5 = st.columns(5)
hot_count    = (filtered["total_score"] >= HOT_THR).sum()
warm_count   = ((filtered["total_score"] >= WARM_THR) & (filtered["total_score"] < HOT_THR)).sum()
cold_count   = (filtered["total_score"] < WARM_THR).sum()
flagged_count = (filtered["risk_flags"].str.len() > 0).sum() if "risk_flags" in filtered.columns else 0

with col1:
    st.metric(f"🔴 Quentes (≥P85 = {HOT_THR:.0f})", hot_count)
with col2:
    st.metric(f"🟠 Mornos (P60–P85)", warm_count)
with col3:
    st.metric(f"🔵 Frios (<P60 = {WARM_THR:.0f})", cold_count)
with col4:
    st.metric("⚠️ Com Alertas", flagged_count)
with col5:
    if "close_value" in filtered.columns:
        hot_value = filtered[filtered["total_score"] >= HOT_THR]["close_value"].sum()
        st.metric("💰 Valor em Quentes", f"R$ {hot_value:,.0f}")

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_pipeline, tab_focus, tab_cleanup, tab_manager, tab_charts, tab_detail = st.tabs([
    "📋 Pipeline",
    "⚡ Meu Foco (Top 10)",
    "🗑️ Pipeline Cleanup",
    "👔 Manager",
    "📊 Análises",
    "🔎 Detalhe do Deal",
])

# ===========================================================================
# TAB 1 — Pipeline completo
# ===========================================================================

with tab_pipeline:
    st.subheader(f"Pipeline Priorizado — {len(filtered):,} deals")
    st.caption(f"Thresholds automáticos: 🔴 ≥{HOT_THR:.0f} · 🟠 {WARM_THR:.0f}–{HOT_THR:.0f} · 🔵 <{WARM_THR:.0f}")

    DISPLAY_COLS = [
        "opportunity_id", "sales_agent", "account", "product", "deal_stage",
        "close_value", "total_score", "win_probability",
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
        "total_score": "Score", "win_probability": "P(win)",
        "score_stage": "Pts Stage", "score_potential": "Pts Potencial",
        "score_velocity": "Pts Velocidade", "score_account": "Pts Conta",
        "score_agent": "Pts Agente", "risk_flags": "Alertas", "explanations": "Explicação",
    }
    display_df = display_df.rename(columns=RENAME)

    if "Valor (R$)" in display_df.columns:
        display_df["Valor (R$)"] = display_df["Valor (R$)"].apply(
            lambda x: f"R$ {x:,.0f}" if pd.notna(x) and float(x) > 0 else "—"
        )
    if "P(win)" in display_df.columns:
        display_df["P(win)"] = display_df["P(win)"].apply(
            lambda x: f"{float(x)*100:.0f}%" if pd.notna(x) else "—"
        )

    def _hl_score(val):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return ""
        if v >= HOT_THR:
            return "background-color:#fde8e8;color:#c0392b;font-weight:700"
        if v >= WARM_THR:
            return "background-color:#fef3e2;color:#d35400;font-weight:600"
        return "background-color:#ebf5fb;color:#2980b9"

    num_fmt = {k: "{:.1f}" for k in ["Score", "Pts Stage", "Pts Potencial",
                                       "Pts Velocidade", "Pts Conta", "Pts Agente"]
               if k in display_df.columns}

    st.dataframe(
        display_df.style.applymap(_hl_score, subset=["Score"]).format(num_fmt, na_rep="—"),
        use_container_width=True, height=520,
    )

    csv_out = filtered[avail].to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Exportar CSV", data=csv_out,
                       file_name="pipeline_priorizado.csv", mime="text/csv")

# ===========================================================================
# TAB 2 — Meu Foco
# ===========================================================================

with tab_focus:
    st.subheader("⚡ Meu Foco — Segunda-feira de Manhã")
    st.markdown("Selecione seu nome. **Foque nestas 10 oportunidades esta semana.**")

    if agents:
        my_agent = st.selectbox("Sou o vendedor:", ["— selecione —"] + list(agents))

        if my_agent != "— selecione —" and "sales_agent" in filtered.columns:
            my_deals = (
                filtered[filtered["sales_agent"] == my_agent]
                .sort_values("total_score", ascending=False)
                .head(10)
                .reset_index(drop=True)
            )
            my_deals.index += 1

            if my_deals.empty:
                st.info("Nenhum deal ativo para este vendedor com os filtros atuais.")
            else:
                for i, (_, row) in enumerate(my_deals.iterrows(), 1):
                    score    = float(row["total_score"])
                    win_prob = float(row.get("win_probability", score_to_win_prob(score)))
                    color    = tier_color(score, HOT_THR, WARM_THR)
                    label    = tier_label(score, HOT_THR, WARM_THR)
                    flags    = str(row.get("risk_flags", ""))

                    deal_id = row.get("opportunity_id", "—")
                    account = row.get("account", "—")
                    product = row.get("product", "—")
                    stage   = row.get("deal_stage", "—")
                    value   = row.get("close_value", 0)
                    value_str = f"R$ {float(value):,.0f}" if pd.notna(value) and float(value) > 0 else "sem valor"

                    with st.expander(
                        f"{label.split()[0]} #{i} — {deal_id} | {account} | "
                        f"Score {score:.0f} · P(win) {win_prob*100:.0f}%",
                        expanded=(i <= 3),
                    ):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.markdown(f"**Produto:** {product}")
                            st.markdown(f"**Stage:** {stage}")
                            st.markdown(f"**Valor:** {value_str}")
                            st.markdown(f"**Probabilidade de fechar:** **{win_prob*100:.0f}%**")
                        with c2:
                            fig_mini = go.Figure(go.Bar(
                                x=[score], y=["Score"], orientation="h",
                                marker_color=color,
                                text=[f"{score:.0f}/100"],
                                textposition="outside",
                            ))
                            fig_mini.update_layout(
                                xaxis=dict(range=[0, 100]),
                                margin=dict(l=0, r=40, t=0, b=0),
                                height=60, showlegend=False,
                            )
                            st.plotly_chart(fig_mini, use_container_width=True)

                        st.markdown("**Por que este score:**")
                        for exp in str(row.get("explanations", "")).split(" | "):
                            if exp.strip():
                                st.markdown(f"  - {exp.strip()}")

                        if flags:
                            st.warning(f"**Alertas:** {flags}")

                        st.markdown("---")
                        if score >= HOT_THR:
                            st.success("✅ **Ação:** Ligue hoje. Agende reunião de fechamento esta semana.")
                        elif score >= WARM_THR:
                            vel = float(row.get("score_velocity", 10))
                            if vel < 7:
                                st.warning("⚠️ **Ação:** Deal esfriando — crie urgência ou requalifique.")
                            else:
                                st.info("📌 **Ação:** Um push pode fechar. Envie proposta ou case de sucesso.")
                        else:
                            st.info("💤 **Ação:** Baixa prioridade. Retome em 30 dias ou coloque em nurture.")

# ===========================================================================
# TAB 3 — Pipeline Cleanup
# ===========================================================================

with tab_cleanup:
    st.subheader("🗑️ Pipeline Cleanup — O que descartar ou arquivar")
    st.markdown(
        "Deals que consomem energia sem perspectiva real de fechar. "
        "**Pergunte: vale continuar investindo tempo aqui?**"
    )

    if "risk_flags" in filtered.columns and "engage_date" in filtered.columns:
        today = pd.Timestamp.today().normalize()
        filt  = filtered.copy()

        # Critérios de descarte (qualquer um dos abaixo)
        filt["days_engaged"] = (
            pd.to_datetime(filt["engage_date"], errors="coerce")
            .apply(lambda d: (today - d).days if pd.notna(d) else 0)
        )

        cold_score   = filt["total_score"] < WARM_THR
        stagnant     = filt["days_engaged"] > 90
        no_value     = filt["close_value"].fillna(0) == 0 if "close_value" in filt.columns else pd.Series(False, index=filt.index)
        overdue      = filt["risk_flags"].str.contains("📅", na=False)

        # Três categorias de cleanup
        zombie = filt[cold_score & stagnant].copy()
        zombie["cleanup_reason"] = "🧟 Zombie — score baixo + parado >90d"

        unqualified = filt[cold_score & no_value & ~stagnant].copy()
        unqualified["cleanup_reason"] = "❓ Não qualificado — score baixo + sem valor"

        overdue_df = filt[overdue & cold_score].copy()
        overdue_df["cleanup_reason"] = "📅 Overdue — data de fechamento vencida + score baixo"

        cleanup_df = (
            pd.concat([zombie, unqualified, overdue_df])
            .drop_duplicates(subset=["opportunity_id"])
            .sort_values("total_score")
        )

        st.info(
            f"**{len(cleanup_df):,} deals candidatos a descarte** "
            f"({len(cleanup_df)/len(filtered)*100:.1f}% do pipeline filtrado). "
            f"Recuperar o tempo gasto neles libera foco para os {hot_count} deals quentes."
        )

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("🧟 Zombies", len(zombie))
            st.caption("Score baixo + parado >90 dias")
        with c2:
            st.metric("❓ Não qualificados", len(unqualified))
            st.caption("Score baixo + sem close_value")
        with c3:
            st.metric("📅 Overdue", len(overdue_df))
            st.caption("Data de fechamento vencida")

        st.divider()

        CLEANUP_COLS = [c for c in [
            "cleanup_reason", "opportunity_id", "sales_agent", "account",
            "product", "deal_stage", "close_value", "total_score",
            "win_probability", "days_engaged", "risk_flags",
        ] if c in cleanup_df.columns]

        cleanup_show = cleanup_df[CLEANUP_COLS].copy().reset_index(drop=True)
        cleanup_show.index += 1
        cleanup_show.index.name = "Rank"

        CLEANUP_RENAME = {
            "cleanup_reason": "Motivo", "opportunity_id": "Deal ID",
            "sales_agent": "Vendedor", "account": "Conta",
            "product": "Produto", "deal_stage": "Stage",
            "close_value": "Valor (R$)", "total_score": "Score",
            "win_probability": "P(win)", "days_engaged": "Dias Parado",
            "risk_flags": "Alertas",
        }
        cleanup_show = cleanup_show.rename(columns=CLEANUP_RENAME)

        if "Valor (R$)" in cleanup_show.columns:
            cleanup_show["Valor (R$)"] = cleanup_show["Valor (R$)"].apply(
                lambda x: f"R$ {x:,.0f}" if pd.notna(x) and float(x) > 0 else "—"
            )
        if "P(win)" in cleanup_show.columns:
            cleanup_show["P(win)"] = cleanup_show["P(win)"].apply(
                lambda x: f"{float(x)*100:.0f}%" if pd.notna(x) else "—"
            )

        st.dataframe(
            cleanup_show.style
            .applymap(lambda _: "background-color:#fdf2f8", subset=["Score"])
            .format({"Score": "{:.1f}"}, na_rep="—"),
            use_container_width=True, height=460,
        )

        csv_cleanup = cleanup_df[CLEANUP_COLS].to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Exportar lista de descarte",
            data=csv_cleanup,
            file_name="pipeline_cleanup.csv",
            mime="text/csv",
        )

        st.markdown(
            "**Como usar esta lista:**\n"
            "1. Converse com o vendedor sobre cada deal\n"
            "2. Se não há resposta há >3 semanas → mover para Lost\n"
            "3. Se sem valor após 60d → requalificar ou perder\n"
            "4. Pipeline limpo = forecast mais preciso"
        )
    else:
        st.info("Dados insuficientes para análise de cleanup.")

# ===========================================================================
# TAB 4 — Manager
# ===========================================================================

with tab_manager:
    st.subheader("👔 Saúde do Pipeline por Manager / Região")

    if "manager" in filtered.columns:
        col_a, col_b = st.columns(2)

        with col_a:
            heatmap_data = (
                filtered.groupby(["manager", "deal_stage"])["total_score"]
                .mean().reset_index()
                .pivot(index="manager", columns="deal_stage", values="total_score")
                .fillna(0)
            )
            fig_heat = px.imshow(
                heatmap_data, color_continuous_scale="RdYlGn",
                title="Score médio por Manager × Stage",
                labels={"color": "Score Médio"}, aspect="auto",
            )
            st.plotly_chart(fig_heat, use_container_width=True)

        with col_b:
            manager_summary = (
                filtered.groupby("manager").agg(
                    deals=("total_score", "count"),
                    score_medio=("total_score", "mean"),
                    quentes=("total_score", lambda x: (x >= HOT_THR).sum()),
                    prob_media=("win_probability", "mean") if "win_probability" in filtered.columns else ("total_score", "count"),
                    valor_total=("close_value", "sum"),
                ).sort_values("score_medio", ascending=False).reset_index()
            )
            manager_summary["valor_total"]  = manager_summary["valor_total"].apply(lambda x: f"R$ {x:,.0f}")
            manager_summary["prob_media"]   = manager_summary["prob_media"].apply(lambda x: f"{x*100:.0f}%" if x <= 1 else f"{x:.0f}")
            manager_summary.columns = ["Manager", "Deals Ativos", "Score Médio", "Quentes", "P(win) Média", "Valor Total"]

            st.dataframe(
                manager_summary.style
                .applymap(
                    lambda v: "background-color:#d5f5e3" if isinstance(v, float) and v >= 60
                    else "background-color:#fef9e7" if isinstance(v, float) and v >= 45
                    else "",
                    subset=["Score Médio"],
                ).format({"Score Médio": "{:.1f}"}, na_rep="—"),
                use_container_width=True, height=300,
            )

        if "sales_agent" in filtered.columns:
            agent_summary = (
                filtered.groupby(["sales_agent", "manager"]).agg(
                    deals=("total_score", "count"),
                    score_medio=("total_score", "mean"),
                    quentes=("total_score", lambda x: (x >= HOT_THR).sum()),
                ).reset_index()
            )
            fig_bubble = px.scatter(
                agent_summary, x="score_medio", y="deals",
                size="quentes", color="manager",
                hover_name="sales_agent",
                labels={"score_medio": "Score Médio", "deals": "Deals Ativos", "quentes": "Deals Quentes"},
                title="Vendedores: volume × qualidade (tamanho = deals quentes)",
                size_max=40,
            )
            fig_bubble.add_vline(x=filtered["total_score"].median(), line_dash="dot",
                                  line_color="gray", annotation_text="Mediana")
            st.plotly_chart(fig_bubble, use_container_width=True)
    else:
        st.info("Dados de manager não disponíveis.")

# ===========================================================================
# TAB 5 — Análises
# ===========================================================================

with tab_charts:
    col_a, col_b = st.columns(2)

    with col_a:
        fig_hist = px.histogram(
            filtered, x="total_score", nbins=25,
            color_discrete_sequence=["#3498db"],
            labels={"total_score": "Score"},
            title="Distribuição de Scores",
        )
        fig_hist.add_vline(x=HOT_THR,  line_dash="dash", line_color="#e74c3c", annotation_text=f"Quente ({HOT_THR:.0f})")
        fig_hist.add_vline(x=WARM_THR, line_dash="dash", line_color="#e67e22", annotation_text=f"Morno ({WARM_THR:.0f})")
        st.plotly_chart(fig_hist, use_container_width=True)

    with col_b:
        # Win probability vs score scatter
        if "win_probability" in filtered.columns:
            sample = filtered.sample(min(500, len(filtered)), random_state=42)
            fig_wp = px.scatter(
                sample, x="total_score", y=sample["win_probability"] * 100,
                color="deal_stage" if "deal_stage" in sample.columns else None,
                labels={"total_score": "Score", "y": "P(win) %"},
                title="Score → Probabilidade de Fechar",
                opacity=0.5,
            )
            fig_wp.add_hline(y=50, line_dash="dot", line_color="gray", annotation_text="50%")
            st.plotly_chart(fig_wp, use_container_width=True)

    col_c, col_d = st.columns(2)

    with col_c:
        score_cols = ["score_stage", "score_potential", "score_velocity", "score_account", "score_agent"]
        max_pts    = {"score_stage": 25, "score_potential": 20, "score_velocity": 20, "score_account": 20, "score_agent": 15}
        labels_map = {"score_stage": "Stage", "score_potential": "Potencial",
                      "score_velocity": "Velocidade", "score_account": "Conta", "score_agent": "Agente"}
        avail_sc   = [c for c in score_cols if c in filtered.columns]
        means      = filtered[avail_sc].mean()
        pct_used   = [means[c] / max_pts[c] * 100 for c in avail_sc]

        fig_factors = px.bar(
            x=[labels_map[c] for c in avail_sc], y=pct_used,
            color=pct_used, color_continuous_scale="RdYlGn",
            range_y=[0, 100],
            labels={"x": "Fator", "y": "% do máximo"},
            title="Aproveitamento médio por fator",
        )
        st.plotly_chart(fig_factors, use_container_width=True)

    with col_d:
        if "risk_flags" in filtered.columns:
            all_flags = []
            for fs in filtered["risk_flags"].dropna():
                if fs:
                    all_flags.extend([f.strip() for f in fs.split("|") if f.strip()])
            if all_flags:
                fc = Counter(all_flags)
                flag_df = pd.DataFrame(fc.most_common(8), columns=["Alerta", "Qtd"])
                fig_flags = px.bar(
                    flag_df, x="Qtd", y="Alerta", orientation="h",
                    color="Qtd", color_continuous_scale="Reds",
                    title="Alertas mais frequentes",
                )
                st.plotly_chart(fig_flags, use_container_width=True)

    if "close_value" in filtered.columns:
        scatter_df = filtered[filtered["close_value"] > 0].copy()
        if not scatter_df.empty:
            hover = [c for c in ["sales_agent", "account", "deal_stage", "product", "win_probability"]
                     if c in scatter_df.columns]
            fig_quad = px.scatter(
                scatter_df, x="total_score", y="close_value",
                color="deal_stage" if "deal_stage" in scatter_df.columns else None,
                hover_data=hover, opacity=0.65,
                labels={"total_score": "Score", "close_value": "Valor (R$)"},
                title="Quadrante: alto score + alto valor = foco máximo",
            )
            fig_quad.add_vline(x=filtered["total_score"].median(), line_dash="dot", line_color="gray")
            st.plotly_chart(fig_quad, use_container_width=True)

# ===========================================================================
# TAB 6 — Detalhe do Deal
# ===========================================================================

with tab_detail:
    st.subheader("🔎 Análise Detalhada de um Deal")

    if "opportunity_id" in filtered.columns:
        selected_id = st.selectbox("Selecione o Deal ID", filtered["opportunity_id"].tolist())

        if selected_id:
            row      = filtered[filtered["opportunity_id"] == selected_id].iloc[0]
            score    = float(row["total_score"])
            win_prob = float(row.get("win_probability", score_to_win_prob(score)))
            flags    = str(row.get("risk_flags", ""))
            label    = tier_label(score, HOT_THR, WARM_THR)
            color    = tier_color(score, HOT_THR, WARM_THR)

            col_score, col_info, col_breakdown = st.columns([1, 1, 2])

            with col_score:
                st.metric("Score Total",         f"{score:.1f} / 100")
                st.metric("P(win) estimada",     f"{win_prob*100:.0f}%")
                if score >= HOT_THR:
                    st.success(f"{label} — priorize agora!")
                elif score >= WARM_THR:
                    st.warning(f"{label} — fique de olho")
                else:
                    st.info(f"{label} — foco em outros primeiro")

                if flags:
                    st.markdown("**Alertas:**")
                    for flag in flags.split("|"):
                        if flag.strip():
                            st.warning(flag.strip())

            with col_info:
                st.markdown("**Dados do Deal**")
                for lbl, key in [
                    ("Stage", "deal_stage"), ("Vendedor", "sales_agent"),
                    ("Conta", "account"), ("Produto", "product"),
                    ("Série", "series"), ("Manager", "manager"),
                    ("Região", "regional_office"),
                ]:
                    val = row.get(key, "—")
                    if pd.notna(val) and str(val).strip():
                        st.markdown(f"**{lbl}:** {val}")

                cv = row.get("close_value", 0)
                cv_str = f"R$ {float(cv):,.0f}" if pd.notna(cv) and float(cv) > 0 else "Não confirmado"
                st.markdown(f"**Valor:** {cv_str}")

                sp = row.get("sales_price", None)
                if pd.notna(sp) and float(sp) > 0:
                    st.markdown(f"**Preço tabela:** R$ {float(sp):,.0f}")

            with col_breakdown:
                st.markdown("**Detalhamento do Score**")
                factor_data = {
                    "Fator":   ["Stage", "Potencial", "Velocidade", "Conta", "Agente"],
                    "Pontos":  [row.get(c, 0) for c in ["score_stage", "score_potential",
                                                          "score_velocity", "score_account", "score_agent"]],
                    "Máximo":  [25, 20, 20, 20, 15],
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

            st.markdown("**Por que este score?**")
            for exp in str(row.get("explanations", "")).split(" | "):
                if exp.strip():
                    st.markdown(f"- {exp.strip()}")

            st.markdown("---")
            st.markdown("**Ação recomendada**")
            vel = float(row.get("score_velocity", 10))
            if score >= HOT_THR:
                st.success("✅ Ligue hoje. Agende fechamento. Este deal está pronto.")
            elif score >= WARM_THR:
                if vel < 7:
                    st.warning("⚠️ Deal esfriando. Crie urgência: desconto por prazo, case de sucesso.")
                else:
                    st.info("📌 Envie proposta formal. Está próximo do quente.")
            else:
                st.info("💤 Coloque em nurture e reveja em 30 dias.")
