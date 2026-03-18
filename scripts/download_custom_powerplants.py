# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Contributors to PyPSA-Earth
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Download custom power plant dataset for Zambia.

This script retrieves a curated power plant dataset from Zenodo
and stores it in the local ``data`` directory for use in PyPSA-Earth workflows.

The dataset is hosted on Zenodo Sandbox:
https://sandbox.zenodo.org/records/471583

The following file is downloaded:

- ``custom_powerplants.csv``:
    A curated and updated database of power plants in Zambia, based on
    national and regional sources, used to improve model accuracy.

This dataset is used to:

- Replace or default PyPSA-Earth power plant data
The script is triggered by the Snakemake rule
``download_custom_powerplants`` when enabled in the configuration file.
**Relevant Settings**
.. code:: yaml

    validation:
      custom_powerplants:
        download_data: true

**Outputs**

- ``data/custom_powerplants.csv``

"""
from pathlib import Path

import requests

params = snakemake.params
output = snakemake.output[0]

Path("data").mkdir(exist_ok=True)

r = requests.get(params.url)
r.raise_for_status()

with open(output, "wb") as f:
    f.write(r.content)
