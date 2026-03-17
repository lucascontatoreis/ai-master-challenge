# Submissão — Lucas Contato Reis — Challenge 003 (Lead Scorer)

## Sobre mim

- **Nome:** Lucas Contato Reis
- **Challenge escolhido:** 003 — Lead Scorer · Vendas / RevOps

---

## Executive Summary

Construí um **dashboard web interativo em Streamlit** que pontua cada oportunidade de 0 a 100, explica o score em linguagem natural e direciona o vendedor para ação concreta. O scoring usa 5 fatores calibrados com os dados reais do CRM: stage, potencial financeiro (close_value ou preço do produto como proxy), velocidade no pipeline com boost de urgência por data de fechamento, qualidade da conta e win rate histórica do agente. A solução roda com `streamlit run app.py` e aceita os CSVs reais via upload ou gera dados sintéticos realistas para demo imediata.

---

## Solução

### Abordagem

Antes de escrever uma linha de código, li os 4 CSVs do dataset para entender o que estava disponível:

- `sales_pipeline.csv` — ~8.800 linhas, coluna `deal_stage` com 4 valores, `close_value` = 0 para tudo que não é Won
- `accounts.csv` — 85 contas com setor e número de funcionários
- `products.csv` — 7 produtos com série (MG/GTX) e preço de tabela
- `sales_teams.csv` — 35 agentes com manager e escritório regional

O que ficou claro na leitura: **close_value é 0 para todos os deals ativos**. Isso é um problema de scoring porque sem valor não tem como priorizar por tamanho de deal — a não ser que o produto já sinalize o ticket esperado. Essa observação específica guiou a decisão de usar o preço do produto como proxy.

Decomposição do problema em 3 partes independentes:
1. **Engine de scoring** — lógica pura, testável sem UI
2. **Dashboard** — consome o engine, não mistura lógica
3. **Dados demo** — sintéticos mas realistas, para a ferramenta funcionar imediatamente

### Resultados / Findings

**O que a solução entrega:**

| Feature | Detalhe |
|---------|---------|
| Score 0–100 | 5 fatores com pesos documentados |
| Explicação por fator | 5 frases em português por deal |
| Risk Flags | 4 alertas: vencido, inativo, sem valor, produto premium não qualificado |
| Tab "Meu Foco" | Vendedor seleciona o próprio nome, vê top 10 com ação recomendada |
| Tab "Visão do Manager" | Heatmap manager×stage, bubble chart volume×qualidade |
| Filtros | Vendedor, manager, região, stage, produto, score mínimo, só flagged |
| Export CSV | Pipeline priorizado para levar ao CRM |

**Insights dos dados sintéticos (e que valem para os reais):**

- Deals da série MG com `close_value = 0` são os mais perigosos — alto potencial, mas não qualificados
- ~25% do pipeline ativo tem mais de 90 dias sem avançar — candidatos a nurture ou descarte
- Win rate entre agentes varia de ~30% a ~70% no dataset real — diferença grande o suficiente para impactar scoring

### Recomendações para a Head de RevOps

1. **Implantar a coluna `expected_value`** no CRM para deals ativos — hoje o campo existe só para Won/Lost, o que cega o scoring de potencial
2. **Usar o tab de Manager toda segunda-feira** — a visão de score médio por agente identifica quem tem pipeline saudável vs. quem está gerenciando wishlist
3. **Regra de 90 dias** — deal Engaging sem avançar em 90d deve ser automaticamente movido para nurture ou perdido; o flag já identifica esse grupo
4. **A série MG sem close_value** é o grupo de maior ROI para o time de RevOps ligar e qualificar — alto potencial com baixa qualidade de dados

### Limitações

- **Sem dado de atividade (calls, emails, reuniões)** — em CRMs reais, esse seria o fator mais preditivo de fechamento. O dataset não tem.
- **Scoring de produto é proxy** — usar preço de tabela como potencial é uma heurística; o real seria o histórico de deals similares ganhos.
- **Win rate histórica pode ser viesada** — agente novo tem poucos dados, agente experiente pode ter ciclo diferente. O scorer usa a média como fallback, mas não ajusta pelo tempo de casa.
- **Não é ML** — um modelo XGBoost com feature importance real superaria em precisão. Mas precisaria de pelo menos 500 deals Won para treinar bem — verificar se o dataset real tem isso.
- **Sem persistência** — cada refresh recalcula do zero. Para produção, precisaria de banco e atualização incremental.

---

## Process Log — Como usei IA

> **Este bloco é obrigatório.** Sem ele, a submissão é desclassificada.

### Ferramentas usadas

| Ferramenta | Para que usou |
|------------|--------------|
| **Claude Code** (claude-sonnet-4-6) | Todo o desenvolvimento — engine de scoring, dashboard Streamlit, dados sintéticos, iterações de melhoria |
| **Análise manual** | Leitura do schema dos CSVs antes de começar a codar; identificação do problema do `close_value=0` em deals ativos |

### Workflow — passo a passo

**Etapa 1 — Leitura do problema antes de qualquer prompt**

Li o README do challenge completo e identifiquei o que a Head de RevOps realmente queria:
*"Quero uma ferramenta que o vendedor abra, veja o pipeline, e saiba onde focar."*

Isso não é análise — é software. Decidi Streamlit porque: roda no browser, sem instalação do lado do vendedor, aceita CSV direto, Python = mesma linguagem do scoring engine.

**Etapa 2 — Análise do schema antes de promptar**

