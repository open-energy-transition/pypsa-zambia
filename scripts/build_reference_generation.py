# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Aggregate historical Zambian generation reference data by PyPSA fuel.

Reads the four wide-format ZESCO / IPP generation datasets (one row per year,
one column per power plant, values in GWh), maps each plant to a reference
fuel, and sums generation by (year, fuel). Output is long-format so it can be
filtered to a single calendar year when overlaid on a scenario comparison
plot.

Fuel is derived from data/custom_powerplants.csv wherever a plant is part of
the network model, using the same Fueltype/Technology -> carrier logic as
scripts/add_electricity.py (see derive_pypsa_fuel), so each row lands on the
same raw carrier code (e.g. "hydro", "ror", "coal") the model itself would
assign; plot_scenario_comparison.py then resolves those to display names via
plotting.nice_names from the run config, same as it does for model carriers.
data/reference_fuel_aliases.csv links each reference-data plant name to its
data/custom_powerplants.csv Name; plants not part of the network model (small
captive/industrial generators) fall back to a hand-set fuel_override instead.
"""

import pandas as pd
from _helpers import configure_logging, create_logger, to_csv_nafix

logger = create_logger(__name__)

# The diesel dataset's "Itezhi tezhi" plant is a different, unrelated plant
# from the IPP dataset's "Itezhi tezhi Power Corporation" (a hydro plant).
# Renamed here to the disambiguated name already used in the fuel aliases.
DIESEL_PLANT_RENAMES = {"Itezhi tezhi": "Itezhi tezhi oil"}

# Mirrors the Fueltype/Technology -> carrier logic in scripts/add_electricity.py
# (attach_hydro's tech_to_carrier dict, and load_powerplants' carrier_dict):
# same raw carrier codes the model assigns, so plotting can resolve display
# names from plotting.nice_names in the run config instead of a second dict.
HYDRO_TECHNOLOGY_TO_FUEL = {
    "Reservoir": "hydro",
    "Run-Of-River": "ror",
    "Pumped Storage": "PHS",
}
FUELTYPE_TO_FUEL = {
    "Hard Coal": "coal",
    "Oil": "oil",
    "Bioenergy": "biomass",
    "Solar": "solar",
}


def derive_pypsa_fuel(fueltype, technology):
    """Map a custom_powerplants.csv (Fueltype, Technology) pair to a raw carrier code."""
    if fueltype == "Hydro":
        return HYDRO_TECHNOLOGY_TO_FUEL.get(technology)
    return FUELTYPE_TO_FUEL.get(fueltype)


def _clean_columns(columns):
    """Collapse whitespace/newlines in (possibly multi-line) CSV headers."""
    return [" ".join(str(c).split()) for c in columns]


def load_plant_generation(path, rename=None):
    """Melt one wide (Year x plant) generation CSV into long format.

    Returns a DataFrame with columns: year, plant, generation_gwh.
    """
    df = pd.read_csv(path)
    df.columns = _clean_columns(df.columns)
    if rename:
        df = df.rename(columns=rename)
    long = df.melt(id_vars="Year", var_name="plant", value_name="generation_gwh")
    long = long.rename(columns={"Year": "year"})
    return long


def build_fuel_mapping(alias_path, custom_powerplants_path):
    """Build a Series mapping each reference-data plant name to a fuel label.

    Plants with a `custom_powerplants_name` alias are joined against
    data/custom_powerplants.csv and their fuel is derived from its
    Fueltype/Technology columns (see derive_pypsa_fuel), so classification
    stays consistent with how the model itself assigns carriers. Plants
    without an alias (not part of the network model) fall back to the
    alias file's `fuel_override` column.
    """
    aliases = pd.read_csv(alias_path)
    custom_ppl = pd.read_csv(custom_powerplants_path).set_index("Name")[
        ["Fueltype", "Technology"]
    ]

    has_alias = aliases["custom_powerplants_name"].notna()
    joined = aliases.loc[has_alias].join(
        custom_ppl, on="custom_powerplants_name", how="left"
    )
    missing = sorted(joined.loc[joined["Fueltype"].isna(), "custom_powerplants_name"])
    if missing:
        logger.warning(
            "custom_powerplants_name(s) not found in %s, dropped: %s",
            custom_powerplants_path,
            missing,
        )
    joined = joined.dropna(subset=["Fueltype"])
    joined["fuel"] = joined.apply(
        lambda row: derive_pypsa_fuel(row["Fueltype"], row["Technology"]), axis=1
    )

    fallback = aliases.loc[~has_alias, ["data", "fuel_override"]].rename(
        columns={"fuel_override": "fuel"}
    )

    mapping = pd.concat([joined[["data", "fuel"]], fallback], ignore_index=True)
    unresolved = sorted(mapping.loc[mapping["fuel"].isna(), "data"])
    if unresolved:
        logger.warning("Could not resolve a reference fuel for: %s", unresolved)
    return mapping.dropna(subset=["fuel"]).set_index("data")["fuel"]


def aggregate_by_fuel(generation, fuel_mapping):
    """Map plants to reference fuels and sum generation by (year, fuel)."""
    unmapped = sorted(set(generation["plant"]) - set(fuel_mapping.index))
    if unmapped:
        logger.warning(
            "%d plant(s) missing from the fuel mapping and dropped: %s",
            len(unmapped),
            unmapped,
        )

    generation = generation.copy()
    generation["fuel"] = generation["plant"].map(fuel_mapping)
    generation = generation.dropna(subset=["fuel"])

    return (
        generation.groupby(["year", "fuel"], as_index=False)["generation_gwh"]
        .sum()
        .sort_values(["year", "fuel"])
        .reset_index(drop=True)
    )


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("build_reference_generation")

    configure_logging(snakemake)

    generation = pd.concat(
        [
            load_plant_generation(snakemake.input.ipp),
            load_plant_generation(snakemake.input.diesel, rename=DIESEL_PLANT_RENAMES),
            load_plant_generation(snakemake.input.large_hydro),
            load_plant_generation(snakemake.input.mini_hydro),
        ],
        ignore_index=True,
    )

    fuel_mapping = build_fuel_mapping(
        snakemake.input.fuel_aliases, snakemake.input.custom_powerplants
    )
    reference_generation = aggregate_by_fuel(generation, fuel_mapping)

    to_csv_nafix(reference_generation, snakemake.output[0], index=False)
