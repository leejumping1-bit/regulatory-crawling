"""
CanLII(webdiff) 스타일 Gap 분석 HTML 생성기.
app.py 의 .diff-del / .diff-add / .diff-omit 클래스와 짝을 이룬다.
"""
import difflib
import html
import re


def _split_sentences(text: str):
    if not text:
        return []
    parts = re.split(r"(?<=[.;。！？])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _changed_text(chunks):
    return "\n".join(chunks).strip() or "변경된 내용 없음"


def generate_gap(past_text: str, present_text: str, collapse_min=2):
    """
    반환: {"past_text": str, "present_text": str, "diff_html": str}

    과거/현재 원문 전체를 화면에 반복하지 않고, SequenceMatcher가 변경으로
    판정한 문장(삭제·추가·교체)만 각각 반환한다. past_text가 없으면 신규
    제정으로 보고 현재 원문 전체를 신규 내용으로 표시한다.
    """
    if not past_text:
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
    equal_count = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            equal_count += i2 - i1
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
