"""DDI-Net 3.0 evidence layer.

Separates three kinds of statement that the earlier API returned side by side
without saying how they differ:

* documented interaction evidence — a source says these two drugs interact
  (DrugBank records shipped with the frozen dataset; official labels when the
  label source is reachable);
* biological annotations — curated facts about each drug on its own (which
  protein it is a substrate, inhibitor or inducer of), from which a mechanism
  can at most be *hypothesised*;
* the BIO-GINE research score — a model's resemblance judgement, never
  evidence of an interaction and never a probability of harm.

Every module here runs on the standard library (plus numpy where the model is
involved), because the lean runtime image carries nothing else. The artifact
this package reads is built by ``python -m serving.evidence.build`` from files
committed to the repository.
"""
