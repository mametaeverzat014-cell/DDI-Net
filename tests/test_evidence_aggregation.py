"""Факторный дизайн V3 над агрегацией типов доказательств.

ЗАЧЕМ ЭТОТ ФАЙЛ. V2 намерила немонотонную лестницу: добавление
экспериментальной биоактивности ChEMBL (M2 → M3) СНИЗИЛО качество. Два
объяснения были предложены post hoc и ни одно не проверено — либо добавленные
элементы разбавляют курированные в общем среднем, либо экспериментальные
доказательства просто менее полезны поэлементно. Одно общее среднее их не
различает: источник с большим числом элементов получает и большую массу, и своё
поэлементное качество, свёрнутые в одно число.

Два флага разводят эти факторы по четырём клеткам A00/A10/A01/A11
(`BioGineConfig.group_means`, `learned_evidence_weights`).

**Главное требование, ради которого файл и написан: A00 обязана воспроизводить
поведение V2 в точности.** Если это не так, факторный контраст измеряет
рефакторинг, а не факторы, и весь эксперимент бессмысленен. Проверяется
численно, а не рассуждением.

Замороженные артефакты V2 здесь не читаются и не меняются: тесты работают на
маленьких синтетических тензорах, проверяя арифметику агрегации.
"""

from __future__ import annotations

import math

import pytest

torch = pytest.importorskip("torch")

from ddinet.models.bio_gine import BioGineConfig, DeepSetsEncoder  # noqa: E402


N_GROUPS = 3
DIM = 4


def _encoder(**kw) -> DeepSetsEncoder:
    """Энкодер с фиксированным сидом: сравниваем агрегацию, а не инициализацию."""
    torch.manual_seed(0)
    return DeepSetsEncoder(
        element_dim=DIM, hidden_dim=8, out_dim=DIM,
        dropout=0.0, aggregation="mean", **kw,
    )


def _fixture():
    """Три препарата с разным составом источников.

    Препарат 0: 1 элемент типа 0, 4 элемента типа 1 — перекос по массе.
    Препарат 1: по одному элементу типов 0 и 2 — сбалансирован, тип 1 отсутствует.
    Препарат 2: элементов нет вообще — путь MISSING.
    """
    owner = torch.tensor([0, 0, 0, 0, 0, 1, 1])
    group = torch.tensor([0, 1, 1, 1, 1, 0, 2])
    torch.manual_seed(1)
    elements = torch.randn(len(owner), DIM)
    sizes = torch.tensor([5.0, 2.0, 0.0])
    empty = torch.tensor([False, False, True])
    return elements, owner, group, sizes, empty


# ── неприкосновенность V2 ───────────────────────────────────────────────────

def test_a00_reproduces_ungrouped_mean_exactly() -> None:
    """A00 обязана быть тем же вычислением, что и V2, до последнего бита."""
    elements, owner, group, sizes, empty = _fixture()

    v2 = _encoder()
    a00 = _encoder(n_groups=N_GROUPS, group_means=False, learned_group_weights=False)
    a00.load_state_dict(v2.state_dict())

    with torch.no_grad():
        ref = v2(elements, owner, 3, sizes, empty)
        got = a00(elements, owner, 3, sizes, empty, group=group)

    assert torch.equal(ref, got), (
        "A00 разошлась с V2 — факторный контраст будет мерить рефакторинг, "
        f"а не факторы; max|Δ| = {(ref - got).abs().max().item():.3e}"
    )


def test_untrained_a11_equals_a10_because_weights_start_equal() -> None:
    """Обучаемые веса стартуют с softplus(x)=1, то есть с равных."""
    elements, owner, group, sizes, empty = _fixture()

    a10 = _encoder(n_groups=N_GROUPS, group_means=True, learned_group_weights=False)
    a11 = _encoder(n_groups=N_GROUPS, group_means=True, learned_group_weights=True)
    a11.load_state_dict(a10.state_dict(), strict=False)

    with torch.no_grad():
        assert torch.allclose(
            a10(elements, owner, 3, sizes, empty, group=group),
            a11(elements, owner, 3, sizes, empty, group=group),
            atol=1e-6,
        ), "необученная A11 должна совпадать с A10: веса инициализируются равными"


# ── то, ради чего группировка и вводится ────────────────────────────────────

