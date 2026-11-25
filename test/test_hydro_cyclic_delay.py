# SPDX-FileCopyrightText: PyPSA-Earth and PyPSA-Eur Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Regression tests for cyclic hydraulic transfers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hydro_cascade import materialize_cascade_storage_units


def test_cyclic_cascade_preserves_delayed_hydraulic_transfers():
    """Preserve turbine and spill transfers across cyclic horizon boundaries."""
    import numpy as np
    import pandas as pd
    import pypsa

    n = pypsa.Network()
    snapshots = pd.date_range("2023-01-01", periods=4, freq="3h")
    n.set_snapshots(snapshots)
    n.snapshot_weightings.loc[:, :] = 3.0

    for carrier in ["AC", "hydro", "water"]:
        n.add("Carrier", carrier)

    for plant, head, inflow in [
        ("A", 40.0, [0.0, 0.0, 0.0, 15.0]),
        ("B", 80.0, [0.0, 0.0, 0.0, 0.0]),
    ]:
        n.add("Bus", plant, carrier="AC")

        component = f"{plant} hydro"

        n.add(
            "StorageUnit",
            component,
            bus=plant,
            carrier="hydro",
            p_nom=100.0,
            max_hours=10.0,
            efficiency_dispatch=0.9,
            cyclic_state_of_charge=True,
            marginal_cost=1.0,
            inflow=pd.Series(inflow, index=snapshots),
        )

        n.storage_units.loc[component, "plant_id"] = plant
        n.storage_units.loc[component, "dam_height_m"] = head
        n.storage_units.loc[component, "hydraulic_head_m"] = head

    topology = pd.DataFrame(
        {
            "upstream": ["A"],
            "downstream": ["B"],
            "travel_time_hours": [3.0],
        }
    )

    materialize_cascade_storage_units(n, topology)

    assert bool(n.links.at["A turbine", "cyclic_delay2"])
    assert bool(n.links.at["A spill", "cyclic_delay"])

    # Force turbine withdrawal in the final snapshot.
    n.add(
        "Load",
        "A demand",
        bus="A",
        p_set=pd.Series([0.0, 0.0, 0.0, 9.0], index=snapshots),
    )

    # Force spillage in the final snapshot.
    spill_profile = pd.Series(
        [0.0, 0.0, 0.0, 1.0],
        index=snapshots,
    )

    n.links.at["A spill", "p_nom"] = 5.0
    n.links_t.p_min_pu["A spill"] = spill_profile
    n.links_t.p_max_pu["A spill"] = spill_profile

    # Consume the transferred hydraulic energy downstream.
    n.add(
        "Load",
        "B demand",
        bus="B",
        p_set=pd.Series([27.0, 0.0, 0.0, 0.0], index=snapshots),
    )

    status, condition = n.optimize(
        solver_name="highs", include_objective_constant=False
    )

    assert status == "ok"
    assert condition == "optimal"

    # Check that both transfers arrive in the first snapshot.
    np.testing.assert_allclose(
        -n.links_t.p2["A turbine"],
        [20.0, 0.0, 0.0, 0.0],
        atol=1e-6,
    )

    np.testing.assert_allclose(
        -n.links_t.p1["A spill"],
        [10.0, 0.0, 0.0, 0.0],
        atol=1e-6,
    )

    # Verify weighted hydraulic energy conservation.
    weights = n.snapshot_weightings.stores

    for link, port, efficiency in [
        ("A turbine", 2, 2.0),
        ("A spill", 1, 2.0),
    ]:
        withdrawn = (n.links_t.p0[link] * weights).sum()
        delivered = (-getattr(n.links_t, f"p{port}")[link] * weights).sum()

        np.testing.assert_allclose(
            delivered,
            withdrawn * efficiency,
            atol=1e-6,
        )
