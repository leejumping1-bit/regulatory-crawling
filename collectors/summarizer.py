"""
요약 엔진
- 기본값: API 키 없이 동작하는 규칙기반(추출식) 요약
- 추후 API 키를 연동하고 싶으면 환경변수(GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY 중 하나)를
  등록하기만 하면 자동으로 LLM 요약으로 전환된다 (아래 summarize() 참고). 여러 개가 설정되어 있으면
  GEMINI_API_KEY를 가장 먼저 사용한다(무료 등급 제공).
"""
import os
import re

SOP_KEYWORDS = [
    "시행규칙", "시행령", "품질관리", "제조 및 품질관리", "기준", "GMP", "허가", "인증",
    "심사", "규정", "고시", "의무", "표시", "라벨", "임상", "등급", "분류",
    "MDR", "IVDR", "QMSR", "820", "notified body", "quality management",
]

SCOPE_KEYWORDS = {
    "체외진단 의료기기": ["체외진단", "IVD", "in vitro diagnostic"],
    "디지털 의료기기": ["디지털의료", "소프트웨어", "AI", "SaMD", "software as a medical device"],
    "체내 이식형 의료기기": ["이식형", "임플란트", "implant"],
}


def guess_scope(text: str) -> str:
    for scope, kws in SCOPE_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in text.lower():
                return scope
    return "종합"


def guess_sop_flag(text: str) -> bool:
    return any(kw.lower() in text.lower() for kw in SOP_KEYWORDS)


def _rule_based_summary(title: str, body_text: str, max_sentences=5) -> str:
    """
    첨부 원문에서 핵심으로 보이는 문장을 추출하는 매우 단순한 규칙기반 요약.
    (정확한 의미요약이 아니라 '핵심 문장 발췌'에 가깝다는 점을 명확히 함)
    """
    if not body_text:
        return (
            f"[문서 제목] {title}\n"
            "[핵심 내용] 원문을 확보하지 못해 세부 변경사항을 자동으로 확인하지 못했습니다.\n"
            "[적용 범위] 제목상 관련 규격·가이드·규제기관 공지에 해당합니다.\n"
            "[실무 검토] 적용 대상 제품, 인증·심사 절차, 내부 품질문서에 영향이 있는지 확인해야 합니다.\n"
            "[확인 필요] 원문 링크에서 시행일, 적용 대상, 첨부파일을 직접 확인해야 합니다."
        )

    normalized_body = re.sub(r"\s+", "", body_text)
    has_page_major_content = "주요내용" in normalized_body or "주요사항" in normalized_body
    if not has_page_major_content and re.search(r"제\s*(?:\d+\s*)?(?:장|조)|부칙", body_text):
        lines = [re.sub(r"\s+", " ", line).strip() for line in body_text.splitlines()]
        lines = [line for line in lines if len(line) >= 4]
        structure = []
        for line in lines:
            if re.search(r"^제\s*(?:\d+\s*)?(?:장|조)|^부칙", line):
                if line not in structure:
                    structure.append(line[:180])
        excerpt_candidates = [
            line for line in lines
            if len(line) >= 15
            and not re.search(r"^제\s*(?:\d+\s*)?(?:장|조)|^부칙", line)
            and any(
                kw in line for kw in ("지정", "신청", "심사", "평가", "품질", "교육", "자격", "부적합", "시정", "이의", "불만", "분쟁", "기록", "문서")
            )
        ]
        excerpt_lines = excerpt_candidates[:8] or lines[:8]
        excerpt = "\n".join(f"  - {line[:360]}" for line in excerpt_lines)
        sections = " / ".join(structure[:8]) or "본문 조문 및 부칙"
        return (
            f"[문서 제목] {title}\n"
            "[문서 성격] 이 문서는 의료기기 관련 규정·고시의 전문으로, 조문 단위의 의무와 절차를 정하는 원문입니다.\n"
            "[핵심 내용] 원문에서 확인되는 목적·지정·평가·품질관리 관련 조항을 기준으로 회사의 적용 여부를 검토해야 합니다.\n"
            f"[구성] {sections}\n"
            f"[원문 주요 발췌]\n{excerpt}\n"
            "[적용 범위] 의료기기 제조·품질관리 또는 관련 기관의 지정·평가·심사 업무에 직접 적용될 수 있습니다. 제품군, 기관 역할, 심사 범위는 조문별로 대조해야 합니다.\n"
            "[시행·변경 확인] 고시일과 부칙의 시행일, 경과조치, 기존 지정·심사 건에 대한 적용례를 반드시 확인해야 합니다.\n"
            "[실무 검토] 품질관리 절차서, 심사 대응자료, 기술문서, 교육·자격관리, 협력기관 관리 기준을 개정할 필요가 있는지 담당자가 판단해야 합니다.\n"
            "[확인 필요] 전문 PDF의 전체 조문과 별표·서식이 요약에 모두 포함되지는 않으므로, 실제 적용 전에는 공식 PDF 원문을 최종 확인해야 합니다.\n"
            "[요약 한계] 규칙기반 요약은 법률적 해석이나 회사별 적용판정을 대신하지 않습니다."
        )

    sentences = re.split(r'(?<=[.다음함됨음됨함임\)])\s+|\n+', body_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 8]

    priority_kw = ["시행일", "시행한다", "적용", "개정", "제정", "폐지", "신설", "삭제", "다음과 같이"]
    scored = []
    for s in sentences:
        score = sum(1 for kw in priority_kw if kw in s)
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    picked = [s for _, s in scored[:max_sentences]] or sentences[:max_sentences]

    excerpts = [s[:420] for s in picked]
    excerpt_text = "\n".join(f"  - {s}" for s in excerpts)
    return (
        f"[문서 제목] {title}\n"
        "[핵심 내용] 아래 내용은 원문에서 규제·적용·개정과 관련된 문장을 우선 추출한 결과입니다.\n"
        f"[원문 핵심 발췌]\n{excerpt_text}\n"
        "[변경·영향 검토] 개정·신설·폐지·적용 시점과 대상 제품 또는 제조·품질관리 절차에 변화가 있는지 확인해야 합니다.\n"
        "[실무 검토] 관련 인증, 심사자료, 기술문서, 위험관리 및 내부 SOP에 반영할 필요가 있는지 담당 부서가 검토해야 합니다.\n"
        "[확인 필요] 본 요약은 자동 발췌이므로 법적 효력, 시행일, 예외 조건은 반드시 링크된 공식 원문과 첨부파일에서 최종 확인해야 합니다.\n"
        "[요약 한계] 규칙기반 fallback은 원문을 완전하게 번역하거나 법률적 의미를 확정하지 않습니다."
    )


