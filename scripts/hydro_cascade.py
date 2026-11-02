# SPDX-FileCopyrightText: PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import ast
import math

import pandas as pd
import pypsa

REQUIRED_TOPOLOGY_COLUMNS = {
    "upstream",
    "downstream",
    "travel_time_hours",
}

PLANT_ID_COLUMN = "plant_id"


def validate_cascade_topology(topology: pd.DataFrame) -> None:
    """
    Validate a directed cascading-hydro topology.

    The topology contains one row per hydraulic connection with the columns
    ``upstream``, ``downstream`` and ``travel_time_hours``.

    Multiple upstream nodes may converge into one downstream node. Splitting
    one upstream flow into multiple downstream branches is currently not
    supported.

    Parameters
    ----------
    topology : pandas.DataFrame
        Cascading-hydro connection table.

    Raises
    ------
    ValueError
        If the topology is malformed or contains unsupported structures.
    """
    missing_columns = REQUIRED_TOPOLOGY_COLUMNS - set(topology.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Cascade topology is missing required columns: {missing}")

    if topology.empty:
        raise ValueError("Cascade topology must contain at least one connection.")

    edges = topology[["upstream", "downstream", "travel_time_hours"]].copy()

    if edges[["upstream", "downstream"]].isna().any().any():
        raise ValueError(
            "Cascade topology contains missing upstream or downstream node IDs."
        )

    for column in ["upstream", "downstream"]:
        edges[column] = edges[column].astype(str).str.strip()

    for column in ["upstream", "downstream"]:
        empty = edges[column].map(
            lambda value: isinstance(value, str) and not value.strip()
        )
        if empty.any():
            raise ValueError(f"Cascade topology contains empty values in '{column}'.")

    if (edges["upstream"] == edges["downstream"]).any():
        raise ValueError("Cascade topology contains a self-loop.")

    if edges.duplicated(["upstream", "downstream"]).any():
        raise ValueError("Cascade topology contains duplicate hydraulic connections.")

    delays = pd.to_numeric(
        edges["travel_time_hours"],
        errors="coerce",
    )

    invalid_delay = delays.map(
        lambda value: pd.isna(value) or not math.isfinite(float(value))
    )

    if invalid_delay.any():
        raise ValueError("Cascade topology contains invalid travel times.")

    if (delays < 0).any():
        raise ValueError("Cascade topology contains negative travel times.")

    downstream_count = edges.groupby("upstream")["downstream"].nunique()

    branching_nodes = downstream_count[downstream_count > 1]

    if not branching_nodes.empty:
        nodes = ", ".join(map(str, branching_nodes.index.tolist()))
        raise ValueError(
            "Cascade topology currently supports at most one "
            f"downstream connection per node. Branching nodes: {nodes}"
        )

    downstream_by_upstream = dict(zip(edges["upstream"], edges["downstream"]))

    completed = set()

    for start in downstream_by_upstream:
        if start in completed:
            continue

        path = set()
        node = start

        while node in downstream_by_upstream:
            if node in path:
                raise ValueError("Cascade topology contains a directed cycle.")

            if node in completed:
                break

            path.add(node)
            node = downstream_by_upstream[node]

        completed.update(path)


def _qualified_project_ids(value) -> set[str]:
    """Return source-qualified IDs such as ``GHPT:G123456``."""
    if value is None:
        return set()

    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() == "nan":
            return set()
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return set()

    if not isinstance(value, dict):
        return set()

    qualified = set()

    for source, identifiers in value.items():
        if isinstance(identifiers, (set, list, tuple)):
            values = identifiers
        else:
            values = [identifiers]

        for identifier in values:
            if identifier is None:
                continue

            if pd.api.types.is_scalar(identifier) and pd.isna(identifier):
                continue

            identifier = str(identifier).strip()

            if identifier and identifier.lower() != "nan":
                qualified.add(f"{source}:{identifier}")

    return qualified


def resolve_cascade_plants(
    topology: pd.DataFrame,
    powerplants: pd.DataFrame,
) -> pd.DataFrame:
    """
    Resolve cascade topology nodes against the powerplant table.

    Topology nodes may either match an explicit ``plant_id`` or use a
    source-qualified powerplantmatching project ID such as
    ``GHPT:G123456``.

    Parameters
    ----------
    topology : pandas.DataFrame
        Cascade connections with ``upstream`` and ``downstream`` node IDs.
    powerplants : pandas.DataFrame
        Power plant table. It may contain an explicit ``plant_id`` column
        and/or the powerplantmatching ``projectid`` metadata.

    Returns
    -------
    pandas.DataFrame
        Powerplant rows participating in the cascade, indexed by the stable
        cascade ``plant_id``.

    Raises
    ------
    ValueError
        If topology nodes cannot be resolved uniquely.
    """
    topology_nodes = {
        str(node).strip()
        for node in set(topology["upstream"]).union(topology["downstream"])
    }

    resolved = {}
    unresolved = set(topology_nodes)

    # Prefer explicitly supplied stable plant IDs.
    if PLANT_ID_COLUMN in powerplants.columns:
        explicit_ids = powerplants[PLANT_ID_COLUMN].map(
            lambda value: ("" if pd.isna(value) else str(value).strip())
        )

        duplicate_mask = (explicit_ids != "") & explicit_ids.duplicated(keep=False)

        if duplicate_mask.any():
            duplicates = sorted(explicit_ids.loc[duplicate_mask].unique())
            raise ValueError(
                "Duplicate plant_id values found in powerplant data: "
                + ", ".join(duplicates)
            )

        for component, plant_id in explicit_ids.items():
            if plant_id in unresolved:
                resolved[plant_id] = component
                unresolved.remove(plant_id)

    # Fall back to immutable source IDs carried by powerplantmatching.
    if unresolved and "projectid" in powerplants.columns:
        matches = {node: [] for node in unresolved}

        for component, project_ids in powerplants["projectid"].items():
            qualified_ids = _qualified_project_ids(project_ids)

            for node in unresolved.intersection(qualified_ids):
                matches[node].append(component)

        ambiguous = {
            node: components
            for node, components in matches.items()
            if len(components) > 1
        }

        if ambiguous:
            details = ", ".join(
                f"{node} ({len(components)} matches)"
                for node, components in sorted(ambiguous.items())
            )
            raise ValueError(
                "Cascade topology project IDs are not unique in powerplant data: "
                + details
            )

        for node, components in matches.items():
            if len(components) == 1:
                resolved[node] = components[0]

        unresolved -= set(resolved)

    if unresolved:
        raise ValueError(
            "Cascade topology references nodes which cannot be "
            "resolved to powerplants: " + ", ".join(sorted(unresolved))
        )

    plants = powerplants.loc[[resolved[node] for node in sorted(topology_nodes)]].copy()

    plants[PLANT_ID_COLUMN] = sorted(topology_nodes)
    plants = plants.set_index(PLANT_ID_COLUMN, drop=False)

    return plants


def add_hydro_reservoir(
    n: pypsa.Network,
    plant_id: str,
    electricity_bus: str,
    p_nom: float,
    max_hours: float,
    efficiency_dispatch: float,
    cyclic: bool = True,
    capital_cost: float = 0.0,
    marginal_cost: float = 0.0,
    build_year: int = 0,
    lifetime: float = math.inf,
) -> dict[str, str]:
    """Add a reservoir as a water bus, Store and turbine Link."""
    if p_nom <= 0:
        raise ValueError("Reservoir p_nom must be positive.")
    if max_hours <= 0:
        raise ValueError("Reservoir max_hours must be positive.")
    if not 0 < efficiency_dispatch <= 1:
        raise ValueError(
            "Reservoir dispatch efficiency must be in the interval (0, 1]."
        )

    if electricity_bus not in n.buses.index:
        raise ValueError(f"Electricity bus '{electricity_bus}' does not exist.")

    water_bus = f"{plant_id} water"
    store = f"{plant_id} reservoir"
    turbine = f"{plant_id} turbine"

    if "water" not in n.carriers.index:
        n.add("Carrier", "water")
    if "hydro" not in n.carriers.index:
        n.add("Carrier", "hydro")

    n.add(
        "Bus",
        water_bus,
        carrier="water",
    )

    n.add(
        "Store",
        store,
        bus=water_bus,
        carrier="hydro",
        e_nom=p_nom * max_hours,
        e_cyclic=cyclic,
        build_year=build_year,
        lifetime=lifetime,
    )

    n.add(
        "Link",
        turbine,
        bus0=water_bus,
        bus1=electricity_bus,
        bus2="",
        carrier="hydro",
        p_nom=p_nom / efficiency_dispatch,
        efficiency=efficiency_dispatch,
        efficiency2=1.0,
        delay2=0.0,
        cyclic_delay2=True,
        capital_cost=capital_cost * efficiency_dispatch,
        marginal_cost=marginal_cost * efficiency_dispatch,
        build_year=build_year,
        lifetime=lifetime,
    )

    return {
        "water_bus": water_bus,
        "store": store,
        "turbine": turbine,
    }


def connect_hydro_reservoirs(
    n: pypsa.Network,
    upstream_plant_id: str,
    downstream_plant_id: str,
    travel_time_hours: float,
    downstream_energy_ratio: float,
    spill_cost: float = 0.0,
    cyclic_delay: bool = False,
) -> dict[str, str]:
    """Connect two hydro reservoirs with delayed turbine outflow and spill."""
    if travel_time_hours < 0:
        raise ValueError("Travel time must be non-negative.")

    if not math.isfinite(travel_time_hours):
        raise ValueError("Travel time must be finite.")

    if downstream_energy_ratio <= 0 or not math.isfinite(downstream_energy_ratio):
        raise ValueError("Downstream energy ratio must be positive and finite.")

    if not math.isfinite(spill_cost):
        raise ValueError("Spill cost must be finite.")

    upstream_water_bus = f"{upstream_plant_id} water"
    downstream_water_bus = f"{downstream_plant_id} water"
    turbine = f"{upstream_plant_id} turbine"
    spill = f"{upstream_plant_id} spill"

    if upstream_water_bus not in n.buses.index:
        raise ValueError(f"Upstream water bus '{upstream_water_bus}' does not exist.")

    if downstream_water_bus not in n.buses.index:
        raise ValueError(
            f"Downstream water bus '{downstream_water_bus}' does not exist."
        )

    if turbine not in n.links.index:
        raise ValueError(f"Upstream turbine '{turbine}' does not exist.")

    n.links.loc[turbine, "bus2"] = downstream_water_bus
    n.links.loc[turbine, "efficiency2"] = downstream_energy_ratio
    n.links.loc[turbine, "delay2"] = travel_time_hours
    n.links.loc[turbine, "cyclic_delay2"] = cyclic_delay

    n.add(
        "Link",
        spill,
        bus0=upstream_water_bus,
        bus1=downstream_water_bus,
        bus2="",
        efficiency2=1.0,
        delay2=0.0,
        cyclic_delay2=True,
        carrier="hydro",
        p_nom=float("inf"),
        efficiency=downstream_energy_ratio,
        marginal_cost=spill_cost,
        delay=travel_time_hours,
        cyclic_delay=cyclic_delay,
    )

    return {
        "turbine": turbine,
        "spill": spill,
    }


def materialize_cascade_storage_units(
    n: pypsa.Network,
    topology: pd.DataFrame,
) -> dict[str, dict[str, str]]:
    """
    Convert preserved cascade StorageUnits into explicit hydraulic components.

    The StorageUnit inflow is already expressed as local hydraulic power.
    It is therefore attached as a fixed Generator on the corresponding
    reservoir water bus.
    """
    topology = topology.copy()
    topology["upstream"] = topology["upstream"].astype(str).str.strip()
    topology["downstream"] = topology["downstream"].astype(str).str.strip()
    validate_cascade_topology(topology)

    dense_inflow = n.get_switchable_as_dense("StorageUnit", "inflow")
    static, _ = pop_cascade_storage_units(n)
    if static.empty:
        raise ValueError(
            "Cascading hydro is enabled but no preserved cascade StorageUnits "
            "were found in the clustered network."
        )

    required = {
        PLANT_ID_COLUMN,
        "bus",
        "p_nom",
        "max_hours",
        "efficiency_dispatch",
        "dam_height_m",
    }
    missing_columns = required - set(static.columns)
    if missing_columns:
        raise ValueError(
            "Cascade StorageUnits are missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    plant_ids = static[PLANT_ID_COLUMN].fillna("").astype(str).str.strip()
    duplicate_ids = plant_ids[plant_ids.ne("") & plant_ids.duplicated(keep=False)]
    if not duplicate_ids.empty:
        raise ValueError(
            "Cascade StorageUnits must have unique plant_id values. Duplicates: "
            + ", ".join(sorted(duplicate_ids.unique()))
        )

    component_by_plant = pd.Series(static.index, index=plant_ids)
    topology_nodes = set(topology["upstream"]).union(topology["downstream"])
    component_nodes = set(component_by_plant.index)

    missing_nodes = sorted(topology_nodes - component_nodes)
    if missing_nodes:
        raise ValueError(
            "Cascade topology nodes are missing from the clustered network: "
            + ", ".join(missing_nodes)
        )

    unexpected_nodes = sorted(component_nodes - topology_nodes)
    if unexpected_nodes:
        raise ValueError(
            "Clustered network contains cascade plants not present in the topology: "
            + ", ".join(unexpected_nodes)
        )

    dam_heights = pd.to_numeric(
        static.set_index(plant_ids)["dam_height_m"],
        errors="coerce",
    )
    invalid_heights = dam_heights[dam_heights.isna() | (dam_heights <= 0)]
    if not invalid_heights.empty:
        raise ValueError(
            "Cascade StorageUnits require positive dam heights: "
            + ", ".join(invalid_heights.index)
        )

    ordered_plant_ids = list(
        dict.fromkeys(topology["upstream"].tolist() + topology["downstream"].tolist())
    )

    components = {}

    for plant_id in ordered_plant_ids:
        component = component_by_plant.loc[plant_id]
        row = static.loc[component]

        names = add_hydro_reservoir(
            n,
            plant_id=plant_id,
            electricity_bus=row["bus"],
            p_nom=float(row["p_nom"]),
            max_hours=float(row["max_hours"]),
            efficiency_dispatch=float(row["efficiency_dispatch"]),
            cyclic=bool(row.get("cyclic_state_of_charge", True)),
            capital_cost=float(row.get("capital_cost", 0.0)),
            marginal_cost=float(row.get("marginal_cost", 0.0)),
            build_year=int(row.get("build_year", 0)),
            lifetime=float(row.get("lifetime", math.inf)),
        )

        if component not in dense_inflow.columns:
            raise ValueError(f"Missing inflow data for cascade plant '{plant_id}'.")

        profile = dense_inflow[component].reindex(n.snapshots)
        if profile.isna().any():
            raise ValueError(
                f"Inflow time series for cascade plant '{plant_id}' "
                "does not cover all network snapshots."
            )
        if (profile < 0).any():
            raise ValueError(
                f"Negative hydraulic inflow found for cascade plant '{plant_id}'."
            )

        inflow_name = f"{plant_id} inflow"
        inflow_p_nom = max(float(profile.max()), 1.0)
        inflow_pu = profile / inflow_p_nom

        n.add(
            "Generator",
            inflow_name,
            bus=names["water_bus"],
            carrier="water",
            p_nom=inflow_p_nom,
            p_nom_extendable=False,
            p_min_pu=inflow_pu,
            p_max_pu=inflow_pu,
            build_year=int(row.get("build_year", 0)),
            lifetime=float(row.get("lifetime", math.inf)),
        )

        components[plant_id] = {
            **names,
            "inflow": inflow_name,
        }

    for edge in topology.itertuples(index=False):
        upstream = edge.upstream
        downstream = edge.downstream

        upstream_component = component_by_plant.loc[upstream]
        upstream_row = static.loc[upstream_component]
        spill_cost = upstream_row.get("spill_cost", 0.0)
        spill_cost = 0.0 if pd.isna(spill_cost) else float(spill_cost)

        connect_hydro_reservoirs(
            n,
            upstream_plant_id=upstream,
            downstream_plant_id=downstream,
            travel_time_hours=float(edge.travel_time_hours),
            downstream_energy_ratio=(
                float(dam_heights.loc[downstream]) / float(dam_heights.loc[upstream])
            ),
            spill_cost=spill_cost,
            cyclic_delay=False,
        )

    # Terminal reservoirs still need a free spill path. A negative-sign
    # Generator acts as a dispatchable sink on the water bus and reproduces
    # the spillage freedom of the original StorageUnit representation.
    terminal_ids = [
        plant_id
        for plant_id in ordered_plant_ids
        if plant_id not in set(topology["upstream"])
    ]

    for plant_id in terminal_ids:
        component = component_by_plant.loc[plant_id]
        row = static.loc[component]
        spill_cost = row.get("spill_cost", 0.0)
        spill_cost = 0.0 if pd.isna(spill_cost) else float(spill_cost)
        spill = f"{plant_id} terminal spill"

        n.add(
            "Generator",
            spill,
            bus=components[plant_id]["water_bus"],
            carrier="water",
            sign=-1.0,
            p_nom=float("inf"),
            p_nom_extendable=False,
            marginal_cost=spill_cost,
            build_year=int(row.get("build_year", 0)),
            lifetime=float(row.get("lifetime", math.inf)),
        )

        components[plant_id]["spill"] = spill

    return components


def pop_cascade_storage_units(
    n: pypsa.Network,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Remove and return cascade StorageUnits while preserving their time series."""
    if PLANT_ID_COLUMN not in n.storage_units.columns:
        return pd.DataFrame(), {}

    plant_ids = n.storage_units[PLANT_ID_COLUMN]
    cascade_i = plant_ids.index[
        plant_ids.notna() & plant_ids.astype(str).str.strip().ne("")
    ]

    if cascade_i.empty:
        return pd.DataFrame(), {}

    static = n.storage_units.loc[cascade_i].copy()

    dynamic = {}
    for attr, df in n.storage_units_t.items():
        if not df.empty:
            columns = df.columns.intersection(cascade_i)
            if not columns.empty:
                dynamic[attr] = df.loc[:, columns].copy()

    n.remove("StorageUnit", cascade_i)

    return static, dynamic


def restore_cascade_storage_units(
    n: pypsa.Network,
    static: pd.DataFrame,
    dynamic: dict[str, pd.DataFrame],
    busmap: pd.Series,
) -> None:
    """Restore cascade StorageUnits on their remapped electrical buses."""
    if static.empty:
        return

    restored = static.copy()
    restored["bus"] = restored["bus"].map(busmap)

    missing_bus = restored["bus"].isna()
    if missing_bus.any():
        missing = ", ".join(restored.index[missing_bus])
        raise ValueError(
            f"Could not map electrical buses for cascade plants: {missing}"
        )

    defaults = n.components["StorageUnit"]["defaults"]
    standard_columns = [
        column
        for column in restored.columns
        if column in defaults.index and defaults.loc[column, "static"]
    ]

    n.add(
        "StorageUnit",
        restored.index,
        **{column: restored[column] for column in standard_columns},
    )

    custom_columns = restored.columns.difference(standard_columns)
    for column in custom_columns:
        n.storage_units.loc[restored.index, column] = restored[column]

    for attr, df in dynamic.items():
        n._import_series_from_df(
            df,
            "StorageUnit",
            attr,
        )
