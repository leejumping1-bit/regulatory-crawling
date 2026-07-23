"""
MDCG(EU) 수집기 — 정규식 기반 재작성판

기존 버전의 버그: a.find_parent()로 "주변 컨텍스트"를 잡을 때 페이지 전체/여러 항목을
아우르는 큰 덩어리를 잡아버려 제목·날짜·의료기기 키워드가 서로 엉뚱하게 섞였다.

이번 버전은 CSS 클래스에 의존하지 않고, 이 사이트가 항상 지키는 URL 규칙
( /latest-updates/<slug>-YYYY-MM-DD_en )에서 정규식으로 직접 (제목, 링크, 날짜)를
한 번에 추출한다. 사이트의 디자인/클래스가 바뀌어도 이 URL 패턴만 유지되면 계속 동작한다.

목록: https://health.ec.europa.eu/latest-updates_en (페이지네이션 ?page=0,1,2,... 0-index)
상세: 각 항목 페이지에서 /document/download/... 링크(?filename=... 로 실제 확장자 확인 가능)를 찾아
      PDF/DOCX 원문을 추출한다.
"""
import re
import sys
import os
from datetime import date
from urllib.parse import urlparse, parse_qs

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_sop_flag  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

BASE = "https://health.ec.europa.eu"
LIST_URL_TMPL = BASE + "/latest-updates_en?page={page}"

# 이 사이트의 상세 URL은 항상 이 패턴을 따른다: /latest-updates/<slug>-YYYY-MM-DD_en
# (실제 확인된 예: /latest-updates/update-mdcg-2021-24-rev1-guidance-classification-medical-devices-april-2026-2026-04-20_en)
ITEM_RE = re.compile(
    r'<a[^>]+href="(?P<url>(?:https://health\.ec\.europa\.eu)?/latest-updates/[a-z0-9\-]+-'
    r'(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})_en)"[^>]*>(?P<title>[^<]{6,300})</a>',
    re.IGNORECASE,
)
DOWNLOAD_RE = re.compile(r'href="(?P<url>https://health\.ec\.europa\.eu/document/download/[^"]+)"')

MD_KEYWORDS = ["medical device", "in vitro diagnostic", "ivdr", "mdcg", " mdr", "eudamed",
               "notified bod", "udi", "emdn", "combine programme", "well-established technolog"]

MAX_PAGES_FULL = 60     # 2026-01부터 전체를 훑을 때 페이지 상한 (안전장치, 뒤 페이지일수록 오래된 글)
MAX_PAGES_TODAY = 3     # '오늘자만' 조회할 때 페이지 상한 — 최신순 정렬이라 보통 1페이지면 충분


def _is_md_related(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in MD_KEYWORDS)


def run(since_year=2026, since_month=1, today_only=False):
    today_str = date.today().isoformat()
    max_pages = MAX_PAGES_TODAY if today_only else MAX_PAGES_FULL

    candidates = []
    for page in range(max_pages):
        res = fetch(LIST_URL_TMPL.format(page=page))
        if res.robots_disallowed:
            return [], res
        if not res.ok:
            break

        found_on_page = 0
        stop_after_page = False
        for m in ITEM_RE.finditer(res.text):
            found_on_page += 1
            pub_date = f"{m.group('y')}-{m.group('m')}-{m.group('d')}"

            if today_only:
                if pub_date != today_str:
                    stop_after_page = True
                    continue
            else:
                y, mo = int(m.group("y")), int(m.group("m"))
                if (y, mo) < (since_year, since_month):
                    stop_after_page = True
                    continue

            title = m.group("title").strip()
            if not _is_md_related(title):
                continue

            raw_url = m.group("url")
            full_url = raw_url if raw_url.startswith("http") else BASE + raw_url
            candidates.append({"title": title, "url": full_url, "pub_date": pub_date})

        if found_on_page == 0 or stop_after_page:
            break

    # 페이지 경계에서 같은 글이 중복 매칭될 수 있어 URL 기준으로 중복 제거
    seen = set()
    unique_candidates = []
    for c in candidates:
        if c["url"] in seen:
            continue
        seen.add(c["url"])
        unique_candidates.append(c)

    results = []
    for c in unique_candidates:
        body_text, status = _fetch_detail(c["url"])
        doc_no = _extract_mdcg_no(c["title"]) or c["title"][:40]

        prev = load_previous_snapshot("MDCG", doc_no)
        gap = generate_gap(prev, body_text or c["title"])
        if body_text:
            save_snapshot("MDCG", doc_no, body_text)

        summary_source = body_text or c["title"]
        results.append({
            "search_month": c["pub_date"][:7],
            "publish_date": c["pub_date"],
            "effective_date": None,
            "publisher": "MDCG (EU)",
            "doc_no": doc_no,
            "title": c["title"],
            "summary": summarize(c["title"], summary_source) + (
                "" if body_text else f"\n\n(첨부 원문 확보 실패: {status})"),
            "scope": guess_scope(c["title"] + " " + summary_source),
            "sop_required": "★" if guess_sop_flag(c["title"] + " " + summary_source) else "",
            "url": c["url"],
            "gap_analysis": gap,
        })

    return results, None


def _extract_mdcg_no(title):
    m = re.search(r"MDCG\s*\d{4}-\d+(\s*rev\.?\s*\d+)?", title, re.IGNORECASE)
    return m.group(0) if m else None


def _fetch_detail(url):
    """상세 페이지에서 첨부파일(/document/download/...?filename=실제파일명.pdf)을 찾아 텍스트를 추출한다.
    filename 쿼리파라미터로 실제 확장자를 알 수 있어 PDF/DOCX 여부를 추측하지 않아도 된다."""
    res = fetch(url)
    if not res.ok:
        return "", res.error or "상세 페이지 접속 실패"

    dl = DOWNLOAD_RE.search(res.text)
    if dl:
        file_url = dl.group("url")
        qs = parse_qs(urlparse(file_url).query)
        filename = qs.get("filename", ["file.pdf"])[0]
        content = fetch_binary(file_url)
        if content:
            text, extract_status = extract_text(content, filename)
            if text:
                return text, "OK (첨부 원문)"
            return "", f"첨부파일 추출 실패: {extract_status}"

    # 첨부가 없으면 본문 HTML에서 태그만 제거한 대략적인 텍스트라도 사용
    text_only = re.sub(r"<[^>]+>", " ", res.text)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    return text_only[:5000], "OK (첨부 없음 — 본문 HTML 발췌)"


if __name__ == "__main__":
    found, block = run(today_only=True)
    print(f"오늘자 수집 {len(found)}건")
    for f in found:
        print(" -", f["title"], f["url"])
