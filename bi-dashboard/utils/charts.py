"""Apache ECharts option builders for the Nimbus BI demo.

Every option leaves series colors to Streamlit's ECharts theme, which reads
``chartCategoricalColors`` / ``chartSequentialColors`` from
``.streamlit/config.toml``. Series always keep a fixed order, so a filter that
removes a category hides its data instead of repainting the survivors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.data import PLANS, PRODUCTS, SOURCES, STAGES, WEEKDAYS
from utils.formatting import money

if TYPE_CHECKING:
    import pandas as pd

_LEGEND_TOP = {
    "top": 0,
    "left": 0,
    "icon": "roundRect",
    "itemWidth": 10,
    "itemHeight": 10,
}
_GRID = {"left": 4, "right": 12, "top": 36, "bottom": 4}
_AXIS_TOOLTIP = {"trigger": "axis", "axisPointer": {"type": "line"}}


def _month_labels(index: pd.Index) -> list[str]:
    return [timestamp.strftime("%b %y") for timestamp in index]


def mrr_growth(
    monthly: pd.DataFrame, active_plans: tuple[str, ...], *, share: bool
) -> dict[str, Any]:
    """Stacked area of MRR (in $K, or % share) per plan over time."""
    values = monthly[list(active_plans)] if active_plans else monthly.iloc[:, :0]
    if share:
        values = values.div(values.sum(axis=1).replace(0, 1), axis=0) * 100
    else:
        values = values / 1_000
    series = [
        {
            "name": plan,
            "type": "line",
            "stack": "mrr",
            "smooth": 0.35,
            "showSymbol": False,
            "lineStyle": {"width": 2},
            "areaStyle": {"opacity": 0.22},
            "emphasis": {"focus": "series"},
            # A plan removed by the global filter keeps its series (and color
            # slot) but draws nothing.
            "data": values[plan].round(1).tolist()
            if plan in values
            else [None] * len(monthly),
        }
        for plan in PLANS
    ]
    return {
        "tooltip": _AXIS_TOOLTIP,
        "legend": _LEGEND_TOP,
        "grid": _GRID,
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "data": _month_labels(monthly.index),
            "axisTick": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "max": 100 if share else None,
            "axisLabel": {"formatter": "{value}%" if share else "${value}K"},
            "splitLine": {"lineStyle": {"opacity": 0.6}},
        },
        "series": series,
    }


def mrr_bridge(movements: dict[str, float]) -> dict[str, Any]:
    """Waterfall from starting to ending MRR, in $K."""
    steps = [
        ("Start", movements["start"], "total"),
        ("New", movements["new"], "increase"),
        ("Expand", movements["expansion"], "increase"),
        ("Contract", -movements["contraction"], "decrease"),
        ("Churn", -movements["churn"], "decrease"),
        ("End", movements["end"], "total"),
    ]
    base: list[float] = []
    columns: dict[str, list[dict[str, Any] | str]] = {"total": [], "increase": [], "decrease": []}
    level = 0.0
    for name, value, kind in steps:
        if kind == "total":
            level = value
            base.append(0)
        elif kind == "increase":
            base.append(round(level / 1_000, 1))
            level += value
        else:
            level += value
            base.append(round(level / 1_000, 1))
        # Labels and tooltips are precomputed strings because the chart spec
        # can't carry JavaScript formatter callbacks.
        bar = {
            "value": round(abs(value) / 1_000, 1),
            "label": {"formatter": money(value)},
            "tooltip": {"formatter": f"{name}: {money(value)}"},
        }
        for column_kind, column in columns.items():
            column.append(bar if column_kind == kind else "-")

    bar_style = {"type": "bar", "stack": "bridge", "barWidth": "56%", "itemStyle": {"borderRadius": 4}}
    label = {"show": True, "position": "top", "fontWeight": 500}
    return {
        "tooltip": {"trigger": "item"},
        "legend": {**_LEGEND_TOP, "data": ["MRR", "Gain", "Loss"]},
        "grid": {**_GRID, "top": 44},
        "xAxis": {
            "type": "category",
            "data": [step[0] for step in steps],
            "axisTick": {"show": False},
            "axisLabel": {"interval": 0},
        },
        "yAxis": {"type": "value", "axisLabel": {"formatter": "${value}K"}},
        "series": [
            {
                # Transparent spacer that lifts the floating bars. A series
                # with an explicit color doesn't consume a palette slot.
                **bar_style,
                "name": "Base",
                "itemStyle": {"color": "transparent"},
                "emphasis": {"disabled": True},
                "tooltip": {"show": False},
                "silent": True,
                "data": base,
            },
            {**bar_style, "name": "MRR", "label": label, "data": columns["total"]},
            {**bar_style, "name": "Gain", "label": label, "data": columns["increase"]},
            {**bar_style, "name": "Loss", "label": label, "data": columns["decrease"]},
        ],
    }


def industry_mix(mrr_by_industry: pd.Series) -> dict[str, Any]:
    """Selectable donut of MRR by industry, with the total in the center."""
    total_k = mrr_by_industry.sum() / 1_000
    total_label = (
        f"${total_k / 1_000:.2f}M" if total_k >= 1_000 else f"${total_k:,.0f}K"
    )
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: ${c}K ({d}%)"},
        "legend": {"bottom": 0, "icon": "circle", "itemWidth": 8, "itemHeight": 8},
        "title": {
            "text": total_label,
            "subtext": "MRR",
            "left": "center",
            "top": "34%",
            "textStyle": {"fontSize": 22, "fontWeight": 600},
        },
        "series": [
            {
                "name": "Industry",
                "type": "pie",
                "radius": ["58%", "80%"],
                "center": ["50%", "42%"],
                "padAngle": 2,
                "itemStyle": {"borderRadius": 6},
                "label": {"show": False},
                "selectedMode": "single",
                "selectedOffset": 8,
                "emphasis": {"scale": True, "scaleSize": 4},
                "data": [
                    {"name": name, "value": round(value / 1_000, 1)}
                    for name, value in mrr_by_industry.items()
                ],
            }
        ],
    }


def usage_heatmap(matrix: pd.DataFrame) -> dict[str, Any]:
    """Weekday by hour heatmap of product sessions."""
    values = matrix.to_numpy(dtype=int)
    cells = [
        {
            "value": [hour, day_index, int(values[day_index, hour])],
            "tooltip": {
                "formatter": f"{day} {hour:02d}:00 UTC · {int(values[day_index, hour]):,} sessions"
            },
        }
        for day_index, day in enumerate(WEEKDAYS)
        for hour in range(24)
    ]
    return {
        "tooltip": {"position": "top"},
        "grid": {"left": 4, "right": 4, "top": 8, "bottom": 48},
        "xAxis": {
            "type": "category",
            "data": [f"{hour:02d}:00" for hour in range(24)],
            "splitArea": {"show": False},
            "axisTick": {"show": False},
            "axisLine": {"show": False},
        },
        "yAxis": {
            "type": "category",
            "data": WEEKDAYS,
            "inverse": True,
            "axisTick": {"show": False},
            "axisLine": {"show": False},
        },
        "visualMap": {
            "min": 0,
            "max": int(matrix.to_numpy().max()) or 1,
            "orient": "horizontal",
            "left": "center",
            "bottom": 0,
            "itemHeight": 220,
            "itemWidth": 10,
            "calculable": False,
            "text": ["More", "Fewer"],
        },
        "series": [
            {
                "name": "Sessions",
                "type": "heatmap",
                "data": cells,
                "itemStyle": {"borderRadius": 3},
                "emphasis": {
                    "itemStyle": {"shadowBlur": 8, "shadowColor": "rgba(0, 0, 0, 0.25)"}
                },
            }
        ],
    }


def account_mrr(history: pd.Series) -> dict[str, Any]:
    """Single-series MRR history for the account drawer."""
    active = history[history > 0]
    if active.empty:
        active = history.tail(12)
    return {
        "tooltip": _AXIS_TOOLTIP,
        "grid": {"left": 4, "right": 8, "top": 12, "bottom": 4},
        "xAxis": {
            "type": "category",
            "boundaryGap": False,
            "data": _month_labels(active.index),
            "axisTick": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "axisLabel": {"formatter": "${value}"},
            "scale": True,
        },
        "series": [
            {
                "name": "MRR",
                "type": "line",
                "smooth": 0.3,
                "showSymbol": False,
                "lineStyle": {"width": 2.5},
                "areaStyle": {"opacity": 0.16},
                "data": active.round().tolist(),
            }
        ],
    }


def product_adoption(account: list[int], plan_average: list[float]) -> dict[str, Any]:
    """Radar of product adoption for one account against its plan average."""
    return {
        "tooltip": {},
        "legend": {"bottom": 0, "icon": "roundRect", "itemWidth": 10, "itemHeight": 10},
        "radar": {
            "indicator": [{"name": product, "max": 100} for product in PRODUCTS],
            "radius": "66%",
            "center": ["50%", "46%"],
            "splitNumber": 4,
        },
        "series": [
            {
                "type": "radar",
                "symbolSize": 6,
                "data": [
                    {
                        "name": "This account",
                        "value": account,
                        "areaStyle": {"opacity": 0.28},
                        "lineStyle": {"width": 2},
                    },
                    {
                        "name": "Plan average",
                        "value": [round(v) for v in plan_average],
                        "areaStyle": {"opacity": 0.08},
                        "lineStyle": {"width": 1.5, "type": "dashed"},
                    },
                ],
            }
        ],
    }


def health_scatter(accounts: pd.DataFrame) -> dict[str, Any]:
    """Health score against MRR, one series per plan, with brush selection."""
    series = []
    for plan in PLANS:
        subset = accounts[accounts["plan"] == plan]
        series.append(
            {
                "name": plan,
                "type": "scatter",
                "data": [
                    {
                        "name": name,
                        "value": [int(health), float(mrr), int(seats)],
                        "symbolSize": max(8, min(28, 6 + seats**0.5)),
                        "tooltip": {"formatter": f"{name} · Health {int(health)} · {money(mrr)} MRR"},
                    }
                    for name, health, mrr, seats in zip(
                        subset["name"], subset["health"], subset["mrr"], subset["seats"], strict=True
                    )
                ],
                "itemStyle": {"opacity": 0.75},
                "emphasis": {"focus": "series"},
            }
        )
    return {
        "tooltip": {"trigger": "item"},
        # Streamlit's hover toolbar sits in the top-right corner, so the
        # brush tools go top-left with the legend after them.
        "legend": {**_LEGEND_TOP, "left": 64},
        "grid": {**_GRID, "top": 40, "right": 40},
        "toolbox": {
            "left": 0,
            "top": 0,
            "feature": {
                "brush": {
                    "type": ["rect", "clear"],
                    "title": {"rect": "Select", "clear": "Clear"},
                }
            },
        },
        "brush": {
            "xAxisIndex": 0,
            "yAxisIndex": 0,
            "throttleType": "debounce",
            "throttleDelay": 300,
        },
        "xAxis": {
            "type": "value",
            "name": "Health score",
            "nameLocation": "middle",
            "nameGap": 28,
            "min": 0,
            "max": 100,
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "log",
            "min": 100,
            "max": max(1_000, float(accounts["mrr"].max()) * 1.5) if len(accounts) else 1_000,
            "axisLabel": {"formatter": "${value}"},
            "splitLine": {"lineStyle": {"opacity": 0.6}},
        },
        "series": series,
    }


def stage_funnel(deals: pd.DataFrame) -> dict[str, Any]:
    """Funnel of how many deals reached each stage, in a single hue."""
    order = STAGES[:5]
    ranks = [_stage_rank(stage) for stage in deals["stage"].tolist()]
    reached = [sum(r >= rank for r in ranks) for rank in range(len(order))]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: {c} deals"},
        "series": [
            {
                "name": "Deals",
                "type": "funnel",
                "left": "4%",
                "width": "92%",
                "top": 8,
                "bottom": 8,
                "sort": "none",
                "gap": 3,
                "minSize": "30%",
                # Every stage uses the first palette slot; the shape already
                # encodes the order. The theme's primary color is dark enough
                # for white text in both modes, like a primary button label.
                "colorBy": "series",
                "label": {
                    "show": True,
                    "position": "inside",
                    "formatter": "{b}  ·  {c}",
                    "color": "#FFFFFF",
                    "textBorderWidth": 0,
                    "fontWeight": 500,
                },
                "itemStyle": {"borderWidth": 0, "borderRadius": 6},
                "data": [
                    {"name": stage, "value": count}
                    for stage, count in zip(order, reached, strict=True)
                ],
            }
        ],
    }


def _stage_rank(stage: str) -> int:
    # Closed lost deals made it past discovery on average, so count them as
    # having reached the proposal stage.
    return {"Closed lost": 2}.get(stage, STAGES.index(stage))


def pipeline_flow(deals: pd.DataFrame) -> dict[str, Any]:
    """Sankey of deal value from lead source, through plan, to outcome."""
    outcome = deals["stage"].map(
        lambda s: (
            "Won" if s == "Closed won" else "Lost" if s == "Closed lost" else "Open"
        )
    )
    first = deals.groupby(["source", "plan"])["amount"].sum().reset_index()
    second = deals.assign(outcome=outcome).groupby(["plan", "outcome"])["amount"].sum().reset_index()
    links = [
        {"source": src, "target": dst, "value": round(value / 1_000, 1)}
        for frame in (first, second)
        for src, dst, value in zip(frame.iloc[:, 0], frame.iloc[:, 1], frame["amount"], strict=True)
        if value > 0
    ]
    nodes = [*SOURCES, *PLANS, "Won", "Open", "Lost"]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}: ${c}K"},
        "series": [
            {
                "type": "sankey",
                "left": 4,
                "right": 64,
                "top": 8,
                "bottom": 8,
                "nodeWidth": 14,
                "nodeGap": 12,
                "layoutIterations": 0,
                "emphasis": {"focus": "adjacency"},
                "lineStyle": {"color": "gradient", "curveness": 0.5},
                "itemStyle": {"borderRadius": 3},
                "data": [{"name": node} for node in nodes],
                "links": links,
            }
        ],
    }


def quota_gauge(attainment: float, pace: float) -> dict[str, Any]:
    """Progress gauge of quarter-to-date bookings against quota."""
    return {
        "series": [
            {
                "type": "gauge",
                "startAngle": 210,
                "endAngle": -30,
                "min": 0,
                "max": 100,
                "radius": "92%",
                "center": ["50%", "58%"],
                "progress": {"show": True, "roundCap": True, "width": 16},
                "axisLine": {"roundCap": True, "lineStyle": {"width": 16}},
                "pointer": {"show": False},
                "axisTick": {"show": False},
                "splitLine": {"show": False},
                "axisLabel": {"show": False},
                "anchor": {"show": False},
                "title": {"offsetCenter": [0, "32%"], "fontSize": 13},
                "detail": {
                    "valueAnimation": True,
                    "offsetCenter": [0, "-4%"],
                    "fontSize": 34,
                    "fontWeight": 650,
                    "formatter": "{value}%",
                },
                "data": [
                    {"value": round(attainment), "name": f"of quota · pace {pace:.0f}%"}
                ],
            }
        ],
    }


def pipeline_by_owner(totals: pd.Series) -> dict[str, Any]:
    """Selectable horizontal bars of open pipeline (in $K) per account executive."""
    return {
        "tooltip": {"trigger": "item"},
        "grid": {"left": 4, "right": 48, "top": 4, "bottom": 4},
        "xAxis": {
            "type": "value",
            "axisLabel": {"formatter": "${value}K"},
            "splitLine": {"lineStyle": {"opacity": 0.6}},
        },
        "yAxis": {
            "type": "category",
            "data": totals.index.tolist(),
            "axisTick": {"show": False},
        },
        "series": [
            {
                "name": "Open pipeline",
                "type": "bar",
                "barWidth": "58%",
                "selectedMode": "single",
                "select": {
                    "itemStyle": {
                        "borderWidth": 0,
                        "shadowBlur": 10,
                        "shadowColor": "rgba(0, 0, 0, 0.2)",
                    }
                },
                "itemStyle": {"borderRadius": [0, 6, 6, 0]},
                "label": {"show": True, "position": "right", "formatter": "${c}K"},
                "data": [
                    {
                        "value": round(value),
                        "label": {"formatter": money(value * 1_000)},
                        "tooltip": {"formatter": f"{owner}: {money(value * 1_000)} open"},
                    }
                    for owner, value in totals.items()
                ],
            }
        ],
    }
