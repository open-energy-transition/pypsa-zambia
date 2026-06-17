# SPDX-FileCopyrightText: Open Energy Transition gGmbH
# SPDX-License-Identifier: AGPL-3.0-or-later


rule compare_scenarios:
    """Cross-scenario comparison plots (capacity, generation, demand, investments,
    CO2 emissions and spatial maps).

    The wildcard {scenario_group} is used as both the output folder name and the
    prefix filter for scenario discovery, so the folder name always matches the
    scenarios it contains.

    Run for a specific group:
        snakemake results/comparison_plots/cap_exp_zambia

    Run for multiple groups at once:
        snakemake results/comparison_plots/cap_exp_zambia results/comparison_plots/validation_dispatch_zambia

    Standalone development usage (from project root):
        python scripts/plot_scenario_comparison.py
    """
    params:
        results_dir="results/",
        base_dir=".",
        scenario_filter=lambda w: [w.scenario_group],
    output:
        directory("results/comparison_plots/{scenario_group}"),
    log:
        "logs/compare_scenarios_{scenario_group}.log",
    script:
        "../scripts/plot_scenario_comparison.py"
