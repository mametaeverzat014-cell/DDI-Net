# Archived: pre-grid smoke artefacts

`smoke_resume_demo_epoch_schema.csv` is the SMOKE_ONLY row from the phase-2
resume demonstration. It was produced by the epoch-denominated trainer, so it
carries `best_epoch`/`epochs_run` columns that the step-denominated grid schema
does not have.

Moved out of `reports/v2_grid/` so the grid's results table contains grid runs
and nothing else. Not deleted: it is the evidence that resume works.
