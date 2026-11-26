from pathlib import Path

GUIDELINES = Path(__file__).resolve().parents[3] / "evaluation" / "guidelines.ar.md"

# One keyword per section of the annotation guidelines (S00 AC-1).
REQUIRED_SECTIONS = [
    "الكتابة العامية",
    "الأرقام",
    "الكلمات الإنجليزية",
    "التردد والتكرار",
    "التداخل",
    "غير المسموع",
    "الصمت والموسيقى",
    "الترقيم",
    "المتحدثون",
    "شروط المقاطع",
    "تغطية",
]


def test_guidelines_cover_every_required_section() -> None:
    text = GUIDELINES.read_text(encoding="utf-8")
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    for keyword in REQUIRED_SECTIONS:
        assert any(keyword in heading for heading in headings), keyword


def test_guidelines_pin_the_canonical_examples_and_conditions() -> None:
    text = GUIDELINES.read_text(encoding="utf-8")
    assert "عايز" in text
    assert "[تداخل]" in text
    assert "[غير مسموع]" in text
    for condition in ["clean", "noisy", "code_switch", "silent", "music"]:
        assert f"`{condition}`" in text, condition
