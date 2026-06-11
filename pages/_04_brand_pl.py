import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils.data_loader import get_all_data
from utils.calculations import filter_data, build_brand_actuals, compute_kpi_row
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

    brand_act = build_brand_actuals(actuals, fx)
    currency = filters["currency"]
    cur = resolve_currency(currency)
    suff = col_suffix(currency)
    cur_label = label(currency)
    p = money_prefix(currency)

    st.markdown("### Brand P&L")

    available_brands = sorted(set(brand_act["brand"].unique()) | set(budget["brand"].unique()))
    sel_brands = st.multiselect("Select Brands", available_brands,
                                default=available_brands[: min(5, len(available_brands))])
    if not sel_brands:
        st.info("Select at least one brand.")
        return

    mask_act = brand_act["brand"].isin(sel_brands)
    mask_bud = budget["brand"].isin(sel_brands)
    b_act = brand_act[mask_act] if not brand_act.empty else pd.DataFrame()
    b_bud = budget[mask_bud] if not budget.empty else pd.DataFrame()

    agg_act = b_act.groupby("brand").agg(
        volume=("volume", "sum"),
        total_revenue=(f"total_revenue{suff}", "sum"),
        total_cost=(f"total_cost{suff}", "sum"),
    ).reset_index() if not b_act.empty else pd.DataFrame()
    agg_act["margin"] = agg_act["total_revenue"] - agg_act["total_cost"]

    bud_rev_col = f"total_revenue_{cur.lower()}"
    bud_cost_col = f"total_cost_{cur.lower()}"
    bud_mar_col = f"total_margin_{cur.lower()}"
    agg_bud = b_bud.groupby("brand").agg(
        forecasted_orders=("forecasted_orders", "sum"),
        total_revenue=(bud_rev_col, "sum"),
        total_cost=(bud_cost_col, "sum"),
        total_margin=(bud_mar_col, "sum"),
    ).reset_index() if not b_bud.empty else pd.DataFrame()

    # If budget doesn't have the currency-specific columns, fall back
    if agg_bud.empty and not b_bud.empty:
        agg_bud = b_bud.groupby("brand").agg(
            forecasted_orders=("forecasted_orders", "sum"),
            total_revenue=("total_revenue_usd", "sum"),
            total_cost=("total_cost_usd", "sum"),
            total_margin=("total_margin_usd", "sum"),
        ).reset_index()

    pl_rows = []
    all_brands = sorted(set(agg_act["brand"].unique()) | set(agg_bud["brand"].unique())) if not agg_bud.empty else agg_act["brand"].unique().tolist()
    for brand in all_brands:
        a = agg_act[agg_act["brand"] == brand]
        b = agg_bud[agg_bud["brand"] == brand]
        act_d = a.iloc[0].to_dict() if not a.empty else {"volume": 0, "total_revenue": 0, "total_cost": 0, "margin": 0}
        bud_d = b.iloc[0].to_dict() if not b.empty else {"forecasted_orders": 0, "total_revenue": 0, "total_cost": 0, "total_margin": 0}

        pl_rows.append({
            "Brand": brand,
            f"Act Income ({cur_label})": act_d["total_revenue"],
            f"Bud Income ({cur_label})": bud_d["total_revenue"],
            "Income Var": act_d["total_revenue"] - bud_d["total_revenue"],
            "Income Var %": (act_d["total_revenue"] - bud_d["total_revenue"]) / bud_d["total_revenue"] if bud_d["total_revenue"] else 0,
            f"Act Cost ({cur_label})": act_d["total_cost"],
            f"Bud Cost ({cur_label})": bud_d["total_cost"],
            "Cost Var": act_d["total_cost"] - bud_d["total_cost"],
            "Cost Var %": (act_d["total_cost"] - bud_d["total_cost"]) / bud_d["total_cost"] if bud_d["total_cost"] else 0,
            f"Act Margin ({cur_label})": act_d["margin"],
            f"Bud Margin ({cur_label})": bud_d["total_margin"],
            "Margin Var": act_d["margin"] - bud_d["total_margin"],
            "Margin Var %": (act_d["margin"] - bud_d["total_margin"]) / abs(bud_d["total_margin"]) if bud_d["total_margin"] else 0,
            "Act Margin %": act_d["margin"] / act_d["total_revenue"] if act_d["total_revenue"] else 0,
            "Bud Margin %": bud_d["total_margin"] / bud_d["total_revenue"] if bud_d["total_revenue"] else 0,
        })

    pl_df = pd.DataFrame(pl_rows)

    fmt_dict = {
        f"Act Income ({cur_label})": f"{p}{{:,.0f}}",
        f"Bud Income ({cur_label})": f"{p}{{:,.0f}}",
        "Income Var": f"{p}{{:+,.0f}}",
        "Income Var %": "{:+.1%}",
        f"Act Cost ({cur_label})": f"{p}{{:,.0f}}",
        f"Bud Cost ({cur_label})": f"{p}{{:,.0f}}",
        "Cost Var": f"{p}{{:+,.0f}}",
        "Cost Var %": "{:+.1%}",
        f"Act Margin ({cur_label})": f"{p}{{:,.0f}}",
        f"Bud Margin ({cur_label})": f"{p}{{:,.0f}}",
        "Margin Var": f"{p}{{:+,.0f}}",
        "Margin Var %": "{:+.1%}",
        "Act Margin %": "{:.1%}",
        "Bud Margin %": "{:.1%}",
    }
    if currency == "Local":
        fmt_dict = {k: v.replace("$", "") for k, v in fmt_dict.items()}

    var_cols = ["Income Var", "Income Var %", "Cost Var", "Cost Var %", "Margin Var", "Margin Var %"]
    styler = pl_df.style.format(fmt_dict).applymap(
        lambda v: "color: #1b8a3d" if isinstance(v, (int, float)) and v > 0
        else ("color: #c0392b" if isinstance(v, (int, float)) and v < 0 else ""),
        subset=var_cols,
    )
    st.dataframe(styler, use_container_width=True, hide_index=True)

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Contribution Waterfall — Margin Variance by Brand**")
        if not pl_df.empty:
            total_mv = pl_df["Margin Var"].sum()
            bars = []
            for _, r in pl_df.iterrows():
                bars.append(go.Bar(name=r["Brand"], x=[r["Brand"]], y=[r["Margin Var"]],
                                  text=f"{p}{r['Margin Var']:+,.0f}", textposition="outside",
                                  marker_color="#1b8a3d" if r["Margin Var"] >= 0 else "#c0392b"))
            fig = go.Figure(data=bars)
            fig.add_hline(y=total_mv, line_dash="dash", line_color="gray",
                          annotation_text=f"Total: {p}{total_mv:+,.0f}")
            fig.update_layout(title=f"Each Brand's Margin Var → Total ({cur_label})", height=350,
                              showlegend=False, yaxis_title=f"Margin Variance ({cur_label})")
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Monthly Margin % Trend**")
        if filters["is_ytd"] and not b_act.empty and not b_bud.empty:
            months = sorted(b_act["month"].unique())
            trend = []
            for m in months:
                m_act = b_act[b_act["month"] == m]
                m_bud = b_bud[b_bud["month"] == m]
                for brand in sel_brands:
                    ba = m_act[m_act["brand"] == brand]
                    bb = m_bud[m_bud["brand"] == brand]
                    if not ba.empty and not bb.empty:
                        a = ba.iloc[0]
                        b = bb.iloc[0]
                        act_mar = a["margin_usd"]
                        act_inc = a["total_revenue_usd"]
                        bud_mar = b.get("total_margin_usd", 0)
                        bud_inc = b.get("total_revenue_usd", 0)
                        trend.append({
                            "month": m, "brand": brand,
                            "act_margin_pct": act_mar / act_inc if act_inc else 0,
                            "bud_margin_pct": bud_mar / bud_inc if bud_inc else 0,
                        })
            if trend:
                fig = px.line(pd.DataFrame(trend), x="month", y="act_margin_pct", color="brand",
                              markers=True, title="Actual Margin % Trend",
                              labels={"month": "Month", "act_margin_pct": "Margin %", "brand": "Brand"})
                fig.update_layout(height=350)
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Select YTD and multiple months to see trend.")

    st.markdown("---")

    with st.expander("Brand × Country Detail", expanded=False):
        if not b_act.empty:
            detail = b_act[b_act["brand"].isin(sel_brands)][
                ["country", "brand", "volume", f"total_revenue{suff}", f"total_cost{suff}"]
            ].copy()
            detail[f"margin_{cur.lower()}"] = detail[f"total_revenue{suff}"] - detail[f"total_cost{suff}"]
            detail["country"] = detail["country"].map(COUNTRY_DISPLAY)
            detail = detail.rename(columns={
                "country": "Country", "brand": "Brand", "volume": "Volume",
                f"total_revenue{suff}": f"Revenue ({cur_label})",
                f"total_cost{suff}": f"Cost ({cur_label})",
                f"margin_{cur.lower()}": f"Margin ({cur_label})",
            })
            detail = detail.sort_values(["Brand", "Country"])
            dfmt = {c: f"{p}{{:,.2f}}" if "Revenue" in c or "Cost" in c or "Margin" in c else "{:,.0f}" for c in detail.columns if c not in ("Country", "Brand")}
            if currency == "Local":
                dfmt = {c: "{:,.2f}" if "Revenue" in c or "Cost" in c or "Margin" in c else "{:,.0f}" for c in dfmt}
            st.dataframe(detail.style.format(dfmt), use_container_width=True, hide_index=True)
