<!--
SPDX-FileCopyrightText:  PyPSA-Earth and PyPSA-Eur Authors

SPDX-License-Identifier: CC-BY-4.0
-->

## Ecosystem
1. PyPSA-Zambia model
2. Google drive for local storage
3. Zenodo data repository
4. PyPSA-Zambia-Status validation workflow
5. Zambia-Data repository keeping data parsers

## Merging upstream

PyPSA-Zambia project is maintained as a soft-fork which means that it's kept in sync with PyPSA-Earth upstream while tailoring development according to the regional needs.

### Best practices

<!-- - [best practices](https://github.com/open-energy-transition/pypsa-zambia/pull/107#issuecomment-4080460981) from Open-TYNDP (many thanks @tgilon for sharing a list!) -->

- The project is a soft-fork of your upstream.
- Feature PRs are always squashed merged into main.
- Upstream is always merged using a merge commit. This is necessary to preserve the blame information from upstream.
- Merge upstream often to simplify the merges.
- Keep your project code separate from upstream code if possible (new files or functions). It helps with merging upstream.


Our successful [experience]((https://github.com/open-energy-transition/pypsa-zambia/pull/109)):
```
$ git remote -v
origin  git@github.com:open-energy-transition/pypsa-zambia.git (fetch)
origin  git@github.com:open-energy-transition/pypsa-zambia.git (push)
upstream        git@github.com:pypsa-meets-earth/pypsa-earth.git (fetch)
upstream        git@github.com:pypsa-meets-earth/pypsa-earth.git (push)
$ git checkout upstream/main  # DETACHED HEAD STATE
$ git switch -c upstream_main  # Create a new local branch following upstream main
$ git pull upstream main  # Pull down the latest commits from the upstream main branch
$ git checkout main  # Switch back to PyPSA-Zambia main branch
$ git pull origin main  # Update local main branch from PyPSA-Zambia remote
$ git checkout -b new_upstream_merge # Now create & checkout a branch from local main, to merge upstream INTO
$ git merge upstream_main  # Merges the branch tracking upstream/main into new_upstream_merge
# Resolve conflicts....
$ git push origin -u new_upstream_merge  # Push the branch to PyPSA-Zambia remote and open PR
```

A detailed general methodology is available in [this document](https://docs.google.com/document/d/1q5Ro2yVpK5lBG2JTIuVAWm5UjnC1-6Tb_SOEVAyruVI/edit?usp=sharing)

## Linter
Use the following command to apply pre-commit changes locally:
```
run pre-commit --all
```

## Backward compatibility
We are following the PyPSA-Earth methodology to verify the effect of the changes introduced into the model. The core idea of this methodology is based on using the objective value for test cases. The objective is sensitive to any changes in the model including both modelling and data-related changes, and keeping its value constant provides a good indication of the modelling workflow remains unchanged.

Technically, tracking the objective function is implemented using reference values of the objective function collected in `utils/obj_ref.csv` for all the test cases. Before merging any contribution, a check must be performed to ensure that the objective values have not undergone any unintended changes.

### Updating objective references
The objective function can change in an expected way in some cases. That includes, for example, updating input datasets or enhancement to the modelling methods. If that is the case, the reference objective values must be updated in `utils/obj_ref.csv`. This updating work can be done by following the steps below.

1. Complete the implementation of the changes and run the continius integration (CI) workflow. Currently, we are using GitHub Actions infrastructure for that.
2. In the output of CI, locate the `Summary` tab, scroll down to the `Artifacts` section and download `ref_objectives-ubuntu`.
3. Unzip the downloaded `ref_objectives-ubuntu.zip` file and copy and paste the objective values from it into `utils/obj_ref.csv`.
4. Create a feature branch, commit the changes, push to the remote repo and open a PR.


