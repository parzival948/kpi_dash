import streamlit as st
import pandas as pd
import plotly.express as px

from utils.data_loader import get_all_data
from utils.calculations import (
    filter_data, build_country_actuals, build_courier_actuals,
    build_brand_actuals, build_province_actuals, compute_waterfall_multi,
)
from utils.components import render_waterfall
from utils.currency import resolve_currency, col_suffix, label, money_prefix
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

    available_countries = sorted(set(actuals["country"].unique()) | set(budget["country"].unique()))
    sel_country = st.selectbox("Select Country", available_countries,
                               format_func=lambda c: COUNTRY_DISPLAY.get(c, c))
    st.markdown(f"### Country Deep Dive — {COUNTRY_DISPLAY.get(sel_country, sel_country)}")

    mask_act = actuals["country"] == sel_country
    mask_bud = budget["country"] == sel_country
    c_actuals = actuals[mask_act].copy() if not actuals.empty else pd.DataFrame()
    c_budget = budget[mask_bud].copy() if not budget.empty else pd.DataFrame()

    if c_actuals.empty and c_budget.empty:
        st.info(f"No data for {sel_country}.")
        return

    c_fx = fx[fx["country"] == sel_country].copy() if not fx.empty else pd.DataFrame()
    c_country_act = build_country_actuals(c_actuals, c_fx)
    c_courier_act = build_courier_actuals(c_actuals, c_fx)
    c_brand_act = build_brand_actuals(c_actuals, c_fx)
    c_province_act = build_province_actuals(c_actuals, c_fx)

    currency = filters["currency"]
    cur = resolve_currency(currency)
    suff = col_suffix(currency)
    cur_label = label(currency)
    p = money_prefix(currency)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Cost Waterfall**")
        if not c_country_act.empty and not c_budget.empty:
            wf = compute_waterfall_multi(c_country_act, c_budget, c_fx, metric="cost")
            st.plotly_chart(render_waterfall(wf, f"Cost Waterfall — {COUNTRY_DISPLAY.get(sel_country, sel_country)} ({cur_label})"),
                            use_container_width=True)

    with col2:
        st.markdown("**Income Waterfall**")
        if not c_country_act.empty and not c_budget.empty:
            wf_inc = compute_waterfall_multi(c_country_act, c_budget, c_fx, metric="revenue")
            st.plotly_chart(render_waterfall(wf_inc, f"Income Waterfall — {COUNTRY_DISPLAY.get(sel_country, sel_country)} ({cur_label})"),
                            use_container_width=True)

    st.markdown("---")

    st.markdown("**Courier Breakdown (Income / Cost / Margin)**")
    if not c_courier_act.empty:
        val_cols = [f"total_revenue{suff}", f"total_cost{suff}", f"margin{suff}"]
        label_map = {f"total_revenue{suff}": "Income", f"total_cost{suff}": "Cost", f"margin{suff}": "Margin"}
        courier_chart = c_courier_act.melt(id_vars=["courier"], value_vars=val_cols, var_name="metric", value_name="val")
        courier_chart["metric"] = courier_chart["metric"].map(label_map)
        fig = px.bar(courier_chart, x="courier", y="val", color="metric", barmode="group",
                     title=f"Income / Cost / Margin per Courier ({cur_label})",
                     color_discrete_map={"Income": "#2ecc71", "Cost": "#e74c3c", "Margin": "#3498db"})
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    col3, col4 = st.columns(2)

    with col3:
        st.markdown("**Brand Scatter: Volume Var % vs Cost Var %**")
        if not c_brand_act.empty and not c_budget.empty:
            bud_agg = c_budget.groupby("brand").agg(
                bud_vol=("forecasted_orders", "sum"),
                bud_cost=(f"total_cost_{cur.lower()}", "sum"),
            ).reset_index()
            act_agg = c_brand_act.groupby("brand").agg(
                act_vol=("volume", "sum"),
                act_cost=(f"total_cost{suff}", "sum"),
            ).reset_index()
            merged_b = bud_agg.merge(act_agg, on="brand", how="inner")
            merged_b["vol_var_pct"] = (merged_b["act_vol"] - merged_b["bud_vol"]) / merged_b["bud_vol"].replace(0, 1)
            merged_b["cost_var_pct"] = (merged_b["act_cost"] - merged_b["bud_cost"]) / merged_b["bud_cost"].replace(0, 1)
            fig = px.scatter(merged_b, x="vol_var_pct", y="cost_var_pct", size="act_vol", text="brand",
                             title=f"Volume Var % vs Cost Var % ({cur_label})",
                             labels={"vol_var_pct": "Volume Variance %", "cost_var_pct": "Cost Variance %"},
                             size_max=30, color="cost_var_pct", color_continuous_scale="RdYlGn_r")
            fig.add_hline(y=0, line_dash="dash", line_color="gray")
            fig.add_vline(x=0, line_dash="dash", line_color="gray")
            fig.update_traces(textposition="top center")
            fig.update_layout(height=350)
            st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.markdown("**Province Cost/Ship**")
        if not c_province_act.empty:
            c_province_act["cost_per_ship"] = c_province_act[f"total_cost{suff}"] / c_province_act["volume"].replace(0, 1)
            top_provs = c_province_act.sort_values("volume", ascending=False).head(20)
            fig = px.bar(top_provs, x="cost_per_ship", y="province", orientation="h", color="cost_per_ship",
                         color_continuous_scale="RdYlGn_r",
                         title=f"Cost/Ship by Province ({cur_label})")
            fig.update_layout(height=350, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    st.markdown("**Province Detail Table**")
    if not c_province_act.empty:
        show_cols = ["province", "volume", f"total_cost{suff}", f"total_revenue{suff}"]
        rename_map = {"province": "Province", "volume": "Volume",
                      f"total_cost{suff}": f"Cost ({cur_label})",
                      f"total_revenue{suff}": f"Revenue ({cur_label})"}
        if f"margin{suff}" in c_province_act.columns:
            show_cols.append(f"margin{suff}")
            rename_map[f"margin{suff}"] = f"Margin ({cur_label})"

        detail_df = c_province_act[show_cols].copy().rename(columns=rename_map)
        detail_df = detail_df.sort_values("Volume", ascending=False)
        num_cols = [c for c in detail_df.columns if c != "Province"]
        for col in num_cols:
            if "Cost" in col or "Revenue" in col or "Margin" in col:
                detail_df[col] = detail_df[col].map(f"{p}{{:.2f}}".format if not currency == "Local" else "{:.2f}".format)
            else:
                detail_df[col] = detail_df[col].map("{:,.0f}".format)
        st.dataframe(detail_df, use_container_width=True, hide_index=True)
