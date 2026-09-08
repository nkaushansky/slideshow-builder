# curate

The Python side: ingest, index, validate, identify, select, review sheets, handoff, apply, reconcile. Each stage is a command over the project folder described in `references/01-stages.md`, reads `project/config.toml`, and refuses to run without it.

Status: the scripts from the first run are being ported here. Until a stage exists as a command, Claude implements it from the references before continuing, and records that in the project brief's changelog.

Planned layout:

```
curate/
  common.py            config loader and project paths
  config.example.toml  copy to project/config.toml; the intake fills it
  requirements.txt     pinned dependencies
  setup.py             creates the environment, installs, fetches models, reports versions
  stages/              one module per stage
  models/              downloaded by setup; see models/README.md for licenses
```
