import streamlit as st
import pandas as pd
import io
import textwrap
from datetime import date

from collectors.store import load_regulations, upsert_regulations
from collectors.mfds_manual import process_manual_entry

st.set_page_config(
    page_title="의료기기 규격 및 규제 모니터링 시스템",
    layout="wide",
    initial_sidebar_state="expanded",
)


def render_html(html: str):
    """
    Streamlit(마크다운)은 4칸 이상 들여쓰기된 줄을 코드블록으로 인식해 HTML을
    그대로 문자로 출력해버리는 버그가 있다. 각 줄의 선행 공백을 제거해서 방지한다.
    """
    flat = "\n".join(line.strip() for line in html.strip().splitlines())
    st.markdown(flat, unsafe_allow_html=True)


st.markdown(textwrap.dedent("""
<style>
.reg-table-container { width: 100%; overflow-x: auto; margin-bottom: 20px; }
.reg-table { width: 100%; border-collapse: collapse; font-size: 13.5px; background:#fff; }
.reg-table th {
  background:#12203c; color:#e7ecfa; font-weight:700; text-align:center;
  vertical-align:middle; padding:10px 8px; border:1px solid #223154; white-space:nowrap;
}
.reg-table td {
  text-align:center; vertical-align:middle; padding:9px 8px; border:1px solid #dee2e6;
  word-break:keep-all; white-space:normal; line-height:1.5;
}
.reg-table td.title-cell { text-align:left; }
.reg-table td.title-cell a { color:#0969da; text-decoration:underline; font-weight:600; }
.reg-table tr:hover td { background:#f6f8fa; }
.diff-box {
  background:#fff; border:1px solid #d0d7de; border-radius:6px; padding:16px;
  font-family:'IBM Plex Mono','Courier New',monospace; line-height:1.8; font-size:13px;
}
.diff-del { background:#ffebe9; color:#cf222e; text-decoration:line-through; padding:2px 4px; border-radius:3px; }
.diff-add { background:#e6ffec; color:#1a7f37; font-weight:700; padding:2px 4px; border-radius:3px; }
.diff-omit { color:#6e7781; font-style:italic; margin:8px 0; }
.summary-card { background:#f6f8fa; border-left:4px solid #0969da; padding:16px; border-radius:6px; margin-bottom:20px; }
</style>
"""), unsafe_allow_html=True)

DEFAULT_SINCE = "2026-01"


@st.cache_data(ttl=5)
def _load():
    return load_regulations()


data = _load()

# ==================== 사이드바 ====================
st.sidebar.title("⚙️ 규제 모니터링 제어")

all_months = sorted({(item.get("search_month") or DEFAULT_SINCE) for item in data}, reverse=True)
if not all_months:
    all_months = [date.today().strftime("%Y-%m")]
selected_month = st.sidebar.selectbox("📅 조회 월 선택", all_months, index=0)

filtered_data = [d for d in data if d.get("search_month") == selected_month]

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
    st.sidebar.download_button(
        label="📥 검토대장 엑셀 다운로드",
        data=output.getvalue(),
        file_name=f"국내외_규격_및_가이던스_업데이트_검토_대장_{selected_month}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.sidebar.markdown("---")
st.sidebar.subheader("🔄 수동 업데이트 (자동 수집 기관)")
st.sidebar.caption("MDCG · FDA · MHRA · MDSAP · TGA · Health Canada · PMDA")
if st.sidebar.button("지금 실행"):
    with st.spinner("최신 데이터를 수집 중입니다... (수 분 소요될 수 있습니다)"):
        from crawler import run_crawler
        since_y, since_m = int(DEFAULT_SINCE[:4]), int(DEFAULT_SINCE[5:7])
        saved, summary = run_crawler(since_y, since_m)
        st.cache_data.clear()
    st.sidebar.success("업데이트 완료!")
    for k, v in summary.items():
        st.sidebar.caption(f"· {k}: {v}")
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.subheader("🇰🇷 MFDS 수동 입력")
st.sidebar.caption(
    "mfds.go.kr은 robots.txt로 자동화된 접근을 차단하고 있어 자동 수집을 하지 않습니다. "
    "직접 확인하신 고시/규정의 첨부파일(PDF/HWPX/DOCX)을 업로드하면 요약·Gap분석을 자동 생성합니다."
)
with st.sidebar.form("mfds_manual_form", clear_on_submit=True):
    m_title = st.text_input("제목")
    m_doc_no = st.text_input("규격/가이던스 번호 (예: 제2026-46호)")
    m_pub = st.text_input("고시일 (YYYY-MM-DD)")
    m_eff = st.text_input("시행일 (YYYY-MM-DD)")
    m_url = st.text_input("원문 URL")
    m_file = st.file_uploader("첨부파일 업로드 (PDF/HWPX/DOCX)", type=["pdf", "hwpx", "docx"])
    submitted = st.form_submit_button("등록")

if submitted:
    if not m_title or not m_doc_no:
        st.sidebar.error("제목과 규격번호는 필수입니다.")
    else:
        file_bytes = m_file.read() if m_file else None
        file_name = m_file.name if m_file else None
        new_item = process_manual_entry(
            m_title, m_doc_no, m_pub or None, m_eff or None, m_url or None,
            uploaded_bytes=file_bytes, uploaded_filename=file_name,
        )
        upsert_regulations([new_item])
        st.cache_data.clear()
        st.sidebar.success("등록 완료!")
        st.rerun()

# ==================== 메인 화면 ====================
st.title("🩺 의료기기 규격 및 규제 모니터링 시스템")
st.caption(f"조회 월: {selected_month} | 총 {len(filtered_data)}건의 법규/규격 개정 사항이 수집되었습니다.")

if not filtered_data:
    st.info("해당 월의 데이터가 없습니다. 사이드바에서 수동 업데이트를 실행하거나 MFDS 항목을 등록해주세요.")
    st.stop()

# ---- 1. 검토대장 ----
st.subheader("📋 국내외 규격 및 가이던스 업데이트 검토 대장")

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
        f'<td>{item.get("scope") or "-"}</td>'
        f'<td style="color:red;font-weight:bold;">{sop}</td>'
        f'</tr>'
    )

table_html = (
    '<div class="reg-table-container"><table class="reg-table"><thead><tr>'
    '<th style="width:5%;">No.</th><th style="width:10%;">고시일</th>'
    '<th style="width:10%;">시행일</th><th style="width:12%;">발행처</th>'
    '<th style="width:15%;">규격/가이던스 번호</th><th style="width:33%;">제목 (클릭 시 이동)</th>'
    '<th style="width:10%;">적용범위</th><th style="width:5%;">SOP</th>'
    f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
)
render_html(table_html)

st.markdown("---")

# ---- 2. 요약 ----
st.subheader("📄 선택 규격 내용 요약")
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
    f'| <b>SOP 반영 필요:</b> <span style="color:red;font-weight:bold;">{selected_item.get("sop_required") or "-"}</span></p>'
    '<hr><p><b>[요약 내용]</b></p>'
    f'<p>{(selected_item.get("summary") or "").replace(chr(10), "<br>")}</p>'
    '</div>'
)
render_html(summary_html)

st.markdown("---")

# ---- 3. Gap 분석 ----
st.subheader("🔄 Gap 분석 (과거 vs 현재 규격 비교)")
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
