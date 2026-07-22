import streamlit as st
import pandas as pd
import io
import textwrap
from datetime import date

from collectors.store import load_regulations

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
.reg-table td.title-cell { text-align:left; }
.reg-table td.title-cell a { color:var(--teal-dark); text-decoration:underline; font-weight:600; }
.reg-table tr:hover td { background:#f1f6f8; }
.reg-scope-tag { display:inline-block; font-size:11px; font-weight:600; padding:2px 8px; border-radius:99px; background:var(--slate-100); color:var(--navy-900); }

.diff-box {
  background:#fff; border:1px solid #d0d7de; border-radius:6px; padding:16px;
  font-family:'IBM Plex Mono','Courier New',monospace; line-height:1.8; font-size:13px;
}
.diff-del { background:#ffebe9; color:#cf222e; text-decoration:line-through; padding:2px 4px; border-radius:3px; }
.diff-add { background:#e6ffec; color:#1a7f37; font-weight:700; padding:2px 4px; border-radius:3px; }
.diff-omit { color:#6e7781; font-style:italic; margin:8px 0; }
.summary-card { background:var(--slate-100); border-left:4px solid var(--teal); padding:16px; border-radius:0 8px 8px 0; margin-bottom:6px; }
</style>
"""), unsafe_allow_html=True)

DEFAULT_SINCE = "2026-01"


@st.cache_data(ttl=5)
def _load():
    return load_regulations()


data = _load()


def effective_month(item):
    """날짜 파싱에 실패한 항목도 조용히 사라지지 않도록 'UNKNOWN' 버킷으로 분류."""
    return item.get("search_month") or "UNKNOWN"


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
ctrl1, ctrl2, ctrl3 = st.columns([2, 1.4, 1.4])

all_months = sorted({effective_month(item) for item in data}, reverse=True)
if not all_months:
    all_months = [date.today().strftime("%Y-%m")]

with ctrl1:
    st.markdown('<div class="rw-controlbar-label">📅 조회 월 선택</div>', unsafe_allow_html=True)
    selected_month = st.selectbox("조회 월", all_months, index=0, label_visibility="collapsed")
    if selected_month == "UNKNOWN":
        st.caption("⚠ 날짜를 파싱하지 못한 항목들입니다 (수집기 점검 필요).")

filtered_data = [d for d in data if effective_month(d) == selected_month]

with ctrl2:
    st.markdown('<div class="rw-controlbar-label">📥 검토대장 다운로드</div>', unsafe_allow_html=True)
    if filtered_data:
        df_export = pd.DataFrame([{
            "No.": item["no"],
            "고시일 Published Date": item.get("publish_date") or "",
            "시행일 Effectiveness Date": item.get("effective_date") or "",
            "발행처 Published by": item.get("publisher") or "",
            "규격 및 가이던스 번호 Regulation & Guidance No.": (item.get("doc_no") or "").replace("\n", " "),
            "제목 Title": item.get("title") or "",
            "내용요약 Summary": item.get("summary") or "",
            "적용 범위 Scope": item.get("scope") or "",
            "SOP": item.get("sop_required") or "",
            "원문 링크": item.get("url") or "",
        } for item in filtered_data])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Sheet1")
        st.download_button(
            "엑셀 다운로드",
            data=output.getvalue(),
            file_name=f"국내외_규격_및_가이던스_업데이트_검토_대장_{selected_month}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    else:
        st.button("엑셀 다운로드", disabled=True, use_container_width=True)

with ctrl3:
    st.markdown('<div class="rw-controlbar-label">🔄 데이터 수동 업데이트</div>', unsafe_allow_html=True)
    run_clicked = st.button("지금 실행 (8개 기관)", use_container_width=True)
    if run_clicked:
        from crawler import run_crawler
        since_y, since_m = int(DEFAULT_SINCE[:4]), int(DEFAULT_SINCE[5:7])

        progress_box = st.empty()
        log_lines = []

        def _progress(agency_key, status):
            log_lines.append(f"· {agency_key}: {status}")
            progress_box.markdown("\n\n".join(log_lines))

        with st.spinner("최신 데이터를 수집 중입니다... (기관별로 끝나는 대로 즉시 저장됩니다)"):
            saved, summary = run_crawler(since_y, since_m, progress_cb=_progress)
            st.cache_data.clear()
        st.success(f"완료! 총 {len(saved)}건 저장됨")
        st.rerun()

st.caption(
    "⚠ 이 버튼으로 수집한 데이터는 이 앱이 실행 중인 서버(임시 저장소)에만 반영됩니다. "
    "GitHub 저장소에는 커밋되지 않으므로, 앱이 재시작되면 사라질 수 있습니다. "
    "영구 반영은 매일 아침 9시(KST) GitHub Actions 자동 수집이 담당합니다."
)

st.caption(
    "MFDS는 robots.txt 상 자동접근 비권장 사이트이나, 비상업적 사내 QA 모니터링 목적으로 "
    "서버 부담을 최소화(요청 간 딜레이 적용)하며 수집합니다."
)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

if not filtered_data:
    st.info("해당 월의 데이터가 없습니다. 상단의 '지금 실행' 버튼을 눌러 데이터를 수집해주세요.")
    st.stop()

# ==================== 1. 검토대장 ====================
with st.container(border=True):
    render_html('<div class="rw-panel-head"><span class="rw-step">01</span>'
                '<h2>국내외 규격 및 가이던스 검토대장</h2></div>')

    rows_html = ""
    for item in filtered_data:
        doc_no_clean = (item.get("doc_no") or "").replace("\n", " ")
        sop = item.get("sop_required") or ""
        rows_html += (
            f'<tr>'
            f'<td>{item["no"]}</td>'
            f'<td>{item.get("publish_date") or "-"}</td>'
            f'<td>{item.get("effective_date") or "-"}</td>'
            f'<td>{item.get("publisher") or "-"}</td>'
            f'<td>{doc_no_clean}</td>'
            f'<td class="title-cell"><a href="{item.get("url") or "#"}" target="_blank">{item["title"]}</a></td>'
            f'<td><span class="reg-scope-tag">{item.get("scope") or "-"}</span></td>'
            f'<td style="color:var(--amber);font-weight:bold;">{sop}</td>'
            f'</tr>'
        )

    table_html = (
        '<div class="reg-table-container"><table class="reg-table"><thead><tr>'
        '<th style="width:5%;">No.</th><th style="width:9%;">고시일</th>'
        '<th style="width:9%;">시행일</th><th style="width:12%;">발행처</th>'
        '<th style="width:14%;">규격/가이던스 번호</th><th style="width:34%;">제목 (클릭 시 이동)</th>'
        '<th style="width:11%;">적용범위</th><th style="width:6%;">SOP</th>'
        f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
    )
    render_html(table_html)
    st.caption(f"조회 월: {selected_month} · 총 {len(filtered_data)}건")

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

# ==================== 2. 요약 ====================
with st.container(border=True):
    render_html('<div class="rw-panel-head"><span class="rw-step">02</span>'
                '<h2>업데이트 내용 요약 <span class="rw-subtle">— 선택 항목 자동 요약(심사원 관점)</span></h2></div>')

    selected_no = st.selectbox(
        "GAP 분석 및 세부 요약을 확인할 규격 [No.]를 선택하세요:",
        options=[item["no"] for item in filtered_data],
        format_func=lambda x: f"No. {x} - {next(i['title'] for i in filtered_data if i['no'] == x)}",
    )
    selected_item = next(item for item in filtered_data if item["no"] == selected_no)

    summary_html = (
        '<div class="summary-card">'
        f'<h4>📌 {selected_item["title"]}</h4>'
        f'<p><b>• 규격 번호:</b> {(selected_item.get("doc_no") or "").replace(chr(10), " ")} '
        f'| <b>발행처:</b> {selected_item.get("publisher") or "-"}</p>'
        f'<p><b>• 적용 범위:</b> {selected_item.get("scope") or "-"} '
        f'| <b>SOP 반영 필요:</b> <span style="color:var(--amber);font-weight:bold;">{selected_item.get("sop_required") or "-"}</span></p>'
        '<hr><p><b>[요약 내용]</b></p>'
        f'<p>{(selected_item.get("summary") or "").replace(chr(10), "<br>")}</p>'
        '</div>'
    )
    render_html(summary_html)

st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

# ==================== 3. Gap 분석 ====================
with st.container(border=True):
    render_html('<div class="rw-panel-head"><span class="rw-step">03</span>'
                '<h2>Gap 분석 <span class="rw-subtle">— 개정 전/후 원문 대조</span></h2></div>')

    gap_data = selected_item.get("gap_analysis", {})

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**과거 규격 내용**")
        st.info(gap_data.get("past_text") or "N.A.")
    with col2:
        st.markdown("**현재 규격 내용**")
        st.success(gap_data.get("present_text") or "N.A.")

    st.markdown("#### 🔍 CanLII Webdiff 스타일 문맥 비교")
    st.caption("🔴 삭제된 문구 | 🟢 신규/업데이트 문구")
    diff_html = gap_data.get("diff_html") or "변경사항이 없거나 신규 제정건입니다."
    render_html(f'<div class="diff-box">{diff_html}</div>')

st.markdown(
    "<p style='text-align:center;font-size:11px;color:var(--slate-500);padding:14px 0;'>"
    "데이터 출처: MFDS · MDCG(EU) · FDA(US) · MHRA(UK) · MDSAP · TGA(AU) · Health Canada · PMDA(JP). "
    "각 항목의 원문 링크에서 최종 확인하시기 바랍니다.</p>",
    unsafe_allow_html=True,
)
