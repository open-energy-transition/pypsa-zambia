# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Generate a production Zenodo API token at Zenodo applications settings with permissions for record creation, file upload and publication.

1. Setup Zenodo API

My Account -> Applications

See https://developers.zenodo.org/#authentication
NB Zenodo.Sandbox

NB2 No quotes please!

[sandbox]
access_token = your-sandbox-token

[production]
access_token = your-production-token

Alternatively, you can export a token in your terminal directly:

```bash
export ZENODO_ACCESS_TOKEN="your-production-token"
```
or

```bash
export SANDBOX_ACCESS_TOKEN="your-production-token"
```

2. Create config

See an example

3. Run upload

Example:
```
# testing
python scripts/data_upload/zenodo_upload.py scripts/data_upload/config.upload.cutout-era5-tutorial.yaml

or 

# production upload
pypsa-zambia % python scripts/data_upload/zenodo_upload.py scripts/data_upload/config.upload.cutout-era5-tutorial.yaml --production --upload

```


"""
import argparse
import configparser
import os
from pathlib import Path

import requests
import yaml

TOKEN_FL = "scripts/data_upload/.zenodo.ini"

# It is convenient to pass parameters through the command line
parser = argparse.ArgumentParser()
parser.add_argument("config", type=Path)
parser.add_argument("--production", action="store_true")
parser.add_argument("--upload", action="store_true")

args = parser.parse_args()

environment = "production" if args.production else "sandbox"
token_env = "ZENODO_ACCESS_TOKEN" if args.production else "SANDBOX_ACCESS_TOKEN"

# Zenodo token can be put into a configuration file
# or defined in the terminal as an environment variable
credentials = configparser.ConfigParser()
credentials.read(TOKEN_FL)

token = credentials.get(environment, "access_token", fallback=None)
token = token or os.getenv(token_env)

if not token:
    raise RuntimeError(
        f"Zenodo {environment} access token is not configured. "
        f"Provide it in {TOKEN_FL} or export {token_env}."
    )

base_url = (
    "https://zenodo.org/api" if args.production else "https://sandbox.zenodo.org/api"
)

headers = {"Authorization": f"Bearer {token}"}

with args.config.open() as f:
    config = yaml.safe_load(f)

record_id = config.get("zenodo", {}).get(f"{environment}_record_id")

if not record_id and not args.upload:
    parser.error("No record ID provided. Use --upload to create a new record.")
if record_id and args.upload:
    parser.error("--upload is only supported for new records.")


# Existing and new uploads should be handled differently
# A record has been still published
if record_id:
    response = requests.get(
        f"{base_url}/records/{record_id}/draft",
        headers=headers,
        timeout=60,
    )

    if response.status_code == 404:
        # Open a published record for editing
        response = requests.get(
            f"{base_url}/records/{record_id}",
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()

        response = requests.post(
            response.json()["links"]["draft"],
            headers=headers,
            timeout=60,
        )

    response.raise_for_status()
    zenodo_draft = response.json()

    response = requests.put(
        zenodo_draft["links"]["self"],
        headers=headers,
        json={
            "metadata": config["metadata"],
            "access": config["access"],
        },
        timeout=60,
    )
    response.raise_for_status()

    print(f"Updated metadata: {record_id}")   

else:
    file_path = Path(config["file"])
    assert file_path.is_file(), f"File not found: {file_path}"

    response = requests.post(
        f"{base_url}/records",
        headers=headers,
        json={
            "metadata": config["metadata"],
            "access": config["access"],
            "files": {"enabled": True},
        },
        timeout=60,
    )

    response.raise_for_status()

    record_id = response.json()["id"]

    print(f"Created draft: {record_id}")
    print(f"Draft URL: {base_url}/records/{record_id}/draft")

if args.upload:
    response = requests.post(
        f"{base_url}/records/{record_id}/draft/files",
        headers=headers,
        json=[{"key": file_path.name}],
        timeout=60,
    )
    response.raise_for_status()
    
    file_info = response.json()["entries"][0]
    
    with file_path.open("rb") as f:
        response = requests.put(
            file_info["links"]["content"],
            headers={
                **headers,
                "Content-Type": "application/octet-stream",
            },
            data=f,
            timeout=3600,
        )
        response.raise_for_status()
    
    response = requests.post(
        file_info["links"]["commit"],
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()
    
    print(f"Draft URL: {base_url.removesuffix('/api')}/uploads/{record_id}")


# # # Technically, it is possible to publish a record automatically
# # if args.publish:
# #     response = requests.post(
# #         f"{base_url}/records/{record_id}/draft/actions/publish",
# #         headers=headers,
# #         timeout=120,
# #     )
# #     response.raise_for_status()

# #     print(f"Published: {response.json()['links']['self_html']}")
# # else:
# #     print("Draft saved. Publication skipped.")
