"""Synthetic data, cached loaders, and filter helpers for the Nimbus BI demo.

Replace the ``_generate_*`` functions with real queries (for example
``st.connection("snowflake").query(...)``). Keep the cached loaders returning
the unfiltered source data, and apply the cheap interactive filters outside
the cache.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

import streamlit as st

# Simulates warehouse latency on the first (uncached) load so the skeleton
# loading states are visible. Set to 0 when wiring up a real data source.
SIMULATED_LATENCY_S = 0.8

# The 24-month window needs one extra month plus a year of lookback for NRR.
N_MONTHS = 40
PERIODS = {"3M": 3, "6M": 6, "12M": 12, "24M": 24}
DEFAULT_PERIOD = "24M"

REGIONS = ["North America", "EMEA", "APAC", "LATAM"]
PLANS = ["Enterprise", "Pro", "Starter"]
INDUSTRIES = ["Fintech", "Healthcare", "Retail", "Manufacturing", "Media", "Logistics"]
PRODUCTS = ["Analytics", "Automation", "AI copilot", "Data sync", "Security"]
STATUSES = ["Healthy", "Needs attention", "At risk", "Churned"]
STAGES = [
    "Prospecting",
    "Discovery",
    "Proposal",
    "Negotiation",
    "Closed won",
    "Closed lost",
]
OPEN_STAGES = STAGES[:4]
SOURCES = ["Inbound", "Outbound", "Partner", "Events"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

STAGE_PROBABILITY = {
    "Prospecting": 0.1,
    "Discovery": 0.25,
    "Proposal": 0.5,
    "Negotiation": 0.75,
    "Closed won": 1.0,
    "Closed lost": 0.0,
}

_CSMS = ["Ava Chen", "Marcus Reid", "Priya Nair", "Jonas Berg", "Sofia Rossi"]
_AES = [
    "Diego Alvarez",
    "Hannah Kim",
    "Liam Walsh",
    "Noor Haddad",
    "Ethan Brooks",
    "Mei Tanaka",
]
_NAME_PREFIXES = [
    "Apex", "Bluefin", "Cobalt", "Driftwood", "Ember", "Fjordline", "Granite",
    "Halcyon", "Ionix", "Juniper", "Keystone", "Lumora", "Meridian", "Novalis",
    "Orchid", "Pinnacle", "Quartzite", "Redwood", "Solstice", "Tidewater",
    "Umbra", "Vantage", "Willowmere", "Zephyr", "Aurora", "Basalt", "Cinder",
    "Delta Nine", "Evergreen", "Foxglove",
]  # fmt: skip
_NAME_SUFFIXES = [
    "Labs", "Health", "Logistics", "Systems", "Capital", "Retail", "Robotics",
    "Media", "Foods", "Energy", "Analytics", "Bio",
]  # fmt: skip
_PLAN_MRR_RANGE = {
    "Starter": (500, 2_000),
    "Pro": (1_500, 6_000),
    "Enterprise": (6_000, 22_000),
}
_PLAN_SEAT_PRICE = {"Starter": 25, "Pro": 45, "Enterprise": 70}
_PLAN_DEAL_RANGE = {
    "Starter": (4_000, 15_000),
    "Pro": (18_000, 70_000),
    "Enterprise": (90_000, 380_000),
}
# Hour offset of each region's business day relative to UTC, used to shift
# the product usage pattern so the region filter changes the heatmap.
_REGION_UTC_OFFSET = {"North America": -6, "EMEA": 1, "APAC": 8, "LATAM": -3}


@dataclass(frozen=True)
class Filters:
    """Global filters set in the sidebar of the entrypoint."""

    period: str
    regions: tuple[str, ...]
    plans: tuple[str, ...]

    @property
    def months(self) -> int:
        return PERIODS[self.period]

    def describe(self) -> str:
        regions = (
            "All regions"
            if len(self.regions) == len(REGIONS)
            else ", ".join(self.regions)
        )
        plans = "all plans" if len(self.plans) == len(PLANS) else ", ".join(self.plans)
        return f"{regions} · {plans} · last {self.months} months"


def current_filters() -> Filters:
    """Read the global sidebar filters from Session State."""
    period = st.session_state.get("period") or DEFAULT_PERIOD
    regions = tuple(st.session_state.get("regions") or REGIONS)
    plans = tuple(st.session_state.get("plans") or PLANS)
    return Filters(period=period, regions=regions, plans=plans)


def month_index() -> pd.DatetimeIndex:
    """Return the first day of each month in the generated history."""
    this_month = pd.Timestamp(date.today()).to_period("M").to_timestamp()
    return pd.date_range(end=this_month, periods=N_MONTHS, freq="MS")


# =============================================================================
# Synthetic data generation (replace with your data source)
# =============================================================================


def _account_names(rng: np.random.Generator, count: int) -> list[str]:
    combos = [f"{p} {s}" for p in _NAME_PREFIXES for s in _NAME_SUFFIXES]
    return list(rng.choice(combos, size=count, replace=count > len(combos)))


def _generate_book(n_accounts: int = 260) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate customer accounts and their monthly MRR history."""
    rng = np.random.default_rng(7)
    months = month_index()

    plan = rng.choice(PLANS, n_accounts, p=[0.17, 0.37, 0.46])
    region = rng.choice(REGIONS, n_accounts, p=[0.42, 0.3, 0.18, 0.1])
    industry = rng.choice(INDUSTRIES, n_accounts)
    # Bias signups toward older months so the book has a mature base.
    start = np.minimum(
        (rng.beta(1.3, 2.2, n_accounts) * N_MONTHS).astype(int), N_MONTHS - 1
    )
    low = np.array([_PLAN_MRR_RANGE[p][0] for p in plan])
    high = np.array([_PLAN_MRR_RANGE[p][1] for p in plan])
    initial_mrr = rng.uniform(low, high)
    drift = rng.normal(0.016, 0.018, n_accounts)

    # Monthly growth factors: drift plus noise, with occasional seat expansions
    # and contractions so the MRR bridge has every kind of movement.
    factors = 1 + drift[:, None] + rng.normal(0, 0.025, (n_accounts, N_MONTHS))
    jumps = rng.random((n_accounts, N_MONTHS))
    factors = np.where(jumps > 0.975, factors * 1.22, factors)
    factors = np.where(jumps < 0.02, factors * 0.82, factors)

    month_offsets = np.arange(N_MONTHS)[None, :] - start[:, None]
    active = month_offsets >= 0
    cumulative = np.cumprod(np.where(active, factors, 1.0), axis=1, dtype=float)
    growth = cumulative / np.take_along_axis(cumulative, start[:, None], axis=1)
    mrr = np.where(active, initial_mrr[:, None] * growth, 0.0)

    churn_month = np.where(
        rng.random(n_accounts) < 0.2,
        start + rng.integers(4, 30, n_accounts),
        N_MONTHS + 1,
    )
    mrr = np.where(np.arange(N_MONTHS)[None, :] >= churn_month[:, None], 0.0, mrr)
    mrr = np.round(mrr / 10) * 10

    ids = [f"ACC-{1000 + i}" for i in range(n_accounts)]
    history = pd.DataFrame(mrr, index=ids, columns=months)
    history.index.name = "account_id"

    current_mrr = mrr[:, -1]
    trend = mrr[:, -12:]
    with np.errstate(divide="ignore", invalid="ignore"):
        momentum = np.where(trend[:, 0] > 0, trend[:, -1] / trend[:, 0] - 1, 0.3)
    health = np.clip(56 + momentum * 50 + rng.normal(0, 16, n_accounts), 3, 99)
    status = np.select(
        [current_mrr == 0, health >= 70, health >= 45],
        ["Churned", "Healthy", "Needs attention"],
        default="At risk",
    )

    product_count = np.clip(
        rng.poisson(
            np.where(plan == "Enterprise", 3.2, np.where(plan == "Pro", 2.2, 1.2))
        ),
        1,
        len(PRODUCTS),
    )
    products = [
        sorted(rng.choice(PRODUCTS, size=k, replace=False), key=PRODUCTS.index)
        for k in product_count
    ]
    adoption = [
        [
            int(rng.uniform(55, 98)) if product in owned else int(rng.uniform(0, 18))
            for product in PRODUCTS
        ]
        for owned in products
    ]

    signup_dates = [
        months[s].date() + timedelta(days=int(rng.integers(0, 27))) for s in start
    ]
    today = date.today()
    renewals = []
    for signup in signup_dates:
        renewal = signup.replace(year=today.year)
        if renewal < today:
            renewal = renewal.replace(year=today.year + 1)
        renewals.append(renewal)

    seats = np.maximum(
        1, np.round(current_mrr / np.array([_PLAN_SEAT_PRICE[p] for p in plan]))
    ).astype(int)

    accounts = pd.DataFrame(
        {
            "account_id": ids,
            "name": _account_names(rng, n_accounts),
            "plan": plan,
            "region": region,
            "industry": industry,
            "mrr": current_mrr,
            "mrr_trend": [row.tolist() for row in trend],
            "seats": np.where(current_mrr == 0, 0, seats),
            "health": np.where(current_mrr == 0, 0, health.round()).astype(int),
            "status": status,
            "products": products,
            "adoption": adoption,
            "nps": rng.integers(-20, 85, n_accounts),
            "owner": rng.choice(_CSMS, n_accounts),
            "customer_since": signup_dates,
            "renewal_date": renewals,
        }
    ).set_index("account_id")
    return accounts, history


