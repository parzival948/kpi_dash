import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px


def kpi_card(label, value, delta=None, delta_color="normal"):
    col = st.columns(1)[0]
    with col:
        st.markdown(
            f"""
        <div style="background:#ffffff;border-radius:8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.3);margin-bottom:8px;">
            <div style="font-size:13px;color:#666;margin-bottom:4px;">{label}</div>
            <div style="font-size:22px;font-weight:700;color:#1a1a1a;">{value}</div>
            {f'<div style="font-size:14px;color:{"var(--success-color)" if delta_color=="normal" and delta and "-" not in delta.replace("%","") else "var(--error-color)"};">{delta}</div>' if delta else ''}
        </div>
        """,
            unsafe_allow_html=True,
        )


def render_waterfall(waterfall_data, title="Cost Waterfall", currency="USD"):
    labels = ["Budget Cost", "Volume Var", "Rate Var", "FX Var", "Actual Cost"]
    measures = ["absolute", "relative", "relative", "relative", "total"]
    values = [
        waterfall_data["budget_cost_usd"],
        waterfall_data["volume_var_usd"],
        waterfall_data["rate_var_usd"],
        waterfall_data["fx_var_usd"],
        waterfall_data["actual_cost_usd"],
    ]

    fig = go.Figure(
        go.Waterfall(
            name=title,
            orientation="v",
            measure=measures,
            x=labels,
            y=values,
            text=[f"${v:,.0f}" for v in values],
            textposition="outside",
            connector={"line": {"color": "#7f8c8d", "dash": "dot"}},
            decreasing={"marker": {"color": "#c0392b"}},
            increasing={"marker": {"color": "#1b8a3d"}},
            totals={"marker": {"color": "#2c3e50"}},
        )
    )
    fig.update_layout(
        title=title,
        height=400,
        margin=dict(l=40, r=40, t=40, b=40),
        yaxis_title=f"Cost ({currency})",
    )
    return fig


def create_diverging_bar(df, x_col, y_col, title, color_col=None, ascending=False, limit=5):
    df = df.sort_values(x_col, ascending=ascending).head(limit)
    colors = ["#1b8a3d" if v >= 0 else "#c0392b" for v in df[x_col]]
    fig = go.Figure(
        go.Bar(
            x=df[x_col],
            y=df[y_col],
            orientation="h",
            marker_color=colors,
            text=[f"{v:+.1%}" for v in df[x_col]],
            textposition="outside",
        )
    )
    fig.update_layout(
        title=title, height=250, margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="Margin Variance %",
        yaxis=dict(tickfont=dict(size=10)),
    )
    return fig


def color_var(val, pct=False):
    if val is None or pd.isna(val):
        return ""
    if pct:
        val_num = val.replace("%", "").replace("+", "")
        try:
            val_num = float(val_num)
        except ValueError:
            return ""
    else:
        val_num = val
    if val_num > 0:
        return "color: #1b8a3d"
    elif val_num < 0:
        return "color: #c0392b"
    return ""
