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
- When resolving merge conflicts, it's worth to add a comment to facilitate reviews 

#### Git hand-ons

```
### setup remotes
$ git remote add upstream https://github.com/pypsa-meets-earth/$ pypsa-earth.git
$ git remote add origin https://github.com/open-energy-transition/pypsa-zambia.git
```

```
$ git remote -v
origin  git@github.com:open-energy-transition/pypsa-zambia.git (fetch)
origin  git@github.com:open-energy-transition/pypsa-zambia.git (push)
upstream        git@github.com:pypsa-meets-earth/pypsa-earth.git (fetch)
upstream        git@github.com:pypsa-meets-earth/pypsa-earth.git (push)

```

#### Merging procedure

1. Version 1
Based on our successful [experience]((https://github.com/open-energy-transition/pypsa-zambia/pull/109)) in this project:
```
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
2. Version 2
Follows up OET soft-fork guide. A detailed original soft-fork maintainance methodology is available in [this document](https://docs.google.com/document/d/1q5Ro2yVpK5lBG2JTIuVAWm5UjnC1-6Tb_SOEVAyruVI/edit?usp=sharing). To use it in this project, we have added a few modifications which are highlighted bellow.

!!! note
The original line (`git push --set-upstream origin upstream`) is a bit risky as it can lead to pushing into upstream and could be modified into

First, the upstream changes must be fetched and placed into a dedicated local branch `upstream_local_branch`. In contrast to the original soft-fork methodology, a name of this local branch allows for a clear distinction between `upstream` as a remote name and a name of a branch which is synchronised with the upstream.

```
### fetch latest changes
$ git fetch upstream --filter=blob:none
$ 
$ git checkout upstream/main
# remove an old branch if needed (assuming the old branch is upstream_local_branch)
$ git branch -d upstream_local_branch
$ git checkout -b upstream_local_branch
```

Everything is now ready to be pushed. To be on a safe side, check first where the origin repo is located with `git remote show origin`. Once confindent, push the changes.

```
git push --set-upstream origin upstream_local_branch 
```

## Linter
Use the following command to apply pre-commit changes locally:
```
run pre-commit --all
```
