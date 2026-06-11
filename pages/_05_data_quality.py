import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from utils.data_loader import get_all_data
from utils.calculations import filter_data, build_brand_actuals
from config import COUNTRY_DISPLAY


def render(filters):
    data = get_all_data()
    fd = filter_data(
        data,
        filters["months"],
        filters["countries"],
        filters["brands"],
        filters["couriers"],
        filters["is_ytd"],
    )

    actuals = fd["actuals"]
    budget = fd["budget"]
    fx = fd["fx"]

    st.markdown("### Data Quality & Reconciliation")

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
        [
            "Coverage Matrix",
            "Budget ↔ Actuals",
            "FX Rates",
            "Duplicate Orders",
            "Field Audit",
            "Volume Recon",
        ]
    )

    # ---- Tab 1: Coverage Matrix ----
    with tab1:
        st.markdown("**Country × Courier Shipment Counts (Heatmap)**")
        if not actuals.empty:
            coverage = (
                actuals.groupby(["country", "courier"], observed=True)
                .size()
                .reset_index(name="shipments")
            )
            pivot = coverage.pivot(
                index="country", columns="courier", values="shipments"
            ).fillna(0)
            pivot.index = pivot.index.map(COUNTRY_DISPLAY)

            fig = px.imshow(
                pivot,
                text_auto=".0f",
                color_continuous_scale="Blues",
                aspect="auto",
                title="Shipment Count: Country × Courier",
            )
            fig.update_layout(height=300)
            st.plotly_chart(fig, width="stretch")

            pmax = pivot.values.max()
            st.dataframe(
                pivot.style.format("{:,.0f}").applymap(
                    lambda v: f"background-color: rgba(0,0,255,{min(v/pmax, 0.8)})" if pmax > 0 else "",
                ),
                width="stretch",
            )

    # ---- Tab 2: Budget ↔ Actuals Reconciliation ----
    with tab2:
        st.markdown("**Budget ↔ Actuals Brand Reconciliation**")
        if not actuals.empty and not budget.empty:
            brand_act = build_brand_actuals(actuals, fx)

            bud_brands = set(budget["brand"].unique())
            act_brands = set(brand_act["brand"].unique())
            matched = bud_brands & act_brands
            budget_only = bud_brands - act_brands
            actuals_only = act_brands - bud_brands

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Matched", len(matched))
            col_b.metric("Budget Only", len(budget_only))
            col_c.metric("Actuals Only", len(actuals_only))

            if budget_only:
                st.warning(f"Brands in budget but missing in actuals: {', '.join(sorted(budget_only))}")
            if actuals_only:
                st.info(f"Brands in actuals but missing in budget: {', '.join(sorted(actuals_only))}")

            # Volume reconciliation
            merged = budget.groupby("brand", as_index=False).agg(
                bud_vol=("forecasted_orders", "sum"),
                bud_revenue=("total_revenue_usd", "sum"),
                bud_cost=("total_cost_usd", "sum"),
            )
            act_agg = brand_act.groupby("brand", as_index=False).agg(
                act_vol=("volume", "sum"),
                act_revenue=("total_revenue_usd", "sum"),
                act_cost=("total_cost_usd", "sum"),
            )
            recon = merged.merge(act_agg, on="brand", how="outer").fillna(0)
            recon["_merge"] = recon.apply(
                lambda r: "Both"
                if r["brand"] in matched
                else ("Budget" if r["brand"] in budget_only else "Actuals"),
                axis=1,
            )
            recon = recon.rename(
                columns={
                    "brand": "Brand",
                    "bud_vol": "Budget Vol",
                    "act_vol": "Actual Vol",
                    "bud_revenue": "Budget Revenue",
                    "act_revenue": "Actual Revenue",
                    "bud_cost": "Budget Cost",
                    "act_cost": "Actual Cost",
                    "_merge": "Source",
                }
            )
            st.dataframe(
                recon.style.format(
                    {
                        "Budget Vol": "{:,.0f}",
                        "Actual Vol": "{:,.0f}",
                        "Budget Revenue": "${:,.2f}",
                        "Actual Revenue": "${:,.2f}",
                        "Budget Cost": "${:,.2f}",
                        "Actual Cost": "${:,.2f}",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
        else:
            st.info("Load actuals and budget to see reconciliation.")

    # ---- Tab 3: FX Rate Table ----
    with tab3:
        st.markdown("**FX Rate Table — Actual vs Budget**")
        if not fx.empty:
            fx_display = fx.copy()
            fx_display["country"] = fx_display["country"].map(COUNTRY_DISPLAY)
            fx_display["variance_pct"] = (
                fx_display["actual_rate"] - fx_display["budget_rate"]
            ) / fx_display["budget_rate"].replace(0, 1)
            fx_display["flag"] = fx_display["variance_pct"].abs() > 0.05
            fx_display = fx_display.rename(
                columns={
                    "month": "Month",
                    "country": "Country",
                    "currency_code": "Currency",
                    "actual_rate": "Actual Rate",
                    "budget_rate": "Budget Rate",
                    "variance_pct": "Variance %",
                }
            )

            st.dataframe(
                fx_display.style.format(
                    {
                        "Actual Rate": "{:.6f}",
                        "Budget Rate": "{:.6f}",
                        "Variance %": "{:+.2%}",
                    }
                ).applymap(
                    lambda v: "background-color: #5c0000; color: #ffcccc"
                    if isinstance(v, bool) and v
                    else "",
                    subset=["flag"],
                ),
                width="stretch",
                hide_index=True,
            )

            flagged = fx_display[fx_display["flag"]]
            if not flagged.empty:
                st.warning(
                    f"{len(flagged)} FX rate(s) with >5% variance flagged."
                )

    # ---- Tab 4: Duplicate Order ID Check ----
    with tab4:
        st.markdown("**Duplicate Order ID Check**")
        if not actuals.empty:
            dupes = actuals[actuals.duplicated(subset=["order_id"], keep=False)]
            num_dupes = dupes["order_id"].nunique()

            col1, col2 = st.columns(2)
            col1.metric("Total Orders", f"{actuals['order_id'].nunique():,}")
            col2.metric(
                "Duplicate Order IDs",
                f"{num_dupes:,}",
                delta=f"{num_dupes / actuals['order_id'].nunique():.2%}",
            )

            if num_dupes > 0:
                st.dataframe(
                    dupes[
                        [
                            "order_id",
                            "courier",
                            "country",
                            "brand",
                            "total_cost_local",
                            "total_revenue_local",
                        ]
                    ].sort_values("order_id"),
                    width="stretch",
                    hide_index=True,
                )

                csv_dupes = dupes.to_csv(index=False).encode("utf-8")
                st.download_button(
                    label="📥 Export Duplicates CSV",
                    data=csv_dupes,
                    file_name="duplicate_orders.csv",
                    mime="text/csv",
                )
            else:
                st.success("No duplicate order IDs found.")
        else:
            st.info("No actuals data loaded.")

    # ---- Tab 5: Missing Critical Fields Audit ----
    with tab5:
        st.markdown("**Missing Critical Fields Audit**")
        if not actuals.empty:
            required = [
                "order_id",
                "country",
                "brand",
                "courier",
                "total_cost_local",
                "total_revenue_local",
                "currency",
            ]
            audit_rows = []
            for col in required:
                missing = actuals[col].isna().sum()
                missing_pct = missing / len(actuals) * 100
                audit_rows.append(
                    {
                        "Field": col,
                        "Total Records": len(actuals),
                        "Missing": missing,
                        "Missing %": f"{missing_pct:.2f}%",
                        "Status": "✅" if missing == 0 else "⚠️" if missing_pct < 1 else "❌",
                    }
                )
            audit_df = pd.DataFrame(audit_rows)
            st.dataframe(audit_df, width="stretch", hide_index=True)

            # Cost = 0 check
            zero_cost = (actuals["total_cost_local"] == 0).sum()
            zero_rev = (actuals["total_revenue_local"] == 0).sum()
            st.metric("Orders with Zero Cost", f"{zero_cost:,}")
            st.metric("Orders with Zero Revenue", f"{zero_rev:,}")
        else:
            st.info("No actuals data loaded.")

    # ---- Tab 6: Volume Reconciliation ----
    with tab6:
        st.markdown("**Volume Reconciliation: Budget Vol vs Actual Vol by Brand × Country**")
        if not actuals.empty and not budget.empty:
            brand_act = build_brand_actuals(actuals, fx)

            bud_vol = (
                budget.groupby(["country", "brand"], as_index=False)["forecasted_orders"]
                .sum()
            )
            act_vol = (
                brand_act.groupby(["country", "brand"], as_index=False)["volume"]
                .sum()
            )
            vol_recon = bud_vol.merge(
                act_vol, on=["country", "brand"], how="outer", suffixes=("_budget", "_actual")
            ).fillna(0)
            vol_recon["variance"] = vol_recon["volume_actual"] - vol_recon["volume_budget"]
            vol_recon["variance_pct"] = (
                vol_recon["variance"] / vol_recon["volume_budget"].replace(0, 1)
            )
            vol_recon["country"] = vol_recon["country"].map(COUNTRY_DISPLAY)
            vol_recon = vol_recon.rename(
                columns={
                    "country": "Country",
                    "brand": "Brand",
                    "volume_budget": "Budget Vol",
                    "volume_actual": "Actual Vol",
                    "variance": "Var",
                    "variance_pct": "Var %",
                }
            )

            st.dataframe(
                vol_recon.style.format(
                    {
                        "Budget Vol": "{:,.0f}",
                        "Actual Vol": "{:,.0f}",
                        "Var": "{:+,.0f}",
                        "Var %": "{:+.1%}",
                    }
                ).applymap(
                    lambda v: "color: #1b8a3d"
                    if isinstance(v, (int, float)) and v > 0
                    else ("color: #c0392b" if isinstance(v, (int, float)) and v < 0 else ""),
                    subset=["Var", "Var %"],
                ),
                width="stretch",
                hide_index=True,
            )

            # Visual
            fig = px.bar(
                vol_recon,
                x="Brand",
                y="Var",
                color="Var",
                color_continuous_scale="RdYlGn",
                title="Volume Variance by Brand × Country",
                facet_col="Country",
                labels={"Var": "Volume Variance"},
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Load actuals and budget to see volume reconciliation.")
