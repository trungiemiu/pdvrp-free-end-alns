# Data

This directory contains input instances and CSV manifests consumed by the
experiment runners.

- `instances/`: original project instances.
- `instances_extended/`: generated time-window-free benchmark derivatives.
- `pdptw/`: source benchmark material used to derive the extended instances.
- `exact_validation/`: deterministic small instances for MILP validation.
- `instances_manifest.csv`: initial benchmark manifest.
- `broader_instances_manifest.csv`: conference-scale benchmark manifest.

Keep raw/source data separate from generated solver results. All archives,
metrics, tables, and plots belong under `outputs/`.