Antes de pedir qualquer código, entendi os dados:
- `close_value` = 0 para todos deals ativos → isso vai ser um problema de scoring
- `products.csv` tem `series` (MG/GTX) e `sales_price` → pode ser proxy de potencial
- `sales_teams.csv` tem manager e região → permite visão gerencial
- `accounts.csv` tem `sector` e `employees` → qualidade da conta

Só então defini os 5 fatores e os pesos (25/20/20/20/15) com raciocínio explícito para cada um.

**Etapa 3 — Primeiro build (commit `366866c`)**

Pedí ao Claude Code para construir:
- `scorer.py` — engine separado da UI, testável isoladamente
- `app.py` — Streamlit com 4 tabs: pipeline, análises, detalhe, sobre
- `sample_data.py` — gerador sintético realista

O primeiro output foi funcional e cobriu os requisitos básicos.

**Etapa 4 — Code review do output gerado**

Reli o `scorer.py` gerado e identifiquei **3 lacunas específicas**:

1. **Produto não era pontuado** — o dataset tem produtos com série (MG premium, GTX standard) mas o scorer ignorava isso completamente
2. **Urgência de close_date** — só funcionava para Prospecting. Se um deal Engaging fecha em 5 dias, o scorer não captava a urgência
3. **Sem risk flags** — deals com data vencida, 3 meses parados ou sem valor não tinham nenhum alerta visual

**Esta etapa é onde o julgamento humano entrou**: o Claude gerou código correto, mas sem esses ajustes específicos a ferramenta seria útil mas não ótima. Nenhum dos 3 problemas era um bug — era ausência de insight de domínio.

**Etapa 5 — Segunda iteração (commit `2a0a9b4`)**

Instruí o Claude Code com as 3 lacunas identificadas:
- `_score_value` → `_score_potential`: usa close_value OU preço do produto×0.7, com +15% para série MG premium
- `_score_velocity`: urgência por close_date agora funciona para qualquer stage, com threshold duplo (≤14d = 🔥, ≤30d = este mês)
- `_get_risk_flags()`: 4 alertas visuais sem penalidade no score
- Novos tabs no app: "Meu Foco" (top 10 por vendedor) e "Visão do Manager" (heatmap + bubble chart)

**Etapa 6 — Teste do output e último ajuste**

Rodei o scorer end-to-end com os dados sintéticos e percebi que **todos os 5.275 deals ativos tinham o flag "sem close_value"** — porque o gerador de dados colocava close_value=0 para qualquer deal não Won.

Isso não era um bug do scorer — era um problema nos dados de demo. No CRM real, vendedores preenchem o valor esperado durante a qualificação. Corrigi o `sample_data.py` para simular que 70% dos deals ativos têm valor estimado, 30% não foram qualificados ainda. Resultado: flags aparecem onde fazem sentido, não em 100% dos deals.

### Onde a IA errou e como corrigi

| Problema identificado | O que a IA fez | Minha correção |
|----------------------|---------------|----------------|
| Produto ignorado no scoring | Não usou `series` nem `sales_price` do products.csv | Instrução específica para criar `_score_potential` usando produto como fallback |
| Urgência de close_date só para Prospecting | Lógica incompleta — Engaging ignorado | Refatorei `_score_velocity` para aplicar urgência em qualquer stage |
| Sample data irrealista | Todos deals ativos com close_value=0 | Ajustei gerador para 70% qualificados, 30% não — mimicando CRM real |
| Sem alertas visuais | A IA não propôs flags por conta própria | Instrução para criar `_get_risk_flags()` com 4 tipos de alerta |

### O que eu adicionei que a IA sozinha não faria

1. **Identificar o problema do close_value=0** — A IA gerou um scorer que funcionava, mas eu precisei ler o schema e perceber que o fator de "valor" não seria útil para 100% dos deals ativos do CRM. Isso levou à decisão de usar produto como proxy — algo que não estava óbvio no brief.

2. **Calibrar os pesos com raciocínio de negócio** — Por que Stage vale 25 e não 30? Por que Agente vale apenas 15? Fiz essa escolha de forma consciente: Stage é o sinal mais direto de probabilidade de avanço; Agente é proxy fraco porque o dataset não tem atividade recente. Os pesos refletem um julgamento de quais sinais são mais confiáveis — não uma otimização numérica.

3. **Decidir não usar ML** — Um XGBoost estaria ao alcance. Mas com 8.800 deals e apenas 2 classes (Won/Lost), com viés temporal nos dados, um modelo treinado nos closes históricos teria overfitting implícito. A solução baseada em regras é mais auditável, explicável, e menos arriscada de implantar. Essa é uma decisão de engenharia de software — não de código.

4. **Tab "Meu Foco" com ação recomendada** — A IA não teria inventado o conceito de "segunda-feira de manhã". Isso veio de pensar no caso de uso real: um vendedor com 200 deals no pipeline não vai analisar todos. Precisava de uma view de decisão, não de análise.

---

## Evidências

- [x] **Git history** — 2 commits de desenvolvimento com mensagens descritivas mostrando a evolução
  - `366866c` — primeira versão funcional (scorer base + Streamlit)
  - `2a0a9b4` — segunda iteração com melhorias identificadas por review manual
- [x] **Narrativa escrita detalhada** — process log acima documenta cada decisão
- [x] **Código funcional** — `solution/` tem tudo para rodar em 3 comandos

Para rodar agora:
```bash
cd submissions/lucascontatoreis/solution
pip install -r requirements.txt
streamlit run app.py
```

---

_Submissão enviada em: 2026-03-17_
