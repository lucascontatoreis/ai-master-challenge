# Process Log — Workflow Detalhado

## Ferramenta principal: Claude Code (claude-sonnet-4-6)

Todo o desenvolvimento foi feito via Claude Code — a CLI oficial da Anthropic que roda no terminal com acesso ao filesystem, git, e execução de comandos. O processo inteiro aconteceu em uma sessão de trabalho iterativa.

---

## Linha do tempo

### 1. Leitura e decomposição (sem IA ainda)

Antes de abrir o Claude Code, li o README do challenge completo e os schemas dos 4 CSVs.

Perguntas que formulei antes de qualquer prompt:

- _O que a Head de RevOps vai abrir numa segunda-feira de manhã?_ → Uma lista priorizada, não um dashboard de BI
- _O que diferencia um deal bom de um deal ruim nesse dataset?_ → Stage + velocidade + valor + conta + agente
- _O que está faltando nos dados que vai afetar o scoring?_ → `close_value=0` para deals ativos é um problema

Só depois dessas perguntas fui ao Claude Code.

### 2. Prompt inicial — estrutura da solução

**Decisão de design antes de promptar:**
- Streamlit: roda no browser, sem instalação, Python
- `scorer.py` separado de `app.py`: engine testável sem UI
- `sample_data.py`: demo funciona sem ter os CSVs reais

**O que foi pedido ao Claude Code:**
> "Construa um Lead Scorer em Streamlit para o Challenge 003. Engine de scoring separado em scorer.py com 5 fatores: stage (25pt), close_value (20pt), velocidade no pipeline (20pt), qualidade da conta (20pt), win rate do agente (15pt). Cada deal deve ter 5 frases de explicação. App com filtros por vendedor/manager/região, tabela colorida por score, e gráficos de análise."

**Resultado:** primeira versão funcional — `366866c`

### 3. Code review manual do output

Reli `scorer.py` linha por linha e identifiquei os problemas:

```python
# O que a IA gerou — fator "valor":
def _score_value(self, row):
    value = float(row.get("close_value", 0) or 0)
    normalized = math.sqrt(value) / math.sqrt(self._max_value)
    pts = normalized * WEIGHT_VALUE
    # ...
```

**Problema**: `close_value` é 0 para todos os deals Engaging/Prospecting. Este fator não ia funcionar para a maioria do pipeline. A solução: usar o preço do produto como proxy quando close_value=0.

```python
# O que a IA gerou — urgência no scoring de velocidade:
def _score_velocity(self, row):
    stage = str(row.get("deal_stage", ""))
    if stage == "Prospecting":  # <-- só Prospecting!
        close_date = row.get("close_date")
        if pd.notna(close_date):
            days_to_close = (close_date - today).days
            # ...
```

**Problema**: urgência de data de fechamento só era avaliada para Prospecting. Um deal Engaging fechando em 3 dias não recebia boost.

**Problema 3 — ausente**: Sem nenhum sistema de alertas visuais. Deals com data vencida, 6 meses parados, ou sem valor eram indistinguíveis na UI.

### 4. Segunda iteração — instruções específicas

Passei as 3 lacunas identificadas ao Claude Code com instruções precisas:

> 1. "Substitua `_score_value` por `_score_potential`: se close_value > 0, usa ele; se = 0, usa 70% do preço do produto como estimativa de potencial; produtos da série MG recebem +15% sobre GTX quando não têm close_value confirmado."
>
> 2. "Refatore `_score_velocity`: aplique o boost de urgência para qualquer stage, não só Prospecting. Deals fechando em ≤14 dias = boost de 50% do peso; ≤30 dias = 30%."
>
> 3. "Adicione `_get_risk_flags(row)` que retorna lista de strings com alertas: data vencida, deal parado >90d, sem close_value, produto premium não qualificado."
>
> 4. "No app.py: adicione tab 'Meu Foco' onde o vendedor seleciona o próprio nome e vê top 10 deals com card expandível mostrando score breakdown e ação recomendada. Adicione tab 'Visão do Manager' com heatmap manager×stage e bubble chart volume×qualidade."

**Resultado:** commit `2a0a9b4`

### 5. Teste e último ajuste

Rodei o scorer end-to-end:

```python
python -c "
from sample_data import generate_all
from scorer import LeadScorer
pipeline, accounts, products, teams = generate_all()
df = LeadScorer(pipeline, accounts, products, teams).score_all()
print(f'Deals com alertas: {(df[\"risk_flags\"].str.len() > 0).sum()}')
"
# Output: Deals com alertas: 5275  ← todos os deals tinham alerta!
```

**Problema identificado**: O gerador de dados sintéticos colocava `close_value=0` para todos os deals ativos. No CRM real, ~70% dos deals Engaging/Prospecting têm valor estimado preenchido pelo vendedor. Com 100% dos deals tendo o flag "💰 Sem close_value", o alerta perdia o significado.

**Correção no `sample_data.py`**:
```python
# Antes:
elif stage in ("Engaging", "Prospecting"):
    close_value = 0.0  # todos sem valor

# Depois: 70% qualificados, 30% sem valor (realista)
elif stage in ("Engaging", "Prospecting") and random.random() < 0.70:
    close_value = base_price * random.uniform(0.5, 1.2)
else:
    close_value = 0.0
```

**Resultado final**: 1.614 deals sem close_value (30%) — flags aparecem onde fazem sentido.

---

## Contagem de iterações

| Iteração | O que foi pedido | Por que |
|----------|-----------------|---------|
| 1 | Build inicial completo | Primeira versão funcional |
| 2 | Melhorias de scoring + novos tabs | 3 lacunas identificadas por code review |
| 3 | Fix no sample_data.py | Flags aparecendo em 100% dos deals |

3 iterações principais. Cada uma com razão específica — não foi "bom, tenta de novo" mas sim "esse trecho específico tem esse problema específico por essa razão".

---

## O que o Claude Code fez bem

- Separação de responsabilidades (scorer.py vs app.py) sem precisar pedir
- Normalização de colunas com `lower().strip()` — robusto para CSVs reais com variações
- Uso de `@st.cache_data` para não recalcular o scoring a cada interação
- Tratamento de `pd.isna()` em todas as datas antes de operar

## O que precisou de correção humana

- Scoring de produto completamente ausente na primeira versão
- Urgência de close_date incompleta (só Prospecting)
- Sample data não simulava CRM real (sem close_value em deals ativos)
- Nenhum sistema de alertas/flags proposto espontaneamente
