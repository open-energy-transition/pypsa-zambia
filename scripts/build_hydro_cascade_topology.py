#!/usr/bin/env python

# SPDX-FileCopyrightText: PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Identify candidate cascading-hydropower connections from HydroBASINS.
"""

import logging

import geopandas as gpd
import pandas as pd
from _helpers import configure_logging, read_csv_nafix
from hydro_cascade import _parse_qualified_project_ids

logger = logging.getLogger(__name__)


def resolve_stable_plant_ids(powerplants: pd.DataFrame) -> pd.Series:
    """
    Resolve stable source-qualified identifiers for power plants.

    Identifier sources are ranked from the input data according to how many
    plants they can identify uniquely. This avoids assuming a specific
    powerplant database or country.
    """
    explicit_ids = {}
    project_ids = {}

    for idx, row in powerplants.iterrows():
        plant_id = row.get("plant_id")
        if pd.notna(plant_id) and str(plant_id).strip():
            explicit_ids[idx] = str(plant_id).strip()
            project_ids[idx] = set()
        else:
            explicit_ids[idx] = None
            project_ids[idx] = _parse_qualified_project_ids(row.get("projectid"))

    all_ids = [project_id for ids in project_ids.values() for project_id in ids]
    id_counts = pd.Series(all_ids).value_counts().to_dict()

    sources = sorted(
        {project_id.split(":", 1)[0] for project_id in all_ids if ":" in project_id}
    )

    source_coverage = {}

    for source in sources:
        coverage = 0

        for ids in project_ids.values():
            source_ids = [
                project_id
                for project_id in ids
                if project_id.startswith(f"{source}:")
                and id_counts.get(project_id, 0) == 1
            ]

            if len(source_ids) == 1:
                coverage += 1

        source_coverage[source] = coverage

    source_priority = sorted(
        sources,
        key=lambda source: (-source_coverage[source], source),
    )

    logger.info(
        "Project ID source priority inferred from unique coverage: %s",
        ", ".join(
            f"{source} ({source_coverage[source]})" for source in source_priority
        ),
    )

    resolved = {}

    explicit_counts = (
        pd.Series(
            [plant_id for plant_id in explicit_ids.values() if plant_id is not None]
        )
        .value_counts()
        .to_dict()
    )

    for idx in powerplants.index:
        explicit_id = explicit_ids[idx]

        if explicit_id is not None:
            resolved[idx] = (
                explicit_id if explicit_counts.get(explicit_id, 0) == 1 else None
            )
            continue

        ids = project_ids[idx]
        stable_id = None

        for source in source_priority:
            source_ids = sorted(
                project_id
                for project_id in ids
                if project_id.startswith(f"{source}:")
                and id_counts.get(project_id, 0) == 1
            )

            if len(source_ids) == 1:
                stable_id = source_ids[0]
                break

        resolved[idx] = stable_id

    return pd.Series(resolved, dtype="object")


def load_hydro_powerplants(
    powerplants_path,
    technologies=("Reservoir",),
):
    """
    Load hydropower plants eligible for cascade topology generation.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Resolved hydropower plants and unresolved plant-ID cases.
    """
    powerplants = read_csv_nafix(powerplants_path, index_col=0)

    hydro = powerplants[
        powerplants["Fueltype"].astype(str).str.casefold().eq("hydro")
    ].copy()

    hydro = hydro.rename(
        columns={
            "projectID": "projectid",
            "DamHeight_m": "damheight_m",
        }
    )

    if technologies is not None:
        if "Technology" not in hydro.columns:
            raise ValueError(
                "Powerplant data has no Technology column, but cascade "
                "technologies were specified."
            )

        allowed = {str(technology).casefold() for technology in technologies}

        hydro = hydro.loc[
            hydro["Technology"].fillna("").astype(str).str.casefold().isin(allowed)
        ].copy()

    hydro["stable_id"] = resolve_stable_plant_ids(hydro)

    unresolved = hydro["stable_id"].isna()
    ambiguity_rows = []

    for idx, row in hydro.loc[unresolved].iterrows():
        name = row.get("Name")
        plant = str(name).strip() if pd.notna(name) and str(name).strip() else str(idx)

        explicit_id = row.get("plant_id")
        project_ids = _parse_qualified_project_ids(row.get("projectid"))

        has_identifier = (pd.notna(explicit_id) and str(explicit_id).strip()) or bool(
            project_ids
        )

        ambiguity_rows.append(
            {
                "reason": (
                    "non_unique_stable_id" if has_identifier else "missing_stable_id"
                ),
                "plant": plant,
                "plant_index": idx,
            }
        )

    if unresolved.any():
        logger.warning(
            "Skipping %d hydropower plants without a unique stable ID: %s",
            int(unresolved.sum()),
            ", ".join(row["plant"] for row in ambiguity_rows),
        )

    id_ambiguities = pd.DataFrame(
        ambiguity_rows,
        columns=["reason", "plant", "plant_index"],
    )

    hydro = hydro.loc[~unresolved].copy()

    return hydro, id_ambiguities


def assign_plants_to_basins(
    powerplants: pd.DataFrame,
    hydrobasins: gpd.GeoDataFrame,
) -> pd.DataFrame:
    """Assign each hydropower plant to one HydroBASINS basin."""
    required = {"HYBAS_ID", "NEXT_DOWN", "DIST_MAIN", "geometry"}
    missing = required - set(hydrobasins.columns)

    if missing:
        raise ValueError(
            "HydroBASINS data is missing required columns: "
            + ", ".join(sorted(missing))
        )

    plants = gpd.GeoDataFrame(
        powerplants.copy(),
        geometry=gpd.points_from_xy(
            powerplants["lon"],
            powerplants["lat"],
        ),
        crs="EPSG:4326",
    ).to_crs(hydrobasins.crs)

    matched = gpd.sjoin(
        plants,
        hydrobasins[["HYBAS_ID", "geometry"]],
        how="left",
        predicate="within",
    )

    duplicated = matched.index.duplicated(keep=False)
    if duplicated.any():
        raise ValueError("Some hydropower plants match multiple HydroBASINS polygons.")

    unmatched = matched["HYBAS_ID"].isna()
    if unmatched.any():
        logger.warning(
            "Skipping %d hydropower plants outside HydroBASINS polygons.",
            int(unmatched.sum()),
        )
        matched = matched.loc[~unmatched].copy()

    matched["HYBAS_ID"] = matched["HYBAS_ID"].astype(int)

    return pd.DataFrame(matched.drop(columns="geometry"))


def identify_cascade_connections(
    powerplants: pd.DataFrame,
    hydrobasins: gpd.GeoDataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Identify unambiguous downstream hydropower connections.

    For every plant, follow the HydroBASINS ``NEXT_DOWN`` chain until the
    first downstream basin containing another hydropower plant is reached.

    Plants sharing the same HydroBASINS basin are reported as ambiguous and
    are not ordered automatically.
    """
    assigned = assign_plants_to_basins(powerplants, hydrobasins)

    basins = hydrobasins.set_index("HYBAS_ID")
    next_down = basins["NEXT_DOWN"]

    plants_by_basin = assigned.groupby("HYBAS_ID")["stable_id"].apply(list).to_dict()

    ambiguous_rows = []

    for basin_id, plant_ids in plants_by_basin.items():
        if len(plant_ids) > 1:
            ambiguous_rows.append(
                {
                    "reason": "multiple_plants_same_basin",
                    "hybas_id": basin_id,
                    "plants": ";".join(sorted(plant_ids)),
                }
            )

    ambiguous_basins = {
        basin_id
        for basin_id, plant_ids in plants_by_basin.items()
        if len(plant_ids) > 1
    }

    connections = []

    for plant in assigned.itertuples():
        upstream = plant.stable_id
        source_basin = plant.HYBAS_ID

        if source_basin in ambiguous_basins:
            continue

        current = next_down.get(source_basin)
        visited = {source_basin}

        while pd.notna(current) and int(current) != 0:
            current = int(current)

            if current in visited:
                raise ValueError(
                    f"Cycle detected in HydroBASINS downstream routing at {current}."
                )

            visited.add(current)

            downstream_plants = plants_by_basin.get(current, [])

            if len(downstream_plants) > 1:
                ambiguous_rows.append(
                    {
                        "reason": "multiple_downstream_plants_same_basin",
                        "hybas_id": current,
                        "plants": ";".join(sorted(downstream_plants)),
                        "upstream": upstream,
                    }
                )
                break

            if len(downstream_plants) == 1:
                downstream = downstream_plants[0]

                if downstream != upstream:
                    connections.append(
                        {
                            "upstream": upstream,
                            "downstream": downstream,
                            "upstream_hybas_id": source_basin,
                            "downstream_hybas_id": current,
                        }
                    )

                break

            if current not in next_down.index:
                break

            current = next_down.loc[current]

    connections = pd.DataFrame(
        connections,
        columns=[
            "upstream",
            "downstream",
            "upstream_hybas_id",
            "downstream_hybas_id",
        ],
    ).drop_duplicates()

    ambiguous = pd.DataFrame(
        ambiguous_rows,
        columns=[
            "reason",
            "plant",
            "plant_index",
            "hybas_id",
            "plants",
            "upstream",
        ],
    ).drop_duplicates()

    return connections, ambiguous


