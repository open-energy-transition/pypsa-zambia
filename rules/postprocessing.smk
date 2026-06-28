# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later


rule compare_scenarios:
    """Concrete entry point — resolves {scenario_group} from plotting.scenario_comparison.output_name in config.

    Run with:
        snakemake compare_scenarios
    """
    input:
        expand(
            "results/comparison_plots/{name}",
            name=config.get("plotting", {})
            .get("scenario_comparison", {})
            .get("output_name", "comparison"),
        ),


rule _compare_scenarios_group:
    """Wildcard rule invoked by compare_scenarios. Can also be called directly with a concrete path:

        snakemake results/comparison_plots/<output_name>

    where <output_name> matches plotting.scenario_comparison.output_name in the run config.
    Scenarios to compare are defined by plotting.scenario_comparison.scenario_filter.
    """
    params:
        results_dir="results/",
    output:
        directory("results/comparison_plots/{scenario_group}"),
    log:
        "logs/compare_scenarios_{scenario_group}.log",
    script:
        "../scripts/plot_scenario_comparison.py"
