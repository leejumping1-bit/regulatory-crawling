from collectors.summarizer import guess_manufacturer_obligation, guess_scope


UDI_TITLE = "New MDCG Position Paper: UDI assignment between manufacturers and distributors"


def test_mdr_ivdr_wide_reference_is_comprehensive_scope():
    text = f"{UDI_TITLE} This guidance applies to MDR and IVDR."
    assert guess_scope(text) == "종합"


def test_product_scope_requires_explicit_product_signal_not_incidental_text():
    assert guess_scope(UDI_TITLE) == "종합"
    assert guess_scope("Guidance for in vitro diagnostic medical devices") == "체외진단 의료기기"


def test_mfds_scope_uses_title_only_and_defaults_to_comprehensive():
    body = "이 PDF에는 체외진단의료기기와 소프트웨어가 함께 언급된다."
    assert guess_scope(body, title="의료기기 제조 및 품질관리 기준", publisher="MFDS (Korea)") == "종합"
    assert guess_scope(body, title="체외진단의료기기 품목 및 품목별 등급에 관한 규정", publisher="MFDS (Korea)") == "체외진단 의료기기"
    assert guess_scope(body, title="체외 관련 일반 의료기기 안내", publisher="MFDS (Korea)") == "체외진단 의료기기"
    assert guess_scope(body, title="디지털 의료기기 허가 가이드라인", publisher="MFDS (Korea)") == "디지털 의료기기"
    assert guess_scope(body, title="디지털 전환 관련 의료기기 안내", publisher="MFDS (Korea)") == "디지털 의료기기"


def test_foreign_scope_uses_title_tokens_and_mixed_tokens_are_comprehensive():
    mixed_body = "The PDF mentions IVDR, MDR, vitro, and digital devices."
    body = "The PDF contains general regulatory content."
    assert guess_scope(mixed_body, title="Monitoring of Notified Bodies: new MDR and IVDR reports", publisher="MDCG (EU)") == "종합"
    assert guess_scope("The document explains in vitro diagnostic requirements.", title="Guidance for in vitro diagnostic devices", publisher="MDCG (EU)") == "체외진단 의료기기"
    assert guess_scope("MDR requirements only", title="MDR guidance", publisher="MDCG (EU)") == "MDR"
    assert guess_scope("IVDR requirements only", title="IVDR guidance", publisher="MDCG (EU)") == "체외진단 의료기기"
    assert guess_scope(body, title="Medical Devices Regulations", publisher="Health Canada") == "종합"
    assert guess_scope(body, title="MDR medical devices guidance", publisher="MDCG (EU)") == "MDR"
    assert guess_scope(body, title="Digital transformation guidance", publisher="MDCG (EU)") == "디지털 의료기기"
    assert guess_scope(body, title="Digital medical device guidance", publisher="MDCG (EU)") == "디지털 의료기기"
    assert guess_scope(body, title="Implantable device guidance", publisher="MDCG (EU)") == "종합"
    assert guess_scope(body, title="Updated list of notified bodies", publisher="MDCG (EU)") == "종합"


def test_generic_foreign_title_with_ivdr_in_body_is_ivdr():
    body = "The document covers MD requirements and IVDR obligations in separate sections."
    assert guess_scope(body, title="Updated submission request template for medical devices", publisher="MDCG (EU)") == "체외진단 의료기기"
    assert guess_scope("General medical device requirements for syringes.", title="Medical device guidance", publisher="MDCG (EU)") == "종합"


def test_manufacturer_obligation_requires_an_explicit_duty_or_modal():
    body = "This position paper explains UDI assignment between manufacturers and distributors."
    assert guess_manufacturer_obligation(UDI_TITLE, body) is False
    assert guess_manufacturer_obligation("Manufacturer requirement", "Manufacturers shall assign and maintain unique UDIs.") is True


def test_manufacturer_obligation_detects_documentation_and_responsibility_language():
    assert guess_manufacturer_obligation("Manufacturer documentation", "The manufacturer must document the UDI assignment.") is True
    assert guess_manufacturer_obligation("Manufacturer responsibility", "제조업체 책임이다.") is True