def build_hydro_cascade_topology(
    powerplants_path,
    hydrobasins_path,
    output_path,
    ambiguous_output_path,
    technologies=("Reservoir",),
):
    """Build candidate cascade connections from plant and basin data."""
    powerplants, id_ambiguities = load_hydro_powerplants(
        powerplants_path,
        technologies=technologies,
    )
    hydrobasins = gpd.read_file(hydrobasins_path)

    connections, basin_ambiguities = identify_cascade_connections(
        powerplants,
        hydrobasins,
    )

    ambiguous = pd.concat(
        [id_ambiguities, basin_ambiguities],
        ignore_index=True,
    ).drop_duplicates()

    ambiguity_columns = [
        "reason",
        "plant",
        "plant_index",
        "hybas_id",
        "plants",
        "upstream",
    ]
    ambiguous = ambiguous.reindex(columns=ambiguity_columns)

    connections.to_csv(output_path, index=False)
    ambiguous.to_csv(ambiguous_output_path, index=False)

    logger.info(
        "Identified %d candidate cascade connections and %d ambiguous cases.",
        len(connections),
        len(ambiguous),
    )


if __name__ == "__main__":
    if "snakemake" not in globals():
        from _helpers import mock_snakemake

        snakemake = mock_snakemake("build_hydro_cascade_topology")

    configure_logging(snakemake)

    build_hydro_cascade_topology(
        powerplants_path=snakemake.input.powerplants,
        hydrobasins_path=snakemake.input.hydrobasins,
        output_path=snakemake.output.topology,
        ambiguous_output_path=snakemake.output.ambiguous,
        technologies=snakemake.params.technologies,
    )
