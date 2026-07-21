# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later


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
    params:
        results_dir="results/",
    output:
        directory("results/comparison_plots/{scenario_group}"),
    log:
        "logs/compare_scenarios_{scenario_group}.log",
    script:
        "../scripts/plot_scenario_comparison.py"