def _generate_deals(n_deals: int = 520) -> pd.DataFrame:
    """Generate sales opportunities created over the past two years."""
    rng = np.random.default_rng(11)
    today = pd.Timestamp(date.today())

    plan = rng.choice(PLANS, n_deals, p=[0.18, 0.4, 0.42])
    low = np.array([_PLAN_DEAL_RANGE[p][0] for p in plan])
    high = np.array([_PLAN_DEAL_RANGE[p][1] for p in plan])
    age_days = (rng.beta(1.0, 2.6, n_deals) * 540 + 3).astype(int)
    cycle_days = rng.integers(30, 180, n_deals)
    source = rng.choice(SOURCES, n_deals, p=[0.38, 0.27, 0.2, 0.15])

    # Deals older than their sales cycle are closed; partner and inbound
    # deals win more often.
    win_rate = np.select([source == "Partner", source == "Inbound"], [0.42, 0.34], 0.24)
    closed = age_days > cycle_days
    won = rng.random(n_deals) < win_rate
    open_stage = rng.choice(OPEN_STAGES, n_deals, p=[0.34, 0.28, 0.22, 0.16])
    stage = np.where(closed, np.where(won, "Closed won", "Closed lost"), open_stage)

    created = today - pd.to_timedelta(age_days, unit="D")
    close_date = created + pd.to_timedelta(cycle_days, unit="D")

    deals = pd.DataFrame(
        {
            "deal_id": [f"OPP-{5000 + i}" for i in range(n_deals)],
            "account": _account_names(rng, n_deals),
            "plan": plan,
            "region": rng.choice(REGIONS, n_deals, p=[0.42, 0.3, 0.18, 0.1]),
            "source": source,
            "owner": rng.choice(_AES, n_deals),
            "stage": stage,
            "amount": np.round(rng.uniform(low, high), -2),
            "created": created.date,
            "close_date": close_date.date,
        }
    ).set_index("deal_id")
    return deals


