# SPDX-FileCopyrightText: PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import numpy as np
import pandas as pd
import pytest
from build_glofas_profile import allocate_shared_hydraulic_inflow


@pytest.fixture
def hydro_data():
    plants = pd.DataFrame(
        {
            "p_nom": [720.0, 360.0, 100.0],
            "damheight_m": [92.0, 92.0, 50.0],
            "technology": ["Reservoir", "Reservoir", "Reservoir"],
            "hydraulic_resource_id": ["shared", "shared", ""],
        }
    )

    discharge = pd.DataFrame(
        {
            0: [300.0, 600.0, 900.0],
            1: [300.0, 600.0, 900.0],
            2: [100.0, 200.0, 300.0],
        },
        dtype=np.float32,
    )

    return discharge, plants


def test_shared_discharge_allocation(hydro_data):
    discharge, plants = hydro_data
    original = discharge.copy()

    result = allocate_shared_hydraulic_inflow(discharge, plants)

    np.testing.assert_allclose(result[0], discharge[0] * 2 / 3)
    np.testing.assert_allclose(result[1], discharge[1] / 3)
    np.testing.assert_allclose(result[[0, 1]].sum(axis=1), discharge[0])

    pd.testing.assert_series_equal(result[2], discharge[2])
    pd.testing.assert_frame_equal(discharge, original)


def test_backward_compatibility(hydro_data):
    discharge, plants = hydro_data

    result = allocate_shared_hydraulic_inflow(
        discharge,
        plants.drop(columns="hydraulic_resource_id"),
    )

    pd.testing.assert_frame_equal(result, discharge)


def test_unassigned_resources(hydro_data):
    discharge, plants = hydro_data
    plants["hydraulic_resource_id"] = [None, "", " "]

    result = allocate_shared_hydraulic_inflow(discharge, plants)

    pd.testing.assert_frame_equal(result, discharge)


def test_single_installation(hydro_data):
    discharge, plants = hydro_data
    plants["hydraulic_resource_id"] = ["shared", "", ""]

    result = allocate_shared_hydraulic_inflow(discharge, plants)

    pd.testing.assert_frame_equal(result, discharge)


@pytest.mark.parametrize(
    "column,value,error",
    [
        ("p_nom", 0.0, "Invalid capacities"),
        ("p_nom", -100.0, "Invalid capacities"),
        ("p_nom", np.nan, "Invalid capacities"),
        ("damheight_m", 100.0, "Inconsistent hydraulic heads"),
        ("damheight_m", 0.0, "Inconsistent hydraulic heads"),
        ("damheight_m", np.nan, "Inconsistent hydraulic heads"),
        ("technology", "Run-Of-River", "Incompatible hydro technologies"),
    ],
)
def test_invalid_shared_resource(hydro_data, column, value, error):
    discharge, plants = hydro_data
    plants.loc[1, column] = value

    with pytest.raises(ValueError, match=error):
        allocate_shared_hydraulic_inflow(discharge, plants)


def test_inconsistent_discharge_profiles(hydro_data):
    discharge, plants = hydro_data
    discharge.loc[0, 1] = 500.0

    with pytest.raises(ValueError, match="Different discharge profiles"):
        allocate_shared_hydraulic_inflow(discharge, plants)
