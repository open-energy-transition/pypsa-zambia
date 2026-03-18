# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText: Contributors to PyPSA-Earth
# SPDX-FileCopyrightText: Open Energy Transition gGmbH
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
This script retrieves cross-border interconnection data from Zenodo
and stores it in the local ``data`` directory for use in validation workflows.

The dataset is hosted on Zenodo Sandbox:
https://sandbox.zenodo.org/records/471583

The following files are downloaded:

- ``zm_substations.csv``:
    Cross-border interconnection substations representing import/export nodes
    between Zambia and neighbouring countries.

- ``sapp_links.csv``:
    Cross-border transmission links (interconnectors) defining the topology
    and capacity of connections between Zambia and the SAPP region.

- ``sapp_countries.csv``:
    Country-level metadata used for modelling electricity imports and exports.

These datasets are used to:

- Represent cross-border electricity trade
The script is triggered by the Snakemake rule
``download_interconnection_data`` when enabled in the configuration file.
**Relevant Settings**

.. code:: yaml

    validation:
      interconnectors:
        download_data: true

**Outputs**

- ``data/zm_substations.csv``
- ``data/sapp_links.csv``
- ``data/sapp_countries.csv``

"""
from pathlib import Path

import requests

# Snakemake inputs
params = snakemake.params
outputs = snakemake.output

Path("data").mkdir(exist_ok=True)


def download(url, path):
    r = requests.get(url)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)


download(params.substations_url, outputs.substations)
download(params.links_url, outputs.links)
download(params.countries_url, outputs.countries)