def test_grouping_changes_the_answer_when_sources_are_unbalanced() -> None:
    """Иначе флаг ничего не делает и эксперимент пуст."""
    elements, owner, group, sizes, empty = _fixture()

    a00 = _encoder(n_groups=N_GROUPS, group_means=False)
    a10 = _encoder(n_groups=N_GROUPS, group_means=True)
    a10.load_state_dict(a00.state_dict())

    with torch.no_grad():
        x = a00(elements, owner, 3, sizes, empty, group=group)
        y = a10(elements, owner, 3, sizes, empty, group=group)

    # Препарат 0 несбалансирован (1 против 4) — там разница обязана быть.
    assert not torch.allclose(x[0], y[0], atol=1e-5), (
        "группировка не изменила представление перекошенного препарата"
    )
    # Препарат 1 сбалансирован (1 против 1) — там её быть не должно.
    assert torch.allclose(x[1], y[1], atol=1e-6), (
        "у сбалансированного препарата группировка не должна менять результат"
    )


def test_group_means_equalise_source_mass() -> None:
    """Проверка арифметики напрямую, без rho.

    При group_means результат обязан равняться невзвешенному среднему
    ПРИСУТСТВУЮЩИХ групповых средних — а не среднему по элементам.
    """
    enc = _encoder(n_groups=N_GROUPS, group_means=True)
    h = torch.tensor([[1.0], [10.0], [10.0], [10.0], [10.0]])
    owner = torch.zeros(5, dtype=torch.long)
    group = torch.tensor([0, 1, 1, 1, 1])

    with torch.no_grad():
        got = enc._grouped(h, owner, group, n_drugs=1)

    # группа 0 → 1.0, группа 1 → 10.0, группа 2 отсутствует
    assert got.item() == pytest.approx(5.5), (
        f"ожидалось (1+10)/2 = 5.5, получено {got.item()}; "
        "поэлементное среднее дало бы 8.2 — значит масса не выровнена"
    )


def test_absent_groups_do_not_drag_the_result_toward_zero() -> None:
    """Отсутствующий источник исключается, а не считается нулём.

    Иначе препарат с одним источником систематически притягивался бы к началу
    координат — и это было бы кодированием изученности, ровно того конфаунда,
    который дизайн и пытается удержать проверяемым.
    """
    enc = _encoder(n_groups=N_GROUPS, group_means=True)
    h = torch.tensor([[4.0], [4.0]])
    owner = torch.zeros(2, dtype=torch.long)
    group = torch.tensor([0, 0])          # только группа 0 из трёх

    with torch.no_grad():
        got = enc._grouped(h, owner, group, n_drugs=1)

    assert got.item() == pytest.approx(4.0), (
        f"ожидалось 4.0, получено {got.item()}; "
        "деление на 3 вместо 1 означало бы, что пустые источники учтены нулями"
    )


def test_learned_weights_do_not_depend_on_per_drug_counts() -> None:
    """Вес источника — глобальный, один на всю модель.

    Вес, способный прочитать n_{d,e}, вернул бы размер множества через саму
    схему взвешивания.
    """
    enc = _encoder(n_groups=N_GROUPS, group_means=True, learned_group_weights=True)
    with torch.no_grad():
        w = enc._group_weights()
    assert w.shape == (N_GROUPS,), (
        f"весов должно быть ровно по одному на источник, получено {tuple(w.shape)}"
    )
    assert (w > 0).all(), "softplus обязан давать положительные веса"
    assert torch.allclose(w, torch.ones(N_GROUPS), atol=1e-6), (
        "инициализация должна давать ровно 1, чтобы старт был с равных весов"
    )


def test_weights_receive_gradient() -> None:
    """Необучаемый обучаемый вес — молчаливо мёртвая ветвь."""
    elements, owner, group, sizes, empty = _fixture()
    enc = _encoder(n_groups=N_GROUPS, group_means=True, learned_group_weights=True)
    enc(elements, owner, 3, sizes, empty, group=group).sum().backward()
    g = enc.group_weight_raw.grad
    assert g is not None and torch.isfinite(g).all() and g.abs().sum() > 0, (
        "веса источников не получили градиент"
    )


# ── защита от несовместимых сочетаний ───────────────────────────────────────

def test_grouping_is_refused_together_with_sum() -> None:
    """SUM существует, чтобы СОХРАНИТЬ счёт; группировка его нормализует.

    Вместе они сделали бы CONTROL C неинтерпретируемым.
    """
    with pytest.raises(ValueError, match="aggregation"):
        BioGineConfig(
            n_protein_vocab=10, n_pathway_vocab=10,
            aggregation="sum", group_means=True,
        )


def test_grouped_encoder_refuses_without_group_index() -> None:
    elements, owner, _, sizes, empty = _fixture()
    enc = _encoder(n_groups=N_GROUPS, group_means=True)
    with pytest.raises(ValueError, match="group index"):
        enc(elements, owner, 3, sizes, empty)


