# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cross-scenario comparison plots for PyPSA-Zambia.

Reads solved networks from multiple scenario runs and produces stacked bar
charts of installed capacity, generation mix, demand, investments and CO2
emissions for side-by-side scenario comparison.
"""

import os
import re

import matplotlib.pyplot as plt
import pandas as pd
import pypsa
from _helpers import configure_logging, create_logger
from pypsa.statistics import get_carrier

logger = create_logger(__name__)

# Preferred stack order uses n.carriers.nice_name values.
preferred_order = pd.Index(
    [
        "Reservoir & Dam",
        "Run of River",
        "Pumped Hydro Storage",
        "Onshore Wind",
        "Offshore Wind (AC)",
        "Offshore Wind (DC)",
        "Solar",
        "Biomass",
        "Geothermal",
        "Nuclear",
        "Coal",
        "Oil",
        "Open-Cycle Gas",
        "Combined-Cycle Gas",
        "Battery Storage",
        "Hydrogen Storage",
    ]
)


def resolve_nice_name(carrier, nice_names=None):
    """Display name for a raw carrier code, e.g. for a reference-data fuel
    label that has no n.carriers entry to read nice_name from.
    """
    return (nice_names or {}).get(carrier, carrier.title())


def carrier_nice_names(n):
    """Series mapping raw carrier name → display name."""
    names = n.carriers["nice_name"].copy()
    missing = names.isna() | (names.str.strip() == "")
    names[missing] = names.index[missing]
    return names


def carrier_colors(n, tech_colors=None):
    """Dict mapping display name → color."""
    nice = carrier_nice_names(n)
    result = {}
    for carrier in n.carriers.index:
        display = nice[carrier]
        color = n.carriers.at[carrier, "color"]
        if not color or str(color).strip() == "":
            fallback = tech_colors or {}
            color = fallback.get(display) or fallback.get(carrier) or "#aaaaaa"
        result[display] = color
    return result


def find_scenario_networks(results_dir, scenario_filter):
    """Return {scenario_label: path} for each run name in scenario_filter."""
    results_dir = os.path.realpath(results_dir)
    networks = {}
    for dirpath, dirnames, filenames in os.walk(results_dir):
        for fname in sorted(filenames):
            if not fname.endswith(".nc"):
                continue
            nc_path = os.path.join(dirpath, fname)
            parent = os.path.basename(dirpath)
            # Networks live at <scenario>/networks/*.nc; step up one level to
            # get the scenario folder name. Otherwise use the parent directly.
            if parent == "networks":
                label = os.path.basename(os.path.dirname(dirpath))
            else:
                label = parent
            if label not in scenario_filter:
                continue
            if label not in networks:
                networks[label] = nc_path
    return networks


def clean_scenario_label(label, label_map=None):
    """Return a display label for a scenario folder name."""
    return (label_map or {}).get(label, label)


def resolve_reference_year(run_name):
    """Extract a calendar year from a trailing _YYYY in a run.name, if any."""
    match = re.search(r"_(\d{4})$", run_name)
    return int(match.group(1)) if match else None


def load_reference_generation(path, year, nice_names=None):
    """Annual generation by display-name carrier [TWh] for one calendar year."""
    reference_generation = pd.read_csv(path)
    reference_generation = reference_generation[reference_generation["year"] == year]
    if reference_generation.empty:
        return pd.Series(dtype=float)
    generation_by_fuel = (
        reference_generation.set_index("carrier")["generation_gwh"] / 1e3
    )
    generation_by_fuel.index = generation_by_fuel.index.map(
        lambda f: resolve_nice_name(f, nice_names)
    )
    return generation_by_fuel.groupby(level=0).sum()


def _by_carrier(s, exclude):
    """Aggregate a (component, carrier) statistics Series to carrier level."""
    return s.groupby(level="carrier").sum().pipe(lambda x: x[~x.index.isin(exclude)])


def extract_capacity(n, exclude_carriers=None):
    """Installed optimised capacity by display-name carrier [GW / GWh]."""
    exclude = set(exclude_carriers or [])
    nice = carrier_nice_names(n)
    stats = n.statistics.optimal_capacity(groupby=get_carrier, nice_names=False)
    stats = stats.drop("Line", level="component", errors="ignore")
    stats = stats.drop(("Link", "AC"), errors="ignore")
    result = _by_carrier(stats, exclude)
    result.index = result.index.map(nice)
    return result.groupby(level=0).sum() / 1e3


def extract_generation(n, exclude_carriers=None):
    """Annual net generation by display-name carrier [TWh]."""
    exclude = set(exclude_carriers or [])
    nice = carrier_nice_names(n)
    result = _by_carrier(
        n.statistics.energy_balance(groupby=get_carrier, nice_names=False).drop(
            "Load", level="component", errors="ignore"
        ),
        exclude,
    )
    result.index = result.index.map(nice)
    return result.groupby(level=0).sum() / 1e6


def extract_demand(n):
    """Total annual electricity demand [TWh]."""
    return (
        float(
            n.statistics.withdrawal(
                comps=["Load"], groupby=get_carrier, nice_names=False
            ).sum()
        )
        / 1e6
    )


def extract_investments(n, exclude_carriers=None):
    """Annualised capital cost by display-name carrier [EUR million/yr]."""
    exclude = set(exclude_carriers or [])
    nice = carrier_nice_names(n)
    result = _by_carrier(
        n.statistics.capex(groupby=get_carrier, nice_names=False).drop(
            "Line", level="component", errors="ignore"
        ),
        exclude,
    )
    result.index = result.index.map(nice)
    return result.groupby(level=0).sum() / 1e6


def extract_co2_emissions(n, exclude_carriers=None):
    """Annual CO2 emissions by display-name carrier [Mt CO2/yr]."""
    if "co2_emissions" not in n.carriers.columns:
        return pd.Series(dtype=float)
    exclude = set(exclude_carriers or [])
    nice = carrier_nice_names(n)
    ef = n.carriers["co2_emissions"]
    gen = _by_carrier(
        n.statistics.supply(groupby=get_carrier, nice_names=False).drop(
            ["Line", "Link"], level="component", errors="ignore"
        ),
        exclude,
    )
    result = (gen * gen.index.map(ef)).dropna()
    result.index = result.index.map(nice)
    return result.groupby(level=0).sum() / 1e6


def build_comparison_dfs(
    networks, tech_colors=None, label_map=None, exclude_carriers=None
):
    """Load each network; return comparison DataFrames and a merged color dict."""
    capacity_cols = {}
    generation_cols = {}
    investment_cols = {}
    co2_cols = {}
    demand_vals = {}
    display_colors = {}

    for label, path in networks.items():
        logger.info("Loading %s: %s", label, path)
        try:
            n = pypsa.Network(path)
        except Exception as e:
            logger.warning("Skipping %s: %s", label, e)
            continue
        short = clean_scenario_label(label, label_map=label_map)
        capacity_cols[short] = extract_capacity(n, exclude_carriers=exclude_carriers)
        generation_cols[short] = extract_generation(
            n, exclude_carriers=exclude_carriers
        )
        investment_cols[short] = extract_investments(
            n, exclude_carriers=exclude_carriers
        )
        co2_cols[short] = extract_co2_emissions(n, exclude_carriers=exclude_carriers)
        demand_vals[short] = extract_demand(n)
        display_colors.update(carrier_colors(n, tech_colors))

    capacity_df = pd.DataFrame(capacity_cols).fillna(0)
    generation_df = pd.DataFrame(generation_cols).fillna(0)
    investment_df = pd.DataFrame(investment_cols).fillna(0)
    co2_df = pd.DataFrame(co2_cols).fillna(0)
    demand_s = pd.Series(demand_vals)
    return capacity_df, generation_df, investment_df, co2_df, demand_s, display_colors


def _sort_df(df):
    in_pref = [c for c in preferred_order if c in df.index]
    out_pref = [c for c in df.index if c not in preferred_order]
    return df.loc[in_pref + out_pref]


def plot_stacked_bar(df, ylabel, title, display_colors, output_path, threshold=0.01):
    """Stacked bar chart with one bar per scenario (column)."""
    df = _sort_df(df.copy())
    df = df[df.max(axis=1) >= threshold]
    if df.empty:
        logger.warning("No data above threshold for: %s", title)
        return

    colors = [display_colors.get(t, "#aaaaaa") for t in df.index]
    n_scenarios = len(df.columns)

    fig, ax = plt.subplots(figsize=(max(8, n_scenarios * 1.6), 7))
    df.T.plot(
        kind="bar",
        stacked=True,
        ax=ax,
        color=colors,
        width=0.6,
        edgecolor="white",
        linewidth=0.4,
    )

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(
        handles[::-1],
        labels[::-1],
        ncol=1,
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        fontsize=9,
        frameon=True,
    )
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, pad=10)
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", output_path)


def plot_demand_bar(demand_s, output_path):
    """Simple bar chart of total annual demand per scenario."""
    if demand_s.empty or demand_s.sum() == 0:
        return
    fig, ax = plt.subplots(figsize=(max(6, len(demand_s) * 1.4), 5))
    bars = ax.bar(
        demand_s.index, demand_s.values, color="#110d63", width=0.5, edgecolor="white"
    )
    ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
    ax.set_ylabel("Annual demand [TWh]", fontsize=11)
    ax.set_title("Total Electricity Demand by Scenario", fontsize=13, pad=10)
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    ax.grid(axis="y", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", output_path)


def run_comparison(
    results_dir,
    output_dir,
    tech_colors,
    scenario_filter,
    label_map=None,
    exclude_carriers=None,
    reference_data=None,
    reference_generation_path=None,
    nice_names=None,
):
    networks = find_scenario_networks(results_dir, scenario_filter)
    if not networks:
        logger.warning("No .nc network files found under %s", results_dir)
        return

    logger.info("Found %d scenarios: %s", len(networks), list(networks.keys()))
    os.makedirs(output_dir, exist_ok=True)

    capacity_df, generation_df, investment_df, co2_df, demand_s, display_colors = (
        build_comparison_dfs(
            networks,
            tech_colors=tech_colors,
            label_map=label_map,
            exclude_carriers=exclude_carriers,
        )
    )

    # scenario_filter order defines the x-axis order for every chart.
    labels = [
        clean_scenario_label(name, label_map=label_map) for name in scenario_filter
    ]
    cols = [c for c in labels if c in capacity_df.columns]
    capacity_df = capacity_df[cols]
    generation_df = generation_df[cols]
    investment_df = investment_df[cols]
    co2_df = co2_df[cols]
    demand_s = demand_s.reindex(cols)

    if "generation" in (reference_data or []) and reference_generation_path:
        gen_order = []
        reference_cols = {}
        for raw_name, short in zip(scenario_filter, labels):
            if short not in generation_df.columns:
                continue
            gen_order.append(short)
            year = resolve_reference_year(raw_name)
            if year is None:
                logger.warning(
                    "Could not resolve a reference year from run.name %r; "
                    "skipping reference overlay for this scenario.",
                    raw_name,
                )
                continue
            ref_series = load_reference_generation(
                reference_generation_path, year, nice_names=nice_names
            )
            if ref_series.empty:
                logger.warning(
                    "No reference generation data for year %d (scenario %s)",
                    year,
                    raw_name,
                )
                continue
            ref_label = f"Actual {year}"
            reference_cols[ref_label] = ref_series
            gen_order.append(ref_label)

        if reference_cols:
            ref_df = pd.DataFrame(reference_cols)
            generation_df = pd.concat([generation_df, ref_df], axis=1).fillna(0)
            generation_df = generation_df[gen_order]

    if not capacity_df.empty:
        plot_stacked_bar(
            capacity_df,
            ylabel="Installed capacity [GW / GWh]",
            title="Installed Capacity by Scenario",
            display_colors=display_colors,
            output_path=os.path.join(output_dir, "installed_capacity.png"),
        )

    if not generation_df.empty:
        plot_stacked_bar(
            generation_df,
            ylabel="Annual generation [TWh]",
            title="Generation Mix by Scenario",
            display_colors=display_colors,
            output_path=os.path.join(output_dir, "generation_mix.png"),
        )

    if not investment_df.empty:
        plot_stacked_bar(
            investment_df,
            ylabel="Annualised capital cost [EUR million/yr]",
            title="Investments by Scenario",
            display_colors=display_colors,
            output_path=os.path.join(output_dir, "investments.png"),
        )

    if not co2_df.empty:
        plot_stacked_bar(
            co2_df,
            ylabel="Annual CO₂ emissions [Mt CO₂/yr]",
            title="Carbon Emissions by Scenario",
            display_colors=display_colors,
            output_path=os.path.join(output_dir, "co2_emissions.png"),
            threshold=0.001,
        )

    if not demand_s.empty:
        plot_demand_bar(demand_s, os.path.join(output_dir, "demand.png"))

    logger.info("All comparison plots saved to %s", output_dir)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake(
            "_compare_scenarios_group", scenario_group="cap_exp_zambia"
        )

    configure_logging(snakemake)

    tech_colors = snakemake.config["plotting"]["tech_colors"]
    nice_names = snakemake.config["plotting"]["nice_names"]
    results_dir = snakemake.params.results_dir
    scenario_group = snakemake.wildcards.scenario_group
    all_groups = snakemake.config.get("plotting", {}).get("scenario_comparison", {})
    sc_cfg = all_groups.get(scenario_group, {})
    # Exact run.name values to compare; defined in plotting.scenario_comparison.<group>.scenario_filter.
    scenario_filter = sc_cfg.get("scenario_filter", [])
    label_map = sc_cfg.get("label_map", None)
    exclude_carriers = sc_cfg.get("exclude_carriers", [])
    reference_data = sc_cfg.get("reference_data", [])
    reference_generation_path = getattr(snakemake.input, "reference_generation", None)

    run_comparison(
        results_dir=results_dir,
        output_dir=snakemake.output[0],
        tech_colors=tech_colors,
        scenario_filter=scenario_filter,
        label_map=label_map,
        exclude_carriers=exclude_carriers,
        reference_data=reference_data,
        reference_generation_path=reference_generation_path,
        nice_names=nice_names,
    )
