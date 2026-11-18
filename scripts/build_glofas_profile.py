# SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Create a custom inflow profile to be used in a modelling workflow
by using GloFAS dataset

Relevant Settings
-----------------
.. code:: yaml

    snapshots:

Inputs
------
- ``resources/powerplants.csv`` is a file with locations of power plants
- ``cutouts/{country}-{year}-glofas.nc`` is GloFAS file used as an input

Outputs
-------

- ``cutouts/profile_hydro_glofas.nc``

Description
-----------
A custom hydro profile is built using GloFAS data on inflow directly
instead of using a usual atlite workflow based on ERA5

"""

import numpy as np
import pandas as pd
import xarray as xr
from _helpers import configure_logging, create_logger
from add_electricity import load_powerplants

logger = create_logger(__name__)

DEFAULT_DAMHEIGHT_M = 5.0  # default reservoir water height
# HYDRO_MULTIPLIER = 10 * (1e3 * 10.0) / 1e6


def extract_inflow_df(
    snapshots: list,
    ppl_df: pd.DataFrame,
    glofas_xr: xr.Dataset,
    inflow_scaling: float,
) -> pd.DataFrame:
    """
    Extract inflow for locations of hydropowerplants
    """
    glofas_copy_xr = glofas_xr.copy(deep=True)

    # TODO Account for the case when there is no hydro generation
    # NB 'technology' contains data on 'Reservoir' and 'Run-Of-River'
    ppl_hydro_df = ppl_df.query("carrier=='hydro'")

    ppl_hydro_lat = xr.DataArray(
        ppl_hydro_df["lat"].to_numpy(),
        dims="plant",
        coords={"plant": ppl_hydro_df.index},
    )

    ppl_hydro_lon = xr.DataArray(
        ppl_hydro_df["lon"].to_numpy(),
        dims="plant",
        coords={"plant": ppl_hydro_df.index},
    )
    # Height may be unknown especially for smaller reservoirs
    ppl_height_m = ppl_hydro_df["damheight_m"].replace(0, DEFAULT_DAMHEIGHT_M)

    # TODO Average by a few cells instead taking only the nearest one
    ppl_hydro_inflow_df = (
        glofas_copy_xr["dis24"]
        .sel(
            latitude=ppl_hydro_lat,
            longitude=ppl_hydro_lon,
            method="nearest",
        )
        .to_pandas()
    )

    ppl_hydro_inflow_df.index.name = "time"
    ppl_hydro_inflow_df.columns.name = "plant"

    # GloFAS dis24 timestamps mark the end of the preceding 24-hour
    # averaging period. Shift them to the day represented by the discharge.
    ppl_hydro_inflow_df.index = pd.to_datetime(
        ppl_hydro_inflow_df.index
    ) - np.timedelta64(1, "D")

    # To get hydro potential inflow must be multiplied by height, g and a scaling factor
    # TODO Get rid of a scaling factor
    ppl_hydro_inflow_df = ppl_hydro_inflow_df.mul(ppl_height_m, axis="columns")
    ppl_hydro_inflow_df = ppl_hydro_inflow_df * inflow_scaling

    start = pd.Timestamp(snapshots["start"])
    end = pd.Timestamp(snapshots["end"])
    inclusive = snapshots.get("inclusive", "left")

    snapshots_hourly = pd.date_range(
        start,
        end,
        freq="1h",
        inclusive=inclusive,
    )
    snapshots_daily = pd.DatetimeIndex(snapshots_hourly.normalize().unique())

    missing_days = snapshots_daily.difference(ppl_hydro_inflow_df.index)
    if not missing_days.empty:
        preview = ", ".join(str(timestamp) for timestamp in missing_days[:5])
        if len(missing_days) > 5:
            preview += ", ..."
        raise ValueError(
            "GloFAS inflow does not cover the requested snapshot period. "
            f"Missing {len(missing_days)} daily timestamp(s): {preview}"
        )

    ppl_hydro_daily_cut_inflow_df = ppl_hydro_inflow_df.loc[snapshots_daily]

    # Preserve the existing linear interpolation between daily GloFAS values.
    # The last daily value is extended over the remaining hours of that day.
    ppl_hydro_daily_cut_inflow_df = (
        ppl_hydro_daily_cut_inflow_df.resample("1h")
        .interpolate(method="linear")
        .reindex(snapshots_hourly)
        .ffill()
    )

    return ppl_hydro_daily_cut_inflow_df


def transform_to_xr(inflow_df: pd.DataFrame) -> pd.DataFrame:
    """
    Transform dataframe into xarray dataset with structure
    of hydro renewable profile
    """

    tmp_df = inflow_df

    hydro_xr = xr.Dataset(
        data_vars={"inflow": (("plant", "time"), tmp_df.to_numpy().T)},
        coords={
            "plant": tmp_df.columns.to_numpy(),
            "time": tmp_df.index.to_numpy(),
        },
    )

    return hydro_xr


if __name__ == "__main__":
    if "snakemake" not in globals():
        # TODO Avoid excessive import
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("build_glofas_profile")
    configure_logging(snakemake)

    # Inflow to energy units: pho_water * g & W -> MW
    inflow_scaling = (1e3 * 10.0) / 1e6 * snakemake.params.multiplier

    ppls = load_powerplants(snakemake.input.powerplants)
    glofas_xr = xr.open_dataset(snakemake.input.glofas)

    inflow_ppl_df = extract_inflow_df(
        snapshots=snakemake.params.snapshots,
        ppl_df=ppls,
        glofas_xr=glofas_xr,
        inflow_scaling=inflow_scaling,
    )

    inflow_xr = transform_to_xr(inflow_ppl_df)

    inflow_xr.to_netcdf(snakemake.output.profile)
