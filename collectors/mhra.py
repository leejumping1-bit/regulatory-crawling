"""
MHRA(UK) 수집기 — v2 (변경이력 changelog 방식)

사용자가 확인해준 대로, MHRA 가이던스 페이지는 하단에 "Last updated: DATE —
See all updates" 를 펼치면 날짜별 변경 이력이 그대로 나온다. 이건 정부가 이미
"무엇이 바뀌었는지" 문장으로 정리해둔 것이므로, 페이지 전체를 스크래핑해서
의료기기 여부를 추측할 필요 없이 이 변경이력 블록만 그대로 가져오면 된다.

대상 2개 페이지:
  1) https://www.gov.uk/guidance/regulating-medical-devices-in-the-uk
  2) https://www.gov.uk/government/collections/medical-devices-guidance-for-manufacturers-on-vigilance

처리 방식:
  - 페이지에서 "Last updated: DATE" 와 그 아래 날짜별 변경이력 항목들을 추출한다.
  - 변경이력 전체 텍스트를 이전에 저장해둔 스냅샷과 비교(diff_engine)한다 —
    새로 추가된 날짜/문구만 "추가"로 표시되고, 기존 항목은 자동으로 접힌다.
  - 페이지에 첨부된 PDF/DOCX가 있으면 함께 추출해 스냅샷에 포함시켜, 변경이력에
    명시되지 않은 첨부파일 자체의 변경도 다음 비교에서 잡히도록 한다.

한계: gov.uk의 정확한 CSS 클래스는 이 환경에서 확인하지 못해, 텍스트 레이아웃
(날짜가 단독 줄에 오고 그 아래 설명이 이어지는 패턴)에 의존한 정규식으로 파싱한다.
실제 배포 후 결과가 이상하면 셀렉터를 조정해야 할 수 있다.
"""
import re
import sys
import os
from datetime import date

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from collectors.http_utils import fetch, fetch_binary  # noqa: E402
from collectors.file_extract import extract_text  # noqa: E402
from collectors.summarizer import summarize, guess_scope  # noqa: E402
from collectors.diff_engine import generate_gap  # noqa: E402
from collectors.store import load_previous_snapshot, save_snapshot  # noqa: E402

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

SOURCES = {
    "MHRA-medical-devices-uk": "https://www.gov.uk/guidance/regulating-medical-devices-in-the-uk",
    "MHRA-vigilance-manufacturers": "https://www.gov.uk/government/collections/medical-devices-guidance-for-manufacturers-on-vigilance",
}

LAST_UPDATED_RE = re.compile(r"Last updated:?\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
DATE_HEADING_RE = re.compile(r"(?:^|\n)(\d{1,2}\s+[A-Za-z]+\s+\d{4})\n")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"])}


def _to_iso(date_text):
    parts = date_text.split()
    if len(parts) != 3:
        return None
    d, mon, y = parts
    mo = MONTHS.get(mon)
    if not mo:
        return None
    try:
        return f"{y}-{mo:02d}-{int(d):02d}"
    except ValueError:
        return None


def _extract_changelog(text):
    matches = list(DATE_HEADING_RE.finditer(text))
    entries = []
    for i, m in enumerate(matches):
        date_str = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else min(len(text), start + 800)
        desc = text[start:end].strip()
        if desc:
            entries.append((date_str, desc))
    return entries


def _extract_attachment_text(soup, page_url):
    for ext in (".pdf", ".docx"):
        a = soup.select_one(f'a[href$="{ext}"]')
        if not a:
            continue
        href = a.get("href")
        file_url = href if href.startswith("http") else "https://www.gov.uk" + href
        content = fetch_binary(file_url)
        if content:
            filename = file_url.rsplit("/", 1)[-1]
            text, status = extract_text(content, filename)
            if text:
                return text
    return ""


def _process_source(doc_no, url, today_only):
    res = fetch(url)
    if res.robots_disallowed:
        return None, res
    if not res.ok:
        return None, res
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 미설치")

    soup = BeautifulSoup(res.text, "html.parser")
    page_text = soup.get_text("\n", strip=True)

    m_last = LAST_UPDATED_RE.search(page_text)
    last_updated_text = m_last.group(1) if m_last else None
    last_updated_iso = _to_iso(last_updated_text) if last_updated_text else None

    if today_only:
        if not last_updated_iso or last_updated_iso != date.today().isoformat():
            return None, None

    entries = _extract_changelog(page_text)
    changelog_text = "\n\n".join(f"[{d}]\n{desc}" for d, desc in entries) or "(변경이력 없음 — 페이지 구조 확인 필요)"

    attachment_text = _extract_attachment_text(soup, url)
    full_snapshot_text = changelog_text + (
        f"\n\n[첨부파일 원문]\n{attachment_text}" if attachment_text else ""
    )

    prev = load_previous_snapshot(doc_no, doc_no)
    gap = generate_gap(prev, full_snapshot_text)
    save_snapshot(doc_no, doc_no, full_snapshot_text)

    title_prefix = soup.title.get_text(strip=True) if soup.title else doc_no
    latest_entry_desc = entries[0][1] if entries else ""
    summary = summarize(title_prefix, latest_entry_desc or changelog_text)
    if not prev:
        summary += "\n\n(※ 이번이 최초 수집이라 개정 전/후 비교는 다음 업데이트부터 가능합니다.)"

    item = {
        "search_month": (last_updated_iso or "")[:7],
        "publish_date": last_updated_iso,
        "effective_date": None,
        "publisher": "MHRA (UK)",
        "doc_no": doc_no,
        "title": f"{title_prefix} — 변경이력 업데이트 ({last_updated_text or '날짜 미확인'})",
        "summary": summary,
        "scope": guess_scope(title_prefix + " " + changelog_text),
        "sop_required": "★",  # 사용자가 명시적으로 지정한 핵심 모니터링 페이지 — 항상 SOP 대상
        "url": url + "#full-publication-update-history",
        "gap_analysis": gap,
    }
    return item, None


def run(since_year=2026, since_month=1, today_only=False):
    results = []
    for doc_no, url in SOURCES.items():
        try:
            item, err = _process_source(doc_no, url, today_only)
        except Exception as e:
            print(f"[mhra] {doc_no} 처리 실패: {e}")
            continue
        if err and getattr(err, "robots_disallowed", False):
            print(f"[mhra] {doc_no} robots.txt 차단")
            continue
        if item:
            results.append(item)
    return results, None


if __name__ == "__main__":
    found, block = run()
    print(f"수집 {len(found)}건")
    for f in found:
        print(" -", f["title"])
