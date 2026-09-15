"""Baseline, изолирующий графовость молекулярного энкодера.

ЗАЧЕМ ЭТОТ ФАЙЛ. Заглавный вопрос проекта — сохраняется ли преимущество GNN над
простыми baseline при честной оценке. V2 на него не отвечает: единственный
неграфовый baseline (BIO-RF) отличается от BIO-GINE **двумя** свойствами сразу —
он и не нейронный, и не графовый. Разрыв между ними неатрибутируем.

`molecular_encoder="fingerprint"` меняет ровно один фактор: графовая сеть над
атомным графом заменяется на MLP над битами ECFP4. Биологические ветви, слияние
и симметричный декодер остаются теми же объектами.

Тесты здесь проверяют именно это — что подменяется только молекулярная ветвь, а
всё остальное остаётся неотличимым. Если тест на «одинаковость биологии»
сломается, сравнение перестанет быть однофакторным и перестанет отвечать на
заглавный вопрос.

Обучения не запускаются, замороженные артефакты не читаются.
"""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
np = pytest.importorskip("numpy")

from ddinet.data.biology import EVIDENCE_POLICIES, BiologyBundle  # noqa: E402
from ddinet.models.bio_gine import (  # noqa: E402
    BioGine,
    BioGineConfig,
    BiologicalSets,
    FingerprintEncoder,
)

N_DRUGS = 4
N_BITS = 32


def _bundle() -> BiologyBundle:
    return BiologyBundle(
        drug_ids=[f"D{i}" for i in range(N_DRUGS)],
        protein_vocab=[f"P{i}" for i in range(4)],
        pathway_vocab=[f"Q{i}" for i in range(3)],
        protein_items=[
            np.array([[0, 0, 0], [1, 1, 1]], dtype=np.int64),
            np.array([[2, 0, 2]], dtype=np.int64),
            np.zeros((0, 3), dtype=np.int64),
            np.array([[3, 3, 0]], dtype=np.int64),
        ],
        pathway_items=[
            np.array([0], dtype=np.int64), np.array([0, 1], dtype=np.int64),
            np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64),
        ],
        counts=np.zeros((N_DRUGS, 8)),
        policy=EVIDENCE_POLICIES["M4"],
    )


def _fp_table() -> torch.Tensor:
    g = torch.Generator().manual_seed(7)
    return (torch.rand(N_DRUGS, N_BITS, generator=g) < 0.2).float()


def _model(**kw) -> BioGine:
    torch.manual_seed(0)
    cfg = BioGineConfig(
        n_protein_vocab=4, n_pathway_vocab=3,
        bio_dim=8, hidden_dim=16, mol_dim=8,
        dropout_bio=0.0, dropout_pair=0.0, dropout_mol=0.0,
        **kw,
    )
    m = BioGine(cfg)
    m.set_biology(BiologicalSets(_bundle()))
    if cfg.molecular_encoder == "fingerprint":
        m.set_fingerprints(_fp_table())
    m.eval()
    return m


def _fp_model(**kw) -> BioGine:
    return _model(molecular_encoder="fingerprint", fp_bits=N_BITS, **kw)


# ── однофакторность сравнения ───────────────────────────────────────────────

def test_only_the_molecular_branch_differs_from_the_gine_variant() -> None:
    """Биологические ветви двух вариантов должны быть неотличимы.

    Если это не так, разрыв между моделями измеряет не графовость.
    """
    gine = _model(atom_dim=5, bond_dim=3)
    fp = _fp_model()

    g_prot, g_path, g_mask = gine.encode_biology(None)
    f_prot, f_path, f_mask = fp.encode_biology(None)

    assert torch.equal(g_mask, f_mask), "маски присутствия модальностей разошлись"
    for name, a, b in (("белки", g_prot, f_prot), ("пути", g_path, f_path)):
        assert (a is None) == (b is None), f"ветвь {name} есть только у одной модели"
        if a is not None:
            assert a.shape == b.shape, f"ветвь {name}: формы разошлись"


def test_the_two_variants_have_the_same_decoder_and_fusion_shapes() -> None:
    """Слияние и декодер обязаны остаться теми же объектами по форме."""
    gine = _model(atom_dim=5, bond_dim=3)
    fp = _fp_model()
    for a, b in zip(gine.pair_mlp.parameters(), fp.pair_mlp.parameters()):
        assert a.shape == b.shape, "парный декодер отличается по форме"
    assert gine.fusion.out_features == fp.fusion.out_features
    assert gine.fusion.in_features == fp.fusion.in_features, (
        "разная ширина входа слияния означает, что молекулярная ветвь "
        "отдаёт вектор другого размера — сравнение перестаёт быть однофакторным"
    )


def test_fingerprint_variant_has_no_graph_encoder_and_vice_versa() -> None:
    assert _fp_model().mol_encoder is None
    assert _fp_model().fp_encoder is not None
    assert _model(atom_dim=5, bond_dim=3).fp_encoder is None


# ── свойства, унаследованные от V2 и обязанные сохраниться ──────────────────

def test_pair_score_stays_exactly_symmetric() -> None:
    m = _fp_model()
    a, b = torch.tensor([0, 1, 2, 3]), torch.tensor([3, 2, 1, 0])
    with torch.no_grad():
        h, mask = m.encode()
        assert torch.equal(
            m.score_pairs(h, mask, a, b).interaction_logit,
            m.score_pairs(h, mask, b, a).interaction_logit,
        ), "симметрия f(A,B) = f(B,A) сломана"


