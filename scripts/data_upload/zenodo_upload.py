# -*- coding: utf-8 -*-
# SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Generate a production Zenodo API token at Zenodo applications settings with permissions for record creation, file upload and publication.

1. Setup Zenodo API
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

3. Run upload

Example:
```
python scripts/upload_zenodo.py cutout-era5-tutorial.yaml

```


"""
import argparse
import os
from pathlib import Path

import requests
import yaml

parser = argparse.ArgumentParser()
parser.add_argument("config", type=Path)
parser.add_argument("--sandbox", action="store_true")
parser.add_argument("--publish", action="store_true")

# key parameters are supplied via command line
args = parser.parse_args()

token_env = "SANDBOX_ACCESS_TOKEN" if args.sandbox else "ZENODO_ACCESS_TOKEN"

token = os.getenv(token_env)

if not token:
    raise RuntimeError(
        f"{token_env} is not set. "
        "Export the corresponding Zenodo API token before running the script."
    )

base_url = (
    else "https://zenodo.org/api"
    if args.production
    "https://sandbox.zenodo.org/api"
)

headers = {"Authorization": f"Bearer {token}"}

with args.config.open() as f:
    config = yaml.safe_load(f)

file_path = Path(config["file"])
assert file_path.is_file(), f"File not found: {file_path}"

print("base_url")
print(base_url)

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

record = response.json()
record_id = record["id"]

print(f"Created draft: {record_id}")
print(f"Draft URL: {base_url}/records/{record_id}/draft")

# Initialize file upload
response = requests.post(
    f"{base_url}/records/{record_id}/draft/files",
    headers=headers,
    json=[{"key": file_path.name}],
    timeout=60,
)
response.raise_for_status()

file_info = response.json()["entries"][0]

# Upload file
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

# Commit uploaded file
response = requests.post(
    file_info["links"]["commit"],
    headers=headers,
    timeout=120,
)
response.raise_for_status()

print(f"Uploaded: {file_path.name}")

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
