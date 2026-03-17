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
| **Valor do Deal** | 20 pts | Normalizado pela raiz quadrada do valor máximo do pipeline |
| **Velocidade no Pipeline** | 20 pts | Baseado em dias desde o engajamento vs. mediana histórica |
| **Qualidade da Conta** | 20 pts | Setor estratégico (15 setores mapeados) + tamanho da empresa |
| **Performance do Vendedor** | 15 pts | Taxa histórica de fechamento do agente vs. média do time |

### Por que esses critérios?

**Stage** — Engaging é evidência direta de interesse. Prospecting ainda é hipótese.

**Valor** — Deal grande merece atenção, mas com raiz quadrada para não dominar o score e esconder deals menores com alta probabilidade.

**Velocidade** — Pipeline com momentum positivo tem maior chance de fechar. Deal parado por 2x a mediana histórica tem risco real de esfriar. É o fator que mais diferencia deals que parecem iguais na superfície.

**Conta** — Setores com ciclos de compra recorrentes e grande base de funcionários têm potencial de expansão. Um deal pequeno numa conta grande pode virar uma conta estratégica.

**Agente** — Taxa histórica do vendedor é proxy de qualidade da qualificação. Vendedores com alta win rate tendem a ter pipeline mais limpo.

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
