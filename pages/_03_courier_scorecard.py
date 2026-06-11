import streamlit as st
import pandas as pd
import plotly.express as px

from utils.data_loader import get_all_data
from utils.calculations import (
    filter_data, build_courier_actuals, build_courier_brand_actuals,
)
from utils.currency import resolve_currency, col_suffix, label, col_suffix_local, money_prefix
from config import COUNTRY_DISPLAY


def render(filters):
    data = get_all_data()
    fd = filter_data(
        data, filters["months"], filters["countries"], filters["brands"],
        filters["couriers"], filters["is_ytd"],
    )
    actuals = fd["actuals"]
    fx = fd["fx"]

    if actuals.empty:
        st.warning("No actuals data for selected filters.")
        return

    courier_act = build_courier_actuals(actuals, fx)
    currency = filters["currency"]
    cur = resolve_currency(currency)
    suff = col_suffix(currency)
    cur_label = label(currency)
    p = money_prefix(currency)

    st.markdown("### Courier Scorecard")

    scorecard_rows = []
    for _, row in courier_act.iterrows():
        volume = row["volume"]
        income = row[f"total_revenue{suff}"]
        cost = row[f"total_cost{suff}"]
        margin = income - cost
        margin_pct = margin / income if income else 0
        cost_per_ship = cost / volume if volume else 0

        entry = {
            "Country": COUNTRY_DISPLAY.get(row["country"], row["country"]),
            "Courier": row["courier"].title(),
            "Volume": int(volume),
            f"Income ({cur_label})": income,
            f"Cost ({cur_label})": cost,
            f"Margin ({cur_label})": margin,
            "Margin %": margin_pct,
            "Cost/Ship": cost_per_ship,
        }
        if currency == "Both":
            income_l = row["total_revenue_local"]
            cost_l = row["total_cost_local"]
            margin_l = income_l - cost_l
            entry["Income (Local)"] = income_l
            entry["Cost (Local)"] = cost_l
            entry["Margin (Local)"] = margin_l

        scorecard_rows.append(entry)

    scorecard = pd.DataFrame(scorecard_rows)
    if scorecard.empty:
        st.info("No scorecard data.")
        return

    scorecard["Country Median Cost/Ship"] = scorecard.groupby("Country")["Cost/Ship"].transform("median")
    scorecard["Cost Var % vs Median"] = ((scorecard["Cost/Ship"] - scorecard["Country Median Cost/Ship"])
                                         / scorecard["Country Median Cost/Ship"].replace(0, 1))

    display_cols = ["Country", "Courier", "Volume", f"Income ({cur_label})", f"Cost ({cur_label})",
                    f"Margin ({cur_label})", "Cost/Ship", "Margin %", "Country Median Cost/Ship", "Cost Var % vs Median"]
    if currency == "Both":
        both_cols = []
        for c in display_cols:
            both_cols.append(c)
            if c.startswith("Income"):
                both_cols.append("Income (Local)")
            elif c.startswith("Cost (") and "Local" not in c:
                both_cols.append("Cost (Local)")
            elif c.startswith("Margin (") and "Local" not in c:
                both_cols.append("Margin (Local)")
        # Deduplicate
        seen = set()
        uniq = []
        for c in both_cols:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        display_cols = uniq

    display_df = scorecard[[c for c in display_cols if c in scorecard.columns]].copy()

    fmt_map = {
        "Volume": "{:,.0f}",
        "Cost/Ship": f"{p}{{:,.2f}}",
        "Margin %": "{:.1%}",
        "Country Median Cost/Ship": f"{p}{{:,.2f}}",
        "Cost Var % vs Median": "{:+.1%}",
    }
    for c in display_df.columns:
        if "Income" in c or "Cost" in c or "Margin" in c:
            if "Local" in c:
                fmt_map[c] = "{:,.0f}"
            else:
                fmt_map[c] = f"{p}{{:,.0f}}"

    styler = display_df.style.format(fmt_map)
    if "Cost Var % vs Median" in display_df.columns:
        styler = styler.applymap(
            lambda v: "color: #1b8a3d" if isinstance(v, (int, float)) and v < 0
            else ("color: #c0392b" if isinstance(v, (int, float)) and v > 0 else ""),
            subset=["Cost Var % vs Median"],
        )
    st.dataframe(styler, use_container_width=True, hide_index=True)

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Courier Ranking — Avg Cost/Ship**")
        avg_cps = scorecard.groupby("Courier")["Cost/Ship"].mean().sort_values().reset_index()
        fig = px.bar(avg_cps, x="Cost/Ship", y="Courier", orientation="h", color="Cost/Ship",
                     color_continuous_scale="RdYlGn_r", title="Courier Ranking by Avg Cost/Ship")
        fig.update_layout(height=350, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Country Cost/Ship Distribution**")
        fig = px.box(scorecard, x="Country", y="Cost/Ship", color="Country",
                     title="Cost/Ship Distribution by Country", points="all")
        fig.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    csv = scorecard.to_csv(index=False).encode("utf-8")
    st.download_button(label="📥 Export Scorecard CSV", data=csv,
                       file_name=f"courier_scorecard_{cur_label}.csv", mime="text/csv")

    with st.expander("Courier × Brand Detail", expanded=False):
        cb_act = build_courier_brand_actuals(actuals, fx)
        if not cb_act.empty:
            detail_cols = ["country", "courier", "brand", "volume",
                           f"total_revenue{suff}", f"total_cost{suff}"]
            detail = cb_act[detail_cols].copy()
            detail[f"margin_{cur.lower()}"] = detail[f"total_revenue{suff}"] - detail[f"total_cost{suff}"]
            detail["country"] = detail["country"].map(COUNTRY_DISPLAY)
            rename = {"country": "Country", "courier": "Courier", "brand": "Brand", "volume": "Volume",
                      f"total_revenue{suff}": f"Income ({cur_label})", f"total_cost{suff}": f"Cost ({cur_label})",
                      f"margin_{cur.lower()}": f"Margin ({cur_label})"}
            detail = detail.rename(columns=rename)
            detail = detail.sort_values(["Country", "Courier", "Brand"])
            sub_fmt = {c: f"{p}{{:,.2f}}" if "Income" in c or "Cost" in c or "Margin" in c else "{:,.0f}" for c in detail.columns if c not in ("Country", "Courier", "Brand")}
            if currency == "Local":
                sub_fmt = {c: "{:,.2f}" if "Income" in c or "Cost" in c or "Margin" in c else "{:,.0f}" for c in sub_fmt}
            st.dataframe(detail.style.format(sub_fmt), use_container_width=True, hide_index=True)
