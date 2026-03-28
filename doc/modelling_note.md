
# General design

The workflow is configured using configuraiton files. To ensure reproducibility, all the config files are git-tracked. In particular, `config.yaml` is not included into `Snakefile` and wouldn't have effect on the workflow.

## Particular configurations

The following yaml configuration files are available for different types of modelling runs. The folder `configs` stores definitions of the configuration files used in the worflow, and `pypsa-zambia` contains `config.default.yaml` and `config.tutorial.yaml`.

### Service configurations

A number of files in `configs` are service files used in each run:
- bundle_config.yaml defines parameters of the pre-compiled data bundles applicable on the global level, along with `data/versions.csv` file 
-  
- `powerplantmatching_config.yaml` is used to define default configuration of search in databases ported with `powerplantmatching` package
- `regions_definition_config.yaml` defines parameters needed to match geographic regions 
 
### Scenario configurations

The configuraiton following configuration 

#### Project root folder

The following universal files are available directly in `pypsa-zambia` folder:
- `config.default.yaml` contains default values of all the parameters which are used to fill any gaps in scenario-specific configuration files;
- `config.tutorial.yaml` defines a light-weight workflow which is used to run tutorial in upstream and is a convenient base to run tests. Currently, the testing worflow applies `config.zm_dispatch.yaml` over `config.tutorial.yaml` when running regional tests.

#### Configuration folder

`configs/scenarios` folder contains an example definition of a configuration file (not difectly relevant for the project).

Specific configuration files are available to build regional-specific cutouts for the country:
- `build_cutout_zambia_config.yaml` containts parameters used to build a full-scale cutout;
- `build_cutout_tutorial_zambia_config.yaml` contains parameters user to build a tutorial cutout.

`Customisation` section in the project README describes how to use those configurations when building a cutout for a year of interest.

To run a modeling scenario, a scenario-specific configuraiton file should be applied on top of the service configurations and `config.default.yaml`. Currently, the following configuration files are available:
- `validation_dispatch_zambia.yaml` defines a dispatch modelling run which aims to reproduce a national power system in a specific year in the past and is intended to be used for validation

## Validation

### Validation assumptions

### Validation runs

- `validation_dispatch_zambia.yaml` contains definitions for a dispatch run reproducing behaviour of the national power system in a reference year from the past

### Validation routine



