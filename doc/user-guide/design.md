<!--
SPDX-FileCopyrightText: PyPSA-Earth, PyPSA-Zambia and PyPSA-Eur Authors

SPDX-License-Identifier: CC-BY-4.0
-->

# PyPSA-Zambia Design & Features

This page documents the modelling choices specific to PyPSA-Zambia and how they
differ from the upstream PyPSA-Earth framework. For the general workflow
structure inherited from PyPSA-Earth, see [Introduction](../home/introduction.md).

## Relationship to PyPSA-Earth

PyPSA-Zambia is maintained as a soft fork of [PyPSA-Earth](https://github.com/pypsa-meets-earth/pypsa-earth).
This means that it is developed in parallel with PyPSA Earth and remains compatible by merging upstream changes and can also contributes it's major changes back to upstream.

Zambia-specific code lives primarily in two places:

- `scripts/utility_custom_features.py` - helper functions for all ZM-specific
  network modifications (interconnectors, biomass potential, demand disaggregation,
  forced thermal dispatch, etc.)
- `configs/validation_dispatch_zambia.yaml` - the ZM-specific default configuration that
  overrides PyPSA-Earth's `config.default.yaml` with Zambia cost data, voltage
  levels, and feature flags

## Hydro Modelling

Zambia's electricity system is dominated by large hydropower reservoirs. Accurate
water flow data are therefore the single most important input to the model.

PyPSA-Earth's default approach uses ERA5 weather reanalysis processed by
[Atlite](https://github.com/PyPSA/atlite/) to derive runoff-based inflow
estimates. Use of ERA5 as a data source is also inherited in PyPSA-Zambia as well. However, PyPSA-Zambia also provides an alternative: inflow profiles built directly
from [GloFAS](https://global-flood.emergency.copernicus.eu/) river discharge
data, which measures actual river flow at the coordinates of each hydro plant
rather than estimating it from atmospheric variables.

The approach is controlled by a single config key in the `renewable.hydro` block:

```yaml
renewable:
  hydro:
    source: era5     # standard PyPSA-Earth approach using atlite
    # source: custom  # use GloFAS data instead
```

When `source: custom`, the `add_electricity` rule reads the hydro profile from
`data/hydro_profiles/glofas_profile.nc` rather than the atlite-generated
`resources/.../profile_hydro.nc`. The GloFAS profile itself is built by the
`build_glofas_profile` rule (`scripts/build_glofas_profile.py`), which reads
a GloFAS dataset (`cutouts/zm-{year}-glofas.nc`) and extracts discharge
time-series at the location of each hydro plant.

Pre-built GloFAS datasets for multiple years are available via the `inflow-glofas`
databundle entry in `configs/validation_dispatch_zambia.yaml`:

```yaml
  inflow-glofas:
    source: primary
    version: v1.0
    year: 2013   # adjust to match the weather year in use
```

## Power Plant Data

PyPSA-Earth populates generators from the global
[powerplantmatching](https://github.com/PyPSA/powerplantmatching) database.
PyPSA-Zambia replaces this with a curated inventory of Zambian plants in
`data/custom_powerplants.csv`, activated by:

```yaml
electricity:
  custom_powerplants: replace
```

The file contains named plants - Kafue Gorge Upper (990 MW), Kariba North Bank
(720 MW), Itezhi Tezhi (120 MW), Victoria Falls (108 MW), and others - with
individual lat/lon coordinates, commission and decommission years, and reservoir
parameters. The `powerplants_filter` config key controls which plants are active
for a given study year. The parameter `DateIn` specifies the year the plant was commissioned (came online/started generation) while `DateOut` gives the year of decommision of the power plant.

So `DateIn <= 2024` means "only include plants that were built by 2024." while So `DateOut >= 2024` means "only include plants that haven't retired yet by 2024."
The `!= DateOut` parts are handling nulls. In pandas, NaN != NaN is true, so `DateOut != DateOut` is a way of saying "or the retirement date is unknown/missing." It's a quirk of how pandas evaluates query strings. In plain English it means "treat a missing date as still active."

```yaml
electricity:
  powerplants_filter: (DateOut >= 2024 or DateOut != DateOut) and (DateIn <= 2024 or DateIn != DateIn)
```

### Plant disaggregation

By default, PyPSA-Earth aggregates all generators at a bus into a single entry
during network simplification, which loses individual plant identities. The
`disaggregate_powerplants` feature preserves named plants through simplification,
enabling validation against plant-level generation data:

```yaml
electricity:
  disaggregate_powerplants: true
  exclude_carriers: [coal, oil, hydro, ror, PHS, biomass]
```

The `exclude_carriers` list tells the simplification step which carriers must not
be re-aggregated. This is required whenever `disaggregate_powerplants: true`.

## Demand Modelling

### Spatial disaggregation

PyPSA-Earth distributes electricity demand across buses using GDP and population
density. In Zambia, the copper mining sector is a dominant electricity consumer
whose spatial distribution differs significantly from population. PyPSA-Zambia
adds a mining-weighted component:

```yaml
load_options:
  demand_weights:
    mining: 0.76   # fraction of demand attributed to mining intensity
    gdp: 0.24
  zambia_demand_distribution: true
```

When `zambia_demand_distribution: true`, a mining raster is built from
`data/mining/zambia_provincial_mining_demand.csv` and
`data/mining/zambia_pangaea_mining_polygons.csv` via the `build_mining_raster`
rule, and used alongside GDP to disaggregate load spatially.

### Demand source

The config key `load_options.source` selects the demand dataset:

```yaml
load_options:
  source: gegis       # default PyPSA-Earth source
  # source: demandcast  # DemandCast alternative
```

For capacity expansion scenarios, the `scale` parameter adjusts total demand to
a target year projection:

```yaml
load_options:
  scale: 2.64   # IRP 2030 demand (41,925 GWh) / DemandCast base (15,909 GWh)
```

## SAPP Interconnectors

Zambia is a member of the Southern African Power Pool (SAPP) and imports and
exports power to neighbouring countries. The model represents cross-border links
explicitly using data in `data/sapp_countries.csv`, `data/sapp_links.csv`, and
`data/zm_substations.csv`.

Interconnectors are added to the network in `scripts/prepare_network.py` via
`add_interconnectors()` in `scripts/utility_custom_features.py`, controlled by:

```yaml
validation:
  interconnectors:
    enable: true
    download_data: true
```

## Biomass Potential

PyPSA-Zambia can model biomass as an extendable generation carrier with
province-level potential constraints derived from land-use data. The feature is
enabled by:

```yaml
electricity:
  biomass_potential: true
```

When enabled, `add_biomass_potential()` in `scripts/utility_custom_features.py`
reads `data/biomass.geojson`, which contains province shapes with total biomass
capacity in MW sourced from Pangaea. Each network bus receives a share of its
province's total capacity as its `p_nom_max`, preventing the optimiser from
building more biomass than the land base can sustainably support.

If biomass is also listed in `extendable_carriers.Generator`, the optimiser can
invest in new biomass capacity up to that provincial limit. If it is not listed
as extendable, existing biomass plants are still subject to the `p_nom_max`
constraint.

Biomass potential is disabled by default (`biomass_potential: false`) in
capacity expansion base configs and must be enabled explicitly.

## Study Modes

PyPSA-Zambia supports two distinct study configurations:

### Dispatch Modelling

All `extendable_carriers` lists are empty - the installed fleet is fixed. The
solver only determines how to schedule existing plants to minimise
operating cost. This mode is used to reproduce a historical year's operation and
compare against ZESCO's reported generation data.

The key config in carrying out this operation is the: `configs/validation_dispatch_zambia.yaml`

```bash
snakemake -j 1 solve_all_networks configfile configs/validation_dispatch_zambia.yaml
```

### Capacity expansion

Solar and onwind are marked as extendable, allowing the solver to optimise both
investment and dispatch jointly. The `existing_thermal_dispatch` feature forces
existing coal and oil plants to always dispatch (see below), reflecting their
sunk-cost status in forward-looking runs.

Entry point: `configs/cap_exp_zambia.yaml` (base) + year-specific overrides in
`configs/scenarios_zambia/`

```bash
snakemake -j 1 run_all_scenarios
```

## Forced Thermal Dispatch

In capacity expansion runs, existing coal and oil plants would normally compete
against cheaper renewables on marginal cost, potentially being left largely idle.
In practice ZESCO operates these plants as baseload assets - their capital costs
are sunk and they are needed to hedge against hydro shortfalls.

The `existing_thermal_dispatch` feature replicates this by setting marginal cost
to zero for qualifying thermal plants, ensuring the optimiser always dispatches
them before anything else:

```yaml
electricity:
  existing_thermal_dispatch:
    enable: true
    base_year: 2025
    carriers: [coal, oil]
```

The function `set_existing_thermal_zero_mc()` in
`scripts/utility_custom_features.py` applies a zero marginal cost to any
non-extendable generator whose carrier is in the list and whose
`build_year <= base_year`. This applies only to existing plants - any new
capacity the solver chooses to build is not affected.

## Future Scenarios

Four planning horizon configurations are provided in `configs/scenarios_zambia/`:

| Config file | Horizon | Demand scale | Fleet |
|---|---|---|---|
| `config.cap_exp_zambia_2025.yaml` | 2025 | 1.0× (base) | Plants with `DateIn <= 2025` |
| `config.cap_exp_zambia_2030.yaml` | 2030 | 2.64× | Plants with `DateIn <= 2030` |
| `config.cap_exp_zambia_2040.yaml` | 2040 | 3.75× | Plants with `DateIn <= 2040` |
| `config.cap_exp_zambia_2050.yaml` | 2050 | 4.76× | Plants with `DateIn <= 2050` |

Demand scale factors are derived from Zambia's Integrated Resource Plan (IRP)
projected national demand divided by the DemandCast base year value of 15,909 GWh.

All four capacity expansion configs (`config.cap_exp_zambia_{year}.yaml`) inherit shared settings from `configs/cap_exp_zambia_base.yaml` (ERA5
2023 cutout, 22 clusters, 3-hour temporal resolution, costs from Zambia's IRP).
Each scenario diff only overrides `powerplants_filter`, `extendable_carriers`,
`load_options.scale`, and `costs.year`.

To run all four scenarios in sequence:

```bash
snakemake -j 1 run_all_scenarios
```

Each scenario is solved independently and its results saved under
`results/{scenario_name}/`.

## Cross-Scenario Comparison

After running multiple scenarios, the `compare_scenarios` rule reads solved
networks and produces stacked bar charts of installed capacity, generation mix,
and CO₂ emissions across all scenarios side by side.

The comparison is configured in the `plotting.scenario_comparison` block:

```yaml
plotting:
  scenario_comparison:
    output_name: "cap_exp_zambia"
    scenario_filter:
      - "cap_exp_zambia_2025"
      - "cap_exp_zambia_2030"
      - "cap_exp_zambia_2040"
      - "cap_exp_zambia_2050"
    label_map:
      cap_exp_zambia_2025: "cap_exp 2025"
      cap_exp_zambia_2030: "cap_exp 2030"
      cap_exp_zambia_2040: "cap_exp 2040"
      cap_exp_zambia_2050: "cap_exp 2050"
```

To run the comparison:

```bash
snakemake -j 1 compare_scenarios
```

Outputs are saved to `results/comparison_plots/{output_name}/`.
