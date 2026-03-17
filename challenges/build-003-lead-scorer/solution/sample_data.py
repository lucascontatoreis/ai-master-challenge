"""
Gerador de dados de exemplo para o Lead Scorer.
Cria CSVs sintéticos com a mesma estrutura do dataset CRM do Kaggle.
Usado para demo quando o usuário não carregou os arquivos reais.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import numpy as np
import pandas as pd

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

# ---------------------------------------------------------------------------
# Dados base
# ---------------------------------------------------------------------------

SECTORS = [
    "Technology", "Finance", "Healthcare", "Retail", "Manufacturing",
    "Telecommunications", "Energy", "Real Estate", "Education", "Logistics",
]

REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]

MANAGERS = [
    "Caren Jone", "Dustin Brinkmann", "Melvin Marxen",
    "Summer Sewald", "Rocco Neubert",
]

PRODUCTS = [
    ("MG Special", "MG", 55000),
    ("GTX Pro", "GTX", 40000),
    ("GTX Basic", "GTX", 20000),
    ("MG Advanced", "MG", 75000),
    ("GTX Plus", "GTX", 30000),
    ("GTXPro Plus", "GTX", 48000),
    ("MG Ultimate", "MG", 90000),
]

STAGES_WITH_WEIGHTS = [
    ("Engaging", 0.35),
    ("Prospecting", 0.25),
    ("Won", 0.25),
    ("Lost", 0.15),
]


def _random_date(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, max(delta, 0)))


def generate_accounts(n: int = 85) -> pd.DataFrame:
    company_suffixes = ["Corp", "Inc", "LLC", "Solutions", "Group", "Partners", "Tech"]
    rows = []
    for i in range(1, n + 1):
        sector = random.choice(SECTORS)
        rows.append({
            "account": f"Account_{i:03d}",
            "sector": sector,
            "revenue": round(random.uniform(1e6, 500e6), -3),
            "employees": random.choice([50, 100, 250, 500, 1000, 2500, 5000, 10000]),
            "office_location": random.choice(REGIONS),
            "subsidiary_of": f"Account_{random.randint(1,20):03d}" if random.random() < 0.2 else "",
        })
    return pd.DataFrame(rows)


def generate_products() -> pd.DataFrame:
    rows = [
        {"product": name, "series": series, "sales_price": price}
        for name, series, price in PRODUCTS
    ]
    return pd.DataFrame(rows)


def generate_sales_teams(managers: list[str] = MANAGERS, agents_per_manager: int = 7) -> pd.DataFrame:
    first_names = [
        "Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Drew",
        "Cameron", "Avery", "Quinn", "Blake", "Reese", "Sage", "Parker",
        "Hayden", "Kendall", "Rowan", "Emerson", "Logan", "Finley",
        "Skyler", "Devon", "Harley", "Shawn", "Peyton", "Remi", "Jaden",
        "Carter", "Ariel", "Elliot", "Spencer", "Charlie", "Bailey",
        "Corey", "Jamie",
    ]
    last_names = [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
        "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
        "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
        "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
        "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
        "Wright",
    ]
    rows = []
    name_pool = [f"{f} {l}" for f, l in zip(first_names, last_names)]
    idx = 0
    for manager in managers:
        region = random.choice(REGIONS)
        for _ in range(agents_per_manager):
            if idx >= len(name_pool):
                break
            rows.append({
                "sales_agent": name_pool[idx],
                "manager": manager,
                "regional_office": region,
            })
            idx += 1
    return pd.DataFrame(rows)


def generate_pipeline(
    accounts_df: pd.DataFrame,
    products_df: pd.DataFrame,
    teams_df: pd.DataFrame,
    n: int = 8800,
) -> pd.DataFrame:
    today = date.today()
    start = today - timedelta(days=365)

    accounts = accounts_df["account"].tolist()
    products = products_df["product"].tolist()
    agents = teams_df["sales_agent"].tolist()

    # Agentes com alta/baixa performance (determinístico pelo seed)
    high_perf_agents = set(random.sample(agents, k=max(1, len(agents) // 4)))
    low_perf_agents = set(random.sample(
        [a for a in agents if a not in high_perf_agents],
        k=max(1, len(agents) // 5),
    ))

    stages = [s for s, _ in STAGES_WITH_WEIGHTS]
    weights = [w for _, w in STAGES_WITH_WEIGHTS]

    rows = []
    for i in range(1, n + 1):
        agent = random.choice(agents)
        stage = random.choices(stages, weights=weights, k=1)[0]

        engage_date = _random_date(start, today - timedelta(days=1))
        if stage in ("Won", "Lost"):
            close_date = _random_date(engage_date, today)
        elif stage == "Engaging":
            close_date = _random_date(today, today + timedelta(days=120))
        else:
            close_date = _random_date(today, today + timedelta(days=180))

        product_name = random.choice(products)
        base_price = products_df.loc[products_df["product"] == product_name, "sales_price"].values[0]

        # Performance influencia win/loss mais realista.
        # Deals ativos (Engaging/Prospecting) têm close_value estimado pelo rep (~70% dos casos),
        # simulando CRMs reais onde o vendedor preenche o valor esperado na qualificação.
        if stage == "Won":
            if agent in high_perf_agents:
                close_value = base_price * random.uniform(0.9, 1.3)
            elif agent in low_perf_agents:
                close_value = base_price * random.uniform(0.6, 0.95)
            else:
                close_value = base_price * random.uniform(0.75, 1.1)
        elif stage in ("Engaging", "Prospecting") and random.random() < 0.70:
            # 70% dos deals ativos têm valor estimado; 30% ainda não foram qualificados
            close_value = base_price * random.uniform(0.5, 1.2)
        else:
            close_value = 0.0

        rows.append({
            "opportunity_id": f"OP_{i:05d}",
            "sales_agent": agent,
            "product": product_name,
            "account": random.choice(accounts),
            "deal_stage": stage,
            "engage_date": engage_date.isoformat(),
            "close_date": close_date.isoformat(),
            "close_value": round(close_value, 2),
        })

    return pd.DataFrame(rows)


def generate_all() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Retorna (pipeline, accounts, products, teams) como DataFrames."""
    accounts = generate_accounts()
    products = generate_products()
    teams = generate_sales_teams()
    pipeline = generate_pipeline(accounts, products, teams)
    return pipeline, accounts, products, teams
