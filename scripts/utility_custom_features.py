# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Contributors to PyPSA-Earth
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Utility functions for adding Zambia interconnectors to a PyPSA network."""

import geopandas as gpd
import pandas as pd
from pypsa.io import import_components_from_dataframe, import_series_from_dataframe


def annual_gwh_to_average_mw(energy_gwh, hours_per_year=8760):
    """Convert annual energy in GWh to average power in MW."""
    return energy_gwh * 1000 / hours_per_year


def load_interconnector_data(countries_path, links_path, substations_path):
    """Load interconnector input data from CSV files."""
    return (
        pd.read_csv(countries_path),
        pd.read_csv(links_path),
        pd.read_csv(substations_path),
    )


def find_nearest_bus(n, lat, lon, distance_crs="EPSG:20935"):
    """Return the nearest Zambian bus to a given latitude and longitude."""
    buses = n.buses[n.buses["country"] == "ZM"].copy()
    buses = gpd.GeoDataFrame(
        buses,
        geometry=gpd.points_from_xy(buses["x"], buses["y"]),
        crs="EPSG:4326",
    ).to_crs(distance_crs)
    target_point = (
        gpd.GeoSeries.from_xy([lon], [lat], crs="EPSG:4326")
        .to_crs(distance_crs)
        .iloc[0]
    )
    distances = buses.geometry.distance(target_point)
    return distances.idxmin()


def add_foreign_buses(n, power_pool_countries):
    """Add neighbouring-country buses to the network."""
    for _, row in power_pool_countries.iterrows():
        country = row["country"]
        if country not in n.buses.index:
            n.add("Bus", country, x=row["lon"], y=row["lat"], carrier="AC")
            n.buses.loc[country, "country"] = country
    return n


def add_cross_border_links(n, power_pool_links, substation_dict, distance_crs):
    """Add cross-border links to the network."""
    for _, row in power_pool_links.iterrows():
        name = row["name"]
        if row["from_country"] == "ZM":
            lat, lon = substation_dict[name]
            bus0 = find_nearest_bus(n, lat, lon, distance_crs)
        else:
            bus0 = row["from_country"]
        if row["to_country"] == "ZM":
            lat, lon = substation_dict[name]
            bus1 = find_nearest_bus(n, lat, lon, distance_crs)
        else:
            bus1 = row["to_country"]

        if name not in n.links.index:
            n.add(
                "Link",
                name,
                bus0=bus0,
                bus1=bus1,
                carrier="AC",
                p_nom=row["capacity_mw"],
                efficiency=1.0,
                p_min_pu=-1.0,
            )
    return n


def add_trade_components(n, power_pool_countries, hours_per_year=8760):
    """Add import loads and export generators for neighbouring countries."""
    for _, row in power_pool_countries.iterrows():
        country = row["country"]
        if country not in n.buses.index:
            continue

        load_name = f"import_{country}"
        gen_name = f"export_{country}"

        if load_name not in n.loads.index:
            n.add(
                "Load",
                load_name,
                bus=country,
                carrier="import",
                p_set=annual_gwh_to_average_mw(row["demand_gwh"], hours_per_year),
            )

        if gen_name not in n.generators.index:
            n.add(
                "Generator",
                gen_name,
                bus=country,
                carrier="export",
                p_nom=annual_gwh_to_average_mw(row["generation_gwh"], hours_per_year),
                marginal_cost=row["marginal_cost"],
            )
    return n


def add_interconnectors(
    n,
    power_pool_countries,
    power_pool_links,
    substations,
    distance_crs,
    hours_per_year=8760,
):
    """Add foreign buses, interconnectors, and trade components to the network."""
    substation_dict = {
        row["name"]: (row["lat"], row["lon"]) for _, row in substations.iterrows()
    }

    n = add_foreign_buses(n, power_pool_countries)
    n = add_cross_border_links(n, power_pool_links, substation_dict, distance_crs)
    n = add_trade_components(n, power_pool_countries, hours_per_year)

    return n


def load_custom_line_types(line_types: str) -> pd.DataFrame:
    """Load and format custom transmission line types for a PyPSA network."""
    custom_line_types = pd.read_csv(line_types)

    custom_line_types = custom_line_types.rename(
        columns={
            "PyPSA Type Name": "name",
            "f_nom (Hz)": "f_nom",
            "r_per_length (Ω/km)": "r_per_length",
            "x_per_length (Ω/km)": "x_per_length",
            "c_per_length (nF/km)": "c_per_length",
            "i_nom (kA)": "i_nom",
            "cross_section (mm²)": "cross_section",
        }
    )
    custom_line_types = custom_line_types.set_index("name")
    return custom_line_types


def add_custom_line_types(n, custom_line_types):
    """merge custom line_types into the pypsa network"""
    n.line_types = pd.concat([n.line_types, custom_line_types], axis=0)
    n.line_types = n.line_types[~n.line_types.index.duplicated(keep="last")]
    return n


def map_buses_from_coords(
    n, df, distance_crs="EPSG:20935", buses_df=None, geo_crs="EPSG:4326"
):
    """Find the nearest bus for each row in df using lat/lon."""
    candidates = n.buses if buses_df is None else buses_df
    bus_points = gpd.GeoDataFrame(
        index=candidates.index,
        geometry=gpd.points_from_xy(candidates["x"], candidates["y"]),
        crs=geo_crs,
    ).to_crs(distance_crs)
    plant_points = gpd.GeoDataFrame(
        index=df.index,
        geometry=gpd.points_from_xy(df["lon"], df["lat"]),
        crs=geo_crs,
    ).to_crs(distance_crs)

    return plant_points.geometry.apply(
        lambda plant: bus_points.geometry.distance(plant).idxmin()
    )


def disaggregate_plants(
    n, ppl, name_fallback="plant", buses_df=None, geo_crs="EPSG:4326"
):
    """Rename ppl rows to real plant names and assign each to its nearest bus.

    Parameters
    ----------
    n : pypsa.Network
        The network whose buses are used for geo-matching.
    ppl : pd.DataFrame
        Power plant table. Must contain ``lat`` and ``lon`` columns.
        If a ``name`` column is present, its values are used as the plant name
        prefix in the new index; otherwise ``name_fallback`` is used.
    name_fallback : str, optional
        Prefix used in the new index when a plant has no name (default: "plant").
        E.g. ``name_fallback="hydro"`` produces index entries like ``"hydro-3"``.
    buses_df : pd.DataFrame or None, optional
        Candidate buses for geo-matching. Defaults to all buses in ``n``.
    geo_crs : str, optional
        Geographic CRS used to construct GeoDataFrames before reprojection
        (default: ``"EPSG:4326"``). Should match ``config["crs"]["geo_crs"]``.
    """
    new_names = []
    for i in ppl.index:
        if "name" in ppl.columns:
            plant_name = ppl.loc[i, "name"]
            if plant_name is not None and str(plant_name).strip() != "":
                new_name = str(plant_name) + "-" + str(i)
            else:
                new_name = name_fallback + "-" + str(i)
        else:
            new_name = name_fallback + "-" + str(i)
        new_names.append(new_name)
    ppl.index = new_names
    ppl["bus"] = map_buses_from_coords(n, ppl, buses_df=buses_df, geo_crs=geo_crs)


def save_excluded_components(n, component, busmap, exclude_carriers):
    """
    Save components we want to protect from aggregation.
    Works for any component type: "Generator", "Load", "StorageUnit", etc.
    Pulls out matching rows, remaps their buses, and saves their time-series.
    """
    if not exclude_carriers:
        return pd.DataFrame(), {}
    component_table = n.df(component)
    if "carrier" not in component_table.columns:
        return pd.DataFrame(), {}
    is_excluded = component_table.carrier.isin(exclude_carriers)
    if not is_excluded.any():
        return pd.DataFrame(), {}
    saved = component_table[is_excluded].copy()
    saved["bus"] = saved["bus"].map(busmap).fillna(saved["bus"])
    list_name = n.components[component]["list_name"]
    ts_container = getattr(n, list_name + "_t")
    saved_timeseries = {}
    for attr in ts_container:
        ts_data = getattr(ts_container, attr)
        if ts_data.empty:
            continue
        cols = ts_data.columns.intersection(saved.index)
        if not cols.empty:
            saved_timeseries[attr] = ts_data[cols]
    return saved, saved_timeseries


def restore_excluded_components(n, component, saved_components, saved_timeseries):
    """
    Put protected components back into the network after aggregation
    """
    if saved_components.empty:
        return
    import_components_from_dataframe(n, saved_components, component)
    for attr, data in saved_timeseries.items():
        if not data.empty:
            import_series_from_dataframe(n, data, component, attr)


def is_identity_busmap(busmap):
    """
    Check if every bus maps to itself.
    """
    return (busmap.index == busmap.values).all()
