import pandas as pd
import numpy as np


def _fx_rate_map(fx: pd.DataFrame) -> dict:
    result = {}
    for _, row in fx.iterrows():
        key = (row["month"], row["country"])
        result[key] = (row["actual_rate"], row["budget_rate"])
    return result


def aggregate_actuals(
    actuals: pd.DataFrame,
    fx: pd.DataFrame,
    group_cols: list,
) -> pd.DataFrame:
    if actuals.empty:
        return pd.DataFrame()

    grouped = (
        actuals.groupby(group_cols, observed=True)
        .agg(
            volume=("order_id", "nunique"),
            total_cost_local=("total_cost_local", "sum"),
            total_revenue_local=("total_revenue_local", "sum"),
        )
        .reset_index()
    )
    grouped["margin_local"] = (
        grouped["total_revenue_local"] - grouped["total_cost_local"]
    )

    fx_map = _fx_rate_map(fx)

    def _apply_fx(row):
        key = (row["month"], row["country"])
        rates = fx_map.get(key, (1.0, 1.0))
        return pd.Series(
            {
                "actual_rate": rates[0],
                "budget_rate": rates[1],
                "total_cost_usd": row["total_cost_local"] / rates[0]
                if rates[0] != 0
                else 0,
                "total_revenue_usd": row["total_revenue_local"] / rates[0]
                if rates[0] != 0
                else 0,
                "margin_usd": (row["total_revenue_local"] / rates[0])
                - (row["total_cost_local"] / rates[0])
                if rates[0] != 0
                else 0,
            }
        )

    rate_df = grouped.apply(_apply_fx, axis=1)
    grouped = pd.concat([grouped, rate_df], axis=1)
    return grouped


def compute_waterfall(
    act_vol: float,
    act_cost_local: float,
    bud_vol: float,
    bud_cost_local: float,
    bud_cost_usd: float = 0,
    act_rate: float = 1.0,
    bud_rate: float = 1.0,
) -> dict:
    bud_cost_per_ship = bud_cost_local / bud_vol if bud_vol != 0 else 0
    act_cost_per_ship = act_cost_local / act_vol if act_vol != 0 else 0

    budget_cost_usd = bud_cost_local / bud_rate if bud_rate != 0 else 0
    act_cost_usd_at_act = act_cost_local / act_rate if act_rate != 0 else 0
    act_cost_usd_at_bud = act_cost_local / bud_rate if bud_rate != 0 else 0

    volume_var_usd = (act_vol - bud_vol) * bud_cost_per_ship / bud_rate if bud_rate != 0 else 0
    rate_var_usd = (act_cost_per_ship - bud_cost_per_ship) * act_vol / bud_rate if bud_rate != 0 else 0
    fx_var_usd = act_cost_usd_at_act - act_cost_usd_at_bud

    return {
        "budget_cost_usd": budget_cost_usd,
        "volume_var_usd": volume_var_usd,
        "rate_var_usd": rate_var_usd,
        "fx_var_usd": fx_var_usd,
        "actual_cost_usd": act_cost_usd_at_act,
    }


def compute_waterfall_multi(
    country_actuals: pd.DataFrame,
    budget: pd.DataFrame,
    fx: pd.DataFrame,
    metric: str = "cost",
) -> dict:
    if country_actuals.empty or budget.empty:
        return {"budget_cost_usd": 0, "volume_var_usd": 0, "rate_var_usd": 0,
                "fx_var_usd": 0, "actual_cost_usd": 0}

    col_map = {
        "cost":    ("total_cost_local",    "total_cost_usd",    "total_cost_local",    "total_cost_usd"),
        "margin":  ("total_margin_local",  "total_margin_usd",  "margin_local",        "margin_usd"),
        "revenue": ("total_revenue_local", "total_revenue_usd", "total_revenue_local", "total_revenue_usd"),
    }
    bud_local_col, bud_usd_col, act_local_col, act_usd_col = col_map.get(metric, col_map["cost"])

    fx_map = _fx_rate_map(fx)
    bud_agg = budget.groupby(["month", "country"]).agg(
        bud_vol=("forecasted_orders", "sum"),
        bud_val_local=(bud_local_col, "sum"),
    ).reset_index()
    act_agg = country_actuals.groupby(["month", "country"]).agg(
        act_vol=("volume", "sum"),
        act_val_local=(act_local_col, "sum"),
    ).reset_index()
    merged = bud_agg.merge(act_agg, on=["month", "country"], how="outer").fillna(0)

    total_budget_usd = 0.0
    total_volume_var_usd = 0.0
    total_rate_var_usd = 0.0
    total_fx_var_usd = 0.0

    for _, r in merged.iterrows():
        key = (r["month"], r["country"])
        rates = fx_map.get(key, (1.0, 1.0))
        wf = compute_waterfall(
            act_vol=r["act_vol"],
            act_cost_local=r["act_val_local"],
            bud_vol=r["bud_vol"],
            bud_cost_local=r["bud_val_local"],
            act_rate=rates[0],
            bud_rate=rates[1],
        )
        total_budget_usd += wf["budget_cost_usd"]
        total_volume_var_usd += wf["volume_var_usd"]
        total_rate_var_usd += wf["rate_var_usd"]
        total_fx_var_usd += wf["fx_var_usd"]

    act_val_usd = country_actuals[act_usd_col].sum() if act_usd_col in country_actuals.columns else 0

    return {
        "budget_cost_usd": total_budget_usd,
        "volume_var_usd": total_volume_var_usd,
        "rate_var_usd": total_rate_var_usd,
        "fx_var_usd": total_fx_var_usd,
        "actual_cost_usd": act_val_usd,
    }


