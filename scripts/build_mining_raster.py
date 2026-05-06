# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Contributors to PyPSA-Earth
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from utility_custom_features import build_mining_raster, load_mining_data

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    provincial_demand, mining_polygons = load_mining_data(
        snakemake.input.provincial_demand,
        snakemake.input.mining_polygons,
    )

    os.makedirs(os.path.dirname(snakemake.output.mining_raster), exist_ok=True)

    build_mining_raster(
        provincial_demand=provincial_demand,
        mining_polygons=mining_polygons,
        output_path=snakemake.output.mining_raster,
        area_crs=snakemake.params.area_crs,
    )
