import sys
import streamlit as st
import plotly.io as pio
pio.templates.default = "plotly_dark"

from utils.data_loader import get_all_data
from config import COUNTRY_DISPLAY

st.set_page_config(
    page_title="Dispatch KPI Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
    .reportview-container .main .block-container { padding-top: 1rem; }
    .st-emotion-cache-1v0mbdj { margin-top: -2rem; }
    div[data-testid="stSidebarNav"] { display: none; }
    footer { display: none; }
</style>
""",
    unsafe_allow_html=True,
)


def init_session_state():
    if "page" not in st.session_state:
        st.session_state.page = "Executive Summary"
    if "cache_cleared" not in st.session_state:
        st.session_state.cache_cleared = False


def sidebar() -> dict:
    data = get_all_data()

    with st.sidebar:
        st.markdown("## Filters")

        period = st.radio(
            "Period",
            ["Current Month", "YTD"],
            index=0,
            key="period",
        )

        is_ytd = period == "YTD"

        months = data["months"]
        act_months = sorted(data["actuals"]["month"].unique()) if not data["actuals"].empty else []
        default_month = act_months[-1] if act_months else (months[-1] if months else None)
        sel_months = [default_month] if default_month else []

        if not is_ytd:
            default_idx = months.index(default_month) if default_month in months else len(months) - 1
            sel_month = st.selectbox(
                "Month",
                months,
                index=default_idx if months else 0,
                key="month_sel",
            )
            sel_months = [sel_month]

        countries = data["countries"]
        sel_countries = st.multiselect(
            "Countries",
            countries,
            default=countries,
            format_func=lambda c: COUNTRY_DISPLAY.get(c, c),
            key="countries_sel",
        )

        brands = data["brands"]
        sel_brands = st.multiselect(
            "Brands",
            brands,
            default=brands,
            key="brands_sel",
        )

        couriers = data.get("couriers", [])
        sel_couriers = st.multiselect(
            "Couriers",
            couriers,
            default=couriers,
            format_func=lambda c: c.title(),
            key="couriers_sel",
        )

        currency = st.radio(
            "Currency",
            ["USD", "Local", "Both"],
            index=0,
            key="currency",
        )

        variance_view = st.radio(
            "Variance View",
            ["%", "Absolute", "Waterfall"],
            index=0,
            key="variance_view",
        )

        if st.button("🗑️ Clear Cache", width="stretch"):
            st.cache_data.clear()
            st.session_state.cache_cleared = True
            st.rerun()

        if st.session_state.get("cache_cleared"):
            st.success("Cache cleared!")
            st.session_state.cache_cleared = False

    return {
        "period": period,
        "is_ytd": is_ytd,
        "months": sel_months,
        "countries": sel_countries,
        "brands": sel_brands,
        "couriers": sel_couriers,
        "currency": currency,
        "variance_view": variance_view,
    }


def render_nav():
    pages = [
        "Executive Summary",
        "Country Deep Dive",
        "Courier Scorecard",
        "Brand P&L",
        "Data Quality",
    ]

    with st.sidebar:
        st.markdown("---")
        st.markdown("### Navigation")

        for p in pages:
            if st.button(
                p,
                width="stretch",
                type="secondary" if st.session_state.page != p else "primary",
                key=f"nav_{p}",
            ):
                st.session_state.page = p
                st.rerun()


def main():
    st.cache_data.clear()

    init_session_state()

    filters = sidebar()
    render_nav()

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "<div style='font-size:12px;color:#888;text-align:center;'>"
        "Dispatch KPI Dashboard v1.1<br>"
        "Waterfall: FX-rate based<br>"
        "Data refresh: Monthly XLSX drop</div>",
        unsafe_allow_html=True,
    )

    page = st.session_state.page

    if page == "Executive Summary":
        from pages import _01_executive_summary
        _01_executive_summary.render(filters)
    elif page == "Country Deep Dive":
        from pages import _02_country_deep_dive
        _02_country_deep_dive.render(filters)
    elif page == "Courier Scorecard":
        from pages import _03_courier_scorecard
        _03_courier_scorecard.render(filters)
    elif page == "Brand P&L":
        from pages import _04_brand_pl
        _04_brand_pl.render(filters)
    elif page == "Data Quality":
        from pages import _05_data_quality
        _05_data_quality.render(filters)


if __name__ == "__main__":
    main()