def test_drug_vector_does_not_depend_on_which_drugs_are_encoded_together() -> None:
    """Батч-независимость: то же свойство, что позволяет предпосчитать инференс."""
    m = _fp_model()
    with torch.no_grad():
        full, _ = m.encode()
        subset, _ = m.encode(node_idx=torch.tensor([2, 0]))
    assert torch.allclose(subset[0], full[2], atol=1e-6)
    assert torch.allclose(subset[1], full[0], atol=1e-6)


def test_chemistry_actually_reaches_the_score() -> None:
    """Иначе получится модель без химии, которая молча отчитается числом."""
    m = _fp_model()
    with torch.no_grad():
        before, _ = m.encode()
        m.set_fingerprints(1.0 - _fp_table())
        after, _ = m.encode()
    assert not torch.allclose(before, after, atol=1e-5), (
        "смена фингерпринтов не изменила представления — химия не доходит"
    )


# ── отказы вместо тихих подмен ──────────────────────────────────────────────

def test_scoring_without_fingerprints_raises() -> None:
    torch.manual_seed(0)
    m = BioGine(BioGineConfig(
        n_protein_vocab=4, n_pathway_vocab=3, molecular_encoder="fingerprint",
        fp_bits=N_BITS, bio_dim=8, hidden_dim=16, mol_dim=8,
    ))
    m.set_biology(BiologicalSets(_bundle()))
    with pytest.raises(ValueError, match="fingerprints not installed"):
        m.encode()


def test_wrong_table_width_is_refused() -> None:
    enc = FingerprintEncoder(n_bits=N_BITS, hidden_dim=8, dropout=0.0)
    with pytest.raises(ValueError, match=str(N_BITS)):
        enc.set_fingerprints(torch.zeros(N_DRUGS, N_BITS + 1))


def test_installing_fingerprints_on_the_gine_variant_is_refused() -> None:
    """Молчаливое принятие означало бы прогон, сравнивающий не то, что задумано."""
    m = _model(atom_dim=5, bond_dim=3)
    with pytest.raises(ValueError, match="no fingerprint branch"):
        m.set_fingerprints(_fp_table())


def test_unknown_encoder_name_is_refused() -> None:
    with pytest.raises(ValueError, match="molecular_encoder"):
        BioGineConfig(n_protein_vocab=4, n_pathway_vocab=3, molecular_encoder="mlp")


def test_variant_is_named_in_the_ablation_label() -> None:
    """Иначе два прогона неразличимы в отчётах."""
    base = dict(n_protein_vocab=4, n_pathway_vocab=3)
    assert "fingerprint" not in BioGineConfig(**base).ablation_name()
    assert "fingerprint" in BioGineConfig(
        **base, molecular_encoder="fingerprint"
    ).ablation_name()


# ── дыры, найденные мутационным тестированием ───────────────────────────────
# Обе проверки ниже добавлены после того, как мутации прошли мимо: снятие
# LayerNorm и подмена гатера на «всегда первая строка» не роняли ни один тест.

def test_each_drug_reads_its_own_fingerprint_row() -> None:
    """Меняем строку одного препарата — меняться должен только его вектор.

    Ловит гатер, который игнорирует node_idx: там все препараты получили бы
    одно и то же представление, и проверки на согласованность и на «химия
    доходит» обе прошли бы.
    """
    m = _fp_model()
    table = _fp_table()
    with torch.no_grad():
        m.set_fingerprints(table)
        before, _ = m.encode()
        flipped = table.clone()
        flipped[1] = 1.0 - flipped[1]        # трогаем только препарат 1
        m.set_fingerprints(flipped)
        after, _ = m.encode()

    changed = [i for i in range(N_DRUGS)
               if not torch.allclose(before[i], after[i], atol=1e-6)]
    assert changed == [1], (
        f"измениться должен был только препарат 1, изменились {changed}; "
        "скорее всего таблица читается не по индексу препарата"
    )


def test_distinct_fingerprints_give_distinct_vectors() -> None:
    m = _fp_model()
    with torch.no_grad():
        h, _ = m.encode()
    pairs = [(i, j) for i in range(N_DRUGS) for j in range(i + 1, N_DRUGS)]
    assert all(not torch.allclose(h[i], h[j], atol=1e-6) for i, j in pairs), (
        "разные препараты получили одинаковые представления"
    )


def test_output_is_layer_normalised() -> None:
    """Нормировка выхода — не косметика, а условие честности сравнения.

    Число единичных битов ECFP растёт с размером молекулы, ровно как норма
    sum-пулинга у GINE. Без LayerNorm фингерпринтовая ветвь кодировала бы
    размер, и разрыв между моделями измерял бы это, а не графовость.
    """
    enc = FingerprintEncoder(n_bits=N_BITS, hidden_dim=8, dropout=0.0)
    enc.set_fingerprints(_fp_table())
    with torch.no_grad():
        out = enc(None)
    # LayerNorm считает смещённую дисперсию; на инициализации weight=1, bias=0.
    assert torch.allclose(out.mean(dim=-1), torch.zeros(N_DRUGS), atol=1e-5), (
        "строки выхода не центрированы — LayerNorm не применён"
    )
    assert torch.allclose(out.std(dim=-1, unbiased=False),
                          torch.ones(N_DRUGS), atol=1e-3), (
        "строки выхода не нормированы — LayerNorm не применён"
    )
