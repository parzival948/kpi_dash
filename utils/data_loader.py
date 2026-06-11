import os
import re
import pandas as pd

from config import COUNTRY_NORMALIZE, BRAND_NORMALIZE


def _normalize_brand(name: str) -> str:
    key = name.strip().lower()
    return BRAND_NORMALIZE.get(key, name.strip())


def get_all_data():
    budget = pd.read_excel("data/budget/budget.xlsx")
    budget["month"] = budget["month"].astype(str)
    budget["country"] = budget["country"].str.strip().str.upper()
    budget["country"] = budget["country"].map(COUNTRY_NORMALIZE)
    budget["brand"] = budget["brand"].str.strip()

    fx = pd.read_excel("data/exchange_rates/exchange_rate.xlsx")
    fx["month"] = fx["month"].astype(str)
    fx["country"] = fx["country"].str.strip().str.upper()
    fx["country"] = fx["country"].map(COUNTRY_NORMALIZE)
    fx.rename(columns={"currency_rate": "actual_rate"}, inplace=True)

    cost_dir = "data/costs"
    frames = []
    pattern = re.compile(r"(\d{4}_\d{2})_(.+)\.xlsx")
    for fname in os.listdir(cost_dir):
        m = pattern.match(fname)
        if not m:
            continue
        month_str = m.group(1).replace("_", "-")
        courier = m.group(2).lower()
        df = pd.read_excel(os.path.join(cost_dir, fname))
        df["month"] = month_str
        df["courier"] = courier
        df["country"] = df["country"].str.strip().str.upper()
        df["country"] = df["country"].map(COUNTRY_NORMALIZE)
        df["brand"] = df["brand"].str.strip().apply(_normalize_brand)
        df["province"] = df["province"].str.strip().str.upper()
        frames.append(df)

    actuals = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    months = sorted(set(budget["month"].unique()) | set(actuals["month"].unique()))
    countries = sorted(budget["country"].unique())
    budget_brands = set(budget["brand"].unique())
    actuals_brands = set(actuals["brand"].unique()) if not actuals.empty else set()
    brands = sorted(budget_brands | actuals_brands)
    couriers = sorted(actuals["courier"].unique()) if not actuals.empty else []

    return {
        "budget": budget,
        "fx": fx,
        "actuals": actuals,
        "months": months,
        "countries": countries,
        "brands": brands,
        "couriers": couriers,
    }
