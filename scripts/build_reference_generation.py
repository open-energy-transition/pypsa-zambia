# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Aggregate historical Zambian generation reference data by PyPSA fuel.

Reads the four wide-format ZESCO / IPP generation datasets (one row per year,
one column per power plant, values in GWh), maps each plant to a PyPSA fuel
via data/source_to_pypsa_fuels_mapping.csv, and sums generation by
(year, fuel). Output is long-format so it can be filtered to a single
calendar year when overlaid on a scenario comparison plot.
"""

import pandas as pd
from _helpers import configure_logging, create_logger, to_csv_nafix

logger = create_logger(__name__)

# The diesel dataset's "Itezhi tezhi" plant is a different, unrelated plant
# from the IPP dataset's "Itezhi tezhi Power Corporation" (a hydro plant).
# Renamed here to the disambiguated name already used in the fuel mapping.
DIESEL_PLANT_RENAMES = {"Itezhi tezhi": "Itezhi tezhi oil"}


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


def aggregate_by_fuel(generation, fuel_mapping_path):
    """Map plants to PyPSA fuels and sum generation by (year, fuel)."""
    fuel_mapping = pd.read_csv(fuel_mapping_path).set_index("data")["pypsa"]

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

    reference_generation = aggregate_by_fuel(generation, snakemake.input.fuel_mapping)

    to_csv_nafix(reference_generation, snakemake.output[0], index=False)
