"""
CanLII(webdiff) 스타일 Gap 분석 HTML 생성기.
app.py 의 .diff-del / .diff-add / .diff-omit 클래스와 짝을 이룬다.
"""
import difflib
import html
import re

REVISION_PATTERNS = (
    r"\brev(?:ision)?\.?\s*\d*\b",
    r"\brevised\b",
    r"\brevision history\b",
    r"\bchanges?\s+(?:in|to|from)\b",
    r"개정",
    r"일부개정",
    r"변경사항",
    r"변경 내용",
)


def _split_sentences(text: str | None):
    if not text:
        return []
    parts = re.split(r"(?<=[.;。！？])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _changed_text(chunks):
    return "\n".join(chunks).strip() or "변경된 내용 없음"


def is_revision_document(title: str, body_text: str = "", publisher: str = "") -> bool:
    """문서가 기존 규격의 개정/Revision을 명시하는지 판정한다."""
    haystack = f"{title or ''}\n{body_text or ''}"
    return any(re.search(pattern, haystack, re.IGNORECASE) for pattern in REVISION_PATTERNS)


def should_treat_as_new(title: str, body_text: str = "", publisher: str = "") -> bool:
    """
    '제정' 또는 제목의 'news' 게시물은 기존 snapshot이 있더라도 신규 게시로
    취급한다. 다만 Revision/Rev/개정 근거가 있으면 예외적으로 Gap 비교한다.
    """
    title_text = title or ""
    is_new_marker = (
        "제정" in title_text
        or "신규" in title_text
        or "발표" in title_text
        or re.search(r"\bnews\b|\bnew\b", title_text, re.IGNORECASE)
    )
    return bool(is_new_marker and not is_revision_document(title_text, body_text, publisher))


def generate_gap(past_text: str | None, present_text: str | None, collapse_min=2, force_new=False):
    """
    반환: {"past_text": str, "present_text": str, "diff_html": str}

    기본 비교에서는 SequenceMatcher가 변경으로 판정한 문장(삭제·추가·교체)만
    반환한다. force_new=True이면 기존 snapshot이 있어도 신규 published 문서로
    보고 현재 원문 전체를 표시한다.
    """
    if force_new or not past_text:
        escaped = html.escape(present_text or "").replace("\n", "<br>")
        html_result = (
            f'<span class="diff-add">{escaped}</span><br><br>'
            '<i>(신규 published 문서 — 과거 규격 내용 없음)</i>'
        )
        return {
            "past_text": "N.A. (신규 문서)",
            "present_text": present_text or "",
            "diff_html": html_result,
        }

    old_sents = _split_sentences(past_text)
    new_sents = _split_sentences(present_text)
    sm = difflib.SequenceMatcher(a=old_sents, b=new_sents, autojunk=False)

    old_changed = []
    new_changed = []
    chunks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old_part = " ".join(old_sents[i1:i2]).strip()
        new_part = " ".join(new_sents[j1:j2]).strip()
        if tag in ("delete", "replace") and old_part:
            old_changed.append(old_part)
            chunks.append(f'<div class="diff-del">{html.escape(old_part)}</div>')
        if tag in ("insert", "replace") and new_part:
            new_changed.append(new_part)
            chunks.append(f'<div class="diff-add">{html.escape(new_part)}</div>')

    if not chunks:
        chunks = ['<div class="diff-omit">변경된 문단이 없습니다. 동일한 원문은 생략했습니다.</div>']

    return {
        "past_text": _changed_text(old_changed),
        "present_text": _changed_text(new_changed),
        "diff_html": "\n".join(chunks),
    }


def generate_document_gap(past_text: str | None, present_text: str | None, title: str = "", publisher: str = ""):
    """문서 유형별 예외 규칙을 적용한 Gap 생성 진입점."""
    force_new = should_treat_as_new(title, present_text or "", publisher)
    if force_new:
        return {
            "past_text": "비교 제외 (신규 제정·발표 문서)",
            "present_text": "비교 제외 (신규 제정·발표 문서)",
            "diff_html": '<div class="diff-omit">신규 제정·발표 문서이므로 Gap 분석을 수행하지 않습니다. 공식 원문에서 직접 확인하세요.</div>',
        }
    return generate_gap(past_text, present_text, force_new=force_new)
