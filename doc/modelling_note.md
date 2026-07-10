<!--
SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors

SPDX-License-Identifier: CC-BY-4.0
-->

# General design

The workflow is configured using configuration files. To ensure reproducibility, all the config files are git-tracked. In particular, `config.yaml` is not included into `Snakefile` and wouldn't have effect on the workflow.

## Particular configurations

The following yaml configuration files are available for different types of modelling runs. The folder `configs` stores definitions of the configuration files used in the workflow, and `pypsa-zambia` contains `config.default.yaml` and `config.tutorial.yaml`.

### Service configurations

A number of files in `configs` are service files used in each run:
- bundle_config.yaml defines parameters of the pre-compiled data bundles applicable on the global level, along with `data/versions.csv` file
-
- `powerplantmatching_config.yaml` is used to define default configuration of search in databases ported with `powerplantmatching` package
- `regions_definition_config.yaml` defines parameters needed to match geographic regions

### Scenario configurations

The configuration following configuration

#### Project root folder

The following universal files are available directly in `pypsa-zambia` folder:
- `config.default.yaml` contains default values of all the parameters which are used to fill any gaps in scenario-specific configuration files;
- `config.tutorial.yaml` defines a light-weight workflow which is used to run tutorial in upstream and is a convenient base to run tests. Currently, the testing workflow applies `config.zm_dispatch.yaml` over `config.tutorial.yaml` when running regional tests.

#### Configuration folder

`configs/scenarios` folder contains an example definition of a configuration file (not directly relevant for the project).

Specific configuration files are available to build regional-specific cutouts for the country:
- `build_cutout_zambia_config.yaml` contains parameters used to build a full-scale cutout;
- `build_cutout_tutorial_zambia_config.yaml` contains parameters user to build a tutorial cutout.

`Customisation` section in the project README describes how to use those configurations when building a cutout for a year of interest.

To run a modeling scenario, a scenario-specific configuration file should be applied on top of the service configurations and `config.default.yaml`. Currently, the following configuration files are available:
- `validation_dispatch_zambia.yaml` defines a dispatch modelling run which aims to reproduce a national power system in a specific year in the past and is intended to be used for validation

## Validation

Validation implies cross-check of the modelling parameters and outputs against observations data and is needed to ensure that the model is reproducing reality in a way accurate enough to particular modelling purposes. For power system models, standard validation checks include validation of basic inputs (the overall electricity demand, installed generation capacity, topology of the power grid) and main outputs (generation mix).

### Validation assumptions

Validation is done on the data from the past (2024) which means the need to adjust year-related parameters for the following parameters:
- commission and de-commission years for installed generation capacity;
- technology costs and performance parameters;
- scaling parameter for the electricity demand;
- date of OSM data snapshot (we take the latest OSM data which are likely to represent the validation year `2024` in the most accurate way).

For now, the weather year is taken for a default `2013` year (NB can require adjustments to reproduce hydro operation in a more accurate way).

### Validation runs

A configuration file `validation_dispatch_zambia.yaml` contains definitions for a dispatch run reproducing behavior of the national power system in a reference year from the past. To get modelling outputs for the validation scenario, the following commands as used:

```
# good to use a dry-run to make sure that
# retrieve rules are not triggered accidentally
snakemake -j 1 solve_all_networks -n
# actual modelling run
snakemake -j 1 solve_all_networks
```

The validation run doesn't include capacity expansion which allows to run it locally.

### Validation routine

