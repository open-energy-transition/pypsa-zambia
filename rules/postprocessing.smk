# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later


rule build_reference_generation:
    """Aggregates historical ERB/IPP generation datasets by PyPSA carrier.

    Consumed by _compare_scenarios_group for groups that opt in via
    plotting.scenario_comparison.<group>.reference_data: [generation].
    """
    input:
        ipp="data/validation/ipp_generation.csv",
        diesel="data/validation/zesco_diesel_generation.csv",
        large_hydro="data/validation/zesco_large_hydro_generation.csv",
        mini_hydro="data/validation/zesco_mini_hydro_generation.csv",
        fuel_aliases="data/reference_fuel_aliases.csv",
        custom_powerplants="data/custom_powerplants.csv",
    output:
        "results/comparison_plots/reference_generation_by_carrier.csv",
    log:
        "logs/build_reference_generation.log",
    script:
        "../scripts/build_reference_generation.py"


def _compare_scenarios_group_reference_inputs(wildcards):
    """Only require the reference-generation resource for groups that opt in."""
    groups = config.get("plotting", {}).get("scenario_comparison", {})
    reference_data = groups.get(wildcards.scenario_group, {}).get("reference_data", [])
    if "generation" in reference_data:
        return {
            "reference_generation": "results/comparison_plots/reference_generation_by_carrier.csv"
        }
    return {}


rule compare_scenarios:
    """Builds every comparison group defined under plotting.scenario_comparison.

    Run with:
        snakemake compare_scenarios
    """
    input:
        expand(
            "results/comparison_plots/{name}",
            name=list(
                config.get("plotting", {}).get("scenario_comparison", {}).keys()
            ),
        ),


rule _compare_scenarios_group:
    """Wildcard rule invoked by compare_scenarios. Can also be called directly with a concrete path:

        snakemake results/comparison_plots/<scenario_group>

    where <scenario_group> is a key under plotting.scenario_comparison in the run
    config. Scenarios to compare are defined by that group's scenario_filter.
    """
    input:
        unpack(_compare_scenarios_group_reference_inputs),
    params:
        results_dir="results/",
    output:
        directory("results/comparison_plots/{scenario_group}"),
    log:
        "logs/compare_scenarios_{scenario_group}.log",
    script:
        "../scripts/plot_scenario_comparison.py"
