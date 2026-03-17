"""
Gera um relatório HTML standalone com o pipeline priorizado.
Aceita os CSVs reais como argumentos, ou usa dados sintéticos de demo.

Uso:
    python generate_report.py
    python generate_report.py --pipeline sales_pipeline.csv --accounts accounts.csv \
                               --products products.csv --teams sales_teams.csv
    python generate_report.py --output meu_relatorio.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from scorer import LeadScorer, score_to_win_prob
from sample_data import generate_all


# ---------------------------------------------------------------------------

def compute_thresholds(scores: pd.Series) -> tuple[float, float]:
    return float(scores.quantile(0.85)), float(scores.quantile(0.60))


def load_data(args) -> pd.DataFrame:
    if args.pipeline:
        pipeline = pd.read_csv(args.pipeline)
        accounts = pd.read_csv(args.accounts)
        products = pd.read_csv(args.products)
        teams    = pd.read_csv(args.teams)
    else:
        print("Nenhum CSV fornecido — usando dados sintéticos de demo.")
        pipeline, accounts, products, teams = generate_all()

    scorer = LeadScorer(pipeline, accounts, products, teams)
    return scorer.score_all()


def build_html(df: pd.DataFrame) -> str:
    hot_thr, warm_thr = compute_thresholds(df["total_score"])

    hot_count  = int((df["total_score"] >= hot_thr).sum())
    warm_count = int(((df["total_score"] >= warm_thr) & (df["total_score"] < hot_thr)).sum())
    cold_count = int((df["total_score"] < warm_thr).sum())
    flagged    = int((df["risk_flags"].str.len() > 0).sum()) if "risk_flags" in df.columns else 0

    hot_value = float(df[df["total_score"] >= hot_thr]["close_value"].sum()) \
        if "close_value" in df.columns else 0

    # ---- Gráfico 1: Distribuição de scores ----
    fig_hist = px.histogram(
        df, x="total_score", nbins=25,
        color_discrete_sequence=["#3498db"],
        title="Distribuição de Scores",
        labels={"total_score": "Score"},
    )
    fig_hist.add_vline(x=hot_thr,  line_dash="dash", line_color="#e74c3c",
                       annotation_text=f"Quente ({hot_thr:.0f})")
    fig_hist.add_vline(x=warm_thr, line_dash="dash", line_color="#e67e22",
                       annotation_text=f"Morno ({warm_thr:.0f})")
    fig_hist.update_layout(margin=dict(t=40, b=20))

    # ---- Gráfico 2: Aproveitamento por fator ----
    score_cols = ["score_stage", "score_potential", "score_velocity", "score_account", "score_agent"]
    max_pts    = {"score_stage": 25, "score_potential": 20, "score_velocity": 20,
                  "score_account": 20, "score_agent": 15}
    labels_map = {"score_stage": "Stage", "score_potential": "Potencial",
                  "score_velocity": "Velocidade", "score_account": "Conta", "score_agent": "Agente"}
    avail_sc   = [c for c in score_cols if c in df.columns]
    pct_used   = [df[c].mean() / max_pts[c] * 100 for c in avail_sc]

    fig_factors = px.bar(
        x=[labels_map[c] for c in avail_sc], y=pct_used,
        color=pct_used, color_continuous_scale="RdYlGn", range_y=[0, 100],
        title="Aproveitamento médio por fator (%)",
        labels={"x": "Fator", "y": "% do máximo"},
    )

    # ---- Gráfico 3: Pipeline Cleanup ----
    today = pd.Timestamp.today().normalize()
    df_c  = df.copy()
    df_c["days_engaged"] = (
        pd.to_datetime(df_c["engage_date"], errors="coerce")
        .apply(lambda d: (today - d).days if pd.notna(d) else 0)
    )
    zombies  = df_c[(df_c["total_score"] < warm_thr) & (df_c["days_engaged"] > 90)]
    unqual   = df_c[(df_c["total_score"] < warm_thr) & (df_c["close_value"].fillna(0) == 0)]
    overdue  = df_c[(df_c["risk_flags"].str.contains("📅", na=False)) & (df_c["total_score"] < warm_thr)] \
        if "risk_flags" in df_c.columns else pd.DataFrame()

    fig_cleanup = go.Figure(go.Bar(
        x=["🧟 Zombies", "❓ Não qualificados", "📅 Overdue"],
        y=[len(zombies), len(unqual), len(overdue)],
        marker_color=["#8e44ad", "#e67e22", "#e74c3c"],
        text=[len(zombies), len(unqual), len(overdue)],
        textposition="outside",
    ))
    fig_cleanup.update_layout(title="Pipeline Cleanup — Candidatos a Descarte",
                               yaxis_title="Nº de deals", margin=dict(t=40, b=20))

    # ---- Tabela top 50 ----
    TABLE_COLS = [c for c in [
        "opportunity_id", "sales_agent", "account", "product", "deal_stage",
        "close_value", "total_score", "win_probability", "risk_flags",
    ] if c in df.columns]

    top50 = df[TABLE_COLS].head(50).copy()
    top50.index = range(1, len(top50) + 1)

    def row_color(score):
        if score >= hot_thr:  return "#fde8e8"
        if score >= warm_thr: return "#fef3e2"
        return "#ebf5fb"

    table_rows = ""
    for rank, row in top50.iterrows():
        score = float(row["total_score"])
        bg    = row_color(score)
        wp    = f"{float(row.get('win_probability', score_to_win_prob(score)))*100:.0f}%"
        cv    = row.get("close_value", 0)
        cv_s  = f"R$ {float(cv):,.0f}" if pd.notna(cv) and float(cv) > 0 else "—"
        flags = str(row.get("risk_flags", ""))
        table_rows += f"""
        <tr style="background:{bg}">
          <td>{rank}</td>
          <td>{row.get('opportunity_id','')}</td>
          <td>{row.get('sales_agent','')}</td>
          <td>{row.get('account','')}</td>
          <td>{row.get('product','')}</td>
          <td>{row.get('deal_stage','')}</td>
          <td>{cv_s}</td>
          <td style="font-weight:700">{score:.0f}</td>
          <td>{wp}</td>
          <td style="font-size:0.85em">{flags}</td>
        </tr>"""

    charts_json = {
        "hist":    fig_hist.to_json(),
        "factors": fig_factors.to_json(),
        "cleanup": fig_cleanup.to_json(),
    }

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Lead Scorer — Pipeline Priorizado</title>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         margin: 0; background: #f5f7fa; color: #2c3e50; }}
  .header {{ background: #2c3e50; color: white; padding: 24px 40px; }}
  .header h1 {{ margin: 0; font-size: 1.8em; }}
  .header p  {{ margin: 4px 0 0; opacity: 0.7; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px 40px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 16px; margin-bottom: 32px; }}
  .kpi  {{ background: white; border-radius: 8px; padding: 20px; text-align: center;
           box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .kpi .val {{ font-size: 2em; font-weight: 700; }}
  .kpi .lbl {{ font-size: 0.85em; color: #7f8c8d; margin-top: 4px; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 32px; }}
  .chart-card {{ background: white; border-radius: 8px; padding: 16px;
                 box-shadow: 0 1px 4px rgba(0,0,0,.08); }}
  .section-title {{ font-size: 1.2em; font-weight: 600; margin: 32px 0 12px; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px;
           overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); font-size: 0.88em; }}
  th {{ background: #2c3e50; color: white; padding: 10px 8px; text-align: left; }}
  td {{ padding: 8px; border-bottom: 1px solid #eee; }}
  tr:last-child td {{ border-bottom: none; }}
  .note {{ color: #7f8c8d; font-size: 0.82em; margin-top: 8px; }}
  .footer {{ text-align: center; padding: 24px; color: #7f8c8d; font-size: 0.82em; }}
</style>
</head>
<body>
<div class="header">
  <h1>🎯 Lead Scorer — Pipeline Priorizado</h1>
  <p>Challenge 003 · G4 AI Master · {pd.Timestamp.today().strftime('%d/%m/%Y %H:%M')}</p>
</div>

<div class="container">
  <div class="kpis">
    <div class="kpi"><div class="val" style="color:#e74c3c">{hot_count:,}</div>
      <div class="lbl">🔴 Quentes ≥P85 ({hot_thr:.0f})</div></div>
    <div class="kpi"><div class="val" style="color:#e67e22">{warm_count:,}</div>
      <div class="lbl">🟠 Mornos P60–P85</div></div>
    <div class="kpi"><div class="val" style="color:#3498db">{cold_count:,}</div>
      <div class="lbl">🔵 Frios &lt;P60 ({warm_thr:.0f})</div></div>
    <div class="kpi"><div class="val" style="color:#e67e22">{flagged:,}</div>
      <div class="lbl">⚠️ Com Alertas</div></div>
    <div class="kpi"><div class="val" style="color:#27ae60">R$ {hot_value:,.0f}</div>
      <div class="lbl">💰 Valor em Quentes</div></div>
  </div>

  <div class="charts">
    <div class="chart-card"><div id="hist"></div></div>
    <div class="chart-card"><div id="factors"></div></div>
    <div class="chart-card"><div id="cleanup"></div></div>
  </div>

  <div class="section-title">Top 50 Deals Priorizados</div>
  <p class="note">🔴 Quente (≥{hot_thr:.0f}) · 🟠 Morno ({warm_thr:.0f}–{hot_thr:.0f}) · 🔵 Frio (&lt;{warm_thr:.0f}) — P(win) via sigmoid calibrada (score 65 → 50%)</p>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Deal ID</th><th>Vendedor</th><th>Conta</th>
        <th>Produto</th><th>Stage</th><th>Valor</th><th>Score</th>
        <th>P(win)</th><th>Alertas</th>
      </tr>
    </thead>
    <tbody>{table_rows}</tbody>
  </table>
</div>

<div class="footer">Lead Scorer · G4 AI Master Challenge 003</div>

<script>
const charts = {json.dumps(charts_json)};
Plotly.newPlot('hist',    JSON.parse(charts.hist).data,    JSON.parse(charts.hist).layout,    {{responsive:true}});
Plotly.newPlot('factors', JSON.parse(charts.factors).data, JSON.parse(charts.factors).layout, {{responsive:true}});
Plotly.newPlot('cleanup', JSON.parse(charts.cleanup).data, JSON.parse(charts.cleanup).layout, {{responsive:true}});
</script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Gera relatório HTML do Lead Scorer")
    parser.add_argument("--pipeline", help="sales_pipeline.csv")
    parser.add_argument("--accounts", help="accounts.csv")
    parser.add_argument("--products", help="products.csv")
    parser.add_argument("--teams",    help="sales_teams.csv")
    parser.add_argument("--output",   default="lead_scorer_report.html")
    args = parser.parse_args()

    print("Carregando dados e calculando scores...")
    df = load_data(args)
    print(f"  {len(df):,} deals ativos processados")

    html = build_html(df)
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"\n✅ Relatório salvo em: {args.output}")
    print("   Abra o arquivo no seu browser.")


if __name__ == "__main__":
    main()
