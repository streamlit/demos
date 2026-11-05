from datetime import date

import pandas as pd
from streamlit_pivot import st_pivot_table
from utils import charts, data
from utils.components import STAGE_COLORS, card_header, page_header
from utils.formatting import money, money_md

import streamlit as st

CHART_HEIGHT = 300
WON_ACTION = ":material/check_circle: Mark as won"
LOST_ACTION = ":material/cancel: Mark as lost"
PIVOT_FIELDS = {
    "account": "Account",
    "stage": "Stage",
    "owner": "Owner",
    "source": "Source",
    "plan": "Plan",
    "region": "Region",
    "created": "Created",
    "close_date": "Expected close",
    "amount": "Amount",
    "weighted": "Weighted",
    "probability": "Probability",
}

st.session_state.setdefault("deal_overrides", {})

filters = data.current_filters()
actions = page_header("Pipeline", ":material/filter_alt:", filters.describe())


def handle_deal_action(table: pd.DataFrame) -> None:
    click = st.session_state.deal_click
    deal_id = table.index[click.row]
    stage = "Closed won" if click.label == WON_ACTION else "Closed lost"
    st.session_state.deal_overrides[deal_id] = stage
    account = table.at[deal_id, "account"]
    st.toast(
        f"{account} moved to **{stage}**",
        icon=":material/celebration:" if stage == "Closed won" else ":material/cancel:",
    )


def reset_deals() -> None:
    st.session_state.deal_overrides = {}


@st.dialog("Explore deals", width="large", icon=":material/pivot_table_chart:")
def explore_deals(deals: pd.DataFrame) -> None:
    hint = (
        "Turn on **Show closed** to include won and lost deals. "
        if deals["stage"].isin(data.OPEN_STAGES).all()
        else ""
    )
    st.caption(
        f"{len(deals)} deals from the table. {hint}"
        "Click a cell to list the deals behind it."
    )
    # A named index would show up as an extra pivot field, so drop it.
    source = deals[list(PIVOT_FIELDS)].rename(columns=PIVOT_FIELDS)
    st_pivot_table(
        source.reset_index(drop=True),
        key="deals_pivot",
        rows=["Owner"],
        columns=["Stage"],
        values=["Amount", "Weighted"],
        number_format={
            "Amount": "$,.0f",
            "Weighted": "$,.0f",
            "Probability": ".0%",
        },
        row_sort={"by": "value", "direction": "desc", "value_field": "Weighted"},
        sorters={"Stage": data.STAGES, "Plan": data.PLANS},
        filter_fields=["Source", "Plan", "Region"],
        conditional_formatting=[
            {"type": "data_bars", "apply_to": ["Weighted"], "fill": "gradient"}
        ],
        export_filename="nimbus_deals",
        max_height=520,
    )


if st.session_state.deal_overrides:
    actions.button(
        f"Undo {len(st.session_state.deal_overrides)} changes",
        icon=":material/undo:",
        type="tertiary",
        on_click=reset_deals,
    )

with st.skeleton(height=180):
    deals = data.load_deals()
deals = data.with_deal_metrics(
    data.filter_deals(data.apply_deal_overrides(deals), filters)
)
open_deals = deals[deals["stage"].isin(data.OPEN_STAGES)]
closed = deals[deals["stage"].isin(["Closed won", "Closed lost"])]
won = closed[closed["stage"] == "Closed won"]

quarter_start = pd.Timestamp(date.today()).to_period("Q").start_time.date()
quarter_end = pd.Timestamp(date.today()).to_period("Q").end_time.date()
quarter_bookings = won.loc[won["close_date"] >= quarter_start, "amount"].sum()
quarterly_quota = max(won["amount"].sum() / max(filters.months / 3, 1) * 1.15, 1)
days_elapsed = (date.today() - quarter_start).days + 1
quarter_days = (quarter_end - quarter_start).days + 1
win_rate = len(won) / len(closed) if len(closed) else 0
cycle = (
    pd.to_datetime(won["close_date"]) - pd.to_datetime(won["created"])
).dt.days.mean()

with st.container(horizontal=True):
    st.metric(
        "Open pipeline",
        money(open_deals["amount"].sum()),
        f"{len(open_deals)} deals",
        delta_color="off",
        delta_arrow="off",
        icon=":material/account_tree:",
        border=True,
    )
    st.metric(
        "Weighted forecast",
        money(open_deals["weighted"].sum()),
        f"{open_deals['weighted'].sum() / max(open_deals['amount'].sum(), 1):.0%} of pipeline",
        delta_color="off",
        delta_arrow="off",
        icon=":material/query_stats:",
        border=True,
        help="Open deal value weighted by each stage's win probability.",
    )
    st.metric(
        "Win rate",
        f"{win_rate:.0%}",
        f"{len(won)} of {len(closed)} closed",
        delta_color="off",
        delta_arrow="off",
        icon=":material/handshake:",
        border=True,
    )
    st.metric(
        "Avg. sales cycle",
        f"{cycle:.0f} days" if pd.notna(cycle) else "–",
        "created to closed won",
        delta_color="off",
        delta_arrow="off",
        icon=":material/schedule:",
        border=True,
    )

