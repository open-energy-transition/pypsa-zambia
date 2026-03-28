
# General design

The workflow is configured using configuraiton files. To ensure reproducibility, all the config files are git-tracked. In particular, `config.yaml` is not included into `Snakefile` and wouldn't have effect on the worflow.

## Particular configurations

- `config.default.yaml` default values of all the parameters over which all specific configarutions are applied

- parameters used to build a full-scale cutout

- paramaters user to build a tutorial cutout

## Validation

### Validation assumptions

### Validation runs

- `validation_dispatch_zambia.yaml` contains definitions for a dispatch run reproducing behaviour of the national power system in a reference year from the past

### Validation routine



