"""Nimbus BI: a revenue intelligence dashboard for a fictional B2B SaaS company.

Demonstrates:
- Dual light/dark custom theme (``.streamlit/config.toml``) with validated
  chart palettes, Geist fonts, and compact dashboard padding
- ``st.navigation(position="top")`` with an ``app_pages/`` folder
- Global sidebar filters bound to the URL with ``bind="query-params"``
- ``st.echarts_chart`` for stacked areas, waterfalls, donuts, heatmaps,
  funnels, sankeys, gauges, radars, and brushable scatter plots, including
  selection-driven cross-filtering
- ``st.dataframe`` with ``ButtonColumn`` row actions, ``MultiselectColumn``
  colored badges, and sparkline / progress columns
- ``@st.dialog(position="right")`` side drawer for account drill-down
- ``streamlit-pivot`` (a Components v2 package) in a large ``@st.dialog``
  for drag-and-drop pivoting and cell drill-down of the accounts and deals
  tables
- ``@st.fragment(parallel=True)`` cards that load concurrently behind
  ``st.skeleton`` placeholders

All data is synthetic. Replace the generators in ``utils/data.py`` with your
own queries.
"""

from pathlib import Path

from utils import data

import streamlit as st

st.set_page_config(
    page_title="Nimbus BI",
    page_icon=":material/insights:",
    layout="wide",
)

STATIC = Path(__file__).parent / "static"
logo_variant = "dark" if st.context.theme.type == "dark" else "light"
st.logo(
    STATIC / f"logo-{logo_variant}.svg", icon_image=STATIC / "icon.svg", size="large"
)

page = st.navigation(
    [
        st.Page(
            "app_pages/overview.py",
            title="Overview",
            icon=":material/insights:",
            default=True,
        ),
        st.Page("app_pages/accounts.py", title="Accounts", icon=":material/groups:"),
        st.Page(
            "app_pages/pipeline.py", title="Pipeline", icon=":material/filter_alt:"
        ),
    ],
    position="top",
)


def reset_filters() -> None:
    # Bound widgets are reset by assigning their keys in a callback.
    st.session_state.period = data.DEFAULT_PERIOD
    st.session_state.regions = []
    st.session_state.plans = []


with st.sidebar:
    st.subheader("Filters", icon=":material/tune:", anchor=False)
    st.segmented_control(
        "Period",
        list(data.PERIODS),
        default=data.DEFAULT_PERIOD,
        required=True,
        key="period",
        bind="query-params",
        width="stretch",
        wrap=False,
    )
    st.pills(
        "Regions",
        data.REGIONS,
        selection_mode="multi",
        key="regions",
        help="Leave empty to include all regions.",
        bind="query-params",
    )
    st.pills(
        "Plans",
        data.PLANS,
        selection_mode="multi",
        key="plans",
        help="Leave empty to include all plans.",
        bind="query-params",
    )
    st.button(
        "Reset filters",
        icon=":material/restart_alt:",
        type="tertiary",
        on_click=reset_filters,
    )
    st.caption(
        "Synthetic demo data, cached for one hour. Filters are saved in the URL, "
        "so you can share the current view."
    )

page.run()
