"""
공통 파이프라인: 목록에서 얻은 (title, url, pub_date, doc_no) 후보들을 받아
상세 페이지/첨부파일에서 원문을 추출하고, 요약 · scope · SOP · Gap 분석까지
한 번에 처리하여 regulations.json 항목으로 변환한다.
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_sop_flag  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


def fetch_detail_text(url, attachment_exts=(".pdf", ".docx", ".hwpx")):
    """상세 페이지 HTML 본문 + (있다면) 첫 번째 첨부파일 텍스트를 합쳐 반환."""
    res = fetch(url)
    if res.robots_disallowed:
        return "", f"robots.txt 차단됨"
    if not res.ok:
        return "", res.error or "접속 실패"
    if BeautifulSoup is None:
        return "", "beautifulsoup4 미설치"

    soup = BeautifulSoup(res.text, "html.parser")

    for ext in attachment_exts:
        a = soup.select_one(f'a[href$="{ext}"]')
        if a:
            href = a.get("href")
            file_url = href if href.startswith("http") else url.rsplit("/", 1)[0] + "/" + href.lstrip("./")
            content = fetch_binary(file_url)
            if content:
                text, status = extract_text(content, f"file{ext}")
                if text:
                    return text, f"OK (첨부 {ext})"

    main = soup.select_one("main") or soup.select_one("article") or soup.body
    text = main.get_text("\n", strip=True) if main else ""
    return text, ("OK (본문 HTML)" if text else "본문을 찾지 못함")


def build_item(agency_label, title, url, pub_date, doc_no, effective_date=None,
                fetch_detail=True):
    body_text, status = ("", "상세 미조회")
    if fetch_detail:
        body_text, status = fetch_detail_text(url)

    summary_source = body_text or title
    prev = load_previous_snapshot(agency_label, doc_no)
    gap = generate_gap(prev, body_text or title)
    if body_text:
        save_snapshot(agency_label, doc_no, body_text)

    summary = summarize(title, summary_source)
    if not body_text:
        summary += f"\n\n(원문 상세 확보 실패: {status})"

    return {
        "search_month": (pub_date or "")[:7],
        "publish_date": pub_date,
        "effective_date": effective_date,
        "publisher": agency_label,
        "doc_no": doc_no or title[:40],
        "title": title,
        "summary": summary,
        "scope": guess_scope(title + " " + summary_source),
        "sop_required": "★" if guess_sop_flag(title + " " + summary_source) else "",
        "url": url,
        "gap_analysis": gap,
    }


MD_KEYWORDS = [
    "medical device", "in vitro diagnostic", "ivdr", " mdr ", "quality system",
    "quality management", "820", "qmsr", "notified body", "premarket",
    "510(k)", "classification", "udi", "device regulation",
]


def is_medical_device_related(text: str) -> bool:
    t = (text or "").lower()
    return any(kw in t for kw in MD_KEYWORDS)
