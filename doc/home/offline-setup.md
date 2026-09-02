<!--
SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors

SPDX-License-Identifier: CC-BY-4.0
-->

# Offline Setup (No Internet Required)

PyPSA-Earth and related country models (such as PyPSA-Zambia) are increasingly managed with [pixi](https://pixi.prefix.dev/latest/), which installs Python and every package a model needs into one self-contained environment. This page explains how to package a pixi environment, together with a model's input data, so that someone without an internet connection can install it and run the model on their own computer.

This is useful for workshops, field visits, or any setting where participants cannot rely on downloading packages and data on the spot. The steps below apply to any pixi-based PyPSA model; PyPSA-Zambia is used as the running example.

!!! note
    This page assumes you have already read [Installation with pixi](installation.md#installation-with-pixi-alternative). The steps here build on top of a normal pixi installation to make it portable.

## What you end up with

A folder (or USB drive) containing three things: the model's code and data, a single setup file that installs the software, and one small helper file that the setup file needs alongside it. Someone can copy this to their computer and be running the model within a few minutes, without needing to download anything.

## What you need before starting

A computer with an internet connection, where you will prepare the package. This is referred to below as the **preparation computer** — it is not the computer the model will eventually run on.

## Step 1: Install pixi

On the preparation computer:

=== "Linux / macOS"

    ```bash
    curl -fsSL https://pixi.sh/install.sh | sh
    ```

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy Bypass -c "irm -useb https://pixi.sh/install.ps1 | iex"
    ```

This step, and the ones that follow, need an internet connection — the goal is to prepare something that someone else can later use without one.

## Step 2: Make sure the project is set up for pixi

A pixi-based project has two files describing its software requirements: `pixi.toml` (what is needed) and `pixi.lock` (the exact versions to use, so everyone gets the same setup). If a project only has an older-style conda `environment.yaml` instead, pixi can convert it:

```bash
pixi init --import envs/environment.yaml .
```

## Step 3: Build the environment

From inside the project folder:

```bash
pixi install
```

This downloads and installs everything the model needs — Python itself, and every package the model depends on, all pinned to the exact versions the project expects.

## Step 4: Check it actually works

Before packaging anything, test that the environment works, especially the packages that handle maps and geographic data (`rasterio`, `fiona`, `pyproj`) — these are the ones most likely to run into trouble on Windows:

```bash
pixi run python -c "import rasterio, fiona, pyproj; print(rasterio.__version__)"
```

!!! warning "Watch for DLL conflicts on Windows"
    Other mapping-related software that may already be installed on a Windows computer (GIS tools, some scientific software, even some programming-language toolchains) can install their own copies of the same underlying files that these packages rely on. Windows may pick up the wrong copy, causing a confusing `DLL load failed` error even though the environment itself was installed correctly. This is a Windows quirk, not a bug in the model or in pixi. Step 7 below builds in an automatic fix so end users never need to diagnose this themselves.

## Step 5: Install the packaging tool

```bash
pixi global install pixi-pack
```

[pixi-pack](https://github.com/Quantco/pixi-pack) is a companion tool to pixi. Its job is to take an environment you have already built and turn it into something that can be moved to a different computer.

## Step 6: Package the environment as one self-installing file

```bash
pixi-pack path/to/project -e default -p win-64 --create-executable -o setup-environment.ps1
```

!!! danger "Always include `--create-executable`"
    Without it, `pixi-pack` produces a bundle of raw package files that still needs a separate `pixi-unpack` tool to assemble into a working environment — and that tool would not be available on a computer with no internet, which defeats the purpose. With `--create-executable`, everything needed is combined into a single file that installs itself when run. This is the single most important setting in the whole process.

Adjust `-p` to the target platform (`win-64`, `linux-64`, `osx-64`, `osx-arm64`).

## Step 7: Build in a fix for the Windows DLL conflict

Rather than relying on each person to notice and fix the DLL conflict from Step 4 themselves, wrap the setup file from Step 6 inside a small extra script that does two things automatically:

1. Runs the real setup file from Step 6, to install the environment.
2. Adds a short check to the environment's own startup file, so that every time someone activates the environment, it automatically looks for the specific files known to cause conflicts and ignores any other program's copy of them.

This means the person running the model later does not need to know anything about DLL conflicts — it is handled for them, automatically, every time.

## Step 8: Package the model's data, not just the software

The environment on its own is not enough — the model also needs its input data, which it would normally download the first time it runs. To prepare this:

1. Run the model once normally, with an internet connection, so it downloads everything it needs and produces a finished result.
2. Remove the folders the model creates and rebuilds automatically as it runs (for example `resources/`, `networks/`, `benchmarks/`, `logs/`, `.snakemake/`). These are working files, not original data — the model will recreate them by itself.
3. Keep the original input data, and keep one finished result as a reference, so whoever runs it later can check that their own result looks similar.

## Step 9: Put it all together

Three things go into the final package (for example, onto a USB drive):

- **The model project folder** — code, input data, and one reference result
- **The wrapper setup file** (from Step 7) — this is the one people will actually run
- **The self-installing environment file** (from Step 6) — used automatically by the wrapper; it needs to stay in the same folder, but is not run directly

## Step 10: What the end user does

1. Copy the project folder and both setup files onto their own computer's hard disk — do not run directly from a USB drive, since USB drives are slow and the installation step needs a permanent location to work with.
2. Run the wrapper setup file. On Windows, this needs the `-ExecutionPolicy Bypass` option, because Windows often blocks running setup files it does not recognise:

    ```powershell
    powershell -ExecutionPolicy Bypass -File "setup.ps1" -o "install-folder"
    ```

3. Activate the environment using the file it created. On Windows, this should be done from **Command Prompt**, not PowerShell:

    ```
    install-folder\activate.bat
    ```

4. Run the model as usual from inside the project folder. Do a dry run first (for example `snakemake -j 1 solve_all_networks -n`) to confirm nothing tries to download or retrieve anything — if it does, some data was missed when the package was prepared.

!!! warning "Use Command Prompt, not PowerShell, to activate on Windows"
    PowerShell can technically run `activate.bat`, but the environment variable changes it makes do not carry over into the calling PowerShell session, so the environment would not actually be active afterwards. Command Prompt does not have this limitation.

## Other things worth knowing

- Install the environment somewhere the user's account can always write to (their own user folder), rather than a system-wide location — this way it also works on computers with restricted permissions.