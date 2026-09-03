<!--
SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors

SPDX-License-Identifier: CC-BY-4.0
-->

# Running from an Offline Package (For End Users)

This page is for anyone who has been given an offline package of a PyPSA model — for example on a USB drive at a workshop — and wants to install and run it on their own computer, with no internet connection required.

!!! note
    If you are the one preparing such a package for others, see [Preparing an Offline Package](offline-setup-prepare.md) instead.

## What you should have received

Three items, usually together in one folder or on a USB drive:

- **The model project folder** — the code, the input data it needs, and usually one finished result you can compare your own run against
- **A setup file** — this is the one you will run
- **A second, larger file** used automatically by the setup file — it needs to stay in the same folder as the setup file, but you never run it yourself

If you are missing any of these, check with whoever gave you the package.

## Step 1: Copy everything to your computer

Copy the project folder and both setup files onto your own computer's hard disk. Do not run them directly from a USB drive — USB drives are slow, and the installation step needs a permanent location to work with.

## Step 2: Run the setup file

On Windows, this needs the `-ExecutionPolicy Bypass` option, because Windows often blocks running setup files it does not recognise. This does not change any settings permanently — it only applies to this one command.

```powershell
powershell -ExecutionPolicy Bypass -File "setup.ps1" -o "install-folder"
```

Replace `setup.ps1` with the actual name of the setup file you were given, and `install-folder` with wherever you want the software installed (for example, a folder in your own user directory).

## Step 3: Activate the environment

Every time you want to use the model, turn the environment on ("activate" it) using the file the setup step created. On Windows, this should be done from **Command Prompt**, not PowerShell:

```
install-folder\activate.bat
```

!!! warning "Use Command Prompt, not PowerShell, on Windows"
    PowerShell can technically run `activate.bat`, but the environment variable changes it makes do not carry over into the calling PowerShell session, so the environment would not actually be active afterwards. Command Prompt does not have this limitation.

## Step 4: Run the model

Go to the project folder, then do a dry run first to confirm nothing tries to download or retrieve anything:

```
cd project-folder
snakemake -j 1 solve_all_networks -n
```

If the dry run does not try to download or retrieve any data, run the model for real:

```
snakemake -j 1 solve_all_networks
```

## If something goes wrong

!!! tip "Error mentioning \"DLL load failed\""
    This kind of error is usually caused by other software already on your computer conflicting with the model's environment. Offline packages normally include an automatic fix for this that runs whenever you activate the environment (Step 3), so you should not need to do anything extra. If you still see this error after activating, let whoever gave you the package know exactly what the error said — the fix can usually be extended to cover it.

!!! tip "The dry run wants to download something"
    This means some data the model needs was not included in the package you were given. You will need an internet connection for that specific step, or ask whoever prepared the package to include the missing data.