def filter_data(
    data: dict,
    selected_months: list,
    selected_countries: list,
    selected_brands: list,
    selected_couriers: list,
    is_ytd: bool = False,
):
    budget = data["budget"].copy()
    fx = data["fx"].copy()
    actuals = data["actuals"].copy() if not data["actuals"].empty else pd.DataFrame()

    if selected_months:
        if is_ytd and not actuals.empty:
            ytd_months = sorted(actuals["month"].unique())
            budget = budget[budget["month"].isin(ytd_months)]
            fx = fx[fx["month"].isin(ytd_months)]
        elif not is_ytd:
            budget = budget[budget["month"].isin(selected_months)]
            fx = fx[fx["month"].isin(selected_months)]
            if not actuals.empty:
                actuals = actuals[actuals["month"].isin(selected_months)]

    if selected_countries:
        budget = budget[budget["country"].isin(selected_countries)]
        fx = fx[fx["country"].isin(selected_countries)]
        if not actuals.empty:
            actuals = actuals[actuals["country"].isin(selected_countries)]

    if selected_brands:
        budget = budget[budget["brand"].isin(selected_brands)]
        if not actuals.empty:
            actuals = actuals[actuals["brand"].isin(selected_brands)]

    if selected_couriers and not actuals.empty:
        actuals = actuals[actuals["courier"].isin(selected_couriers)]

    return {"budget": budget, "fx": fx, "actuals": actuals}


def build_brand_actuals(actuals: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    if actuals.empty:
        return pd.DataFrame()
    return aggregate_actuals(actuals, fx, ["month", "country", "brand"])


def build_courier_actuals(actuals: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    if actuals.empty:
        return pd.DataFrame()
    return aggregate_actuals(actuals, fx, ["month", "country", "courier"])


def build_country_actuals(actuals: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    if actuals.empty:
        return pd.DataFrame()
    return aggregate_actuals(actuals, fx, ["month", "country"])


def build_province_actuals(actuals: pd.DataFrame, fx: pd.DataFrame) -> pd.DataFrame:
    if actuals.empty:
        return pd.DataFrame()
    return aggregate_actuals(actuals, fx, ["month", "country", "province"])


def build_courier_brand_actuals(
    actuals: pd.DataFrame, fx: pd.DataFrame
) -> pd.DataFrame:
    if actuals.empty:
        return pd.DataFrame()
    return aggregate_actuals(actuals, fx, ["month", "country", "courier", "brand"])


def compute_kpi_row(act_row: dict, bud_row: dict) -> dict:
    act_income = act_row.get("total_revenue_usd", 0)
    act_cost = act_row.get("total_cost_usd", 0)
    act_margin = act_row.get("margin_usd", 0)
    act_vol = act_row.get("volume", 0)

    bud_income = bud_row.get("total_revenue_usd", 0)
    bud_cost = bud_row.get("total_cost_usd", 0)
    bud_margin = bud_row.get("total_margin_usd", 0)
    bud_vol = bud_row.get("forecasted_orders", 0)

    act_margin_pct = act_margin / act_income if act_income != 0 else 0
    bud_margin_pct = bud_margin / bud_income if bud_income != 0 else 0
    act_cost_per_ship = act_cost / act_vol if act_vol != 0 else 0
    bud_cost_per_ship = bud_cost / bud_vol if bud_vol != 0 else 0

    income_var = act_income - bud_income
    income_var_pct = income_var / bud_income if bud_income != 0 else 0
    cost_var = act_cost - bud_cost
    cost_var_pct = cost_var / bud_cost if bud_cost != 0 else 0
    margin_var = act_margin - bud_margin
    margin_var_pct = margin_var / abs(bud_margin) if bud_margin != 0 else 0
    vol_var = act_vol - bud_vol
    vol_var_pct = vol_var / bud_vol if bud_vol != 0 else 0
    cost_per_ship_var = act_cost_per_ship - bud_cost_per_ship
    cost_per_ship_var_pct = (
        cost_per_ship_var / bud_cost_per_ship if bud_cost_per_ship != 0 else 0
    )

    return {
        "act_income": act_income,
        "act_cost": act_cost,
        "act_margin": act_margin,
        "act_margin_pct": act_margin_pct,
        "act_vol": act_vol,
        "act_cost_per_ship": act_cost_per_ship,
        "bud_income": bud_income,
        "bud_cost": bud_cost,
        "bud_margin": bud_margin,
        "bud_margin_pct": bud_margin_pct,
        "bud_vol": bud_vol,
        "bud_cost_per_ship": bud_cost_per_ship,
        "income_var": income_var,
        "income_var_pct": income_var_pct,
        "cost_var": cost_var,
        "cost_var_pct": cost_var_pct,
        "margin_var": margin_var,
        "margin_var_pct": margin_var_pct,
        "vol_var": vol_var,
        "vol_var_pct": vol_var_pct,
        "cost_per_ship_var": cost_per_ship_var,
        "cost_per_ship_var_pct": cost_per_ship_var_pct,
    }


def merge_budget_actuals(
    brand_actuals: pd.DataFrame,
    budget: pd.DataFrame,
) -> pd.DataFrame:
    merged = budget.merge(
        brand_actuals,
        on=["month", "country", "brand"],
        how="outer",
        suffixes=("_budget", "_actual"),
        indicator=True,
    )
    return merged
