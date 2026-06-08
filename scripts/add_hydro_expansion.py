# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

# -*- coding: utf-8 -*-
"""
Adds expandable hydro

Outputs
-------

- ``networks/elec.nc``:

    .. image:: /img/elec.png
            :width: 75 %
            :align: center

Description
-----------

The rule :mod:`add_hydro_expansion` adds expandable hydro reservoirs at specified locations 
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import powerplantmatching as pm
import pypsa
import xarray as xr
from _helpers import (
    configure_logging,
    create_logger,
    read_csv_nafix,
    sanitize_carriers,
    sanitize_locations,
    update_p_nom_max,
)
from powerplantmatching.export import map_country_bus
from utility_custom_features import add_biomass_potential, disaggregate_plants

idx = pd.IndexSlice

logger = create_logger(__name__)

# TODO Revise according to the data format for hydro siting
def load_powerplants(
    ppl_fn: str,
) -> pd.DataFrame:
    """
    Load and preprocess powerplant matching data, fill missing datein/dateout, and assign grouping years.
    Parameters
    ----------
    ppl_fn : str
        Path to powerplant matching csv file.
    costs : pd.DataFrame
        DataFrame containing technology costs.
    fill_values : dict
        Dictionary containing default values for lifetime.
    grouping_years : list
        List of years to group build years into.

    Returns
    -------
    ppl : pd.DataFrame
        Power plant list DataFrame.
    """
    carrier_dict = {
        "ocgt": "OCGT",
        "ccgt": "CCGT",
        "bioenergy": "biomass",
        "ccgt, thermal": "CCGT",
        "hard coal": "coal",
    }
    ppl = (
        read_csv_nafix(ppl_fn, index_col=0, dtype={"bus": "str"})
        .powerplant.to_pypsa_names()
        .powerplant.convert_country_to_alpha2()
        .rename(columns=str.lower)
        .drop(columns=["efficiency"])
        .replace({"carrier": carrier_dict})
    )

    return ppl

# TODO Fix refuse
# def attach_hydro(
#     n: pypsa.Network,
#     costs: pd.DataFrame,
#     ppl: pd.DataFrame,
#     hydro_min_inflow_pu: float = 1.0,
# ) -> None:
#     """
#     Add expandable hydro powerplants to the network as Hydro Storage units

#     Parameters
#     ----------
#     n : pypsa.Network
#         The PyPSA network to modify.
#     costs : pd.DataFrame
#         DataFrame containing technology costs.
#     ppl : pd.DataFrame
#         Power plant DataFrame.

#     Returns
#     -------
#     None
#     """


def attach_hydro(
    n,
    costs,
    ppl,
    hydro_min_inflow_pu=1,
    # disaggregate_flag=False,
):

    carriers = "hydro"

    c = snakemake.params.renewable["hydro"]

    ppl = (
        ppl.query('carrier == "hydro"')
        .assign(ppl_id=lambda df: df.index)
        .reset_index(drop=True)
        .rename(index=lambda s: str(s) + " hydro")
    )    

    # Map technology to carrier before aggregation
    tech_to_carrier = {
        "Run-Of-River": "ror",
        "Pumped Storage": "PHS",
        "Reservoir": "hydro",
    }
    ppl["carrier"] = ppl["technology"].map(tech_to_carrier)

    ror = ppl[ppl["carrier"] == "ror"]
    phs = ppl[ppl["carrier"] == "PHS"]
    hydro = ppl[ppl["carrier"] == "hydro"]
    tbd = ppl[ppl.technology.isna()]  # To be determined technologies

    inflow_idx = ror.index.union(hydro.index).union(tbd.index)
    if not inflow_idx.empty:
        with xr.open_dataarray(snakemake.input.potential) as inflow:
            found_plants = ppl.ppl_id[ppl.ppl_id.isin(inflow.indexes["plant"])]
            missing_plants_idxs = ppl.index.difference(found_plants.index)

            # if missing time series are found, notify the user and exclude missing hydro plants
            if not missing_plants_idxs.empty:
                # original total p_nom
                total_p_nom = ror.p_nom.sum() + hydro.p_nom.sum() + tbd.p_nom.sum()

                ror = ror.loc[ror.index.intersection(found_plants.index)]
                hydro = hydro.loc[hydro.index.intersection(found_plants.index)]
                tbd = tbd.loc[tbd.index.intersection(found_plants.index)]

                # loss of p_nom
                loss_p_nom = (
                    ror.p_nom.sum() + hydro.p_nom.sum() + tbd.p_nom.sum() - total_p_nom
                )

                logger.warning(
                    f"'{snakemake.input.profile_hydro}' is missing inflow time-series for at least one bus: {', '.join(missing_plants_idxs)}."
                    f"Corresponding hydro plants are dropped, corresponding to a total loss of {loss_p_nom:.2f}MW out of {total_p_nom:.2f}MW."
                )

            # if there are any plants for which runoff data are available
            if not found_plants.empty:
                inflow_t = (
                    inflow.sel(plant=found_plants.values)
                    .assign_coords(plant=found_plants.index)
                    .rename({"plant": "name"})
                    .transpose("time", "name")
                    .to_pandas()
                )

    if "hydro" in carriers and not hydro.empty:

        n.madd(
            "StorageUnit",
            hydro.index,
            carrier="",
            bus=hydro["bus"],
            # p_nom=hydro["p_nom"],
            p_nom_extendable=True,
            max_hours=hydro_max_hours,
            capital_cost=(
                costs.at["hydro", "capital_cost"]
                if c.get("hydro_capital_cost")
                else 0.0
            ),
            marginal_cost=costs.at["hydro", "marginal_cost"],
            p_max_pu=1.0,  # dispatch
            p_min_pu=0.0,  # store
            efficiency_dispatch=costs.at["hydro", "efficiency"],
            efficiency_store=0.0,
            cyclic_state_of_charge=True,
            lifetime=hydro["lifetime"],
        )

        logger.info(
            f"Added {len(hydro)} hydro storage units with {hydro['p_nom'].sum() / 1e3:.2f} GW"
        )

if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("add_electricity", configfile="config_glofas_testing.yaml")

    configure_logging(snakemake)

    n = pypsa.Network(snakemake.input.base_network)
    Nyears = n.snapshot_weightings.objective.sum() / 8760.0

    attach_hydro(
        n,
        costs,
        ppl,
        snakemake.params.renewable["hydro"]["hydro_min_inflow_pu"],
    )

    n.export_to_netcdf(snakemake.output[0])
