"""Guards against stray characters creeping into committed files.

Motivated by a real slip: a CJK character appeared in a chat message where a
Cyrillic word was meant. It never reached a file, but the failure mode is easy
to repeat and hard to spot by eye - a single wrong glyph inside a Russian or
English word reads as normal text at a glance and corrupts a search.

The check allows Latin, Cyrillic, Greek, digits and a small explicit set of
mathematical and typographic symbols the documentation genuinely uses. Anything
else - CJK, Arabic, emoji outside the allowed set, invisible formatting
characters - fails with the file and line named.
"""
import pathlib
import subprocess
import unicodedata

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: Scripts whose presence is expected: the code and docs are English + Russian.
ALLOWED_SCRIPTS = ("LATIN", "CYRILLIC", "GREEK", "DIGIT", "SPACE")

#: Symbols the documentation uses deliberately: set theory and logic in the
#: methodology sections, box drawing in the architecture diagram, and typographic
#: punctuation. Listed explicitly so a new one is a conscious addition.
ALLOWED_SYMBOLS = set(
    "—–…«»“”‘’·±≈≥≤→←↔°µ×÷∆Σ√∞⚠⛔✓✗№§"
    "⇒⇏∈∉≡≠∩∪⊙−ᵀ"          # methodology notation
    "─│┌┐└┘├┤┬┴┼►◄▲▼"      # architecture diagrams
    "•"                    # bullet inside the DATA_PIPELINE.md flow diagram
    "↑↓"                   # direction of exposure/effect change in
                           # MECHANISM_ONTOLOGY.md ("серум-концентрация ↑").
                           # Semantic, not decorative: the ontology's
                           # `direction` field is exactly this distinction.
    "₀₁₂₃₄₅₆₇₈₉"           # subscripts. ECE₁₅ is the expected calibration error
                           # at 15 bins, which is the binning the calibration
                           # tables report; the bin count belongs in the name.
                           # Whole range allowed at once, as for superscripts.
    "∧≫"                   # ∧ joins falsification criteria (F1 ∧ F2) alongside
                           # the ⇒ ∈ ≡ already listed; ≫ states that an effect
                           # is not near its threshold (dz = 7.72 ≫ 0.2), which
                           # ">" would understate.
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"          # superscripts. R² appears throughout (degree-shortcut
                           # probe, adversarial debiasing); the digits and the
                           # superscript minus carry scientific notation for
                           # p-values like 2.4 x 10⁻⁵⁶. The whole digit range is
                           # allowed at once so a new exponent is not a new
                           # test failure.
)

#: U+0301 COMBINING ACUTE ACCENT marks Russian stress, which the negative
#: sampling section needs to distinguish "временны́е" (temporal) from
#: "вре́менные" (temporary). Correct orthography, not a stray glyph.
ALLOWED_COMBINING = {"́"}

TEXT_SUFFIXES = {".py", ".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".cfg", ".toml"}

#: Tracked directories whose text is not ours to police: `external` is vendored
#: upstream code and `data` is generated. Untracked trees need no entry here —
#: see _text_files().
SKIP_DIRS = {"external", "data"}


def _text_files() -> list[pathlib.Path]:
    """Files git tracks, which is what "committed" in this module's name means.

    Previously this walked the filesystem and skipped a hand-listed set of
    directories. That broke the moment an untracked directory of third-party
    text appeared: installing the frontend's dependencies put ~600 emoji- and
    CJK-bearing READMEs under web/node_modules, and the test failed on other
    people's changelogs. Asking git is both the correct question and immune to
    every future case of it — node_modules, virtualenvs, build output, the
    gitignored runtime/ tree carrying the model artifact.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO, capture_output=True, check=True,
    ).stdout.decode()
    out = []
    for rel in listing.split("\0"):
        if not rel:
            continue
        path = REPO / rel
        if SKIP_DIRS & set(pathlib.PurePosixPath(rel).parts):
            continue
        if not path.is_file():          # deleted-but-staged, or a submodule
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in (".gitignore", "requirements.txt"):
            out.append(path)
    return out


def _offending(path: pathlib.Path) -> list[tuple[int, str, str, str]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    hits = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for char in line:
            if ord(char) < 128 or char in ALLOWED_SYMBOLS or char in ALLOWED_COMBINING:
                continue
            name = unicodedata.name(char, "")
            if any(script in name for script in ALLOWED_SCRIPTS):
                continue
            hits.append((lineno, char, hex(ord(char)), name))
    return hits


def test_no_unexpected_scripts_in_committed_text():
    problems = {}
    for path in _text_files():
        hits = _offending(path)
        if hits:
            problems[str(path.relative_to(REPO))] = hits[:5]
    assert not problems, (
        "Unexpected characters found. If one is deliberate, add it to "
        "ALLOWED_SYMBOLS with a comment saying why:\n"
        + "\n".join(
            f"  {f}: " + ", ".join(f"line {ln} {c!r} {code} {nm}" for ln, c, code, nm in hits)
            for f, hits in problems.items()
        )
    )


def test_the_guard_actually_detects_a_stray_glyph(tmp_path):
    """A guard that never fires is indistinguishable from no guard.

    The offending character is built with ``chr`` rather than written literally,
    because a literal one in this file would be flagged by the scan above - the
    guard would fail on its own fixture.
    """
    glyph = chr(0x9AD8)          # CJK ideograph, the exact slip being guarded
    bad = tmp_path / "bad.md"
    bad.write_text(f"на высоте and {glyph} in the middle\n", encoding="utf-8")
    hits = _offending(bad)
    assert hits and hits[0][1] == glyph


def test_cyrillic_and_latin_pass_cleanly(tmp_path):
    ok = tmp_path / "ok.md"
    ok.write_text("Схема разбиения — drug-level split, ΔE ≥ 8, временны́е негативы\n",
                  encoding="utf-8")
    assert _offending(ok) == []