def _llm_summary(title: str, body_text: str) -> str | None:
    """
    GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY 순서로 확인해서 설정된 것이 있으면
    그걸로 실제 LLM 요약을 시도한다. 아무 키도 없으면 None을 반환해 규칙기반 요약으로 대체된다.
    """
    prompt = (
        "당신은 의료기기 인증기관(BSI, SGS 등) 심사원입니다. 아래는 의료기기 규제/규격 문서 원문입니다. "
        "회사가 반드시 검토해야 할 내용을 한국어로 6~10문장 분량의 상세 요약으로 작성하세요. "
        "반드시 다음 항목을 포함하세요: 핵심 내용, 변경사항, 적용 범위, 시행일/일정, 회사 실무 영향, 필요한 조치, 확인이 필요한 불확실한 사항.\n\n"
        f"[제목]\n{title}\n\n[원문]\n{body_text[:12000]}"
    )

    gemini_key = os.environ.get("GEMINI_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            text = (resp.text or "").strip()
            if text:
                return text
        except Exception as e:
            print(f"[summarizer] Gemini 요약 실패, 다음 후보로 넘어감: {e}")

    if openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            print(f"[summarizer] OpenAI 요약 실패, 규칙기반으로 대체: {e}")
            return None

    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            resp = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                messages=[{"role": "user", "content": prompt}],
            )
            return resp.content[0].text.strip()
        except Exception as e:
            print(f"[summarizer] Anthropic 요약 실패, 규칙기반으로 대체: {e}")
            return None

    return None


def summarize(title: str, body_text: str) -> str:
    llm_result = _llm_summary(title, body_text)
    if llm_result and len(llm_result) >= 240 and ("핵심" in llm_result or "적용" in llm_result):
        return llm_result
    return _rule_based_summary(title, body_text)
