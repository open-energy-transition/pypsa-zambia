<!--
SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors

SPDX-License-Identifier: CC-BY-4.0
-->

# Configuration

PyPSA-Earth imports the configuration options originally developed in [PyPSA-Eur](https://pypsa-eur.readthedocs.io/en/latest/index.html) and here reported and adapted.
The options here described are collected in a `config.yaml` file located in the root directory.
Users should copy the provided default configuration (`config.default.yaml`) and amend
their own modifications and assumptions in the user-specific configuration file (`config.yaml`);
confer installation instructions at [installation](../home/installation.md).

  Credits to PyPSA-Eur developers for the initial drafting of the configuration documentation here reported

## Top-level configuration

```yaml
--8<-- "configtables/snippets/toplevel.yaml"
```

{{ read_csv('configtables/toplevel.csv') }}

## run

It is common conduct to analyse energy system optimisation models for **multiple scenarios** for a variety of reasons,
e.g. assessing their sensitivity towards changing the temporal and/or geographical resolution or investigating how
investment changes as more ambitious greenhouse-gas emission reduction targets are applied.

The `run` section is used for running and storing scenarios with different configurations which are not covered by [wildcards](wildcards.md). It determines the path at which resources, networks and results are stored. Therefore the user can run different configurations within the same directory. If a run with a non-empty name should use cutouts shared across runs, set `shared_cutouts` to `true`.

```yaml
--8<-- "configtables/snippets/run.yaml"
```

{{ read_csv('configtables/run.csv') }}

## scenario

The `scenario` section is an extraordinary section of the config file
that is strongly connected to the [wildcards](wildcards.md) and is designed to
facilitate running multiple scenarios through a single command

```bash
snakemake -j 1 solve_all_networks
```

For each wildcard, a **list of values** is provided. The rule `solve_all_networks` will trigger the rules for creating `results/networks/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc` for **all combinations** of the provided wildcard values as defined by Python's [itertools.product(...)](https://docs.python.org/2/library/itertools.html#itertools.product) function that snakemake's [expand(...) function](https://snakemake.readthedocs.io/en/stable/snakefiles/rules.html#targets) uses.

An exemplary dependency graph (starting from the simplification rules) then looks like this:

![Image](https://raw.githubusercontent.com/pypsa-meets-earth/documentation/main/doc/img/scenarios.png)

```yaml
--8<-- "configtables/snippets/scenario.yaml"
```

{{ read_csv('configtables/scenario.csv') }}

## snapshots

Specifies the temporal range for the historical weather data, which is used to build the energy system model. It uses arguments to [pandas.date_range](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.date_range.html). The date range must be in the past (before 2022). A well-tested year is 2013.

```yaml
--8<-- "configtables/snippets/snapshots.yaml"
```

{{ read_csv('configtables/snapshots.csv') }}

## data

Listing sources of custom regional-focused data used by the workflow.

```yaml
--8<-- "configtables/snippets/data.yaml"
```

## crs

Defines the coordinate reference systems (crs).

```yaml
--8<-- "configtables/snippets/crs.yaml"
```

{{ read_csv('configtables/crs.csv') }}

## augmented_line_connection

If enabled, it increases the connectivity of the network. It makes the network graph [k-edge-connected](https://en.wikipedia.org/wiki/K-edge-connected_graph), i.e.,
if fewer than k edges are removed, the network graph stays connected. It uses the [k-edge-augmentation](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.connectivity.edge_augmentation.k_edge_augmentation.html#networkx.algorithms.connectivity.edge_augmentation.k_edge_augmentation)
algorithm from the [NetworkX](https://networkx.org/documentation/stable/index.html) Python package.

```yaml
--8<-- "configtables/snippets/augmented_line_connection.yaml"
```

{{ read_csv('configtables/augmented_line_connection.csv') }}

## cluster_options

Specifies the options to simplify and cluster the network. This is done in two stages, first using the rule `simplify_network` and then using the rule `cluster_network`. For more details on this process, see the [PyPSA-Earth paper](https://www.sciencedirect.com/science/article/pii/S0306261923004609), section 3.7.

```yaml
--8<-- "configtables/snippets/cluster_options.yaml"
```

{{ read_csv('configtables/cluster_options.csv') }}

## build_shape_options

Specifies the options to build the shapes in which the region of interest (`countries`) is divided.

```yaml
--8<-- "configtables/snippets/build_shape_options.yaml"
```

{{ read_csv('configtables/build_shape_options.csv') }}

## subregion

If enabled, this option allows a region of interest (`countries`) to be redefined into subregions,
which can be activated at various stages of the workflow. Currently, it is used in `simplify_network` and `cluster_network` rule.

```yaml
--8<-- "configtables/snippets/subregion.yaml"
```

{{ read_csv('configtables/subregion.csv') }}

The names of subregions are arbitrary. Its sizes are determined by how many GADM IDs that are included in the list.
A single country can be divided into multiple subregions, and a single subregion can include GADM IDs from multiple countries.
If the same GADM ID appears in different subregions, the first subregion listed will take precedence over that region.
The remaining GADM IDs that are not listed will be merged back to form the remaining parts of their respective countries.
For example, consider the Central District of Botswana, which has a GADM ID of `BW.3`. To separate this district from the rest of the country, you can select:

> **See `config.default.yaml` for the full configuration.**

There are several formats for GADM IDs depending on the version, so before using this feature, please review the `resources/shapes/gadm_shape.geojson` file which can be created using the command:

``bash
snakemake -j 1 build_shapes

!!! note
    The rule `build_shapes` currently use [Version 4.1](https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/) for their GADM data. This may change in the future.

## clean_osm_data_options

Specifies the options to clean the [OpenStreetMap](https://wiki.osmfoundation.org/wiki/Main_Page) (OSM) data.

```yaml
--8<-- "configtables/snippets/clean_osm_data_options.yaml"
```

{{ read_csv('configtables/clean_osm_data_options.csv') }}

## build_osm_network

Specifies the options to build the [OpenStreetMap](https://wiki.osmfoundation.org/wiki/Main_Page) (OSM) network.

```yaml
--8<-- "configtables/snippets/build_osm_network.yaml"
```

{{ read_csv('configtables/build_osm_network.csv') }}

## base_network

Specifies the minimum voltage magnitude in the base network and the offshore substations.

```yaml
--8<-- "configtables/snippets/base_network.yaml"
```

{{ read_csv('configtables/base_network.csv') }}

## load_options

Specifies the options to estimate future electricity demand (load). Different years might be considered for weather and the socioeconomic pathway (GDP and population growth), to enhance modelling capabilities.

```yaml
--8<-- "configtables/snippets/load_options.yaml"
```

{{ read_csv('configtables/load_options.csv') }}

The snapshots date range (`snapshots\start` - `snapshots\end`) must be in the `weather_year`.

## co2_budget

If enabled, this option allows setting different CO₂ targets for each planning horizon year. Only supports foresights with planning horizon such as myopic.

```yaml
--8<-- "configtables/snippets/co2budget.yaml"
```

{{ read_csv('configtables/co2_budget.csv') }}

## electricity

Specifies the options for the rule `add_electricity`. This includes options across several features, including but not limited to: voltage levels, electricity carriers available, renewable capacity estimation, CO2 emission limits, operational reserve, storage parameters. See the table below for more details.

```yaml
--8<-- "configtables/snippets/electricity.yaml"
```

{{ read_csv('configtables/electricity.csv') }}

Carriers in `conventional_carriers` must not also be in `extendable_carriers`.

## lines

Specifies electricity line parameters.

```yaml
--8<-- "configtables/snippets/lines.yaml"
```

{{ read_csv('configtables/lines.csv') }}

## links

Specifies Link parameters. Links are a fundamental component of [PyPSA](https://pypsa.readthedocs.io/en/latest/components.html) .

```yaml
--8<-- "configtables/snippets/links.yaml"
```

{{ read_csv('configtables/links.csv') }}

## transformers

Specifies transformers parameters and types.

```yaml
--8<-- "configtables/snippets/transformers.yaml"
```

{{ read_csv('configtables/transformers.csv') }}

## atlite

Define and specify the `atlite.Cutout` used for calculating renewable potentials and time-series. All options except for `features` are directly used as [cutout parameters](https://atlite.readthedocs.io/en/latest/ref_api.html#cutout).

{{ read_csv('configtables/atlite.csv') }}

## renewable

Specifies the options to obtain renewable potentials in every cutout. These are divided in five different renewable technologies: onshore wind (`onwind`), offshore wind with AC connection (`offwind-ac`), offshore wind with DC connection (`offwind-dc`), solar (`solar`), and hydropower (`hydro`).

#### onwind

```yaml
--8<-- "configtables/snippets/renewable_onwind.yaml"
```

{{ read_csv('configtables/onwind.csv') }}

#### offwind-ac

```yaml
--8<-- "configtables/snippets/renewable_offwind-ac.yaml"
```

{{ read_csv('configtables/offwind-ac.csv') }}

#### offwind-dc

```yaml
--8<-- "configtables/snippets/renewable_offwind-dc.yaml"
```

{{ read_csv('configtables/offwind-dc.csv') }}

#### solar

```yaml
--8<-- "configtables/snippets/renewable_solar.yaml"
```

{{ read_csv('configtables/solar.csv') }}

#### hydro

```yaml
--8<-- "configtables/snippets/renewable_hydro.yaml"
```

> **See `config.default.yaml` for the full configuration.**

{{ read_csv('configtables/hydro.csv') }}

#### csp

```yaml
--8<-- "configtables/snippets/renewable_csp.yaml"
```

> **See `config.default.yaml` for the full configuration.**

{{ read_csv('configtables/csp.csv') }}

## costs

Specifies the cost assumptions of the technologies considered. Cost information is obtained from the config file and the file `data/costs.csv`, which can also be modified manually.

```yaml
--8<-- "configtables/snippets/costs.yaml"
```

{{ read_csv('configtables/costs.csv') }}

!!! note
    To change cost assumptions in more detail (i.e. other than `marginal_cost`), consider modifying cost assumptions directly in `data/costs.csv` as this is not yet supported through the config file.
    You can also build multiple different cost databases. Make a renamed copy of `data/costs.csv` (e.g. `data/costs-optimistic.csv`) and set the variable `COSTS=data/costs-optimistic.csv` in the `Snakefile`.

    The `marginal costs` or in this context `variable costs` of operating the assets is important for realistic operational model outputs.
    It can define the curtailment order of renewable generators, the dispatch order of generators, and the dispatch of storage units.
    If not appropriately set, the model might output unrealistic results. Learn more about this in
    [Parzen et al. 2023](https://www.sciencedirect.com/science/article/pii/S2589004222020028) and in
    [Kittel et al. 2022](https://www.sciencedirect.com/science/article/pii/S2589004222002723).

## data
```yaml
--8<-- "configtables/snippets/data.yaml"
```

{{ read_csv('configtables/data.csv') }}


Controls which versions of input data are used for building the model.
Versions that are available for each dataset can be found in `data/versions.csv`.
By default, we retrieve the `latest` supported version for each dataset from an archive source.
This means that when upgrading between PyPSA-Zambia versions, new versions of input data will automatically be downloaded and used.
To freeze a model to a specific version of input data, you can set a specific version in the `version` field for each dataset to one specific version as listed in the `version` column of `data/versions.csv`.

Some datasets support `primary` or `build` as a source option, meaning that the data can be retrieved from the original
data source or build it from the latest available data.
See the `data/versions.csv` file for all available datasets and their sources/versions that are supported.

Note that a high-level overview of the datasets are stored in `doc/data_inventory.csv`. This provides a summary of the datasets,
their sources, licenses and a general description.

## monte_carlo

Specifies the options for Monte Carlo sampling.

```yaml
--8<-- "configtables/snippets/monte_carlo.yaml"
```

{{ read_csv('configtables/monte-carlo.csv') }}

## policy_config

Specifies the options regarding energy policy, for example in relation to hydrogen exports.

```yaml
--8<-- "configtables/snippets/policy_config.yaml"
```

{{ read_csv('configtables/policy_config.csv') }}

## demand_data

Specifies sector-coupled related demand.

```yaml
--8<-- "configtables/snippets/demand_data.yaml"
```

{{ read_csv('configtables/demand_data.csv') }}

## export

Specifies the option related to hydrogen exports.

```yaml
--8<-- "configtables/snippets/export.yaml"
```

{{ read_csv('configtables/export.csv') }}

## custom_data

Specifies which custom datasets are used to replace or supplement the default model data. For full details see [Custom Data Integration](custom-data.md).

```yaml
--8<-- "configtables/snippets/custom_data.yaml"
```

{{ read_csv('configtables/custom_data.csv') }}

## sector

Specifies the options for the sector coupling, i.e. the integration of the electricity system with other sectors such as heating and transport.

### top-level

```yaml
--8<-- "configtables/snippets/sector_toplevel.yaml"
```

{{ read_csv('configtables/sector_toplevel.csv') }}

### heat sector

```yaml
--8<-- "configtables/snippets/sector_heat.yaml"
```

{{ read_csv('configtables/sector_heat.csv') }}

### land transport sector

```yaml
--8<-- "configtables/snippets/sector_land_transport.yaml"
```

{{ read_csv('configtables/sector_land_transport.csv') }}

### biomass sector

```yaml
--8<-- "configtables/snippets/sector_biomass.yaml"
```

{{ read_csv('configtables/sector_biomass.csv') }}

### electricity distribution grid

```yaml
--8<-- "configtables/snippets/sector_electricity_distribution_grid.yaml"
```

{{ read_csv('configtables/sector_electricity_distribution_grid.csv') }}

### shipping & aviation sector

```yaml
--8<-- "configtables/snippets/sector_shipping_aviation.yaml"
```

{{ read_csv('configtables/sector_shipping_aviation.csv') }}

### ccus & conversion options

```yaml
--8<-- "configtables/snippets/sector_ccus.yaml"
```

{{ read_csv('configtables/sector_ccus.csv') }}

### industry options

```yaml
--8<-- "configtables/snippets/sector_industry.yaml"
```

{{ read_csv('configtables/sector_industry.csv') }}

### powerplants options

```yaml
--8<-- "configtables/snippets/sector_powerplants.yaml"
```

{{ read_csv('configtables/sector_powerplants.csv') }}

## solving

Specify linear power flow formulation and optimization solver settings.

### options

```yaml
--8<-- "configtables/snippets/solving_options.yaml"
```

{{ read_csv('configtables/solving-options.csv') }}

### solver

```yaml
--8<-- "configtables/snippets/solving_solver.yaml"
```

{{ read_csv('configtables/solving-solver.csv') }}

## plotting

Specifies plotting options.

```yaml
--8<-- "configtables/snippets/plotting.yaml"
```

{{ read_csv('configtables/plotting.csv') }}

# From PyPSA-Earth to PyPSA-ZM

Zambia-specific default config file:

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
