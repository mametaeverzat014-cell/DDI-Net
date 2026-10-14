"""Typed contract of the DDI-Net 3.0 evidence API.

Three families of object, kept in separate fields on purpose so a client can
never render one as another:

* ``EvidenceRecord``  — a source states that the two drugs interact.
* ``AnnotationRef`` / ``MechanismFinding`` — curated facts about each drug
  separately, and a configuration of those facts that *could* explain an
  interaction. A finding is a hypothesis built from documented parts; it is not
  interaction evidence.
* ``ModelBlock`` — the BIO-GINE research score and the diagnostics that say how
  much that score can be trusted for this particular pair.

No field carries a severity grade invented here. ``source_severity`` is filled
only when a source supplies one in its own words, and none of the sources
currently integrated does.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Bi(BaseModel):
    """A user-facing string in both interface languages. Russian is the default."""

    ru: str
    en: str


# ---------------------------------------------------------------- drugs ----
class DrugOut(BaseModel):
    id: str = Field(description="DrugBank ID — the canonical identifier.")
    inn: str | None = Field(None, description="DrugCentral INN joined on InChIKey; null if unmatched.")
    name_ru: str | None = Field(None, description="Rule-based transliteration of the INN. A UI label, not sourced data.")
    name_ru_is_transliteration: bool = True
    groups: str = ""
    drug_type: str = ""
    query: str | None = None
    matched_on: str | None = None


class ResolveCandidate(BaseModel):
    id: str
    inn: str | None
    name_ru: str | None


class ResolveOut(BaseModel):
    query: str
    status: Literal["resolved", "suggestions", "multiple_ingredients", "not_in_universe", "not_found", "invalid"]
    drug: DrugOut | None = None
    candidates: list[ResolveCandidate] = []
    note: str | None = None
    rxnorm: dict | None = Field(None, description="RxNorm concept(s) used, when the external source resolved the name.")


# ------------------------------------------------------------- evidence ----
class EvidenceCategory(str, Enum):
    LABEL_CONTRAINDICATION = "label_contraindication"
    LABEL_BOXED_WARNING = "label_boxed_warning"
    LABEL_WARNING_OR_INTERACTION = "label_warning_or_interaction"
    DATABASE_INTERACTION_RECORD = "database_interaction_record"
    #: A label sentence names the partner drug in wording that reports *no*
    #: relevant effect under studied conditions. Kept, never read as reassurance.
    LABEL_MENTION_NO_EFFECT_REPORTED = "label_mention_no_effect_reported"


class EvidenceRecord(BaseModel):
    id: str
    category: EvidenceCategory
    source_name: str
    source_version: str | None = None
    source_record_id: str | None = None
    source_url: str | None = None
    retrieval_url: str | None = None
    original_identifiers: dict[str, str] = {}
    statement: str = Field(description="The source's own words: a verbatim excerpt or the source's sentence template with the drug names filled in.")
    statement_origin: Literal["verbatim_excerpt", "source_template_filled", "source_template_direction_neutral"]
    source_template: str | None = None
    direction: Literal["symmetric", "as_exported_verified", "not_verified", "not_applicable"] = "not_applicable"
    direction_check: dict | None = Field(None, description="Measured agreement of the export's drug order with documented roles for this interaction type.")
    statement_ru: str | None = Field(None, description="Project translation of the source statement. Not the source's words; the English statement is.")
    section: str | None = Field(None, description="Label section the excerpt comes from, as named in the source.")
    drug1_id: str | None = Field(None, description="Drug in the source's '#Drug1' / label-owner position.")
    drug2_id: str | None = Field(None, description="Drug in the source's '#Drug2' / mentioned position.")
    retrieved_at: str
    license: str | None = None
    source_severity: str | None = Field(None, description="Severity in the source's own terms. None: the source gives none.")
    qualifiers: list[str] = []


class Conflict(BaseModel):
    record_ids: list[str]
    affected_drug_id: str
    description: Bi


# ------------------------------------------------------------ mechanism ----
class ProteinOut(BaseModel):
    uniprot: str
    gene: str
    name: str
    organism: str = ""
    family: str
    plain: Bi = Field(description="Project-written description of the protein family. General background, not a sourced statement about this pair.")


class AnnotationRef(BaseModel):
    id: str
    drug_id: str
    uniprot: str
    relation: Literal["target", "enzyme", "transporter", "carrier"]
    roles: list[str]
    raw_action: str
    source_name: str
    source_version: str
    known_action: str | None = None
    pmids: list[str] = []
    organism: str = ""
    retrieved_at: str


class MechanismFinding(BaseModel):
    id: str
    protein: ProteinOut
    relation: Literal["target", "enzyme", "transporter", "carrier"]
    pattern: Literal[
        "inhibitor_substrate", "inducer_substrate", "shared_substrate",
        "opposing_target_action", "same_direction_target_action", "shared_annotation",
    ]
    actor_drug_id: str | None = None
    affected_drug_id: str | None = None
    roles_a: list[str]
    roles_b: list[str]
    annotation_ids: list[str]
    consistent_with_records: list[str] = []
    status: Literal["hypothesis"] = "hypothesis"


class SharedPathway(BaseModel):
    id: str
    name: str
    n_proteins_in_pathway: int
    via_a: list[str]
    via_b: list[str]
    source: str = "Reactome (UniProt2Reactome, all levels)"


class MechanismBlock(BaseModel):
    findings: list[MechanismFinding]
    shared_pathways: list[SharedPathway]
    n_shared_pathways_total: int
    annotations: dict[str, AnnotationRef]
    coverage: dict[str, dict[str, int]]
    note: Bi


# ---------------------------------------------------------------- model ----
class MeasuredPerformance(BaseModel):
    view: str
    metric: str
    mean: float
    sd: float
    n_seeds: int
    source: str


class ModelBlock(BaseModel):
    available: bool
    unavailable_reason: str | None = None
    model: str = "BIO-GINE M4"
    checkpoint: str = "bd45f84e3c1b2c33"
    raw_model_score: float | None = None
    calibrated_model_score: float | None = None
    band: Literal["high", "moderate", "low"] | None = None
    regime: Literal["S1", "S2", "S3"]
    split_a: str
    split_b: str
    training_label_seen: bool
    reliability: Literal["training_label_seen", "not_evaluated_regime", "held_out_like"]
    measured_performance: list[MeasuredPerformance] = []
    biology_available_a: bool
    biology_available_b: bool
    notes: list[Bi] = []
    abstain: bool = Field(False, description="True when the score should not be read as a signal for this pair.")


# ----------------------------------------------------------- explanation ----
class Statement(BaseModel):
    kind: Literal["documented", "annotation", "hypothesis", "model", "missing", "caveat"]
    text: Bi
    refs: list[str] = []


class Section(BaseModel):
    id: Literal["known", "why", "ai", "certainty", "missing"]
    title: Bi
    statements: list[Statement]


class Explanation(BaseModel):
    method: str = "deterministic templates over retrieved records; no language model"
    sections: list[Section]


# ---------------------------------------------------------------- report ----
class EvidenceStatus(str, Enum):
    CONTRAINDICATION_IN_LABEL = "contraindication_in_label"
    WARNING_IN_LABEL = "warning_in_label"
    DOCUMENTED_NO_SEVERITY = "documented_no_severity"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    MODEL_SIGNAL_ONLY = "model_signal_only"
    NO_DOCUMENTED_EVIDENCE_FOUND = "no_documented_evidence_found"


class SourceCheck(BaseModel):
    source: str
    status: Literal["ok", "no_match", "unavailable", "disabled", "not_applicable"]
    detail: str | None = None


class PairReport(BaseModel):
    report_version: Literal["3.0"] = "3.0"
    drug_a: DrugOut
    drug_b: DrugOut
    evidence_status: EvidenceStatus
    evidence_status_label: Bi
    evidence: list[EvidenceRecord]
    conflicts: list[Conflict]
    mechanism: MechanismBlock
    model: ModelBlock
    explanation: Explanation
    sources_checked: list[SourceCheck]
    limitations: list[Bi]
    disclaimer: Bi
    generated_at: str


# ------------------------------------------------------------ multi-drug ----
class MultiPair(BaseModel):
    drug_a: str
    drug_b: str
    evidence_status: EvidenceStatus
    n_database_records: int
    n_label_records: int
    n_mechanism_hypotheses: int
    calibrated_model_score: float | None
    regime: str
    training_label_seen: bool
    needs_review: bool
    review_reasons: list[str]


class MultiReport(BaseModel):
    report_version: Literal["3.0"] = "3.0"
    drugs: list[DrugOut]
    pairs: list[MultiPair]
    sources_checked: list[SourceCheck]
    scope_note: Bi
    disclaimer: Bi
    generated_at: str


# --------------------------------------------------------- mechanism graph ----
class GraphNode(BaseModel):
    id: str
    kind: Literal["drug", "protein", "pathway"]
    label: str
    side: Literal["a", "b", "shared", "pathway"]
    detail: dict = {}


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: Literal["annotation", "pathway_membership", "documented_interaction", "model_reliance"]
    established: bool
    detail: dict = {}


class MechanismGraph(BaseModel):
    drug_a: str
    drug_b: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: dict[str, int]
    legend: dict[str, Bi]