def _generate_usage() -> pd.DataFrame:
    """Generate product sessions by region, weekday, and UTC hour."""
    rng = np.random.default_rng(3)
    hours = np.arange(24)
    weekday_weight = np.array([1.0, 1.06, 1.04, 0.98, 0.86, 0.32, 0.24])
    rows = []
    for region, offset in _REGION_UTC_OFFSET.items():
        local_hour = (hours + offset) % 24
        # Business-hours bell curve with a small lunch dip.
        hourly = np.exp(-((local_hour - 13.5) ** 2) / 14) - 0.12 * np.exp(
            -((local_hour - 12.5) ** 2) / 0.8
        )
        hourly = np.clip(hourly, 0.03, None)
        scale = {"North America": 950, "EMEA": 700, "APAC": 430, "LATAM": 240}[region]
        for day_index, day in enumerate(WEEKDAYS):
            noise = rng.normal(1, 0.06, 24)
            sessions = scale * hourly * weekday_weight[day_index] * noise
            rows += [
                {"region": region, "weekday": day, "hour": h, "sessions": int(s)}
                for h, s in zip(hours, sessions, strict=True)
            ]
    return pd.DataFrame(rows)


# =============================================================================
# Cached loaders
# =============================================================================


@st.cache_data(ttl="1h", show_spinner=False)
def load_book() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load customer accounts and their monthly MRR history."""
    time.sleep(SIMULATED_LATENCY_S)
    return _generate_book()


@st.cache_data(ttl="15m", show_spinner=False)
def load_deals() -> pd.DataFrame:
    """Load sales opportunities."""
    time.sleep(SIMULATED_LATENCY_S)
    return _generate_deals()


@st.cache_data(ttl="1h", show_spinner=False)
def load_usage() -> pd.DataFrame:
    """Load product usage sessions by region, weekday, and hour."""
    time.sleep(SIMULATED_LATENCY_S)
    return _generate_usage()


# =============================================================================
# Filtering and aggregation (cheap, runs outside the cache)
# =============================================================================


def filter_accounts(accounts: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    mask = accounts["region"].isin(filters.regions) & accounts["plan"].isin(
        filters.plans
    )
    return accounts[mask]


def filter_deals(deals: pd.DataFrame, filters: Filters) -> pd.DataFrame:
    """Filter deals by the global filters, keeping open deals of any age."""
    window_start = date.today() - timedelta(days=30 * filters.months)
    in_window = (deals["created"] >= window_start) | deals["stage"].isin(OPEN_STAGES)
    mask = (
        deals["region"].isin(filters.regions)
        & deals["plan"].isin(filters.plans)
        & in_window
    )
    return deals[mask]


def apply_deal_overrides(deals: pd.DataFrame) -> pd.DataFrame:
    """Apply stage changes made in this session (for example, "Mark won")."""
    overrides: dict[str, str] = st.session_state.get("deal_overrides", {})
    if not overrides:
        return deals
    deals = deals.copy()
    ids = [deal_id for deal_id in overrides if deal_id in deals.index]
    deals.loc[ids, "stage"] = [overrides[deal_id] for deal_id in ids]
    deals.loc[ids, "close_date"] = date.today()
    return deals


def with_deal_metrics(deals: pd.DataFrame) -> pd.DataFrame:
    deals = deals.copy()
    deals["probability"] = deals["stage"].map(STAGE_PROBABILITY)
    deals["weighted"] = deals["amount"] * deals["probability"]
    return deals


def mrr_by_plan(
    history: pd.DataFrame, accounts: pd.DataFrame, months: int
) -> pd.DataFrame:
    """Return total MRR per month (rows) and plan (columns)."""
    window = history.loc[accounts.index].iloc[:, -months:]
    totals = window.groupby(accounts["plan"]).sum().T
    return totals.reindex(columns=PLANS, fill_value=0)


def mrr_movements(
    history: pd.DataFrame, account_ids: pd.Index, months: int
) -> dict[str, float]:
    """Decompose the MRR change over the window into its movement types."""
    window = history.loc[account_ids].iloc[:, [-months - 1, -1]]
    before, after = window.iloc[:, 0], window.iloc[:, 1]
    change = after - before
    return {
        "start": float(before.sum()),
        "new": float(after[before == 0].sum()),
        "expansion": float(change[(before > 0) & (change > 0)].sum()),
        "contraction": float(-change[(after > 0) & (change < 0)].sum()),
        "churn": float(before[(before > 0) & (after == 0)].sum()),
        "end": float(after.sum()),
    }


def monthly_kpis(
    history: pd.DataFrame, account_ids: pd.Index, months: int
) -> pd.DataFrame:
    """Return per-month ARR, net new MRR, net revenue retention, and churn.

    The rows cover the selected window plus one extra month so every KPI
    can be compared with the start of the window.
    """
    mrr = history.loc[account_ids]
    total = mrr.sum()
    previous = mrr.shift(1, axis=1)
    churned = previous.where((previous > 0) & (mrr == 0), 0).sum()
    contraction = (previous - mrr).where((mrr > 0) & (mrr < previous), 0).sum()
    year_ago = mrr.shift(12, axis=1)
    retained = mrr.where(year_ago > 0, 0).sum()
    base = year_ago.where(year_ago > 0, 0).sum()

    kpis = pd.DataFrame(
        {
            "arr": total * 12,
            "net_new_mrr": total.diff(),
            "nrr": (retained / base.replace(0, np.nan)) * 100,
            "gross_churn": ((churned + contraction) / previous.sum().replace(0, np.nan))
            * 100,
            "customers": (mrr > 0).sum(),
        }
    )
    return kpis.iloc[-(months + 1) :]


def usage_matrix(usage: pd.DataFrame, regions: tuple[str, ...]) -> pd.DataFrame:
    """Return sessions per weekday (rows) and UTC hour (columns)."""
    subset = usage[usage["region"].isin(regions)]
    return subset.pivot_table(
        index="weekday", columns="hour", values="sessions", aggfunc="sum"
    ).reindex(index=WEEKDAYS, columns=range(24), fill_value=0)


def accounts_csv(accounts: pd.DataFrame) -> bytes:
    columns = [
        "name",
        "plan",
        "region",
        "industry",
        "mrr",
        "seats",
        "health",
        "status",
        "owner",
        "renewal_date",
    ]
    return accounts[columns].to_csv().encode()
