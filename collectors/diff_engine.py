"""
CanLII(webdiff) 스타일 Gap 분석 HTML 생성기.
app.py 의 .diff-del / .diff-add / .diff-omit 클래스와 짝을 이룬다.
"""
import re
import difflib


def _split_sentences(text: str):
    if not text:
        return []
    parts = re.split(r'(?<=[.;])\s+|\n+', text.strip())
    return [p.strip() for p in parts if p.strip()]


def generate_gap(past_text: str, present_text: str, collapse_min=2):
    """
    반환: {"past_text": str, "present_text": str, "diff_html": str}
    past_text 가 없으면 신규 제정으로 처리한다.
    """
    if not past_text:
        html = f'<span class="diff-add">{present_text}</span><br><br><i>(신규 제정 문서 — 개정 전 내용 N.A.)</i>'
        return {"past_text": "N.A.", "present_text": present_text or "", "diff_html": html}

    old_sents = _split_sentences(past_text)
    new_sents = _split_sentences(present_text)
    sm = difflib.SequenceMatcher(a=old_sents, b=new_sents, autojunk=False)

    chunks = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            seg = old_sents[i1:i2]
            if len(seg) > collapse_min:
                chunks.append(f'<div class="diff-omit">⋯ ({len(seg)}개 문장 동일 내용 생략) ⋯</div>')
            else:
                chunks.append(" ".join(seg))
        elif tag == "delete":
            chunks.append(f'<span class="diff-del">{" ".join(old_sents[i1:i2])}</span>')
        elif tag == "insert":
            chunks.append(f'<span class="diff-add">{" ".join(new_sents[j1:j2])}</span>')
        elif tag == "replace":
            chunks.append(f'<span class="diff-del">{" ".join(old_sents[i1:i2])}</span>')
            chunks.append(f'<span class="diff-add">{" ".join(new_sents[j1:j2])}</span>')

    return {
        "past_text": past_text,
        "present_text": present_text,
        "diff_html": "<br>".join(chunks) if chunks else "변경 사항이 감지되지 않았습니다.",
    }
