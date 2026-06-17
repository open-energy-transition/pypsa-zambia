# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Cross-scenario comparison plots for PyPSA-Zambia.

Reads solved networks from multiple scenario runs and produces:
- Stacked bar charts of installed capacity, generation mix and demand
- Per-scenario spatial maps with generation-mix pie charts at each bus

Outputs go to the directory defined by snakemake.output[0].

Snakemake usage:
    snakemake compare_scenarios

Standalone development usage (runs mock_snakemake from project root):
    python scripts/plot_scenario_comparison.py
"""

import os

import geopandas as gpd
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pypsa
from _helpers import configure_logging, create_logger

logger = create_logger(__name__)


def rename_techs(label):
    if label == "hydro":
        return "hydro reservoir"
    elif label == "ror":
        return "run of river"
    elif label in ("PHS", "hydro+PHS"):
        return "hydro reservoir"
    elif label == "solar":
        return "solar PV"
    elif label == "onwind":
        return "onshore wind"
    elif label == "offwind-ac":
        return "offshore wind (AC)"
    elif label == "offwind-dc":
        return "offshore wind (DC)"
    elif "battery" in label:
        return "battery storage"
    elif label == "H2":
        return "hydrogen storage"
    return label


preferred_order = pd.Index(
    [
        "hydro reservoir",
        "run of river",
        "onshore wind",
        "offshore wind (AC)",
        "offshore wind (DC)",
        "solar PV",
        "biomass",
        "geothermal",
        "nuclear",
        "coal",
        "oil",
        "OCGT",
        "CCGT",
        "battery storage",
        "hydrogen storage",
    ]
)


def find_scenario_networks(results_dir, scenario_filter=None):
    """Return {scenario_label: path} for one solved network per scenario run.

    Skips brownfield (_planned) networks and the root-level results/networks/
    folder which belongs to no named run.

    Parameters
    ----------
    scenario_filter : list of str, optional
        If provided, only scenario labels starting with one of these prefixes
        are included. Pass None to include all discovered scenarios.
    """
    results_dir = os.path.realpath(results_dir)
    networks = {}
    for dirpath, dirnames, filenames in os.walk(results_dir):
        for fname in sorted(filenames):
            if not fname.endswith(".nc") or "_planned" in fname:
                continue
            nc_path = os.path.join(dirpath, fname)
            parent = os.path.basename(dirpath)
            if parent == "networks":
                scenario_dir = os.path.dirname(dirpath)
                if os.path.realpath(scenario_dir) == results_dir:
                    continue
                label = os.path.basename(scenario_dir)
            else:
                label = parent
            if scenario_filter and not any(
                label.startswith(p) for p in scenario_filter
            ):
                continue
            if label not in networks:
                networks[label] = nc_path
    return networks


def clean_scenario_label(label):
    """Shorten scenario directory names for plot axis labels."""
    replacements = [
        ("cap_exp_zambia_", "CapExp "),
        ("validation_dispatch_zambia_", "Dispatch "),
        ("zm_cap_exp", "ZM CapExp"),
        ("zm_dispatch", "ZM Dispatch"),
    ]
    for pattern, replacement in replacements:
        if label.startswith(pattern):
            return replacement + label[len(pattern) :]
    return label


def extract_capacity(n):
    """Installed optimised capacity by display-name carrier [GW]."""
    parts = []
    if not n.generators.empty and "p_nom_opt" in n.generators.columns:
        parts.append(n.generators.groupby("carrier")["p_nom_opt"].sum())
    if not n.storage_units.empty and "p_nom_opt" in n.storage_units.columns:
        parts.append(n.storage_units.groupby("carrier")["p_nom_opt"].sum())
    if not parts:
        return pd.Series(dtype=float)
    result = pd.concat(parts).groupby(level=0).sum()
    result = result[result > 0]
    result.index = result.index.map(rename_techs)
    return result.groupby(level=0).sum() / 1e3  # MW → GW


def extract_generation(n):
    """Annual generation by display-name carrier [TWh]."""
    w = n.snapshot_weightings.generators
    parts = []
    if not n.generators_t.p.empty:
        gen = (
            n.generators_t.p.multiply(w, axis=0)
            .sum()
            .groupby(n.generators.carrier)
            .sum()
        )
        parts.append(gen)
    if not n.storage_units_t.p.empty:
        p_su = n.storage_units_t.p.clip(lower=0)
        gen_su = p_su.multiply(w, axis=0).sum().groupby(n.storage_units.carrier).sum()
        parts.append(gen_su)
    if not parts:
        return pd.Series(dtype=float)
    result = pd.concat(parts).groupby(level=0).sum()
    result = result[result > 0]
    result.index = result.index.map(rename_techs)
    return result.groupby(level=0).sum() / 1e6  # MWh → TWh


def extract_demand(n):
    """Total annual electricity demand [TWh]."""
    if n.loads_t.p.empty:
        return 0.0
    w = n.snapshot_weightings.generators
    return float(n.loads_t.p.clip(lower=0).multiply(w, axis=0).sum().sum()) / 1e6


def extract_investments(n):
    """Annualised capital cost by display-name carrier [EUR million/yr].

    Uses p_nom_opt * capital_cost from generators and storage units.
    Carriers with zero capital cost (load shedding, export) are excluded.
    """
    parts = []
    if not n.generators.empty and "p_nom_opt" in n.generators.columns:
        cap = n.generators["capital_cost"] * n.generators["p_nom_opt"]
        parts.append(cap.groupby(n.generators["carrier"]).sum())
    if not n.storage_units.empty and "p_nom_opt" in n.storage_units.columns:
        cap = n.storage_units["capital_cost"] * n.storage_units["p_nom_opt"]
        parts.append(cap.groupby(n.storage_units["carrier"]).sum())
    if not parts:
        return pd.Series(dtype=float)
    result = pd.concat(parts).groupby(level=0).sum()
    result = result[result > 0]
    result.index = result.index.map(rename_techs)
    return result.groupby(level=0).sum() / 1e6  # EUR → EUR million


def extract_co2_emissions(n):
    """Annual CO2 emissions by display-name carrier [Mt CO2/yr].

    Uses n.carriers.co2_emissions [tCO2/MWh_el] multiplied by
    annual generation per carrier.
    """
    if "co2_emissions" not in n.carriers.columns:
        return pd.Series(dtype=float)
    w = n.snapshot_weightings.generators
    emission_factors = n.carriers["co2_emissions"]

    parts = []
    if not n.generators_t.p.empty:
        gen = (
            n.generators_t.p.multiply(w, axis=0)
            .sum()
            .groupby(n.generators["carrier"])
            .sum()
        )
        co2 = gen * gen.index.map(emission_factors)
        parts.append(co2)

    if not parts:
        return pd.Series(dtype=float)

    result = pd.concat(parts).groupby(level=0).sum()
    result = result[result > 0]
    result.index = result.index.map(rename_techs)
    return result.groupby(level=0).sum() / 1e6  # tCO2 → Mt CO2


def build_comparison_dfs(networks):
    """Load each network; return comparison DataFrames for all metrics."""
    capacity_cols = {}
    generation_cols = {}
    investment_cols = {}
    co2_cols = {}
    demand_vals = {}

    for label, path in networks.items():
        logger.info("Loading %s: %s", label, path)
        try:
            n = pypsa.Network(path)
        except Exception as e:
            logger.warning("Skipping %s: %s", label, e)
            continue
        short = clean_scenario_label(label)
        capacity_cols[short] = extract_capacity(n)
        generation_cols[short] = extract_generation(n)
        investment_cols[short] = extract_investments(n)
        co2_cols[short] = extract_co2_emissions(n)
        demand_vals[short] = extract_demand(n)

    capacity_df = pd.DataFrame(capacity_cols).fillna(0)
    generation_df = pd.DataFrame(generation_cols).fillna(0)
    investment_df = pd.DataFrame(investment_cols).fillna(0)
    co2_df = pd.DataFrame(co2_cols).fillna(0)
    demand_s = pd.Series(demand_vals)
    return capacity_df, generation_df, investment_df, co2_df, demand_s


def _sort_df(df):
    in_pref = df.index.intersection(preferred_order)
    out_pref = df.index.difference(preferred_order)
    return df.loc[in_pref.tolist() + out_pref.tolist()]


def _get_color(tech, tech_colors):
    return tech_colors.get(tech, tech_colors.get(rename_techs(tech), "#aaaaaa"))


def plot_stacked_bar(df, ylabel, title, tech_colors, output_path, threshold=0.01):
    """Stacked bar chart with one bar per scenario (column)."""
    df = _sort_df(df.copy())
    df = df[df.max(axis=1) >= threshold]
    if df.empty:
        logger.warning("No data above threshold for: %s", title)
        return

    colors = [_get_color(t, tech_colors) for t in df.index]
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


def _bus_generation_by_carrier(n):
    """DataFrame[bus x display-carrier] of annual generation [GWh]."""
    w = n.snapshot_weightings.generators
    parts = []

    if not n.generators_t.p.empty:
        gen = n.generators_t.p.multiply(w, axis=0).sum()
        meta = n.generators[["carrier", "bus"]].copy()
        meta["gen"] = gen
        pivot = (
            meta[meta["gen"] > 0]
            .groupby(["bus", "carrier"])["gen"]
            .sum()
            .unstack(fill_value=0)
        )
        pivot.columns = pivot.columns.map(rename_techs)
        pivot = pivot.T.groupby(level=0).sum().T
        parts.append(pivot)

    if not n.storage_units_t.p.empty:
        p = n.storage_units_t.p.clip(lower=0)
        gen = p.multiply(w, axis=0).sum()
        meta = n.storage_units[["carrier", "bus"]].copy()
        meta["gen"] = gen
        pivot = (
            meta[meta["gen"] > 0]
            .groupby(["bus", "carrier"])["gen"]
            .sum()
            .unstack(fill_value=0)
        )
        pivot.columns = pivot.columns.map(rename_techs)
        pivot = pivot.T.groupby(level=0).sum().T
        parts.append(pivot)

    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, axis=0).fillna(0).groupby(level=0).sum() / 1e3


def plot_spatial_map(
    n, label, tech_colors, output_path, country_shapes_path=None, bus_regions_path=None
):
    """Geographic map with generation-mix pie charts at each bus.

    Pie-chart radius is proportional to total installed capacity.
    """
    buses = n.buses[n.buses.carrier == "AC"].copy()
    if buses.empty:
        buses = n.buses.copy()

    bus_gen = _bus_generation_by_carrier(n)
    if bus_gen.empty:
        logger.warning("No generation data for spatial map of %s", label)
        return

    # Capacity per bus for sizing pie charts
    bus_cap = pd.Series(0.0, index=buses.index)
    if not n.generators.empty and "p_nom_opt" in n.generators.columns:
        g = n.generators[n.generators["bus"].isin(buses.index)]
        bus_cap = bus_cap.add(g.groupby("bus")["p_nom_opt"].sum() / 1e3, fill_value=0)
    if not n.storage_units.empty and "p_nom_opt" in n.storage_units.columns:
        su = n.storage_units[n.storage_units["bus"].isin(buses.index)]
        bus_cap = bus_cap.add(su.groupby("bus")["p_nom_opt"].sum() / 1e3, fill_value=0)

    fig, ax = plt.subplots(figsize=(10, 9))

    # Background outline
    if country_shapes_path and os.path.exists(country_shapes_path):
        gpd.read_file(country_shapes_path).boundary.plot(
            ax=ax, color="gray", linewidth=0.8, zorder=1
        )
    elif bus_regions_path and os.path.exists(bus_regions_path):
        gpd.read_file(bus_regions_path).boundary.plot(
            ax=ax, color="lightgray", linewidth=0.5, zorder=1
        )

    # Transmission lines
    for _, line in n.lines.iterrows():
        b0, b1 = line.get("bus0"), line.get("bus1")
        if b0 in buses.index and b1 in buses.index:
            x0, y0 = buses.loc[b0, ["x", "y"]]
            x1, y1 = buses.loc[b1, ["x", "y"]]
            ax.plot(
                [x0, x1], [y0, y1], color="#70af1d", linewidth=0.8, zorder=2, alpha=0.7
            )

    # Order carriers for consistent pie slices
    carriers_all = [c for c in preferred_order if c in bus_gen.columns]
    carriers_all += [c for c in bus_gen.columns if c not in preferred_order]

    max_cap = bus_cap.max() if bus_cap.max() > 0 else 1.0
    pie_scale = 1.5  # max pie radius in degrees

    for bus_id, bus_row in buses.iterrows():
        if bus_id not in bus_gen.index:
            continue
        gen_row = bus_gen.loc[bus_id, [c for c in carriers_all if c in bus_gen.columns]]
        if gen_row.sum() == 0:
            continue
        cap = bus_cap.get(bus_id, 0)
        radius = pie_scale * (cap / max_cap) ** 0.5
        x, y = bus_row["x"], bus_row["y"]
        inset = ax.inset_axes(
            [x - radius, y - radius, 2 * radius, 2 * radius],
            transform=ax.transData,
        )
        inset.pie(
            gen_row.values,
            colors=[_get_color(c, tech_colors) for c in gen_row.index],
            startangle=90,
        )
        inset.set_aspect("equal")

    # Carrier legend
    legend_carriers = [c for c in carriers_all if c in bus_gen.columns]
    patches = [
        mpatches.Patch(color=_get_color(c, tech_colors), label=c)
        for c in legend_carriers
    ]
    ax.legend(handles=patches, loc="lower left", fontsize=8, ncol=2, framealpha=0.9)

    ax.set_xlim(buses["x"].min() - 2, buses["x"].max() + 2)
    ax.set_ylim(buses["y"].min() - 2, buses["y"].max() + 2)
    ax.set_title("Generation Mix — {}".format(label), fontsize=13, pad=10)
    ax.set_xlabel("Longitude", fontsize=9)
    ax.set_ylabel("Latitude", fontsize=9)
    ax.grid(alpha=0.2)

    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", output_path)


def run_comparison(
    results_dir,
    output_dir,
    tech_colors,
    scenario_filter=None,
    country_shapes_path=None,
    bus_regions_path=None,
):
    networks = find_scenario_networks(results_dir, scenario_filter=scenario_filter)
    if not networks:
        logger.warning("No .nc network files found under %s", results_dir)
        return

    logger.info("Found %d scenarios: %s", len(networks), list(networks.keys()))
    os.makedirs(output_dir, exist_ok=True)

    capacity_df, generation_df, investment_df, co2_df, demand_s = build_comparison_dfs(
        networks
    )

    if not capacity_df.empty:
        plot_stacked_bar(
            capacity_df,
            ylabel="Installed capacity [GW]",
            title="Installed Capacity by Scenario",
            tech_colors=tech_colors,
            output_path=os.path.join(output_dir, "installed_capacity.png"),
        )

    if not generation_df.empty:
        plot_stacked_bar(
            generation_df,
            ylabel="Annual generation [TWh]",
            title="Generation Mix by Scenario",
            tech_colors=tech_colors,
            output_path=os.path.join(output_dir, "generation_mix.png"),
        )

    if not investment_df.empty:
        plot_stacked_bar(
            investment_df,
            ylabel="Annualised capital cost [EUR million/yr]",
            title="Investments by Scenario",
            tech_colors=tech_colors,
            output_path=os.path.join(output_dir, "investments.png"),
        )

    if not co2_df.empty:
        plot_stacked_bar(
            co2_df,
            ylabel="Annual CO₂ emissions [Mt CO₂/yr]",
            title="Carbon Emissions by Scenario",
            tech_colors=tech_colors,
            output_path=os.path.join(output_dir, "co2_emissions.png"),
            threshold=0.001,
        )

    if not demand_s.empty:
        plot_demand_bar(demand_s, os.path.join(output_dir, "demand.png"))

    spatial_dir = os.path.join(output_dir, "spatial")
    for label, path in networks.items():
        try:
            n = pypsa.Network(path)
        except Exception as e:
            logger.warning("Skipping spatial map for %s: %s", label, e)
            continue
        short = clean_scenario_label(label)
        safe = short.replace(" ", "_").replace("/", "_")
        plot_spatial_map(
            n,
            label=short,
            tech_colors=tech_colors,
            output_path=os.path.join(spatial_dir, "{}_spatial.png".format(safe)),
            country_shapes_path=country_shapes_path,
            bus_regions_path=bus_regions_path,
        )

    logger.info("All comparison plots saved to %s", output_dir)


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("compare_scenarios")

    configure_logging(snakemake)

    tech_colors = snakemake.config["plotting"]["tech_colors"]
    results_dir = snakemake.params.results_dir
    scenario_filter = snakemake.params.get("scenario_filter", None)

    country_shapes = os.path.join("resources", "shapes", "country_shapes.geojson")
    bus_regions = os.path.join(
        "resources", "bus_regions", "regions_onshore_elec_s_10.geojson"
    )

    run_comparison(
        results_dir=results_dir,
        output_dir=snakemake.output[0],
        tech_colors=tech_colors,
        scenario_filter=scenario_filter,
        country_shapes_path=country_shapes,
        bus_regions_path=bus_regions,
    )