Once the results are ready, [PyPSA-Earth-Status](https://github.com/open-energy-transition/pypsa-earth-status) workflow can be used to automatically generate diagrams and tables for major validation metrics. To make it work:
1. Clone [PyPSA-Earth-Status](https://github.com/open-energy-transition/pypsa-earth-status) fork. **NB** There is no need to retrieve data bundles for PyPSA-Earth sub-workflow. All what we need from PyPSA-Earth-Status is the code (a transition from sub-workflows to a fork design should be discussed in the PyPSA-Earth-Status upstream).
2. Place the solved network and clean osm geojsons for lines and substations into `pypsa-earth-status/resources`.
3. Adjust paths and country codes `pypsa-earth-status/config.yaml`.
4. Run `snakemake -j 1 visualize_data` from `pypsa-earth-status` folder

Once a validation run completed, the outputs are available in `pypsa-earth-status/results`.

For more advanced analysis (e.g. checking imports and exports), a validation notebook is available in [notebooks](https://github.com/open-energy-transition/pypsa-zambia/tree/main/notebooks) folder.

## Capacity Expansion Validation Setup

Capacity-expansion outputs are checked against Zambia's 2023 Integrated Resource Plan (IRP), using the [IRP scenarios scoping document](https://docs.google.com/document/d/13av6J_Yz-iMXanWeEhmLaMoAJUq39FRrF4-dA1Gn8Vs/edit?usp=sharing).

Demand and costs in the model are already set to match IRP figures for each planning year. The validation is in what the model chooses to build and generate given those inputs, compared against the IRP's own plan for the same years: installed capacity by technology, generation mix, and emissions.

Comparison is done at four horizons - 2025, 2030, 2040, and 2050. Comparison plots are produced via `scripts/plot_scenario_comparison.py` and saved to `results/comparison_plots/cap_exp_zambia/`.

## Capacity Expansion

Capacity expansion scenarios extend the dispatch-only run by letting the model size new generation to meet demand at future planning horizons, using cost and technology parameters calibrated to Zambia's 2023 Integrated Resource Plan (IRP).

### Design

**What can be expanded.** Only solar and onshore wind can be newly built by the model. Hydro, coal, oil, biomass, and geothermal capacities are fixed in each planning-year snapshot: whatever is scheduled to be in service that year (based on commissioning/decommissioning dates in the powerplants data) is what the model has to work with, and the optimizer only decides how much solar and wind to add on top.

Solar and wind siting is currently based on general land-cover suitability across the whole country, with no per-region cap and no restriction to specific sites. The IRP instead limits wind to a set of measured candidate sites and caps additions at 1,000 MW per region per planning period.

**Four independent planning-year snapshots.** `configs/scenarios_zambia/config.cap_exp_zambia_{2025,2030,2040,2050}.yaml` each merge on top of the shared `cap_exp_zambia_base.yaml` and are solved as fully independent optimizations - there is no myopic/multi-horizon linkage between them. A generator built in the 2040 run has no bearing on 2050; each year re-derives its own fixed fleet, demand level, and solar/wind buildout from scratch. This means that capacity trajectories between horizons are not guaranteed to be monotonic.

**Weather and hydro conditions.** All four planning years are solved against the same single weather year - ERA5 `cutout-{year}-era5`, hourly, within a given year e.g `2023-01-01` to `2024-01-01`.

Hydro specifically is non-extendable in every scenario, normalized via the IRENA method against 2023 generation statistics with a uniform multiplier of 2.19, and drawn from the same `{year}` ERA5 cutout as solar/wind.

Solar and wind use `correction_factor` 0.93 and 0.83 respectively (empirical de-rating of the raw ERA5-derived profile), and siting eligibility is computed with a `simple` land-use potential method.

**Demand and cost basis.** Demand is a DemandCast hourly profile for the 2023 weather year, scaled per planning year (`load_options:scale`) to match IRP Table 3's national demand projection for that year (e.g. 2030: scale 2.64 against IRP's 41,925 GWh vs. DemandCast's unscaled 15,909 GWh base). Investment, marginal cost, FOM, lifetime, and CO2 emission factors are transcribed directly from the Zambia 2023 IRP (Table 5, Table 9, Annex 3), converted at a fixed 0.7532 EUR/USD rate, with `costs.year` set per scenario.

### Results

Generation mix by technology, model vs. IRP Table 12, in TWh:

| Year | Hydro Storage | Hydro RoR | Solar | Wind | Coal & Oil | Biomass & Geo | Total |
|---|---|---|---|---|---|---|---|
| 2025/26 | 11.4 / 9.2 | 10.1 / 9.4 | 0.3 / 3.0 | 0.1 / 0.9 | 0.9 / — | — / — | 22.8 / 22.9 |
| 2030 | 18.9 / 9.7 | 11.2 / 20.8 | 4.0 / 3.8 | 2.8 / 2.5 | 2.9 / 4.0 | 1.8 / 1.0 | 41.6 / 41.9 |
| 2040 | 18.2 / 10.0 | 21.6 / 23.0 | 5.5 / 6.4 | 3.8 / 7.0 | 3.0 / 7.0 | 7.3 / 6.1 | 59.3 / 59.6 |
| 2050 | 19.0 / 8.3 | 25.7 / 31.4 | 6.9 / 9.2 | 3.6 / 11.5 | 4.4 / 5.4 | 15.8 / 9.9 | 75.5 / 75.7 |

*(model / IRP)*

Total demand matches IRP closely at every horizon, as expected since it's calibrated to it directly. Wind is under-represented relative to the IRP throughout, and the gap grows with each horizon, while hydro storage carries a larger share of generation than the IRP assumes. These figures are from an earlier scenario run, using an earlier version of the wind/solar siting data; expect the mix to shift as the model is re-run with updated inputs.

There's a separate mismatch worth flagging in the underlying capacity, independent of which run's generation numbers are used: the split between hydro storage and hydro run-of-river doesn't match IRP even where total hydro is close. The model's run-of-river capacity in 2025 is around 1,517 MW, well above the roughly 820 MW the IRP counts for existing run-of-river plants plus the committed Kafue Gorge Lower project. This looks like a difference in how individual plants are classified between the two datasets rather than a resource or siting issue, and hasn't been investigated further yet.
