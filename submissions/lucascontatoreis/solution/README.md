# Lead Scorer — Solução Challenge 003

Ferramenta web para priorização de pipeline de vendas com scoring explicável.
Desenvolvida para o **G4 AI Master Challenge 003 — Lead Scorer**.

---

## Setup e execução

### Pré-requisitos

- Python 3.10+
- pip

### Instalação

```bash
cd challenges/build-003-lead-scorer/solution
pip install -r requirements.txt
```

### Rodando

```bash
streamlit run app.py
```

A aplicação abre em `http://localhost:8501`.

### Com os dados reais do Kaggle

1. Baixe o dataset [CRM Sales Predictive Analytics](https://www.kaggle.com/datasets/agungpambudi/crm-sales-predictive-analytics)
2. Extraia os 4 CSVs: `sales_pipeline.csv`, `accounts.csv`, `products.csv`, `sales_teams.csv`
3. Na sidebar da aplicação, desative **"Usar dados de demonstração"**
4. Faça upload dos arquivos CSV

Sem upload, a aplicação roda com **dados sintéticos de demonstração** (8.800 deals, 85 contas, 35 vendedores).

---

## Lógica de Scoring

Cada deal recebe uma nota de **0 a 100 pontos**, composta por 5 fatores:

| Fator | Peso | Critério |
|-------|------|----------|
| **Stage de Pipeline** | 25 pts | Engaging = 25, Prospecting = 15 |
| **Potencial do Deal** | 20 pts | `close_value` se preenchido; preço de tabela do produto como proxy se não qualificado |
| **Velocidade + Urgência** | 20 pts | Dias no pipeline vs. mediana histórica + boost se fecha em ≤30 dias |
| **Qualidade da Conta** | 20 pts | Setor estratégico (15 setores mapeados) + tamanho da empresa |
| **Performance do Vendedor** | 15 pts | Taxa histórica de fechamento do agente vs. média do time |

### Por que esses critérios?

**Stage** — Engaging é evidência direta de interesse ativo. Prospecting ainda é hipótese.

**Potencial** — Usa `close_value` quando disponível. Para deals não qualificados (valor = 0), usa o preço de tabela do produto como proxy — assim produtos da série MG (premium) pontuam mais que GTX, mesmo sem valor confirmado. Normalizado com raiz quadrada para não deixar outliers dominar.

**Velocidade + Urgência** — Dois componentes combinados: (1) deals com bom ritmo de avanço pontuam mais; deals parados há 2x a mediana histórica perdem pontos. (2) Se a data de fechamento está dentro de 14 dias, recebe boost de urgência — independente do stage.

**Conta** — Setores com ciclos de compra recorrentes e grande base de funcionários têm potencial de expansão. Deal pequeno numa conta grande pode virar conta estratégica.

**Agente** — Taxa histórica do vendedor é proxy de qualidade de qualificação. Vendedores com alta win rate tendem a ter pipeline mais limpo.

### Risk Flags (alertas sem penalidade no score)

Além do score, cada deal pode ter alertas visuais:

| Flag | Significado |
|------|------------|
| 📅 Vencido há Xd | Data de fechamento já passou — deal atrasado |
| 🧊 Inativo há Xd | Mais de 90 dias no pipeline sem avançar |
| 💰 Sem close_value | Deal não qualificado financeiramente |
| 💰 Produto premium sem valor | Alto ticket potencial, mas valor ainda não confirmado |

### Explainability

Cada deal exibe **5 frases de explicação** — uma por fator — para o vendedor entender exatamente por que o score é alto ou baixo. Não existe "caixa-preta".

---

## Limitações

- **Sem ML preditivo**: o modelo é baseado em regras + heurísticas. Isso é intencional — mais transparente e auditável para vendedores. Um XGBoost poderia capturar interações não-lineares, mas exigiria dados históricos maiores e perderia explainability.
- **Velocidade usa mediana global**: idealmente seria por segmento (produto × setor). Com mais dados, valia segmentar.
- **Sem dados de engajamento externo**: aberturas de email, visitas ao site, interações anteriores poderiam enriquecer muito o score.
- **Qualidade da conta é estática**: não considera crescimento recente, mudanças de liderança, sinais de expansão.
- **Para escalar**: integrar via API (FastAPI) com o CRM real (Salesforce, HubSpot) para recálculo em tempo real a cada atualização de deal.

---

## Estrutura dos arquivos

```
solution/
├── app.py           # Dashboard Streamlit (interface visual)
├── scorer.py        # Engine de scoring (lógica pura, testável)
├── sample_data.py   # Gerador de dados sintéticos para demo
├── requirements.txt
└── README.md
```
