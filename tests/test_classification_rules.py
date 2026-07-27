from collectors.summarizer import guess_manufacturer_obligation, guess_scope


UDI_TITLE = "New MDCG Position Paper: UDI assignment between manufacturers and distributors"


def test_mdr_ivdr_wide_reference_is_comprehensive_scope():
    text = f"{UDI_TITLE} This guidance applies to MDR and IVDR."
    assert guess_scope(text) == "종합"


def test_product_scope_requires_explicit_product_signal_not_incidental_text():
    assert guess_scope(UDI_TITLE) == "종합"
    assert guess_scope("Guidance for in vitro diagnostic medical devices") == "체외진단 의료기기"


def test_manufacturer_obligation_requires_an_explicit_duty_or_modal():
    body = "This position paper explains UDI assignment between manufacturers and distributors."
    assert guess_manufacturer_obligation(UDI_TITLE, body) is False
    assert guess_manufacturer_obligation("Manufacturer requirement", "Manufacturers shall assign and maintain unique UDIs.") is True


def test_manufacturer_obligation_detects_documentation_and_responsibility_language():
    assert guess_manufacturer_obligation("Manufacturer documentation", "The manufacturer must document the UDI assignment.") is True
    assert guess_manufacturer_obligation("Manufacturer responsibility", "제조업체 책임이다.") is True
