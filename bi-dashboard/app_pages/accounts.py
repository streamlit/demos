from datetime import date, timedelta

import pandas as pd
from streamlit_pivot import st_pivot_table
from utils import charts, data
from utils.components import (
    STATUS_ICONS,
    account_columns,
    account_table,
    card_header,
    open_clicked_account,
    page_header,
)

import streamlit as st

# The pivot only handles scalar columns, so list-valued fields such as
# products and the MRR trend are left out.
PIVOT_FIELDS = {
    "name": "Account",
    "region": "Region",
    "industry": "Industry",
    "plan": "Plan",
    "status": "Status",
    "owner": "Owner",
    "customer_since": "Customer since",
    "renewal_date": "Renewal",
    "mrr": "MRR",
    "seats": "Seats",
    "health": "Health",
    "nps": "NPS",
}


@st.dialog("Explore accounts", width="large", icon=":material/pivot_table_chart:")
def explore_accounts(accounts: pd.DataFrame) -> None:
    st.caption(
        f"{len(accounts)} accounts matching the current filters. Drag fields between "
        "rows, columns, and values, or click a cell to list the accounts behind it."
    )
    # A named index would show up as an extra pivot field, so drop it.
    source = accounts[list(PIVOT_FIELDS)].rename(columns=PIVOT_FIELDS)
    st_pivot_table(
        source.reset_index(drop=True),
        key="accounts_pivot",
        rows=["Region", "Industry"],
        columns=["Plan"],
        values=["MRR", "Health"],
        aggregation={"MRR": "sum", "Health": "avg"},
        number_format={
            "MRR": "$,.0f",
            "Health": ",.0f",
            "Seats": ",.0f",
            "NPS": ",.0f",
        },
        show_subtotals=True,
        row_sort={"by": "value", "direction": "desc", "value_field": "MRR"},
        sorters={"Plan": data.PLANS, "Status": data.STATUSES},
        filter_fields=["Status", "Owner"],
        conditional_formatting=[
            {"type": "data_bars", "apply_to": ["MRR"], "fill": "gradient"}
        ],
        export_filename="nimbus_accounts",
        max_height=520,
    )


filters = data.current_filters()
actions = page_header("Accounts", ":material/groups:", filters.describe())

with st.container(horizontal=True, vertical_alignment="center"):
    query = st.text_input(
        "Search accounts",
        type="search",
        placeholder="Search by account, owner, or industry",
        live=True,
        label_visibility="collapsed",
        key="account_search",
    )
    statuses = st.pills(
        "Status",
        data.STATUSES,
        selection_mode="multi",
        default=data.STATUSES[:3],
        format_func=lambda status: f"{STATUS_ICONS[status]} {status}",
        key="account_status",
        label_visibility="collapsed",
        width="content",
    )

with st.skeleton(height=420):
    accounts, _ = data.load_book()
accounts = data.filter_accounts(accounts, filters)
accounts = accounts[accounts["status"].isin(statuses or data.STATUSES)]
if query:
    haystack = accounts["name"] + " " + accounts["owner"] + " " + accounts["industry"]
    accounts = accounts[haystack.str.contains(query, case=False, regex=False)]

scatter_col, renewals_col = st.columns([3, 2])
with scatter_col.container(border=True, height="stretch"):
    card_header(
        "Health vs. revenue",
        "Bubble size shows seats. Use the select tool to filter the table.",
    )
    event = st.echarts_chart(
        charts.health_scatter(accounts),
        on_select="rerun",
        height=340,
        alt="Account health score against MRR by plan; most revenue sits in healthy accounts",
    )

# Brush selections come back as indices into each plan's series.
brushed: list[str] = []
for group in event.selection.selected:
    plan_ids = accounts.index[accounts["plan"] == data.PLANS[group["series_index"]]]
    brushed += [plan_ids[index] for index in group["data_indices"]]

with renewals_col.container(border=True, height="stretch"):
    horizon = date.today() + timedelta(days=90)
    renewals = accounts[(accounts["renewal_date"] <= horizon) & (accounts["mrr"] > 0)]
    renewals = renewals.sort_values("renewal_date")
    controls = card_header("Upcoming renewals", "Next 90 days, soonest first")
    controls.badge(f"{len(renewals)} accounts", color="gray")
    renewal_table = account_table(renewals)[
        ["view", "name", "renewal_date", "mrr"]
    ]
    st.dataframe(
        renewal_table,
        column_config=account_columns(key="renewal_click"),
        hide_index=True,
        height=340,
        alt="Accounts renewing in the next 90 days",
    )
    open_clicked_account(renewal_table, "renewal_click")

table_accounts = accounts.loc[brushed] if brushed else accounts
with st.container(border=True):
    controls = card_header(
        "All accounts",
        f"{len(table_accounts)} of {len(accounts)} accounts"
        + (" in the scatter selection" if brushed else ""),
    )
    if brushed:
        controls.badge(
            "Scatter selection", icon=":material/select_all:", color="primary"
        )
    if controls.button(
        "Pivot",
        icon=":material/pivot_table_chart:",
        help="Explore these accounts in a pivot table",
    ):
        explore_accounts(table_accounts)
    table = account_table(table_accounts.sort_values("mrr", ascending=False))
    st.dataframe(
        table,
        column_config=account_columns(key="account_click"),
        hide_index=True,
        height=460,
        alt="All customer accounts",
    )
    open_clicked_account(table, "account_click")

actions.download_button(
    "Export",
    data.accounts_csv(table_accounts),
    file_name="nimbus_accounts.csv",
    mime="text/csv",
    icon=":material/download:",
    on_click="ignore",
)
