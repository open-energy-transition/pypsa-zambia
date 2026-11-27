# SPDX-FileCopyrightText: PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import numpy as np
import pandas as pd
import pypsa
import pytest
from hydro_cascade import (
    pop_cascade_storage_units,
    restore_cascade_storage_units,
)
from hydro_utils import resolve_hydraulic_heads


def test_explicit_head_precedence():
    plants = pd.DataFrame(
        {
            "damheight_m": [600.0, 1.7, 92.0],
            "hydraulic_head_m": [387.0, 105.77, np.nan],
        }
    )

    np.testing.assert_allclose(
        resolve_hydraulic_heads(plants),
        [387.0, 105.77, 92.0],
    )


def test_legacy_compatibility():
    plants = pd.DataFrame(
        {
            "damheight_m": [25.0, 100.0],
        }
    )

    np.testing.assert_allclose(
        resolve_hydraulic_heads(plants),
        [25.0, 100.0],
    )


def test_explicit_head_without_dam_height():
    plants = pd.DataFrame(
        {
            "hydraulic_head_m": [100.0],
        }
    )

    np.testing.assert_allclose(
        resolve_hydraulic_heads(plants),
        [100.0],
    )


def test_default_head():
    plants = pd.DataFrame(
        {
            "damheight_m": [0.0, np.nan],
        }
    )

    np.testing.assert_allclose(
        resolve_hydraulic_heads(plants, default=5.0),
        [5.0, 5.0],
    )


def test_missing_head_in_strict_mode():
    plants = pd.DataFrame(
        {
            "damheight_m": [0.0],
        }
    )

    with pytest.raises(ValueError, match="Missing or invalid"):
        resolve_hydraulic_heads(plants)


@pytest.mark.parametrize("head", [0.0, -10.0, np.inf, "invalid"])
def test_invalid_explicit_head(head):
    plants = pd.DataFrame(
        {
            "damheight_m": [100.0],
            "hydraulic_head_m": [head],
        }
    )

    with pytest.raises(ValueError, match="Invalid explicit"):
        resolve_hydraulic_heads(plants, default=5.0)


def test_cascade_head_metadata_roundtrip(tmp_path):
    n = pypsa.Network()

    n.add("Bus", "original")
    n.add("Bus", "clustered")

    n.add(
        "StorageUnit",
        "A",
        bus="original",
        p_nom=100.0,
        max_hours=10.0,
    )

    n.storage_units.loc["A", "plant_id"] = "A"
    n.storage_units.loc["A", "dam_height_m"] = 50.0
    n.storage_units.loc["A", "hydraulic_head_m"] = 387.0

    static, dynamic = pop_cascade_storage_units(n)

    restore_cascade_storage_units(
        n,
        static,
        dynamic,
        pd.Series({"original": "clustered"}),
    )

    path = tmp_path / "network.nc"
    n.export_to_netcdf(path)

    restored = pypsa.Network(path)

    assert restored.storage_units.at["A", "bus"] == "clustered"
    assert restored.storage_units.at["A", "plant_id"] == "A"
    assert restored.storage_units.at["A", "dam_height_m"] == 50.0
    assert restored.storage_units.at["A", "hydraulic_head_m"] == 387.0

    heads = resolve_hydraulic_heads(
        restored.storage_units,
        legacy_column="dam_height_m",
    )

    assert heads.loc["A"] == 387.0


@pytest.mark.parametrize("explicit_heads", [False, True])
def test_cascade_energy_conversion_ratios(explicit_heads):
    from hydro_cascade import materialize_cascade_storage_units

    n = pypsa.Network()
    n.set_snapshots(pd.date_range("2023-01-01", periods=3, freq="h"))

    plants = {
        "A": (24.5, 24.5),
        "B": (600.0, 387.0),
        "C": (173.3, 173.3),
    }

    for plant_id, (dam_height, hydraulic_head) in plants.items():
        n.add("Bus", f"{plant_id} electricity")

        n.add(
            "StorageUnit",
            plant_id,
            bus=f"{plant_id} electricity",
            carrier="hydro",
            p_nom=100.0,
            max_hours=10.0,
            efficiency_dispatch=0.9,
            cyclic_state_of_charge=True,
            inflow=[10.0, 20.0, 30.0],
        )

        n.storage_units.loc[plant_id, "plant_id"] = plant_id
        n.storage_units.loc[plant_id, "dam_height_m"] = dam_height

        if explicit_heads:
            n.storage_units.loc[plant_id, "hydraulic_head_m"] = hydraulic_head

    topology = pd.DataFrame(
        {
            "upstream": ["A", "B"],
            "downstream": ["B", "C"],
            "travel_time_hours": [1.0, 1.0],
        }
    )

    materialize_cascade_storage_units(n, topology)

    middle_head = 387.0 if explicit_heads else 600.0

    expected_ratios = {
        "A": middle_head / 24.5,
        "B": 173.3 / middle_head,
    }

    for plant_id, ratio in expected_ratios.items():
        assert n.links.at[f"{plant_id} turbine", "efficiency2"] == pytest.approx(ratio)

        assert n.links.at[f"{plant_id} spill", "efficiency"] == pytest.approx(ratio)
