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
    also_in_sections: list[str] = Field([], description="Other sections of the same label containing the same sentence. The excerpt is listed once; repeated text in one document is not separate evidence.")
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


class ModalityReliance(BaseModel):
    """How much the frozen model's score moves when one branch is zeroed.

    Same post-hoc perturbation as the frozen V2 analysis, reproduced for any
    pair and checked against that analysis on all of its test pairs. It
    describes the model's reliance, not a biological cause.
    """

    baseline_raw: float
    without_molecular_raw: float
    without_protein_raw: float
    without_pathway_raw: float
    delta_molecular: float
    delta_protein: float
    delta_pathway: float
    method: str
    validation: dict
    interpretation: Bi


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
    modality_reliance: ModalityReliance | None = None


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


# ------------------------------------------------------ clinical outcomes ----
OutcomeEvidenceStatus = Literal["documented", "mechanistically_supported", "hypothesized"]
EffectLevel = Literal["clinical_outcome", "pharmacodynamic_effect", "pharmacokinetic_change",
                      "reduced_effectiveness", "unspecified_adverse"]
SeriousnessClass = Literal["documented_contraindication", "explicit_serious_warning",
                           "documented_no_standard_severity", "not_applicable"]
LinkProvenance = Literal["documented", "verified_annotation", "plausible_unconfirmed", "unavailable"]


class OutcomeSupport(BaseModel):
    """One source statement supporting an outcome, in the source's own words."""

    evidence_record_id: str | None = Field(None, description="The EvidenceRecord this support was read from; None for annotation-only support.")
    source_type: Literal["fda_label", "drugbank_tdc", "annotation"]
    source_name: str
    source_document_id: str | None = Field(None, description="SPL set ID for a label; the DrugBank record key for the database.")
    source_url: str | None = None
    section: str | None = None
    excerpt: str = Field(description="Verbatim: the label sentence, or DrugBank's template as stored in the record. Never paraphrased.")
    matched_terms: list[str] = []
    extraction_method: str = Field(description="Versioned deterministic rule that produced this support, e.g. 'drugbank_type_map/v1:type=66'.")
    direction: Literal["symmetric", "as_exported_verified", "not_verified", "from_annotation", "as_stated_in_excerpt", "not_applicable"]
    affected_drug_id: str | None = Field(None, description="Only when the direction is verified, symmetric-irrelevant, or stated by annotations.")
    source_seriousness: str | None = Field(None, description="Seriousness in the source's own terms (section or quoted wording); None when the source gives none.")
    retrieved_at: str | None = None
    qualifiers: list[str] = []


class ClinicalOutcome(BaseModel):
    id: str = Field(description="Stable: outcome:<drug ids sorted>:<category>:<effect>.")
    drug_a: str
    drug_b: str
    category: str
    effect: str
    effect_level: EffectLevel
    label: Bi = Field(description="What the sources state, in plain words. Project wording; the excerpts are the evidence.")
    explanation: Bi
    evidence_status: OutcomeEvidenceStatus
    supports: list[OutcomeSupport]
    n_source_documents: int = Field(description="Distinct source documents behind the outcome. Several excerpts of one document are one source.")
    affected_drug_id: str | None = None
    direction_note: Bi
    seriousness: SeriousnessClass
    seriousness_basis: Bi
    evidence_strength: Literal["official_label_statement", "database_standard_sentence", "label_and_database", "annotation_hypothesis"]
    evidence_strength_text: Bi
    extraction_note: Bi | None = Field(None, description="Measured extraction quality on the pilot set, when one exists for this method. Never a probability that the outcome occurs.")
    limitations: list[Bi] = []
    research_only: bool = Field(False, description="True for hypotheses without a documented outcome: shown in Research mode only.")


class ChainLink(BaseModel):
    source: str
    target: str
    relation: str
    provenance: LinkProvenance
    text: Bi
    refs: list[str] = []


class ChainNode(BaseModel):
    id: str
    kind: Literal["drug", "protein", "effect", "outcome"]
    label: Bi
    ref: str | None = None


class MechanismChain(BaseModel):
    id: str
    nodes: list[ChainNode]
    links: list[ChainLink]
    outcome_ids: list[str] = []
    research_only: bool
    summary: Bi


class OutcomeReport(BaseModel):
    method: str = "deterministic: DrugBank type map v1 + label outcome lexicon v1; no language model"
    interaction_status: Literal["documented_interaction", "documented_outcome_unclear", "research_prediction_only",
                                "insufficient_evidence", "source_unavailable"]
    interaction_status_label: Bi
    interaction_status_hint: Bi
    outcomes: list[ClinicalOutcome]
    chains: list[MechanismChain]
    seriousness: SeriousnessClass
    seriousness_text: Bi
    coverage: list[Bi] = Field(description="Which sources were consulted, what they can and cannot say.")
    no_outcome_text: Bi | None = Field(None, description="Set when no supported outcome could be identified; shown instead of an empty list.")
    mechanism_without_outcome_text: Bi | None = None
    individual_limit: Bi


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
    outcomes: OutcomeReport | None = Field(None, description="Clinical outcome block. Absent from API versions before the outcome engine.")


# ------------------------------------------------------------ multi-drug ----
class MultiPair(BaseModel):
    drug_a: str
    drug_b: str
    evidence_status: EvidenceStatus
    n_database_records: int
    n_label_records: int = Field(description="Distinct label excerpts (a sentence repeated across sections of one label counts once).")
    n_label_documents: int | None = Field(None, description="Distinct FDA label documents (SPL set IDs) the excerpts come from. Absent from older APIs.")
    n_mechanism_hypotheses: int
    calibrated_model_score: float | None
    regime: str
    training_label_seen: bool
    needs_review: bool
    review_reasons: list[str]
    interaction_status: str | None = Field(None, description="Outcome-engine pair status; absent from older APIs.")
    outcome_categories: list[str] = Field([], description="Categories of documented (or mechanistically supported) outcomes for the pair.")
    outcome_ids: list[str] = []
    seriousness: str | None = None


class MultiReport(BaseModel):
    report_version: Literal["3.0"] = "3.0"
    drugs: list[DrugOut]
    pairs: list[MultiPair]
    sources_checked: list[SourceCheck]
    scope_note: Bi
    disclaimer: Bi
    generated_at: str
    shared_outcome_categories: dict[str, list[list[str]]] = Field({}, description="Documented outcome category -> the pairs it was documented for. Pairwise only: no additive or three-way inference.")
    outcome_categories: dict[str, Bi] = Field({}, description="Labels of the categories used.")


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
    directed: bool = Field(True, description="False when source/target order carries no meaning (e.g. an interaction record whose drug order is not verified).")
    detail: dict = {}


class MechanismGraph(BaseModel):
    drug_a: str
    drug_b: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: dict[str, int]
    legend: dict[str, Bi]
