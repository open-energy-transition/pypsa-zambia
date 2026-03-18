import numpy as np
import pandas as pd


def find_nearest_zm_bus(n, lat, lon):
    """Find the nearest Zambian bus

    Arguments
    =========
    n: pypsa.network
        The PyPSA network to interrogate
    lat: shapely.Point
        Latitude
    lon: shapely.Point
        Longitude

    Returns
    =======
    str
        The name of the nearest bus
    """
    smallest_distance = 999999999
    nearest_bus = None

    for bus_name in n.buses.index:
        if n.buses.loc[bus_name, "country"] == "ZM":
            bus_lat = n.buses.loc[bus_name, "y"]
            bus_lon = n.buses.loc[bus_name, "x"]

            distance = np.sqrt((bus_lat - lat) ** 2 + (bus_lon - lon) ** 2)

            if distance < smallest_distance:
                smallest_distance = distance
                nearest_bus = bus_name
    return nearest_bus


# Add Interconnectors
def add_interconnectors(n, power_pool_countries, power_pool_links, zm_substations):
    power_pool_countries = pd.read_csv(power_pool_countries)
    power_pool_links = pd.read_csv(power_pool_links)
    zm_substations = pd.read_csv(zm_substations)
    importing_countries = ["MZ", "ZW", "NA", "CD"]
    exporting_countries = ["MZ", "ZA", "ZW"]
    # build substation dictionary
    substation_dict = {}
    for _, row in zm_substations.iterrows():
        substation_dict[row["name"]] = (row["lat"], row["lon"])

    # add foreign buses
    for _, row in power_pool_countries.iterrows():
        bus_name = row["country"]
        if bus_name not in n.buses.index:
            n.add("Bus", bus_name, x=row["lon"], y=row["lat"], carrier="AC")
            n.buses.loc[bus_name, "country"] = row["country"]

    # add links
    for _, row in power_pool_links.iterrows():
        link_name = row["name"]
        capacity_mw = row["capacity_mw"]
        if row["from_country"] == "ZM":
            lat, lon = substation_dict[link_name]
            bus0 = find_nearest_zm_bus(n, lat, lon)
        else:
            bus0 = row["from_country"]
        if row["to_country"] == "ZM":
            lat, lon = substation_dict[link_name]
            bus1 = find_nearest_zm_bus(n, lat, lon)
        else:
            bus1 = row["to_country"]

        if link_name not in n.links.index:
            n.add(
                "Link",
                link_name,
                bus0=bus0,
                bus1=bus1,
                carrier="AC",
                p_nom=capacity_mw,
                efficiency=1.0,
                p_min_pu=-1.0,
            )
    for _, row in power_pool_countries.iterrows():
        country = row["country"]
        if country not in n.buses.index:
            continue
        if country in importing_countries:
            p_set = row["demand_gwh"] * 1000 / 8760
            n.add(
                "Load", f"import_{country}", bus=country, carrier="import", p_set=p_set
            )
        elif country in exporting_countries:
            p_nom = row["generation_gwh"] * 1000 / 8760
            n.add(
                "Generator",
                f"export_{country}",
                bus=country,
                carrier="export",
                p_nom=p_nom,
                marginal_cost=row["marginal_cost"],
            )

    return n
