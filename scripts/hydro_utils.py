# SPDX-FileCopyrightText: PyPSA-Earth and PyPSA-Eur Authors
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Shared utilities for hydropower modelling."""

import numpy as np
import pandas as pd


def resolve_hydraulic_heads(
    plants: pd.DataFrame,
    legacy_column: str = "damheight_m",
    default: float | None = None,
) -> pd.Series:
    """
    Resolve effective hydraulic heads in metres.

    Explicit hydraulic heads take precedence over legacy dam heights.
    Missing explicit values fall back to legacy dam heights.
    An optional default is used for missing or zero legacy values.
    Explicitly supplied invalid hydraulic heads raise an error.
    """
    heads = pd.to_numeric(
        plants.get(
            legacy_column,
            pd.Series(np.nan, index=plants.index),
        ),
        errors="coerce",
    ).astype(float)

    if default is not None:
        heads = heads.replace(0, np.nan).fillna(default)

    if "hydraulic_head_m" in plants.columns:
        raw = plants["hydraulic_head_m"]

        supplied = raw.notna() & raw.astype(str).str.strip().ne("")

        explicit = pd.to_numeric(raw, errors="coerce")

        invalid = supplied & (explicit.isna() | ~np.isfinite(explicit) | explicit.le(0))

        if invalid.any():
            raise ValueError(
                "Invalid explicit hydraulic heads for plants: "
                + ", ".join(map(str, plants.index[invalid]))
            )

        heads.loc[supplied] = explicit.loc[supplied]

    invalid = heads.isna() | ~np.isfinite(heads) | heads.le(0)

    if invalid.any():
        raise ValueError(
            "Missing or invalid hydraulic heads for plants: "
            + ", ".join(map(str, plants.index[invalid]))
        )

    return heads.rename("hydraulic_head_m")
