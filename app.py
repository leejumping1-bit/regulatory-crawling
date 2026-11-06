import streamlit as st
import pandas as pd
import io
import textwrap
import requests
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

from collectors.store import load_regulations
from collectors.mfds_pdf_display import evidence_for_item, load_evidence_images
from app_logic import (
    effective_month,
    filter_by_month,
    effective_publisher,
    filter_by_publisher,
    estimate_export_row_height,
    extract_core_content,
    display_doc_no,
    mdsap_status_is_stale,
)

PERMANENT_UPDATE_WORKFLOW_URL = (
    "https://github.com/leejumping1-bit/regulatory-crawling/"
    "actions/workflows/scheduled_crawl.yml"
)

st.set_page_config(
    page_title="국내외 규격 및 가이던스 업데이트 검토대장",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def render_html(html: str):
    """Streamlit 마크다운은 4칸 이상 들여쓰기된 줄을 코드블록으로 인식해 HTML을
    그대로 문자로 출력해버리는 버그가 있다. 각 줄의 선행 공백을 제거해서 방지한다."""
    flat = "\n".join(line.strip() for line in html.strip().splitlines())
    st.markdown(flat, unsafe_allow_html=True)


def render_mfds_pdf_evidence(ui, item):
    evidence = evidence_for_item(item)
    if evidence is None:
        return
    ui.markdown('**식약처 공식 신구조문대비표 원본**')
    ui.caption('대비표 시작 쪽부터 PDF 마지막 쪽까지 표시하므로 표 외 내용이 포함될 수 있습니다.')
    ui.link_button('공식 첨부 PDF', evidence['source_url'])
    try:
        images = load_evidence_images(item, evidence)
        for number, image in images:
            ui.image(image, caption=f'공식 PDF {number}쪽', use_container_width=True)
    except Exception:
        ui.warning('공식 PDF 이미지 표시 실패: 원본 접근 또는 무결성 검증에 실패했습니다. 공식 첨부 PDF를 확인하세요.')


def render_revision_evidence(ui, item):
    """Display collector-supplied evidence; never infer changes from missing data."""
    evidence = item.get("revision_evidence")
    if not isinstance(evidence, dict):
        ui.info("개정 내역이 검증되지 않았습니다. 공식 원문을 확인하세요.")
        return

    def valid_url(value):
        if not isinstance(value, str):
            return False
        try:
            parts = urlsplit(value)
            return parts.scheme in ("http", "https") and bool(parts.hostname)
        except ValueError:
            return False

    current = evidence.get("current_url")
    previous = evidence.get("previous_url")
    status = evidence.get("status")
    sections = evidence.get("sections")
    sections = sections if isinstance(sections, list) else []
    sections = [s for s in sections if isinstance(s, dict)
                and isinstance(s.get("quote"), str) and s["quote"].strip()]
    explanation = evidence.get("explanation")

    if status == "revision_history" and valid_url(current) and sections:
        ui.markdown("**공식 개정 이력 원문**")
        for section in sections:
            if isinstance(section.get("title"), str) and section["title"].strip():
                ui.text(section["title"])
            ui.text(section["quote"])
        ui.link_button("개정 이력 출처 (현재 공식 문서)", current)
    elif (status == "verified_comparison" and evidence.get("previous_available") is True
          and valid_url(previous) and valid_url(current)
          and isinstance(explanation, str) and explanation.strip()):
        ui.markdown("**공식 이전·현재 버전 대조 결과**")
        ui.text(explanation)
        ui.link_button("이전 버전 출처", previous)
        ui.link_button("현재 버전 출처", current)
    elif (status == "archived_comparison" and valid_url(current) and valid_url(previous)
          and isinstance(evidence.get("changes"), list) and evidence["changes"]):
        ui.markdown("**개정 내용 — 외부 보관본과 공식 현행본 비교**")
        ui.caption("이전 자료는 발행기관 사이트가 아닌 외부 보관본이며, 발행기관 사이트의 이전 버전 확인은 완료되지 않았습니다.")
        if isinstance(explanation, str) and explanation.strip():
            ui.markdown("**확인된 주요 변경**")
            ui.text(explanation)
        for change in evidence["changes"]:
            if isinstance(change, dict):
                ui.markdown(f"**이전 (외부 보관본, {change.get('before_page', '?')}쪽)**")
                ui.text(str(change.get("before", "")))
                ui.markdown(f"**현재 (공식 문서, {change.get('after_page', '?')}쪽)**")
                ui.text(str(change.get("after", "")))
        ui.link_button("외부 보관본 출처", previous)
        ui.link_button("현재 공식 문서 출처", current)
        ui.warning("이전 버전 확인 실패 — 발행기관 사이트 검색이 완료되지 않았습니다.")
    elif status == "discovery_incomplete":
        ui.warning("이전 버전 확인 실패 — 공식 사이트 검색이나 원문 검증을 완료하지 못했습니다.")
        ui.caption("과거 이력 확인 실패: 변경 여부를 단정할 수 없습니다.")
        if valid_url(current):
            ui.link_button("현재 버전 출처", current)
    else:
        ui.info("개정 내역이 검증되지 않았습니다. 공식 원문을 확인하세요.")
        if valid_url(current):
            ui.link_button("현재 버전 출처", current)

    if evidence.get("previous_available") is False and status != "archived_comparison":
        ui.warning("이전 버전: 찾을 수 없음")
        ui.caption("이전 버전이 없어 직접 대조할 수 없습니다. 자료가 없다는 사실만으로 변경 여부를 단정할 수 없습니다.")


st.markdown(textwrap.dedent("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;900&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

:root {
  --navy-950:#0b1220; --navy-900:#101a30; --navy-800:#16223d;
  --slate-100:#f4f6fb; --slate-200:#e7eaf3; --slate-300:#d3d8e6; --slate-500:#697390;
  --teal:#0f8b8d; --teal-dark:#0b6668; --amber:#c8811a;
}

html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
.stApp { background: var(--slate-100); }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: visible; }
.block-container { padding-top: 1.4rem; max-width: 1180px; }

/* 상단 배너 */
.rw-topbar {
  background: linear-gradient(120deg, var(--navy-950) 0%, var(--navy-800) 100%);
  border-bottom: 3px solid var(--teal); border-radius: 10px;
  padding: 18px 22px; margin-bottom: 18px; color: #fff;
  display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:12px;
}
.rw-brand { display:flex; align-items:center; gap:14px; }
.rw-brand-mark {
  font-family:'IBM Plex Mono',monospace; font-weight:600; font-size:12px; letter-spacing:.12em;
  background:rgba(15,139,141,.25); border:1px solid var(--teal); color:#8fe3e4;
  padding:6px 10px; border-radius:6px; white-space:nowrap;
}
.rw-brand h1 { font-size:19px; margin:0 0 2px; font-weight:700; }
.rw-brand p { margin:0; font-size:12.5px; color:#9fb0d6; font-family:'IBM Plex Mono',monospace; }
.rw-topbar-meta { font-size:12px; color:#b9c4e0; font-family:'IBM Plex Mono',monospace; text-align:right; }

/* 컨트롤바(월선택/다운로드/수동업데이트) */
.rw-controlbar-label { font-size:11.5px; font-weight:600; color:var(--slate-500); margin-bottom:2px; }

/* 패널 헤더 */
.rw-panel-head { display:flex; align-items:center; gap:10px; margin: 4px 0 10px; }
.rw-panel-head h2 { font-size:16px; margin:0; font-weight:700; color:var(--navy-900); }
.rw-panel-head .rw-subtle { font-size:12.5px; font-weight:400; color:var(--slate-500); }
.rw-step {
  font-family:'IBM Plex Mono',monospace; font-size:11px; font-weight:600; color:#fff;
  background:var(--navy-800); border-radius:5px; padding:3px 7px;
}

/* 카드(container border) 스타일 */
div[data-testid="stVerticalBlockBorderWrapper"] {
  background:#fff; border:1px solid var(--slate-300) !important; border-radius:10px !important;
  box-shadow:0 1px 2px rgba(16,26,48,.04); padding: 4px;
}

/* 버튼 - 틸 색상 */
.stButton>button, .stDownloadButton>button {
  background: var(--teal); color:#fff; border:none; border-radius:7px; font-weight:600;
}
.stButton>button:hover, .stDownloadButton>button:hover { filter: brightness(1.08); color:#fff; }

.reg-table-container { width: 100%; overflow-x: auto; margin-bottom: 6px; }
.reg-table { width: 100%; border-collapse: collapse; font-size: 12.8px; background:#fff; }
.reg-table th {
  background:var(--navy-900); color:#e7ecfa; font-weight:700; text-align:center;
  vertical-align:middle; padding:9px 8px; border:1px solid #223154; white-space:nowrap; font-size:11.5px;
}
.reg-table td {
  text-align:center; vertical-align:middle; padding:9px 8px; border:1px solid #dee2e6;
  word-break:keep-all; white-space:normal; line-height:1.5;
}
.reg-table td.date-cell { white-space:nowrap; }
.reg-table td.title-cell { text-align:left; }
.reg-table td.title-cell a { color:var(--teal-dark); text-decoration:underline; font-weight:600; }
.reg-table tr:hover td { background:#f1f6f8; }
.reg-scope-tag { display:inline-block; font-size:11px; font-weight:600; padding:2px 8px; border-radius:99px; background:var(--slate-100); color:var(--navy-900); }

.summary-card { background:var(--slate-100); border-left:4px solid var(--teal); padding:16px; border-radius:0 8px 8px 0; margin-bottom:6px; }
</style>
"""), unsafe_allow_html=True)

DEFAULT_SINCE = "2026-01"
REMOTE_DATA_URL = (
    "https://raw.githubusercontent.com/leejumping1-bit/regulatory-crawling/"
    "main/data/regulations.json"
)


REMOTE_MDSAP_STATUS_URL = REMOTE_DATA_URL.rsplit("/", 1)[0] + "/mdsap_status.json"


@st.cache_data(ttl=60)
def _load_mdsap_status():
    # Never substitute the app's local file for the durable remote status.
    try:
        response = requests.get(REMOTE_MDSAP_STATUS_URL, timeout=15, headers={"Accept": "application/json"})
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict) or value.get("status") not in ("ok", "error"):
            raise ValueError("invalid status")
        checked = datetime.fromisoformat(value["checked_at"])
        if checked.utcoffset() is None:
            raise ValueError("timestamp must have a timezone")
        return value
    except Exception:
        return None


@st.cache_data(ttl=60)
def _load():
    """Use the GitHub Actions artifact as the app's source of truth."""
    try:
        response = requests.get(
            REMOTE_DATA_URL,
            timeout=15,
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        remote_data = response.json()
        if not isinstance(remote_data, list):
            raise ValueError("remote regulations payload is not a list")
        return remote_data, "github-main"
    except Exception as exc:
        print(f"[app] remote dataset unavailable; using local fallback: {exc}")
        return load_regulations(), "local-fallback"


data, data_source = _load()


# ==================== 상단 배너 ====================
render_html(f"""
<div class="rw-topbar">
  <div class="rw-brand">
    <span class="rw-brand-mark">RA/QA</span>
    <div>
      <h1>국내외 규격 및 가이던스 업데이트 검토대장</h1>
      <p>Global Regulatory &amp; Standards Watch — Gap Analysis Console</p>
    </div>
  </div>
  <div class="rw-topbar-meta">수집 항목 {len(data)}건 · 8개 기관 모니터링</div>
</div>
""")

# ==================== 상단 컨트롤바 ====================
ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([1.35, 1.35, 1.4, 1.4])

month_options = ["전체"] + sorted({effective_month(item) for item in data}, reverse=True)
if len(month_options) == 1:
    month_options.append(date.today().strftime("%Y-%m"))

with ctrl1:
    st.markdown('<div class="rw-controlbar-label">📅 조회 월 선택 (기본: 전체)</div>', unsafe_allow_html=True)
    selected_month = st.selectbox("조회 월", month_options, index=0, label_visibility="collapsed")
    if selected_month == "UNKNOWN":
        st.caption("⚠ 날짜를 파싱하지 못한 항목들입니다 (수집기 점검 필요).")

publisher_options = ["전체"] + sorted({effective_publisher(item) for item in data})

with ctrl2:
    st.markdown('<div class="rw-controlbar-label">🏢 발행처 선택 (기본: 전체)</div>', unsafe_allow_html=True)
    selected_publisher = st.selectbox("발행처", publisher_options, index=0, label_visibility="collapsed")

filtered_data = filter_by_publisher(filter_by_month(data, selected_month), selected_publisher)

with ctrl3:
    st.markdown('<div class="rw-controlbar-label">📥 검토대장 다운로드</div>', unsafe_allow_html=True)
    if filtered_data:
        export_rows = []
        for item in filtered_data:
            core_content = extract_core_content(item.get("summary"))
            obligation = item.get("manufacturer_obligation", item.get("sop_required")) or ""
            export_rows.append({
                "No.": item["no"],
                "고시일 Published Date": item.get("publish_date") or "",
                "개정·업데이트일 Revision or update date": item.get("change_date") or item.get("revision_date") or "",
                "시행일 Effectiveness Date": item.get("effective_date") or "",
                "발행처 Published by": item.get("publisher") or "",
                "규격 및 가이던스 번호 Regulation & Guidance No.": display_doc_no(item),
                "제목 Title": item.get("title") or "",
                "내용요약 Summary": item.get("summary") or "",
                "적용 범위 Scope": item.get("scope") or "",
                "Manufacturer obligation": (obligation + "\n[핵심 내용]\n" + core_content).strip()
                    if core_content else obligation,
            })
        df_export = pd.DataFrame(export_rows)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Sheet1")
            workbook = writer.book
            worksheet = writer.sheets["Sheet1"]
            base = workbook.add_format({
                "font_name": "맑은 고딕",
                "font_size": 9,
                "valign": "vcenter",
                "text_wrap": True,
                "border": 1,
                "border_color": "#D9E1F2",
            })
            centered = workbook.add_format({
                "font_name": "맑은 고딕",
                "font_size": 9,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "border": 1,
                "border_color": "#D9E1F2",
            })
            header = workbook.add_format({
                "font_name": "맑은 고딕",
                "font_size": 9,
                "bold": True,
                "font_color": "#FFFFFF",
                "bg_color": "#16223D",
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "border": 1,
                "border_color": "#223154",
            })
            worksheet.set_row(0, 30, header)
            worksheet.set_column("A:A", 6, centered)
            worksheet.set_column("B:D", 14, centered)
            worksheet.set_column("E:E", 18, centered)
            worksheet.set_column("F:F", 28, centered)
            worksheet.set_column("G:G", 48, centered)
            worksheet.set_column("H:H", 38, base)
            worksheet.set_column("I:I", 20, centered)
            worksheet.set_column("J:J", 58, centered)
            worksheet.autofilter(0, 0, len(df_export), len(df_export.columns) - 1)
            worksheet.freeze_panes(1, 0)
            widths = [6, 14, 14, 14, 18, 28, 48, 38, 20, 58]
            for excel_row, row_values in enumerate(df_export.itertuples(index=False, name=None), start=1):
                worksheet.set_row(
                    excel_row,
                    estimate_export_row_height(row_values, widths),
                )
            if hasattr(worksheet, "autofit"):
                worksheet.autofit()
                # Keep the readable layout even when a single long title tries
                # to turn the sheet into a horizontal scroll simulator.
                worksheet.set_column("F:F", 48, centered)
                worksheet.set_column("I:I", 58, centered)
        st.download_button(
            "엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"국내외_규격_및_가이던스_업데이트_검토_대장_{selected_month}_{selected_publisher}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        st.button("엑셀 다운로드", disabled=True, use_container_width=True)

with ctrl4:
    st.markdown('<div class="rw-controlbar-label">🔄 데이터 업데이트</div>', unsafe_allow_html=True)
    st.link_button(
        "갱신",
        PERMANENT_UPDATE_WORKFLOW_URL,
        use_container_width=True,
        help="GitHub Actions에서 Run workflow를 누르면 영구 데이터에 반영됩니다.",
    )

source_label = {
    "github-main": "GitHub main 영구 데이터 (백그라운드 수집 결과)",
    "local-fallback": "앱 로컬 fallback 데이터 (GitHub 접근 실패)",
}.get(data_source, data_source)
st.caption(
    f"데이터 출처: {source_label} · 확인시각: "
    f"{datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}"
)

mdsap_status = _load_mdsap_status()
if mdsap_status is None:
    st.warning("MDSAP 수집 상태 확인 불가: GitHub 영구 상태를 가져오지 못했거나 아직 없습니다.")
elif mdsap_status_is_stale(mdsap_status['checked_at']):
    st.warning(f"MDSAP 수집 상태 오래됨: 마지막 확인 {mdsap_status['checked_at']} (48시간 초과 또는 시계 오류)")
elif mdsap_status["status"] == "error":
    st.warning(f"MDSAP 수집 실패 또는 부분 수집 · 확인 시각: {mdsap_status['checked_at']} (상세 내용은 Actions 로그 확인)")
else:
    st.success(f"MDSAP 수집 완료 · 확인 시각: {mdsap_status['checked_at']} (변경 없음이나 전체 범위 확인을 의미하지 않음)")

st.caption(
    "MFDS는 robots.txt 상 자동접근 비권장 사이트이나, 비상업적 사내 QA 모니터링 목적으로 "
    "서버 부담을 최소화(요청 간 딜레이 적용)하며 수집합니다."
)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

if not filtered_data:
    st.info("해당 조건의 데이터가 없습니다. 갱신을 통해 GitHub Actions에서 업데이트를 실행할 수 있습니다.")
    st.stop()

# ==================== 1. 검토대장 ====================
with st.container(border=True):
    render_html('<div class="rw-panel-head"><span class="rw-step">01</span>'
                '<h2>국내외 규격 및 가이던스 검토대장</h2></div>')

    rows_html = ""
    for item in filtered_data:
        doc_no_clean = display_doc_no(item)
        manufacturer_obligation = item.get("manufacturer_obligation", item.get("sop_required")) or ""
        rows_html += (
            f'<tr>'
            f'<td>{item["no"]}</td>'
            f'<td class="date-cell">{item.get("publish_date") or "-"}</td>'
            f'<td class="date-cell">{item.get("change_date") or item.get("revision_date") or "-"}</td>'
            f'<td class="date-cell">{item.get("effective_date") or "-"}</td>'
            f'<td>{item.get("publisher") or "-"}</td>'
            f'<td>{doc_no_clean}</td>'
            f'<td class="title-cell"><a href="{item.get("url") or "#"}" target="_blank">{item["title"]}</a></td>'
            f'<td><span class="reg-scope-tag">{item.get("scope") or "-"}</span></td>'
            f'<td style="color:var(--amber);font-weight:bold;">{manufacturer_obligation}</td>'
            f'</tr>'
        )

    table_html = (
        '<div class="reg-table-container"><table class="reg-table"><thead><tr>'
        '<th style="width:5%;">No.</th><th style="width:9%;">고시일</th>'
        '<th style="width:10%;">개정·업데이트일</th><th style="width:9%;">시행일</th><th style="width:12%;">발행처</th>'
        '<th style="width:14%;">규격/가이던스 번호</th><th style="width:34%;">제목 (클릭 시 이동)</th>'
        '<th style="width:11%;">적용범위</th><th style="width:12%;">Manufacturer<br>obligation</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
    )
    render_html(table_html)
    st.caption(f"조회 월: {selected_month} · 발행처: {selected_publisher} · 총 {len(filtered_data)}건")

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

# ==================== 2. 요약 ====================
with st.container(border=True):
    render_html('<div class="rw-panel-head"><span class="rw-step">02</span>'
                '<h2>업데이트 내용 요약 <span class="rw-subtle">— 선택 항목 원문 또는 요약</span></h2></div>')

    selected_no = st.selectbox(
        "GAP 분석 및 세부 요약을 확인할 규격 [No.]를 선택하세요:",
        options=[item["no"] for item in filtered_data],
        format_func=lambda x: f"No. {x} - {next(i['title'] for i in filtered_data if i['no'] == x)}",
    )
    selected_item = next(item for item in filtered_data if item["no"] == selected_no)

    summary_html = (
        '<div class="summary-card">'
        f'<h4>📌 {selected_item["title"]}</h4>'
        f'<p><b>• 규격 번호:</b> {display_doc_no(selected_item)} '
        f'| <b>발행처:</b> {selected_item.get("publisher") or "-"}</p>'
        f'<p><b>• 적용 범위:</b> {selected_item.get("scope") or "-"} '
        f'| <b>Manufacturer obligation:</b> <span style="color:var(--amber);font-weight:bold;">{selected_item.get("manufacturer_obligation", selected_item.get("sop_required")) or "-"}</span></p>'
        '<hr><p><b>[요약 내용]</b></p>'
        f'<p>{(selected_item.get("summary") or "").replace(chr(10), "<br>")}</p>'
        '</div>'
    )
    render_html(summary_html)
    if selected_item.get("document_status") in ("draft", "final"):
        st.caption("문서 상태: " + ("초안" if selected_item["document_status"] == "draft" else "최종 규칙·최종 안내"))
    if selected_item.get("summary_retained_stale"):
        st.warning("원문 재조회에 실패해 이전에 저장한 요약을 표시합니다. 최신 여부는 확인되지 않았습니다.")

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

# ==================== 3. 개정 이력 ====================
with st.container(border=True):
    render_html('<div class="rw-panel-head"><span class="rw-step">03</span>'
                '<h2>개정 이력 <span class="rw-subtle">— 공식 출처 기반</span></h2></div>')
    render_revision_evidence(st, selected_item)
    render_mfds_pdf_evidence(st, selected_item)

st.markdown(
    "<p style='text-align:center;font-size:11px;color:var(--slate-500);padding:14px 0;'>"
    "데이터 출처: MFDS · MDCG(EU) · FDA(US) · MHRA(UK) · MDSAP · TGA(AU) · Health Canada · PMDA(JP). "
    "각 항목의 원문 링크에서 최종 확인하시기 바랍니다.</p>",
    unsafe_allow_html=True,
)
