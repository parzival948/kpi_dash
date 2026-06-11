import streamlit as st
import pandas as pd
import plotly.express as px

from utils.data_loader import get_all_data
from utils.calculations import (
    filter_data,
    build_country_actuals,
    build_brand_actuals,
    compute_waterfall_multi,
)
from utils.components import kpi_card, render_waterfall, create_diverging_bar
from utils.currency import resolve_currency, col_suffix, label, fmt_money, pick_col, money_prefix
from config import COUNTRY_DISPLAY


def render(filters):
    data = get_all_data()
    fd = filter_data(
        data, filters["months"], filters["countries"], filters["brands"],
        filters["couriers"], filters["is_ytd"],
    )
    actuals = fd["actuals"]
    budget = fd["budget"]
    fx = fd["fx"]

    if actuals.empty and budget.empty:
        st.warning("No data for selected filters.")
        return

    country_act = build_country_actuals(actuals, fx)
    brand_act = build_brand_actuals(actuals, fx)
    currency = filters["currency"]
    cur = resolve_currency(currency)
    suff = col_suffix(currency)
    cur_label = label(currency)

    st.markdown("### Executive Summary")

    kpi_cols = st.columns(6)
    row = {}

    if not country_act.empty and not budget.empty:
        tot_vol = int(country_act["volume"].sum())
        tot_income = country_act[f"total_revenue{suff}"].sum()
        tot_cost = country_act[f"total_cost{suff}"].sum()
        tot_margin = tot_income - tot_cost
        tot_margin_pct = tot_margin / tot_income if tot_income != 0 else 0
        tot_cost_per_ship = tot_cost / tot_vol if tot_vol else 0

        bud_inc_col = f"total_revenue_{cur.lower()}"
        bud_cost_col = f"total_cost_{cur.lower()}"
        bud_mar_col = f"total_margin_{cur.lower()}"
        if currency == "Local":
            bud_inc_col = "total_revenue_local"
            bud_cost_col = "total_cost_local"
            bud_mar_col = "total_margin_local"

        bud_tot_vol = int(budget["forecasted_orders"].sum())
        bud_tot_income = budget[bud_inc_col].sum() if bud_inc_col in budget else budget["total_revenue_usd"].sum()
        bud_tot_cost = budget[bud_cost_col].sum() if bud_cost_col in budget else budget["total_cost_usd"].sum()
        bud_tot_margin = budget[bud_mar_col].sum() if bud_mar_col in budget else budget["total_margin_usd"].sum()
        bud_cost_per_ship = bud_tot_cost / bud_tot_vol if bud_tot_vol else 0

        income_var = tot_income - bud_tot_income
        income_var_pct = income_var / bud_tot_income if bud_tot_income else 0
        cost_var = tot_cost - bud_tot_cost
        cost_var_pct = cost_var / bud_tot_cost if bud_tot_cost else 0
        margin_var = tot_margin - bud_tot_margin
        margin_var_pct = margin_var / abs(bud_tot_margin) if bud_tot_margin else 0
        vol_var = tot_vol - bud_tot_vol
        vol_var_pct = vol_var / bud_tot_vol if bud_tot_vol else 0
        cps_var = tot_cost_per_ship - bud_cost_per_ship
        cps_var_pct = cps_var / bud_cost_per_ship if bud_cost_per_ship else 0

        p = money_prefix(currency)
        row = {
            "Income": (f"{p}{tot_income:,.0f}", f"{income_var_pct:+.1%} / {p}{income_var:+,.0f}"),
            "Cost": (f"{p}{tot_cost:,.0f}", f"{cost_var_pct:+.1%} / {p}{cost_var:+,.0f}"),
            "Margin": (f"{p}{tot_margin:,.0f}", f"{margin_var_pct:+.1%} / {p}{margin_var:+,.0f}"),
            "Margin %": (f"{tot_margin_pct:.1%}", f"{(tot_margin_pct - (bud_tot_margin/bud_tot_income if bud_tot_income else 0)):+.1%}"),
            "Volume": (f"{tot_vol:,}", f"{vol_var_pct:+.1%} / {vol_var:+,}"),
            "Cost/Ship": (f"{p}{tot_cost_per_ship:.2f}", f"{cps_var_pct:+.1%} / {p}{cps_var:+,.2f}"),
        }
    else:
        row = {k: ("—", "") for k in ["Income", "Cost", "Margin", "Margin %", "Volume", "Cost/Ship"]}

    for i, (k, (v, d)) in enumerate(row.items()):
        with kpi_cols[i]:
            kpi_card(k, v, d)

    # DOL row
    dol_cols = st.columns([1, 1, 1, 1, 1, 1])
    if not country_act.empty and not budget.empty and vol_var_pct != 0:
        dol = margin_var_pct / vol_var_pct
        dol_label = f"{dol:.2f}x"
        dol_desc = "Leveraged" if abs(dol) > 2 else "Moderate" if abs(dol) > 1 else "Low"
        with dol_cols[0]:
            kpi_card("DOL (ΔMargin% / ΔVolume%)", dol_label, dol_desc)
    else:
        with dol_cols[0]:
            kpi_card("DOL (ΔMargin% / ΔVolume%)", "—", "")

    # Also show dual values when "Both"
    if currency == "Both":
        kpi_cols2 = st.columns(6)
        if not country_act.empty and not budget.empty:
            inc_l = country_act["total_revenue_local"].sum()
            cost_l = country_act["total_cost_local"].sum()
            mar_l = inc_l - cost_l
            cps_l = cost_l / tot_vol if tot_vol else 0
            bud_inc_b = budget["total_revenue_local"].sum()
            bud_cost_b = budget["total_cost_local"].sum()
            bud_mar_b = budget["total_margin_local"].sum()
            bud_cps_b = bud_cost_b / bud_tot_vol if bud_tot_vol else 0

            dual = {
                "Income": (f"${inc_l:,.0f} LC", f"{(inc_l-bud_inc_b)/bud_inc_b:+.1%}" if bud_inc_b else "—"),
                "Cost": (f"${cost_l:,.0f} LC", f"{(cost_l-bud_cost_b)/bud_cost_b:+.1%}" if bud_cost_b else "—"),
                "Margin": (f"${mar_l:,.0f} LC", f"{(mar_l-bud_mar_b)/abs(bud_mar_b):+.1%}" if bud_mar_b else "—"),
                "Margin %": (f"{mar_l/inc_l:.1%}" if inc_l else "—", ""),
                "Volume": ("", ""),
                "Cost/Ship": (f"${cps_l:.2f} LC", f"{(cps_l-bud_cps_b)/bud_cps_b:+.1%}" if bud_cps_b else "—"),
            }
            for i, (k, (v, d)) in enumerate(dual.items()):
                with kpi_cols2[i]:
                    kpi_card(k, v, d)

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        if not country_act.empty and not budget.empty:
            wf_cost = compute_waterfall_multi(country_act, budget, fx, metric="cost")
            st.plotly_chart(
                render_waterfall(wf_cost, f"Cost Waterfall ({cur_label})"),
                use_container_width=True,
            )

    with col2:
        if not country_act.empty and not budget.empty:
            wf_margin = compute_waterfall_multi(country_act, budget, fx, metric="margin")
            st.plotly_chart(
                render_waterfall(wf_margin, f"Margin Waterfall ({cur_label})"),
                use_container_width=True,
            )

    if not brand_act.empty and not budget.empty:
        margin_col = f"total_margin_{cur.lower()}"
        rev_col = f"total_revenue_{cur.lower()}"
        cost_col = f"total_cost_{cur.lower()}"
        merged = budget.groupby("brand", as_index=False).agg(
            {rev_col: "sum", cost_col: "sum", margin_col: "sum", "forecasted_orders": "sum"}
        )
        act_brand = brand_act.groupby("brand", as_index=False).agg(
            {f"total_revenue{suff}": "sum", f"total_cost{suff}": "sum", f"margin{suff}": "sum", "volume": "sum"}
        )
        merged = merged.merge(act_brand, on="brand", how="inner")
        merged["margin_var_pct"] = (merged[f"margin{suff}"] - merged[margin_col]) / merged[margin_col].abs()
        merged = merged.sort_values("margin_var_pct", ascending=False)
        extremes = pd.concat([merged.head(5), merged.tail(5)])
        st.plotly_chart(
            create_diverging_bar(extremes, x_col="margin_var_pct", y_col="brand", title="Top/Bottom 5 Brands by Margin Variance %", limit=10),
            use_container_width=True,
        )

    st.markdown("---")
    col3, col4 = st.columns(2)

    with col3:
        if not actuals.empty:
            treemap_df = actuals.groupby(["country", "courier"], observed=True).agg(total_cost_local=("total_cost_local", "sum")).reset_index()
            fig_tm = px.treemap(treemap_df, path=["country", "courier"], values="total_cost_local", color="total_cost_local",
                                color_continuous_scale="RdYlGn_r", title="Courier Cost Treemap (Local Currency)")
            fig_tm.update_traces(textinfo="label+value+percent root")
            fig_tm.update_layout(height=350, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_tm, use_container_width=True)

    with col4:
        if not country_act.empty and not budget.empty:
            ccy = cur.lower()
            bud_cols = {f"bud_vol": ("forecasted_orders", "sum"), f"bud_cost": (f"total_cost_{ccy}", "sum"),
                        f"bud_income": (f"total_revenue_{ccy}", "sum"), f"bud_margin": (f"total_margin_{ccy}", "sum")}
            bud_by = budget.groupby("country").agg(**{k: v for k, v in bud_cols.items()}).reset_index()
            act_by = country_act.groupby("country").agg(
                act_vol=("volume", "sum"), act_cost=(f"total_cost{suff}", "sum"), act_income=(f"total_revenue{suff}", "sum")
            ).reset_index()
            merged_c = bud_by.merge(act_by, on="country", how="outer").fillna(0)
            p = money_prefix(currency)

            summary_data = []
            for _, r in merged_c.iterrows():
                am = r["act_income"] - r["act_cost"]
                bm = r.get("bud_margin", 0)
                mv = am - bm
                mvp = mv / abs(bm) if bm else 0
                vv = r["act_vol"] - r["bud_vol"]
                vvp = vv / r["bud_vol"] if r["bud_vol"] else 0
                cv = r["act_cost"] - r["bud_cost"]
                cvp = cv / r["bud_cost"] if r["bud_cost"] else 0
                mp = am / r["act_income"] if r["act_income"] else 0
                cps = r["act_cost"] / r["act_vol"] if r["act_vol"] else 0
                summary_data.append({
                    "Country": COUNTRY_DISPLAY.get(r["country"], r["country"]),
                    "Volume": f"{int(r['act_vol']):,}", "Vol Var %": f"{vvp:+.1%}",
                    f"Income ({cur_label})": f"{p}{r['act_income']:,.0f}",
                    f"Cost ({cur_label})": f"{p}{r['act_cost']:,.0f}", "Cost Var %": f"{cvp:+.1%}",
                    f"Margin ({cur_label})": f"{p}{am:,.0f}", "Margin %": f"{mp:.1%}", "Margin Var %": f"{mvp:+.1%}",
                    f"Cost/Ship ({cur_label})": f"{p}{cps:.2f}",
                })
            st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

    st.markdown("---")

    if not country_act.empty:
        with st.expander("Country Detail Table (with gradient)", expanded=False):
            detail = country_act.groupby("country").agg(
                Volume=("volume", "sum"),
                **{f"Cost ({cur_label})": (f"total_cost{suff}", "sum"),
                   f"Revenue ({cur_label})": (f"total_revenue{suff}", "sum"),
                   f"Margin ({cur_label})": (f"margin{suff}", "sum")}
            ).reset_index()
            detail["Country"] = detail["country"].map(COUNTRY_DISPLAY)
            detail = detail.drop(columns=["country"]).set_index("Country")
            for col in detail.select_dtypes("number").columns:
                detail[col] = detail[col].map("{:,.0f}".format)
            st.dataframe(detail, use_container_width=True)