flow_col, funnel_col = st.columns([3, 2])
with flow_col.container(border=True, height="stretch"):
    card_header(
        "Pipeline flow", "Deal value from lead source, through plan, to outcome"
    )
    st.echarts_chart(
        charts.pipeline_flow(deals),
        height=CHART_HEIGHT,
        alt="Deal value flowing from lead source through plan to won, open, or lost",
    )
with funnel_col.container(border=True, height="stretch"):
    card_header("Stage conversion", "Deals that reached each stage")
    st.echarts_chart(
        charts.stage_funnel(deals),
        height=CHART_HEIGHT,
        alt="Funnel of deals reaching each sales stage",
    )

gauge_col, owner_col = st.columns([2, 3])
with gauge_col.container(border=True, height="stretch"):
    card_header(
        "Quarter bookings",
        f"{money_md(quarter_bookings)} of {money_md(quarterly_quota)} quota",
        help="Quota is the trailing average quarterly bookings plus 15%.",
    )
    st.echarts_chart(
        charts.quota_gauge(
            quarter_bookings / quarterly_quota * 100,
            pace=days_elapsed / quarter_days * 100,
        ),
        height=CHART_HEIGHT,
        alt="Quarter-to-date bookings as a share of quota",
    )
with owner_col.container(border=True, height="stretch"):
    card_header("Open pipeline by owner", "Click a bar to filter the deals below")
    owner_totals = (open_deals.groupby("owner")["amount"].sum() / 1_000).sort_values()
    owner_event = st.echarts_chart(
        charts.pipeline_by_owner(owner_totals),
        on_select="rerun",
        height=CHART_HEIGHT,
        alt="Open pipeline value per account executive",
    )

selected_owners = [
    owner_totals.index[index]
    for group in owner_event.selection.selected
    for index in group["data_indices"]
]

with st.container(border=True):
    controls = card_header(
        "Deals",
        "Open deals first, then the most recent closes. Use the row menu to close a deal.",
    )
    open_pivot = controls.button(
        "Pivot",
        icon=":material/pivot_table_chart:",
        help="Explore these deals in a pivot table",
    )
    # Left-aligned so the dataframe's hover toolbar can't cover the toggle.
    with st.container(horizontal=True, vertical_alignment="center"):
        show_closed = st.toggle("Show closed", value=False, key="show_closed")
        if selected_owners:
            st.badge(selected_owners[0], icon=":material/person:", color="primary")

    table = deals if show_closed else open_deals
    if selected_owners:
        table = table[table["owner"].isin(selected_owners)]
    if open_pivot:
        explore_deals(table)
    table = table.assign(
        is_open=table["stage"].isin(data.OPEN_STAGES),
    ).sort_values(["is_open", "close_date"], ascending=[False, True])
    table = table.assign(
        actions=pd.Series(
            [[WON_ACTION, LOST_ACTION] if is_open else [] for is_open in table["is_open"]],
            index=table.index,
            dtype=object,
        ),
        stage=table["stage"].map(lambda stage: [stage]),
    )[
        [
            "actions",
            "account",
            "stage",
            "amount",
            "probability",
            "weighted",
            "close_date",
            "owner",
            "source",
            "plan",
            "region",
        ]
    ]
    st.dataframe(
        table,
        column_config={
            "actions": st.column_config.ButtonColumn(
                "",
                type="tertiary",
                pinned=True,
                key="deal_click",
                on_click=handle_deal_action,
                args=(table,),
            ),
            "account": st.column_config.TextColumn("Account", pinned=True),
            "stage": st.column_config.MultiselectColumn(
                "Stage",
                options=data.STAGES,
                color=[STAGE_COLORS[stage] for stage in data.STAGES],
            ),
            "amount": st.column_config.NumberColumn("Amount", format="$%,d"),
            "probability": st.column_config.ProgressColumn(
                "Probability", min_value=0, max_value=1, format="percent"
            ),
            "weighted": st.column_config.NumberColumn("Weighted", format="$%,d"),
            "close_date": st.column_config.DateColumn(
                "Expected close", format="MMM D, YYYY"
            ),
            "owner": st.column_config.TextColumn("Owner"),
            "source": st.column_config.TextColumn("Source"),
            "plan": st.column_config.TextColumn("Plan"),
            "region": st.column_config.TextColumn("Region"),
        },
        hide_index=True,
        height=420,
        alt="Sales deals with stage, value, and expected close date",
    )
