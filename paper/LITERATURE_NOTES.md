# LITERATURE_NOTES.md

Every reference cited in the manuscript, with what it actually shows, how it
relates to DDI-Net, how DDI-Net differs, and the specific manuscript claim it
supports. References that could not be verified against a publisher record were
not included in `references.bib` and are not used anywhere in the paper.

---

## Drug–drug interaction models

### Zitnik, Agrawal & Leskovec (2018) — Decagon
*Bioinformatics* 34(13):i457–i466. doi:10.1093/bioinformatics/bty294

**What it showed.** A multi-relational graph convolutional autoencoder over a
multimodal graph of drugs, proteins and side effects that predicts which of 964
polypharmacy side effects a drug pair will show. It demonstrated that adding
protein–protein and drug–protein edges to a drug interaction graph improves
prediction over drug-graph-only baselines.

**Relation to DDI-Net.** Decagon is the canonical demonstration that biological
context (proteins) helps DDI-type prediction, and is the intellectual ancestor
of DDI-Net's biological branch.

**How DDI-Net differs.** Decagon's model is transductive: every drug is a node
in the training graph, and the representation of a drug is built by
message-passing over its neighbours in that graph, including its known drug
interaction edges. A drug with no edges has no neighbourhood to aggregate.
DDI-Net's central question is what happens when that neighbourhood is removed,
so its evaluation holds out *drugs*, not pairs, and its biological
representation is built only from the drug's own annotations. DDI-Net also runs
falsification controls (shuffled biological identity, annotation-degree-only
baseline) that Decagon does not.

**Supports the claim.** §1.4 that drug-associated protein information is an
established source of signal for interaction prediction; §2.2 and §2.3
positioning of transductive multimodal graph methods.

---

### Ryu, Kim & Lee (2018) — DeepDDI
*PNAS* 115(18). doi:10.1073/pnas.1803294115

**What it showed.** A deep neural network over structural-similarity profiles
predicts 86 DrugBank DDI types with high reported accuracy across ~192,000
interactions.

**Relation to DDI-Net.** DeepDDI defines the 86-type DrugBank DDI label space
that the TDC export used here is drawn from, and is the standard reference point
for "molecular structure alone can predict DDIs".

**How DDI-Net differs.** DeepDDI reports performance under a pair-level
evaluation and treats the task as 86-way typing. DDI-Net collapses the 86 types
to a binary documented-interaction label, adds explicitly generated negatives
(the source has none), and evaluates under a drug-disjoint split in which no
test drug was seen in training.

**Supports the claim.** §3.2 that the source labels are 86 interaction types
rather than a binary label; §2.1 that structure-based DDI prediction is
established.

---

### Nyamabo, Yu & Shi (2021) — SSI-DDI
*Briefings in Bioinformatics* 22(6):bbab133. doi:10.1093/bib/bbab133

**What it showed.** Decomposes DDI prediction into interactions between
substructures of the two molecular graphs, operating directly on molecular
graphs, and improves over prior methods.

**Relation to DDI-Net.** A strong purely molecular DDI method — the family that
DDI-Net's M0 baseline stands in for.

**How DDI-Net differs.** DDI-Net does not aim to beat substructure-attention
methods on molecular modelling. It asks whether *non-structural biological*
annotation adds transferable information on top of a molecular encoder, holding
the molecular encoder fixed between M0 and M4 so the comparison isolates biology.

**Supports the claim.** §2.1 that molecular-graph DDI models are a mature
baseline family; §3.12 justification for an aligned molecular baseline.

---

### Zhang et al. (2023) — EmerGNN
*Nature Computational Science* 3:1023–1033. doi:10.1038/s43588-023-00558-4

**What it showed.** A flow-based GNN that predicts interactions for *emerging*
drugs — drugs with little or no known DDI information — by extracting and
weighting paths between drug pairs through a large biomedical network.
Explicitly motivated by the observation that existing methods need substantial
known DDI information, which emerging drugs lack.

**Relation to DDI-Net.** The closest prior work in motivation: it targets the
same cold-start failure mode DDI-Net's S3 setting isolates, and likewise uses a
biomedical network as the substitute for missing DDI neighbourhood.

