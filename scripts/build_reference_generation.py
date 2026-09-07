# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Aggregate historical Zambian generation reference data by PyPSA carrier.

Reads the four wide-format ERB / IPP generation datasets (one row per year,
one column per power plant, values in GWh), maps each plant to a reference
carrier, and sums generation by (year, carrier).

Carrier is derived from data/custom_powerplants.csv wherever a plant is part of
the network model, using the same Fueltype/Technology -> carrier logic as
scripts/add_electricity.py
"""

import pandas as pd
from _helpers import configure_logging, create_logger, to_csv_nafix

logger = create_logger(__name__)

# Itezhi tezhi is a hydro plant in the IPP dataset, but an oil plant in the diesel dataset.
# Could be a backup diesel generator at the hydro site, but we don't have any way to know for sure.
# We rename it to avoid it not being unmapped in the carrier mapping step and dropping it from the reference generation.
DIESEL_PLANT_RENAMES = {"Itezhi tezhi": "Itezhi tezhi oil"}

HYDRO_TECHNOLOGY_TO_CARRIER = {
    "Reservoir": "hydro",
    "Run-Of-River": "ror",
    "Pumped Storage": "PHS",
}
FUELTYPE_TO_CARRIER = {
    "Hard Coal": "coal",
    "Oil": "oil",
    "Bioenergy": "biomass",
    "Solar": "solar",
}


def derive_pypsa_carrier(fueltype, technology):
    """Map a custom_powerplants.csv (Fueltype, Technology) pair to a raw carrier code."""
    if fueltype == "Hydro":
        return HYDRO_TECHNOLOGY_TO_CARRIER.get(technology)
    return FUELTYPE_TO_CARRIER.get(fueltype)


def _clean_columns(columns):
    """Collapse whitespace/newlines in (possibly multi-line) CSV headers."""
    return [" ".join(str(c).split()) for c in columns]


def load_plant_generation(path, rename=None):
    """Melt one wide (Year x plant) generation CSV into long format."""
    df = pd.read_csv(path)
    df.columns = _clean_columns(df.columns)
    if rename:
        df = df.rename(columns=rename)
    long = df.melt(id_vars="Year", var_name="plant", value_name="generation_gwh")
    long = long.rename(columns={"Year": "year"})
    return long


def build_carrier_mapping(alias_path, custom_powerplants_path):
    """Build a Series mapping each reference-data plant name to a carrier."""
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
    joined["carrier"] = joined.apply(
        lambda row: derive_pypsa_carrier(row["Fueltype"], row["Technology"]), axis=1
    )

    fallback = aliases.loc[~has_alias, ["data", "fuel_override"]].rename(
        columns={"fuel_override": "carrier"}
    )

    mapping = pd.concat([joined[["data", "carrier"]], fallback], ignore_index=True)
    unresolved = sorted(mapping.loc[mapping["carrier"].isna(), "data"])
    if unresolved:
        logger.warning("Could not resolve a reference carrier for: %s", unresolved)
    return mapping.dropna(subset=["carrier"]).set_index("data")["carrier"]


def aggregate_by_carrier(generation, carrier_mapping):
    """Map plants to reference carriers and sum generation by (year, carrier)."""
    unmapped = sorted(set(generation["plant"]) - set(carrier_mapping.index))
    if unmapped:
        logger.warning(
            "%d plant(s) missing from the carrier mapping and dropped: %s",
            len(unmapped),
            unmapped,
        )

    generation = generation.copy()
    generation["carrier"] = generation["plant"].map(carrier_mapping)
    generation = generation.dropna(subset=["carrier"])

    return (
        generation.groupby(["year", "carrier"], as_index=False)["generation_gwh"]
        .sum()
        .sort_values(["year", "carrier"])
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

    carrier_mapping = build_carrier_mapping(
        snakemake.input.fuel_aliases, snakemake.input.custom_powerplants
    )
    reference_generation = aggregate_by_carrier(generation, carrier_mapping)

    to_csv_nafix(reference_generation, snakemake.output[0], index=False)
