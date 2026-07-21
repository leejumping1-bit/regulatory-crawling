"""
요약 엔진
- 기본값: API 키 없이 동작하는 규칙기반(추출식) 요약
- 추후 API 키를 연동하고 싶으면 환경변수(OPENAI_API_KEY 또는 ANTHROPIC_API_KEY)를
  GitHub Secrets에 등록하기만 하면 자동으로 LLM 요약으로 전환된다 (아래 summarize() 참고).
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


def _rule_based_summary(title: str, body_text: str, max_sentences=4) -> str:
    """
    첨부 원문에서 핵심으로 보이는 문장을 추출하는 매우 단순한 규칙기반 요약.
    (정확한 의미요약이 아니라 '핵심 문장 발췌'에 가깝다는 점을 명확히 함)
    """
    if not body_text:
        return f"「{title}」 — 첨부 원문을 확보하지 못해 자동요약을 생성하지 못했습니다. 원문 링크에서 직접 확인이 필요합니다."

    sentences = re.split(r'(?<=[.다음함됨음됨함임\)])\s+|\n+', body_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 8]

    priority_kw = ["시행일", "시행한다", "적용", "개정", "제정", "폐지", "신설", "삭제", "다음과 같이"]
    scored = []
    for s in sentences:
        score = sum(1 for kw in priority_kw if kw in s)
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])
    picked = [s for _, s in scored[:max_sentences]] or sentences[:max_sentences]

    disclaimer = "\n\n(※ 규칙기반 발췌 요약입니다 — 원문의 정확한 뉘앙스는 링크된 원문을 반드시 확인하세요.)"
    return " ".join(picked) + disclaimer


def _llm_summary(title: str, body_text: str) -> str | None:
    """
    OPENAI_API_KEY 또는 ANTHROPIC_API_KEY 가 설정되어 있으면 이 함수가 실제 LLM 요약을 시도한다.
    두 키 모두 없으면 None을 반환하여 규칙기반 요약으로 자동 대체된다.
    """
    prompt = (
        "당신은 의료기기 인증기관(BSI, SGS 등) 심사원입니다. 아래는 의료기기 규제/규격 문서 원문입니다. "
        "회사가 반드시 검토해야 할 핵심 변경사항을 한국어로 5문장 이내로 요약하세요.\n\n"
        f"[제목]\n{title}\n\n[원문]\n{body_text[:12000]}"
    )

    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

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
    if llm_result:
        return llm_result
    return _rule_based_summary(title, body_text)
