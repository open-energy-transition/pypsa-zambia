# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Contributors to PyPSA-Earth
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging

import geopandas as gpd
import pandas as pd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely import wkt

logger = logging.getLogger(__name__)


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
    return n


def load_mining_data(provincial_demand_path, mining_polygons_path):
    """Load mining raster input data from CSV files."""
    return (pd.read_csv(provincial_demand_path), pd.read_csv(mining_polygons_path))


def build_mining_raster(
    provincial_demand,
    mining_polygons,
    output_path,
    resolution=1000,
    geo_crs="EPSG:4326",
    area_crs="ESRI:54009",
):
    """
    Create a mining demand raster for Zambia.

    Inputs:
    - provincial_demand (pd.DataFrame): columns [province, mining_demand_gwh]
    - mining_polygons (pd.DataFrame): columns [province, area_km2, geometry_wkt].
      Each polygon carries a native "province" field, so demand is assigned by
      direct attribute lookup — no spatial intersection is required.
    - output_path (str): path for the output GeoTIFF file
    - resolution (int): raster resolution in units of area_crs (default: 1000 m)
    - geo_crs (str): CRS of the input WKT geometries (default: EPSG:4326)
    - area_crs (str): CRS used for area calculations and raster output (default: ESRI:54009)

    Output values are in MWh/km²/year.
    """

    demand = provincial_demand.set_index("province")
    mines = mining_polygons
    # Total mining area per province
    mines["province_area_km2"] = mines.groupby("province")["area_km2"].transform("sum")
    # Demand intensity
    mines["demand_mwh_per_km2"] = (
        mines["province"].map(demand["mining_demand_gwh"])
        * 1000
        / mines["province_area_km2"]
    )
    # Convert WKT to geometries, then reproject to area_crs for rasterization
    gdf = gpd.GeoDataFrame(
        mines,
        geometry=mines["geometry_wkt"].apply(wkt.loads),
        crs=geo_crs,
    ).to_crs(area_crs)
    # Derive bounding box from reprojected data
    x_min, y_min, x_max, y_max = gdf.total_bounds
    width = round((x_max - x_min) / resolution)
    height = round((y_max - y_min) / resolution)
    transform = from_bounds(x_min, y_min, x_max, y_max, width, height)
    # Rasterize mining demand
    shapes = zip(gdf.geometry, gdf["demand_mwh_per_km2"])

    raster = rasterize(
        shapes,
        out_shape=(height, width),
        transform=transform,
        fill=0,
        dtype="float32",
    )
    # Save raster
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="float32",
        crs=area_crs,
        transform=transform,
        nodata=0,
    ) as dst:
        dst.write(raster, 1)

    return output_path