def test_cell_name_appears_in_the_ablation_label() -> None:
    """Имя клетки должно попадать в отчёты: иначе четыре прогона неразличимы."""
    base = dict(n_protein_vocab=10, n_pathway_vocab=10)
    assert "A" not in BioGineConfig(**base).ablation_name()
    assert "A10" in BioGineConfig(**base, group_means=True).ablation_name()
    assert "A01" in BioGineConfig(**base, learned_evidence_weights=True).ablation_name()
    assert "A11" in BioGineConfig(
        **base, group_means=True, learned_evidence_weights=True
    ).ablation_name()


# ── сквозная проверка на полной модели ──────────────────────────────────────
# Проверка на уровне энкодера не поймала бы ошибку в прокидывании ``ev`` от
# места вызова: там элементы сначала дедуплицируются через ``inverse``, и
# групповой индекс легко подать в неправильном порядке. Такая ошибка дала бы
# не падение, а тихо неверный факторный контраст.

np = pytest.importorskip("numpy")

from ddinet.data.biology import EVIDENCE_POLICIES, BiologyBundle  # noqa: E402
from ddinet.models.bio_gine import BioGine, BiologicalSets  # noqa: E402


def _bundle() -> BiologyBundle:
    """Препараты с намеренно перекошенным составом типов доказательств.

    Столбцы protein_items: (белок, роль, тип доказательства).
    """
    protein_items = [
        # D0: один элемент типа 0 против трёх типа 1 — перекос по массе
        np.array([[0, 0, 0], [1, 1, 1], [2, 1, 1], [3, 0, 1]], dtype=np.int64),
        # D1: по одному элементу типов 0 и 2 — сбалансирован
        np.array([[0, 0, 0], [1, 0, 2]], dtype=np.int64),
        # D2: аннотаций нет — путь MISSING
        np.zeros((0, 3), dtype=np.int64),
        # D3: один элемент, один источник
        np.array([[3, 3, 0]], dtype=np.int64),
    ]
    pathway_items = [np.array([0], dtype=np.int64), np.array([0, 1], dtype=np.int64),
                     np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)]
    return BiologyBundle(
        drug_ids=[f"D{i}" for i in range(4)],
        protein_vocab=[f"P{i}" for i in range(4)],
        pathway_vocab=[f"Q{i}" for i in range(3)],
        protein_items=protein_items, pathway_items=pathway_items,
        counts=np.zeros((4, 8)), policy=EVIDENCE_POLICIES["M4"],
    )


def _model(bundle, **kw) -> BioGine:
    torch.manual_seed(0)
    cfg = BioGineConfig(
        n_protein_vocab=bundle.n_proteins, n_pathway_vocab=bundle.n_pathways,
        use_molecular_branch=False, bio_dim=8, hidden_dim=16, dropout_bio=0.0,
        dropout_pair=0.0, **kw,
    )
    m = BioGine(cfg)
    m.set_biology(BiologicalSets(bundle))
    m.eval()
    return m


def test_full_model_a00_matches_v2_exactly() -> None:
    bundle = _bundle()
    v2, a00 = _model(bundle), _model(bundle, group_means=False,
                                    learned_evidence_weights=False)
    a00.load_state_dict(v2.state_dict())

    a = torch.tensor([0, 1, 2, 3])
    b = torch.tensor([3, 2, 1, 0])
    with torch.no_grad():
        h1, m1 = v2.encode()
        h2, m2 = a00.encode()
        p1 = v2.score_pairs(h1, m1, a, b).interaction_logit
        p2 = a00.score_pairs(h2, m2, a, b).interaction_logit

    assert torch.equal(h1, h2), "представления препаратов разошлись"
    assert torch.equal(p1, p2), "логиты пар разошлись"


def test_full_model_grouping_changes_only_unbalanced_drugs() -> None:
    """Если групповой индекс подан не в том порядке, изменится не тот препарат."""
    bundle = _bundle()
    a00, a10 = _model(bundle), _model(bundle, group_means=True)
    a10.load_state_dict(a00.state_dict())

    with torch.no_grad():
        h0, _ = a00.encode()
        h1, _ = a10.encode()

    changed = [i for i in range(4) if not torch.allclose(h0[i], h1[i], atol=1e-6)]
    assert changed == [0], (
        f"измениться должен был только D0 (единственный с перекосом по типам), "
        f"изменились {changed}; скорее всего групповой индекс подан не в том "
        "порядке, что owner"
    )


def test_full_model_grouped_pair_score_stays_exactly_symmetric() -> None:
    """Группировка не должна сломать точную симметрию f(A,B) = f(B,A)."""
    m = _model(_bundle(), group_means=True, learned_evidence_weights=True)
    a, b = torch.tensor([0, 1, 2, 3]), torch.tensor([3, 2, 1, 0])
    with torch.no_grad():
        h, mask = m.encode()
        assert torch.equal(
            m.score_pairs(h, mask, a, b).interaction_logit,
            m.score_pairs(h, mask, b, a).interaction_logit,
        )
