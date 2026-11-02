#!/usr/bin/env python

# SPDX-FileCopyrightText: PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Hydrological preprocessing for cascading hydropower.
"""

import logging
import math

import atlite
import geopandas as gpd
import numpy as np
import pandas as pd
import xarray as xr
from _helpers import configure_logging, read_csv_nafix
from atlite import hydro as hydrom
from dask.distributed import Client
from hydro_cascade import (
    match_cascade_plants_to_powerplants,
    validate_cascade_topology,
)

logger = logging.getLogger(__name__)


def load_hydro_powerplants(powerplants_path):
    """Load hydro plants from the powerplantmatching-style workflow output."""
    powerplants = read_csv_nafix(
        powerplants_path,
        index_col=0,
    )

    hydro = powerplants[
        powerplants["Fueltype"].astype(str).str.casefold().eq("hydro")
    ].copy()

    hydro = hydro.rename(
        columns={
            "Country": "country",
            "DamHeight_m": "damheight_m",
            "projectID": "projectid",
        }
    )

    return hydro


def extract_glofas_discharge(
    glofas: xr.Dataset,
    cascade_powerplants: pd.DataFrame,
) -> pd.DataFrame:
    """Extract routed GloFAS discharge [m3/s] at cascade plant locations."""
    if "dis24" not in glofas:
        raise ValueError("GloFAS dataset must contain variable 'dis24'.")

    plant_ids = cascade_powerplants.index.astype(str).to_numpy()

    latitudes = xr.DataArray(
        cascade_powerplants["lat"].to_numpy(),
        dims="plant",
        coords={"plant": plant_ids},
    )
    longitudes = xr.DataArray(
        cascade_powerplants["lon"].to_numpy(),
        dims="plant",
        coords={"plant": plant_ids},
    )

    discharge_xr = glofas["dis24"].sel(
        latitude=latitudes,
        longitude=longitudes,
        method="nearest",
    )

    if "time" in discharge_xr.dims:
        time_dim = "time"
    elif "valid_time" in discharge_xr.dims:
        time_dim = "valid_time"
    else:
        raise ValueError(
            "GloFAS discharge must contain a 'time' or 'valid_time' dimension."
        )

    discharge = discharge_xr.transpose(time_dim, "plant").to_pandas()
    discharge.index = pd.DatetimeIndex(discharge.index, name="time")
    discharge.columns = plant_ids
    discharge.columns.name = "plant"

    return discharge


def build_era5_cascade_hydraulic_inflow(
    cutout,
    resource,
    hydro_powerplants,
    topology_path,
    correction_factor=1.0,
    multiplier=1.0,
    clip_min_inflow=None,
):
    """
    Build local natural hydraulic inflow profiles for cascade reservoirs.

    The full upstream catchments determined by atlite are decomposed into
    local catchments so that runoff already represented by upstream cascade
    reservoirs is not counted again downstream.

    Returns
    -------
    hydraulic_inflow : pandas.DataFrame
        Local hydraulic inflow in MW, indexed by time and cascade plant ID.
    cascade_profile_indices : dict
        Mapping from cascade plant IDs to hydro profile indices.
    """
    topology = pd.read_csv(topology_path)
    topology["upstream"] = topology["upstream"].astype(str).str.strip()
    topology["downstream"] = topology["downstream"].astype(str).str.strip()
    validate_cascade_topology(topology)

    if "damheight_m" not in hydro_powerplants.columns:
        raise ValueError("Cascade hydro requires power plant column: damheight_m")

    resolution_input = hydro_powerplants.assign(
        _cascade_profile_index=hydro_powerplants.index
    )

    cascade_powerplants = match_cascade_plants_to_powerplants(
        topology,
        resolution_input,
    )

    cascade_profile_indices = cascade_powerplants["_cascade_profile_index"].to_dict()

    show_progress = resource.get("show_progress", False)
    flowspeed = resource.get("flowspeed", 1.0)
    weight_with_height = resource.get("weight_with_height", False)

    basins = hydrom.determine_basins(
        resource["plants"],
        resource["hydrobasins"],
        show_progress=show_progress,
    )

    matrix = cutout.indicatormatrix(basins.shapes)
    matrix_normalized = np.nan_to_num(
        matrix / matrix.sum(axis=1),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )

    runoff_kwargs = {
        key: value
        for key, value in resource.items()
        if key
        not in {
            "plants",
            "hydrobasins",
            "flowspeed",
            "weight_with_height",
            "show_progress",
        }
    }

    basin_water_volume = cutout.runoff(
        matrix=matrix_normalized,
        index=basins.shapes.index,
        weight_with_height=weight_with_height,
        show_progress=show_progress,
        capacity_factor=True,
        **runoff_kwargs,
    )

    # ERA5 runoff is expressed as water depth per timestep. Multiplication by
    # basin area gives the corresponding water volume per timestep.
    basin_water_volume *= xr.DataArray(basins.shapes.to_crs(dict(proj="cea")).area)

    local_basins = build_local_cascade_basins(
        basins,
        topology,
        cascade_profile_indices,
    )

    local_water_volume = (
        correction_factor
        * hydrom.shift_and_aggregate_runoff_for_plants(
            local_basins,
            basin_water_volume,
            flowspeed=flowspeed,
            show_progress=show_progress,
        )
    )

    local_water_volume = (
        local_water_volume.transpose("time", "plant")
        .to_pandas()
        .rename(
            columns={
                profile_index: plant_id
                for plant_id, profile_index in cascade_profile_indices.items()
            }
        )
    )

    discharge = water_volume_to_discharge(local_water_volume)

    dam_heights = pd.to_numeric(
        cascade_powerplants["damheight_m"],
        errors="coerce",
    )
    invalid_heights = dam_heights[dam_heights.isna() | (dam_heights <= 0)]
    if not invalid_heights.empty:
        raise ValueError(
            "Cascade plants require positive dam heights: "
            + ", ".join(invalid_heights.index)
        )

    hydraulic_inflow = discharge_to_hydraulic_inflow(
        discharge,
        dam_heights,
    )

    if clip_min_inflow is not None:
        hydraulic_inflow = hydraulic_inflow.where(
            hydraulic_inflow >= clip_min_inflow,
            0,
        )

    hydraulic_inflow *= multiplier

    return hydraulic_inflow, cascade_profile_indices


def build_local_cascade_discharge(
    discharge: pd.DataFrame,
    topology: pd.DataFrame,
    routing_hours: pd.Series,
) -> pd.DataFrame:
    """Remove routed upstream discharge from downstream cascade inflows."""
    if len(discharge.index) < 2:
        raise ValueError("At least two discharge timesteps are required.")

    timesteps = discharge.index.to_series().diff().dropna()
    timestep = pd.Timedelta(timesteps.iloc[0])

    if not (timesteps == timestep).all():
        raise ValueError("GloFAS discharge must have a regular timestep.")

    timestep_hours = timestep / pd.Timedelta(hours=1)

    local_discharge = discharge.copy()

    for edge in topology.itertuples(index=False):
        upstream = str(edge.upstream).strip()
        downstream = str(edge.downstream).strip()

        edge_key = (upstream, downstream)
        hours = float(routing_hours.loc[edge_key])
        lag_steps = math.floor(hours / timestep_hours + 0.5)

        # Match atlite's cyclic time routing via xarray.DataArray.roll.
        routed_upstream = pd.Series(
            np.roll(discharge[upstream].to_numpy(), lag_steps),
            index=discharge.index,
        )

        local_discharge[downstream] = local_discharge[downstream] - routed_upstream

    negative_mask = local_discharge < 0.0

    if negative_mask.any().any():
        for plant_id in local_discharge.columns[negative_mask.any(axis=0)]:
            negative = local_discharge[plant_id].clip(upper=0.0).abs().sum()
            positive = local_discharge[plant_id].clip(lower=0.0).sum()
            share = negative / positive if positive > 0 else float("nan")

            logger.warning(
                "Clipping %d negative local-discharge values for %s "
                "(negative volume is %.3f%% of positive volume).",
                int(negative_mask[plant_id].sum()),
                plant_id,
                100.0 * share,
            )

    return local_discharge.clip(lower=0.0)


def get_cascade_routing_hours(
    basins,
    topology: pd.DataFrame,
    cascade_profile_indices: dict[str, object],
    flowspeed: float = 1.0,
) -> pd.Series:
    """Estimate river-routing times between cascade plants from HydroBASINS."""
    if flowspeed <= 0:
        raise ValueError("flowspeed must be positive.")

    routing_hours = {}

    for edge in topology.itertuples(index=False):
        upstream = str(edge.upstream).strip()
        downstream = str(edge.downstream).strip()

        upstream_index = cascade_profile_indices[upstream]
        downstream_index = cascade_profile_indices[downstream]

        upstream_hid = basins.plants.at[upstream_index, "hid"]
        downstream_hid = basins.plants.at[downstream_index, "hid"]

        distance_km = (
            basins.meta.at[upstream_hid, "DIST_MAIN"]
            - basins.meta.at[downstream_hid, "DIST_MAIN"]
        )

        if not np.isfinite(distance_km) or distance_km < 0:
            raise ValueError(
                f"Invalid HydroBASINS routing distance for "
                f"{upstream} -> {downstream}: {distance_km} km."
            )

        routing_hours[(upstream, downstream)] = distance_km / (flowspeed * 3.6)

    return pd.Series(routing_hours, name="routing_hours")


def build_local_cascade_basins(
    basins,
    topology: pd.DataFrame,
    cascade_profile_indices: dict[str, object],
):
    """
    Restrict cascade plants to their local HydroBASINS catchments.

    For each downstream reservoir, basins already draining through an
    immediately upstream cascade reservoir are removed. Travel-time delays
    from the cascade topology are intentionally not used here: runoff routing
    remains the responsibility of atlite.
    """
    topology = topology.copy()
    topology["upstream"] = topology["upstream"].astype(str).str.strip()
    topology["downstream"] = topology["downstream"].astype(str).str.strip()
    validate_cascade_topology(topology)

    cascade_profile_indices = {
        str(plant_id).strip(): index
        for plant_id, index in cascade_profile_indices.items()
    }

    cascade_ids = set(topology["upstream"]).union(topology["downstream"])
    missing = sorted(cascade_ids - set(cascade_profile_indices))
    if missing:
        raise ValueError(
            "Cascade plants are missing from the hydro basin mapping: "
            + ", ".join(missing)
        )

    ordered_ids = dict.fromkeys(
        topology["upstream"].tolist() + topology["downstream"].tolist()
    )
    local_plants = basins.plants.loc[
        [cascade_profile_indices[plant_id] for plant_id in ordered_ids]
    ].copy()

    for downstream, connections in topology.groupby("downstream", sort=False):
        downstream_index = cascade_profile_indices[downstream]
        downstream_basins = list(basins.plants.at[downstream_index, "upstream"])
        downstream_basin_set = set(downstream_basins)
        local_basin_set = set(downstream_basins)

        for upstream in connections["upstream"]:
            upstream_index = cascade_profile_indices[upstream]
            upstream_basin_set = set(basins.plants.at[upstream_index, "upstream"])

            if not upstream_basin_set.issubset(downstream_basin_set):
                raise ValueError(
                    f"Cascade topology {upstream} -> {downstream} "
                    "is inconsistent with the HydroBASINS drainage topology."
                )

            local_basin_set.difference_update(upstream_basin_set)

        local_plants.at[downstream_index, "upstream"] = [
            hid for hid in downstream_basins if hid in local_basin_set
        ]

    return type(basins)(
        local_plants,
        basins.meta,
        basins.shapes,
    )


def water_volume_to_discharge(water_volume: pd.DataFrame) -> pd.DataFrame:
    """Convert water volume per timestep [m3] to discharge [m3/s]."""
    time_index = pd.DatetimeIndex(water_volume.index)

    if len(time_index) < 2:
        raise ValueError(
            "At least two hydro-profile timesteps are required "
            "to convert runoff to discharge."
        )

    timesteps = time_index.to_series().diff().dropna()
    timestep = pd.Timedelta(timesteps.iloc[0])

    if not (timesteps == timestep).all():
        raise ValueError("Hydro runoff profiles must have a regular timestep.")

    timestep_seconds = timestep.total_seconds()
    if timestep_seconds <= 0:
        raise ValueError("Hydro runoff timestep must be positive.")

    return water_volume / timestep_seconds


def discharge_to_hydraulic_inflow(
    discharge: pd.DataFrame,
    dam_heights: pd.Series,
    multiplier: float = 1.0,
) -> pd.DataFrame:
    """
    Convert discharge [m3/s] to hydraulic inflow [MW].

    This follows the existing PyPSA-Earth GloFAS convention:
    discharge * dam height * rho_water * g / 1e6 * multiplier,
    with rho_water = 1000 kg/m3 and g = 10 m/s2.
    """
    missing = sorted(set(discharge.columns) - set(dam_heights.index))

    if missing:
        raise ValueError(
            "Missing dam heights for cascade plants: " + ", ".join(map(str, missing))
        )

    if multiplier <= 0:
        raise ValueError("multiplier must be positive.")

    scaling = (1e3 * 10.0) / 1e6 * multiplier

    return (
        discharge.mul(
            dam_heights[discharge.columns],
            axis="columns",
        )
        * scaling
    )


def build_glofas_cascade_hydraulic_inflow(
    glofas: xr.Dataset,
    hydrobasins: gpd.GeoDataFrame,
    hydro_powerplants: pd.DataFrame,
    topology_path,
    flowspeed: float = 1.0,
    multiplier: float = 1.0,
):
    """Build local hydraulic inflow from routed GloFAS discharge."""
    topology = pd.read_csv(topology_path)
    topology["upstream"] = topology["upstream"].astype(str).str.strip()
    topology["downstream"] = topology["downstream"].astype(str).str.strip()
    validate_cascade_topology(topology)

    cascade_powerplants = match_cascade_plants_to_powerplants(
        topology,
        hydro_powerplants,
    )

    plants = cascade_powerplants.rename(columns={"country": "countries"})[
        ["lon", "lat", "countries"]
    ]

    basins = hydrom.determine_basins(
        plants,
        hydrobasins,
        show_progress=False,
    )

    cascade_profile_indices = {
        str(plant_id): plant_id for plant_id in cascade_powerplants.index
    }

    routing_hours = get_cascade_routing_hours(
        basins,
        topology,
        cascade_profile_indices,
        flowspeed=flowspeed,
    )

    discharge = extract_glofas_discharge(
        glofas,
        cascade_powerplants,
    )

    local_discharge = build_local_cascade_discharge(
        discharge,
        topology,
        routing_hours,
    )

    dam_heights = pd.to_numeric(
        cascade_powerplants["damheight_m"],
        errors="coerce",
    )

    invalid_heights = dam_heights[dam_heights.isna() | (dam_heights <= 0)]
    if not invalid_heights.empty:
        raise ValueError(
            "Cascade plants require positive dam heights: "
            + ", ".join(invalid_heights.index)
        )

    hydraulic_inflow = discharge_to_hydraulic_inflow(
        local_discharge,
        dam_heights,
        multiplier=multiplier,
    )

    return hydraulic_inflow, routing_hours


def build_glofas_cascade_profile_file(
    powerplants_path,
    hydrobasins_path,
    topology_path,
    glofas_path,
    hydro_config,
    snapshots,
    output_path,
):
    """Build and write cascade hydraulic inflow profiles from GloFAS."""
    hydro_powerplants = load_hydro_powerplants(powerplants_path)
    hydrobasins = gpd.read_file(hydrobasins_path)
    glofas = xr.open_dataset(glofas_path)

    hydraulic_inflow, _ = build_glofas_cascade_hydraulic_inflow(
        glofas=glofas,
        hydrobasins=hydrobasins,
        hydro_powerplants=hydro_powerplants,
        topology_path=topology_path,
        flowspeed=hydro_config["resource"].get("flowspeed", 1.0),
        multiplier=hydro_config.get("multiplier", 1.0),
    )

    start = snapshots["start"]
    end = snapshots["end"]
    snapshots_daily = pd.date_range(start, end, freq="1d")

    hydraulic_inflow = hydraulic_inflow.loc[
        hydraulic_inflow.index.isin(snapshots_daily)
    ]

    if hydraulic_inflow.empty:
        raise ValueError(
            "The cascade GloFAS inflow dataframe is empty for the requested snapshots."
        )

    hydraulic_inflow = hydraulic_inflow.resample("1h").interpolate(method="linear")

    profile = xr.DataArray(
        hydraulic_inflow.to_numpy().T,
        dims=("plant", "time"),
        coords={
            "plant": hydraulic_inflow.columns.astype(str),
            "time": hydraulic_inflow.index,
        },
        name="inflow",
    )

    profile.to_netcdf(output_path)


def build_era5_cascade_profile_file(
    powerplants_path,
    hydrobasins_path,
    topology_path,
    cutout_path,
    hydro_config,
    output_path,
    nprocesses=1,
):
    """Build and write plant-level hydraulic inflow profiles for hydro cascades."""
    hydrobasins = gpd.read_file(hydrobasins_path)
    hydro_powerplants = load_hydro_powerplants(powerplants_path)

    hydro_points = gpd.GeoDataFrame(
        hydro_powerplants,
        index=hydro_powerplants.index,
        geometry=gpd.points_from_xy(
            hydro_powerplants.lon,
            hydro_powerplants.lat,
        ),
        crs="EPSG:4326",
    ).to_crs(hydrobasins.crs)

    matched = gpd.sjoin(
        hydro_points,
        hydrobasins,
        predicate="within",
        how="left",
    )

    hydro_powerplants = pd.DataFrame(
        hydro_points.loc[matched.index_right.dropna().index].drop(columns="geometry")
    )

    resource = hydro_config["resource"].copy()
    resource.pop("method", None)

    resource["hydrobasins"] = hydrobasins
    resource["plants"] = hydro_powerplants.rename(columns={"country": "countries"})[
        ["lon", "lat", "countries"]
    ]

    resource["plants"]["installed_hydro"] = True

    client = (
        Client(n_workers=nprocesses, threads_per_worker=1) if nprocesses > 1 else None
    )

    try:
        resource["dask_kwargs"] = {"scheduler": client}

        cutout = atlite.Cutout(cutout_path)

        hydraulic_inflow, _ = build_era5_cascade_hydraulic_inflow(
            cutout=cutout,
            resource=resource,
            hydro_powerplants=hydro_powerplants,
            topology_path=topology_path,
            correction_factor=hydro_config.get("correction_factor", 1.0),
            multiplier=hydro_config.get("multiplier", 1.0),
            clip_min_inflow=hydro_config.get("clip_min_inflow"),
        )

        profile = xr.DataArray(
            hydraulic_inflow.to_numpy().T,
            dims=("plant", "time"),
            coords={
                "plant": hydraulic_inflow.columns.astype(str),
                "time": hydraulic_inflow.index,
            },
            name="inflow",
        )

        profile.to_netcdf(output_path)

    finally:
        if client is not None:
            client.close()


def build_hydro_cascade_profile_file(
    powerplants_path,
    hydrobasins_path,
    topology_path,
    cutout_path,
    hydro_config,
    output_path,
    snapshots=None,
    nprocesses=1,
):
    """Build a cascade inflow profile using the configured hydrological source."""
    source = hydro_config.get("source", "era5")

    if source == "custom":
        if snapshots is None:
            raise ValueError(
                "Snapshots are required for custom GloFAS cascade profiles."
            )

        build_glofas_cascade_profile_file(
            powerplants_path=powerplants_path,
            hydrobasins_path=hydrobasins_path,
            topology_path=topology_path,
            glofas_path=cutout_path,
            hydro_config=hydro_config,
            snapshots=snapshots,
            output_path=output_path,
        )
        return

    if source != "era5":
        raise ValueError(
            f"Unsupported cascading hydro source: {source!r}. "
            "Expected 'era5' or 'custom'."
        )

    build_era5_cascade_profile_file(
        powerplants_path=powerplants_path,
        hydrobasins_path=hydrobasins_path,
        topology_path=topology_path,
        cutout_path=cutout_path,
        hydro_config=hydro_config,
        output_path=output_path,
        nprocesses=nprocesses,
    )


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("build_hydro_cascade_profile")

    configure_logging(snakemake)

    build_hydro_cascade_profile_file(
        powerplants_path=snakemake.input.powerplants,
        hydrobasins_path=snakemake.input.hydrobasins,
        topology_path=snakemake.input.topology,
        cutout_path=snakemake.input.cutout,
        hydro_config=snakemake.params.hydro,
        output_path=snakemake.output.profile,
        snapshots=snakemake.config["snapshots"],
        nprocesses=int(snakemake.threads),
    )
