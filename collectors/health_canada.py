"""
Health Canada 수집기 — v2 (전문 텍스트 Gap 분석 강화)

사용자 요청: 법 원문이 통째로 교체되는 문서이므로 CanLII webdiff처럼 개정 전/후
전문(全文)을 비교하는 것이 중요하다.

이번 버전에서 바뀐 점: 이전에는 "last amended on" 날짜 문구만 확인하고 그 문장을
Gap 분석 대상으로 삼았는데, 이러면 실제로 뭐가 바뀌었는지 알 수 없다. 이번에는
페이지의 조문 본문 전체(article/main 영역)를 긁어와서, 우리가 직전에 저장해둔
스냅샷과 전문 대 전문으로 비교한다.

한계(정직하게 명시): laws-lois.justice.gc.ca가 공식적으로 제공하는 "이전 버전" 아카이브
페이지의 정확한 URL 패턴을 이 환경에서 검증하지 못했다. 따라서 진짜 "정부가 보관한
과거 버전"과 비교하는 대신, 우리가 이 시스템으로 마지막에 수집했을 때 저장해둔 전문과
비교한다 — 즉 최초 수집 시점 이후의 변경사항부터 정확히 잡아낼 수 있다(최초 1회는
비교 대상이 없어 N.A.로 표시된다).
"""
import re
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch  # noqa: E402
from collectors.summarizer import summarize, guess_scope, guess_manufacturer_obligation  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

REGULATION_URL = "https://laws-lois.justice.gc.ca/eng/regulations/sor-98-282/"
AMENDED_RE = re.compile(r"last amended on (\d{4}-\d{2}-\d{2})", re.IGNORECASE)
DOC_NO = "SOR/98-282"


def _extract_dates(text):
    """페이지에서 마지막 개정일만 추출한다. ``current to``는 사용하지 않는다."""
    amended = AMENDED_RE.search(text or "")
    return amended.group(1) if amended else None


def _clean_regulation_text(text):
    """Remove Justice Laws navigation/boilerplate before paragraph diffing."""
    kept = []
    for line in text.splitlines():
        value = " ".join(line.split()).strip()
        low = value.lower()
        if not value:
            continue
        if value in {"Previous Version", "Previous Versions", "Language selection", "Français"}:
            continue
        if low.startswith(("full document:", "accessibility buttons available", "regulations are current to", "this web page has been archived on the web")):
            continue
        kept.append(value)
    return "\n".join(kept)


def _historical_version_url(current_date):
    """Justice Canada PITIndex에서 현재 버전 직전의 공식 전문 URL을 찾는다."""
    res = fetch(REGULATION_URL + "PITIndex.html")
    if not res.ok or BeautifulSoup is None:
        return None
    soup = BeautifulSoup(res.text, "html.parser")
    versions = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"From\s+(\d{4}-\d{2}-\d{2})", a.get_text(" ", strip=True))
        if m:
            href = a["href"]
            if not href.startswith("http"):
                href = REGULATION_URL + href.lstrip("/")
            versions.append((m.group(1), href))
    older = sorted((v for v in versions if v[0] < current_date), reverse=True)
    return older[0][1] if older else None


def _fetch_full_text(url):
    if not url:
        return ""
    if url.rstrip("/") == REGULATION_URL.rstrip("/"):
        url = REGULATION_URL + "FullText.html"
    res = fetch(url)
    if not res.ok or BeautifulSoup is None:
        return ""
    soup = BeautifulSoup(res.text, "html.parser")
    sections = soup.find_all("section")
    main = max(sections, key=lambda node: len(node.get_text(" ", strip=True)), default=None)
    main = main or soup.select_one("main") or soup.select_one("#wb-cont") or soup.select_one("#regContent") or soup.body
    return _clean_regulation_text(main.get_text("\n", strip=True)) if main else ""


def run(since_year=2026, since_month=1, today_only=False):
    res = fetch(REGULATION_URL)
    if res.robots_disallowed:
        return [], res
    if not res.ok:
        return [], res

    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")
    soup = BeautifulSoup(res.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    last_amended = _extract_dates(page_text)

    if not last_amended:
        print("[health_canada] 'last amended on' 문구를 찾지 못했습니다 (페이지 구조 변경 가능성).")
        return [], None

    y, mo = int(last_amended[:4]), int(last_amended[5:7])
    if today_only:
        from datetime import date
        if last_amended != date.today().isoformat():
            return [], None
    elif (y, mo) < (since_year, since_month):
        return [], None

    # 목록 페이지는 목차만 포함할 수 있으므로 공식 FullText 전문을 사용한다.
    full_text = _fetch_full_text(REGULATION_URL)
    if not full_text:
        sections = soup.find_all("section")
        main = max(sections, key=lambda node: len(node.get_text(" ", strip=True)), default=None)
        main = main or soup.select_one("main") or soup.select_one("#wb-cont") or soup.select_one("#regContent") or soup.body
        full_text = _clean_regulation_text(main.get_text("\n", strip=True)) if main else page_text

    # 매번 공식 PITIndex의 직전 버전을 우선 사용한다. 기존 최신 snapshot을
    # 과거본으로 재사용하면 현재본과 현재본을 비교하는 버그가 발생한다.
    prev_url = _historical_version_url(last_amended)
    prev = _fetch_full_text(prev_url)
    if not prev:
        prev = load_previous_snapshot("Health Canada", DOC_NO)
    gap = generate_gap(prev, full_text)
    save_snapshot("Health Canada", DOC_NO, full_text)

    summary_source = full_text
    title = f"Medical Devices Regulations (SOR/98-282) — {last_amended} 개정 반영본"
    summary = summarize(title, summary_source)
    if not prev:
        summary += "\n\n(※ 이번이 이 시스템의 최초 수집이라 개정 전/후 비교는 다음 개정부터 가능합니다.)"

    item = {
        "search_month": last_amended[:7],
        "publish_date": last_amended,
        # current to는 사용자 요청에 따라 사용하지 않는다.
        "effective_date": None,
        "publisher": "Health Canada",
        "doc_no": DOC_NO,
        "title": title,
        "summary": summary,
        "scope": guess_scope(full_text, title=title, publisher="Health Canada"),
        "manufacturer_obligation": "★" if guess_manufacturer_obligation(title, full_text) else "",
        "url": REGULATION_URL,
        "gap_analysis": gap,
    }
    return [item], None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