**How DDI-Net differs.** EmerGNN propagates over a biomedical network including
paths that pass through other drugs and their interactions. DDI-Net deliberately
uses a strictly per-drug, non-propagating set representation (Deep Sets over the
drug's own protein and pathway annotations), so no information can reach a test
drug through the interaction graph at all — and then tests, with two shortcut
controls, whether the gain is biological identity or annotation count. To our
reading, the degree-preserving biological-identity shuffle is not part of the
EmerGNN evaluation.

**Supports the claim.** §2.4 that cold-start DDI prediction is an active
problem with published approaches; §5.8 that DDI-Net's contribution is the
control design rather than the architecture.

---

## Graph neural network and set methods

### Xu, Hu, Leskovec & Jegelka (2019) — GIN
ICLR 2019, arXiv:1810.00826

**What it showed.** Characterises the expressive power of message-passing GNNs,
proves an upper bound at the Weisfeiler-Lehman test, and constructs the Graph
Isomorphism Network, which attains it — with the key result that **sum**
aggregation is strictly more expressive than mean or max for distinguishing
multisets.

**Relation to DDI-Net.** GIN is the base of the GINE molecular encoder.

**How DDI-Net differs.** DDI-Net inherits GIN rather than extending it. It also
uses the sum-vs-mean result in an unusual direction: the same property that makes
sum more expressive also makes it a *counter*, so the biological branch uses mean
deliberately, and sum is run as CONTROL C precisely to detect whether counting
was the signal.

**Supports the claim.** §3.4 molecular encoder; §3.11 and §5.5 the reasoning
behind mean aggregation and CONTROL C.

---

### Hu et al. (2020) — Strategies for Pre-training Graph Neural Networks
ICLR 2020

**What it showed.** Pre-training strategies for molecular GNNs, and in the
process defines the GINE variant that incorporates **edge features** into GIN's
aggregation — the standard formulation for molecular graphs where bond type
matters.

**Relation to DDI-Net.** DDI-Net's molecular encoder is GINE in this sense: bond
features (11 dimensions) enter the message function.

**How DDI-Net differs.** No pre-training is used. The encoder is trained from
random initialisation on the DDI task alone, so no external molecular corpus can
leak into the evaluation.

**Supports the claim.** §3.4 that the molecular encoder is GINE with edge
features.

---

### Zaheer et al. (2017) — Deep Sets
NeurIPS 30, pp. 3391–3401

**What it showed.** Characterises permutation-invariant functions on sets: any
such function can be written as ρ(Σ φ(x)) for suitable φ and ρ. This gives a
principled architecture for inputs that are unordered collections of varying size.

**Relation to DDI-Net.** A drug's biological annotation *is* an unordered set of
varying size — 19 proteins for the median drug, 627 for the largest. Deep Sets is
the architecture DDI-Net uses for both the protein and pathway levels.

**How DDI-Net differs.** DDI-Net substitutes mean for the sum in the canonical
formulation, for the shortcut reason above, and adds relation-type and
evidence-type embeddings to each set element so that a target, an enzyme and a
transporter are distinguishable. It also uses a learned MISSING token for empty
sets rather than a zero vector, so that "no annotation" is not representable as a
point some real drug could occupy.

**Supports the claim.** §3.11 the biological encoder; §5.5 the mean/sum decision.

---

### Guo, Pleiss, Sun & Weinberger (2017) — On Calibration of Modern Neural Networks
ICML, PMLR 70:1321–1330

**What it showed.** Modern deep networks are systematically overconfident, and
**temperature scaling** — dividing logits by a single scalar fitted on held-out
validation data — is a remarkably effective post-hoc fix. Because the transform
is monotonic, it changes probabilities without changing the ranking of examples.

**Relation to DDI-Net.** DDI-Net's calibration follows this method exactly: one
temperature per seed, fitted only on validation predictions, applied unchanged to
the frozen test predictions.

**How DDI-Net differs.** No methodological difference; DDI-Net applies the method
as published and uses its monotonicity property as an internal consistency check
(AUPRC must not move beyond floating-point noise, and it does not).

**Supports the claim.** §3.18 and §4.9 calibration method and the statement that
ranking metrics are unchanged by construction.

---

## Evaluation and statistics

### Saito & Rehmsmeier (2015)
*PLOS ONE* 10(3):e0118432. doi:10.1371/journal.pone.0118432

**What it showed.** On imbalanced data, ROC curves can look reassuring while the
classifier is performing poorly on the minority class, because specificity is
computed against a large negative set. Precision–recall curves reflect
performance on the positive class more faithfully.

**Relation to DDI-Net.** Justifies AUPRC as the primary metric.

**How DDI-Net differs.** DDI-Net's evaluation sets are constructed at prevalence
0.5, so the imbalance argument is weaker here than in the paper's setting. AUPRC
remains primary because it is sensitive to performance on the positive class and
was preregistered; AUROC is reported alongside it.

**Supports the claim.** §3.16 choice of AUPRC as the primary metric.

---

### Holm (1979)
*Scandinavian Journal of Statistics* 6(2):65–70

**What it showed.** A sequentially rejective multiple-testing procedure that
controls the family-wise error rate under any configuration of true hypotheses,
and is uniformly more powerful than the plain Bonferroni correction.

**Relation to DDI-Net.** Five preregistered hypotheses are tested on the same
frozen test set. Without correction, the chance that at least one nominally
significant result is a false positive rises with the number of tests.

**How DDI-Net differs.** No methodological difference. DDI-Net applies Holm
across all five hypotheses including the exploratory H5, which makes the
correction stricter for the four confirmatory ones than restricting the family
to four would be.

**Supports the claim.** §3.17 statistical analysis; every Holm-adjusted p-value
in §4 and Table 4.

---

### Kapoor & Narayanan (2023)
*Patterns* 4(9):100804. doi:10.1016/j.patter.2023.100804

**What it showed.** A survey finding data leakage across 17 scientific fields,
affecting 294 papers, with a taxonomy of eight leakage types — including the
case where the train/test split does not respect the unit of generalisation the
paper claims to address.

**Relation to DDI-Net.** This is the methodological problem the whole project is
organised around. Splitting DDI *pairs* at random lets the same drug appear on
both sides of the split, so a model can score well by recognising drugs rather
than by generalising to new ones.

**How DDI-Net differs.** DDI-Net treats the split scheme as the object of study
rather than a preprocessing detail: it holds out drugs, reports the S3 subset
where both drugs are unseen, and verifies with a leakage auditor that no test
drug appears in training.

**Supports the claim.** §1.3 the leakage and generalisation problem; §3.8 and
§3.9 leakage prevention and splitting.

---

## Cheminformatics

### Rogers & Hahn (2010) — ECFP
*J. Chem. Inf. Model.* 50(5):742–754. doi:10.1021/ci100050t

**What it showed.** Extended-connectivity fingerprints: circular topological
fingerprints built by iteratively hashing atom neighbourhoods, designed for
structure–activity modelling.

**Relation to DDI-Net.** The BIO-RF control uses ECFP4 fingerprints (radius 2,
2,048 bits) as its molecular representation.

**How DDI-Net differs.** ECFPs are used only in the non-neural control, not in
the primary model, which learns its molecular representation with GINE.

**Supports the claim.** §3.12 the BIO-RF baseline specification.

---

### Bemis & Murcko (1996)
*J. Med. Chem.* 39(15):2887–2893. doi:10.1021/jm9602928

**What it showed.** Defines the molecular framework (scaffold) obtained by
stripping side chains, and shows that a small number of frameworks accounts for
a large fraction of known drugs.

**Relation to DDI-Net.** Scaffold-disjoint splitting — grouping drugs by
Bemis–Murcko framework so that structurally analogous drugs cannot straddle the
split — is a stricter generalisation test than drug-disjoint splitting, and
appears in the project's split module and in falsification criterion F5.

**How DDI-Net differs.** Scaffold assignments exist in the frozen data, but **no
scaffold-disjoint evaluation was performed in the final V2 study**. The
manuscript reports this as an open gap rather than a result.

**Supports the claim.** §3.9 the definition of the scaffold scheme; §4/§6 the
statement that F5 is only partially resolved.

---

## Databases

### Wishart et al. (2018) — DrugBank 5.0
*Nucleic Acids Research* 46(D1):D1074–D1082. doi:10.1093/nar/gkx1037

**What it showed.** The DrugBank resource: curated drug entries with targets,
enzymes, transporters, carriers and documented drug interactions.

**Relation to DDI-Net.** DrugBank is both the ultimate source of the DDI labels
(via the TDC export) and the source of the `DOCUMENTED_DATABASE_RELATION`
evidence type — the M1 rung of the evidence ladder.

**How DDI-Net differs.** DDI-Net uses a TDC-filtered subset of 1,705 drugs, not
the full DrugBank, and states explicitly that this subset must not be treated as
a representative sample of DrugBank.

**Supports the claim.** §3.2 label provenance; §3.5 protein relation types;
§6 database-bias limitation.

---

### Mendez et al. (2019) — ChEMBL
*Nucleic Acids Research* 47(D1):D930–D940. doi:10.1093/nar/gky1075

**What it showed.** ChEMBL: a large open bioactivity database with curated
mechanism-of-action assignments and experimentally measured activities.

**Relation to DDI-Net.** Supplies two of the three evidence types: `CURATED_MOA`
(the M2 rung) and `EXPERIMENTAL_BIOACTIVITY` (the M3 rung).

**How DDI-Net differs.** DDI-Net keeps the two ChEMBL evidence classes separate
rather than pooling them, which is what makes the M2-versus-M3 comparison
interpretable — and what revealed that adding bioactivity evidence *lowered*
held-out performance.

**Supports the claim.** §3.5 evidence types; §4.7 the ablation ladder.

---

### Gillespie et al. (2022) — Reactome
*Nucleic Acids Research* 50(D1):D687–D692. doi:10.1093/nar/gkab1028

**What it showed.** A manually curated, peer-reviewed knowledgebase of human
biological pathways and reactions.

**Relation to DDI-Net.** Supplies the pathway level of the biological
representation: proteins are mapped to Reactome pathways, giving each drug a set
of pathways it is annotated into (M4).

**How DDI-Net differs.** DDI-Net uses pathway membership only as set elements in
a permutation-invariant encoder; it does not use reaction topology, directionality
or stoichiometry, and makes no mechanistic claim from pathway membership.

**Supports the claim.** §3.6 pathway integration; §4.7 that the pathway rung did
not improve held-out performance.

---

### UniProt Consortium (2023)
*Nucleic Acids Research* 51(D1):D523–D531. doi:10.1093/nar/gkac1052

**What it showed.** The UniProt knowledgebase of protein sequences with curated
functional annotation, and the accession scheme that identifies proteins.

**Relation to DDI-Net.** UniProt accessions are the canonical protein
identifiers used to join DrugBank and ChEMBL protein references and to map
proteins to Reactome pathways.

**How DDI-Net differs.** UniProt is used purely as an identifier and mapping
authority; no sequence information enters the model.

**Supports the claim.** §3.3 identity mapping; §3.7 graph construction.

---

### Huang et al. (2021) — Therapeutics Data Commons
NeurIPS Datasets and Benchmarks Track, arXiv:2102.09548

**What it showed.** A unified platform of AI-ready therapeutic datasets and
learning tasks, including the DrugBank multi-instance DDI prediction dataset.

**Relation to DDI-Net.** The exact provenance of DDI-Net's label set:
`tdc.multi_pred.DDI(name='DrugBank')`, PyTDC 1.1.15.

**How DDI-Net differs.** DDI-Net does not use TDC's default splits. TDC provides
the data; the split scheme, negative sampling and evaluation protocol are the
study's own, because the default random-pair split is precisely the design this
work argues is misleading for unseen-drug claims.

**Supports the claim.** §3.2 dataset provenance and version.
