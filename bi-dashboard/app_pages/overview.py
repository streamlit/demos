from utils import charts, data
from utils.formatting import change, money, signed_pct, signed_pts
from utils.components import (
    account_columns,
    account_table,
    card_header,
    open_clicked_account,
    page_header,
)

import streamlit as st

CHART_HEIGHT = 320
KPI_HEIGHT = 186

filters = data.current_filters()

# Render the header first; its export button is added once the data is loaded.
actions = page_header("Revenue overview", ":material/insights:", filters.describe())
actions.badge("Live", icon=":material/radio_button_checked:", color="green")


@st.fragment(parallel=True)
def kpi_row(filters: data.Filters) -> None:
    with st.skeleton(height=KPI_HEIGHT):
        accounts, history = data.load_book()
        kpis = data.monthly_kpis(
            history, data.filter_accounts(accounts, filters).index, filters.months
        )
        first, last = kpis.iloc[0], kpis.iloc[-1]
        window = f"vs. {filters.months} months ago"
        with st.container(horizontal=True):
            st.metric(
                "Annual recurring revenue",
                money(last["arr"]),
                signed_pct(change(last["arr"], first["arr"])),
                delta_description=window,
                chart_data=kpis["arr"].iloc[1:],
                chart_type="area",
                icon=":material/payments:",
                border=True,
            )
            st.metric(
                "Net new MRR",
                money(last["net_new_mrr"]),
                signed_pct(
                    change(last["net_new_mrr"], kpis["net_new_mrr"].iloc[1:-1].mean())
                ),
                delta_description="vs. period average",
                chart_data=kpis["net_new_mrr"].iloc[1:],
                chart_type="bar",
                icon=":material/trending_up:",
                border=True,
            )
            st.metric(
                "Net revenue retention",
                f"{last['nrr']:.1f}%",
                signed_pts(last["nrr"] - first["nrr"]),
                delta_description=window,
                chart_data=kpis["nrr"].iloc[1:],
                chart_type="line",
                icon=":material/autorenew:",
                border=True,
                help="MRR today from customers active 12 months ago, divided by their MRR back then.",
            )
            st.metric(
                "Monthly gross churn",
                f"{last['gross_churn']:.1f}%",
                signed_pts(last["gross_churn"] - kpis["gross_churn"].iloc[1:].mean()),
                delta_color="inverse",
                delta_description="vs. period average",
                chart_data=kpis["gross_churn"].iloc[1:],
                chart_type="bar",
                icon=":material/trending_down:",
                border=True,
                help="Churned plus contracted MRR as a share of the previous month's MRR.",
            )


@st.fragment(parallel=True)
def mrr_growth_card(filters: data.Filters) -> None:
    with st.container(border=True, height="stretch"):
        controls = card_header("MRR by plan", "Monthly recurring revenue in $K, stacked by plan")
        view = controls.segmented_control(
            "View",
            ["$", "%"],
            default="$",
            required=True,
            key="growth_view",
            label_visibility="collapsed",
            help="Show absolute MRR or each plan's share",
        )
        with st.skeleton(height=CHART_HEIGHT):
            accounts, history = data.load_book()
            region_accounts = accounts[accounts["region"].isin(filters.regions)]
            monthly = data.mrr_by_plan(history, region_accounts, filters.months)
            st.echarts_chart(
                charts.mrr_growth(monthly, filters.plans, share=view == "%"),
                height=CHART_HEIGHT,
                alt="Monthly recurring revenue by plan over time; Enterprise contributes most",
            )


@st.fragment(parallel=True)
def mrr_bridge_card(filters: data.Filters) -> None:
    with st.container(border=True, height="stretch"):
        card_header(
            "MRR bridge", f"How MRR moved over the last {filters.months} months"
        )
        with st.skeleton(height=CHART_HEIGHT):
            accounts, history = data.load_book()
            ids = data.filter_accounts(accounts, filters).index
            movements = data.mrr_movements(history, ids, filters.months)
            st.echarts_chart(
                charts.mrr_bridge(movements),
                height=CHART_HEIGHT,
                alt=(
                    f"MRR grew from {money(movements['start'])} to {money(movements['end'])}, "
                    "mostly from expansion"
                ),
            )


@st.fragment(parallel=True)
def usage_card(filters: data.Filters) -> None:
    with st.container(border=True):
        card_header(
            "When customers use Nimbus",
            "Product sessions by weekday and hour (UTC) — shifts with the region filter",
        )
        with st.skeleton(height=260):
            matrix = data.usage_matrix(data.load_usage(), filters.regions)
            st.echarts_chart(
                charts.usage_heatmap(matrix),
                height=260,
                alt="Product sessions by weekday and UTC hour, busiest on weekday afternoons",
            )


@st.fragment
def industry_drilldown(filters: data.Filters) -> None:
    """Donut of MRR by industry that filters the top-accounts table on click.

    This is a regular (not parallel) fragment because a click in the table
    opens a dialog, and selecting a slice reruns only this section.
    """
    accounts, _ = data.load_book()
    accounts = data.filter_accounts(accounts, filters)
    active = accounts[accounts["mrr"] > 0]
    by_industry = (
        active.groupby("industry")["mrr"].sum().reindex(data.INDUSTRIES, fill_value=0)
    )

    mix_col, table_col = st.columns([2, 3])
    with mix_col.container(border=True, height="stretch"):
        card_header("Revenue by industry", "Click a slice to filter the accounts")
        event = st.echarts_chart(
            charts.industry_mix(by_industry),
            on_select="rerun",
            height=CHART_HEIGHT + 40,
            alt="Share of MRR by industry",
        )

    selected = [
        data.INDUSTRIES[index]
        for group in event.selection.selected
        for index in group["data_indices"]
    ]
    top = active[active["industry"].isin(selected)] if selected else active
    top = top.nlargest(10, "mrr")

    with table_col.container(border=True, height="stretch"):
        controls = card_header(
            "Top accounts",
            f"{selected[0]} customers by MRR"
            if selected
            else "Largest customers by MRR",
        )
        if selected:
            controls.badge(selected[0], icon=":material/filter_alt:", color="primary")
        table = account_table(top)
        st.dataframe(
            table,
            column_config=account_columns(compact=True, key="top_accounts_click"),
            hide_index=True,
            alt="Top accounts by monthly recurring revenue",
        )
        open_clicked_account(table, "top_accounts_click")


kpi_row(filters)

growth_col, bridge_col = st.columns([3, 2])
with growth_col:
    mrr_growth_card(filters)
with bridge_col:
    mrr_bridge_card(filters)

industry_drilldown(filters)
usage_card(filters)

accounts, _ = data.load_book()
actions.download_button(
    "Export",
    data.accounts_csv(data.filter_accounts(accounts, filters)),
    file_name="nimbus_accounts.csv",
    mime="text/csv",
    icon=":material/download:",
    on_click="ignore",
)
