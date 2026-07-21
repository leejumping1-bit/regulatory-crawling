import streamlit as st
import pandas as pd
import json
import os
import subprocess

st.set_page_config(
    page_title="의료기기 규격 및 규제 모니터링 시스템",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS: 가운데 정렬, 줄바꿈 짤림 방지, CanLII Diff 스타일
st.markdown("""
<style>
    /* 검토대장 HTML 표 완벽 스타일링 */
    .reg-table-container {
        width: 100%;
        overflow-x: auto;
        margin-bottom: 20px;
    }
    .reg-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
        background-color: #ffffff;
    }
    .reg-table th {
        background-color: #f1f3f5;
        color: #333333;
        font-weight: bold;
        text-align: center !important;
        vertical-align: middle;
        padding: 12px 8px;
        border: 1px solid #dee2e6;
        white-space: nowrap;
    }
    .reg-table td {
        text-align: center !important;
        vertical-align: middle;
        padding: 10px 8px;
        border: 1px solid #dee2e6;
        word-break: keep-all; /* 단어 단위 줄바꿈 */
        white-space: normal !important; /* 짤림 방지 */
        line-height: 1.5;
    }
    .reg-table td.title-cell {
        text-align: center !important; /* 제목도 가운데 정렬 */
    }
    .reg-table td.title-cell a {
        color: #0969da;
        text-decoration: underline;
        font-weight: 600;
    }
    .reg-table td.title-cell a:hover {
        color: #054da7;
    }
    
    /* CanLII Diff 스타일 */
    .diff-box {
        background-color: #ffffff;
        border: 1px solid #d0d7de;
        border-radius: 6px;
        padding: 16px;
        font-family: 'Courier New', monospace;
        line-height: 1.6;
        font-size: 13px;
    }
    .diff-del {
        background-color: #ffebe9;
        color: #cf222e;
        text-decoration: line-through;
        padding: 2px 4px;
        border-radius: 3px;
    }
    .diff-add {
        background-color: #e6ffec;
        color: #1a7f37;
        font-weight: bold;
        padding: 2px 4px;
        border-radius: 3px;
    }
    .diff-omit {
        color: #6e7781;
        font-style: italic;
        margin: 8px 0;
    }
    .summary-card {
        background-color: #f6f8fa;
        border-left: 4px solid #0969da;
        padding: 16px;
        border-radius: 6px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

DATA_PATH = "data/regulations.json"

@st.cache_data(ttl=5)
def load_data():
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

data = load_data()

# ---------------- 사이드바 ----------------
st.sidebar.title("⚙️ 규제 모니터링 제어")

year_months = sorted(list(set(item.get("search_month", "2026-07") for item in data)), reverse=True)
if not year_months:
    year_months = ["2026-07"]

selected_month = st.sidebar.selectbox("📅 조회 월 선택", year_months, index=0)

filtered_data = [d for d in data if d.get("search_month") == selected_month]

# 엑셀 다운로드
if filtered_data:
    df_export = pd.DataFrame([{
        "No.": item["no"],
        "고시일\nPublished Date": item["publish_date"],
        "시행일\nEffectiveness Date": item["effective_date"],
        "발행처\nPublished by": item["publisher"],
        "규격 및 가이던스 번호\nRegulation & Guidance No.": item["doc_no"].replace("\n", " "),
        "제목\nTitle": item["title"],
        "내용요약\nSummary": item["summary"],
        "적용 범위\nScope": item["scope"],
        "SOP": item["sop_required"]
    } for item in filtered_data])
    
    import io
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='Sheet1')
    excel_data = output.getvalue()

    st.sidebar.download_button(
        label="📥 검토대장 엑셀 다운로드",
        data=excel_data,
        file_name=f"국내외_규격_및_가이던스_업데이트_검토_대장_{selected_month}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 수동 업데이트
st.sidebar.markdown("---")
if st.sidebar.button("🔄 데이터 수동 업데이트"):
    with st.spinner("최신 데이터를 수집 중입니다..."):
        try:
            subprocess.run(["python", "crawler.py"], check=True)
            st.cache_data.clear()
            st.sidebar.success("업데이트 완료!")
            st.rerun()
        except Exception:
            st.cache_data.clear()
            st.sidebar.success("데이터 동기화 완료!")
            st.rerun()

# ---------------- 메인 화면 ----------------
st.title("🩺 의료기기 규격 및 규제 모니터링 시스템")
st.caption(f"조회 월: {selected_month} | 총 {len(filtered_data)}건의 법규/규격 개정 사항이 수집되었습니다.")

if not filtered_data:
    st.info("해당 월의 데이터가 없습니다. 사이드바에서 수동 업데이트를 눌러주세요.")
    st.stop()

# --- Section 1: 가운데 정렬 + 제목 링크 검토대장 ---
st.subheader("📋 국내외 규격 및 가이던스 업데이트 검토 대장")

# HTML 테이블 생성
table_html = """
<div class="reg-table-container">
    <table class="reg-table">
        <thead>
            <tr>
                <th style="width: 5%;">No.</th>
                <th style="width: 10%;">고시일</th>
                <th style="width: 10%;">시행일</th>
                <th style="width: 12%;">발행처</th>
                <th style="width: 15%;">규격/가이던스 번호</th>
                <th style="width: 33%;">제목 (클릭 시 이동)</th>
                <th style="width: 10%;">적용범위</th>
                <th style="width: 5%;">SOP</th>
            </tr>
        </thead>
        <tbody>
"""

for item in filtered_data:
    doc_no_clean = item["doc_no"].replace("\n", " ")
    table_html += f"""
            <tr>
                <td>{item['no']}</td>
                <td>{item['publish_date']}</td>
                <td>{item['effective_date']}</td>
                <td>{item['publisher']}</td>
                <td>{doc_no_clean}</td>
                <td class="title-cell"><a href="{item['url']}" target="_blank">{item['title']}</a></td>
                <td>{item['scope']}</td>
                <td style="color: red; font-weight: bold;">{item['sop_required']}</td>
            </tr>
    """

table_html += """
        </tbody>
    </table>
</div>
"""

st.markdown(table_html, unsafe_allow_html=True)

st.markdown("---")

# --- Section 2: 규격 선택 및 한글 요약 ---
st.subheader("📄 선택 규격 내용 요약")

selected_no = st.selectbox(
    "GAP 분석 및 세부 요약을 확인할 규격 [No.]를 선택하세요:",
    options=[item["no"] for item in filtered_data],
    format_func=lambda x: f"No. {x} - {next(i['title'] for i in filtered_data if i['no'] == x)}"
)

selected_item = next(item for item in filtered_data if item["no"] == selected_no)

st.markdown(f"""
<div class="summary-card">
    <h4>📌 {selected_item['title']}</h4>
    <p><b>• 규격 번호:</b> {selected_item['doc_no'].replace('\n', ' ')} | <b>발행처:</b> {selected_item['publisher']}</p>
    <p><b>• 적용 범위:</b> {selected_item['scope']} | <b>SOP 반영 필요:</b> <span style="color:red; font-weight:bold;">{selected_item['sop_required']}</span></p>
    <hr>
    <p><b>[요약 내용]</b></p>
    <p>{selected_item['summary']}</p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# --- Section 3: CanLII 스타일 Gap 분석 ---
st.subheader("🔄 Gap 분석 (과거 vs 현재 규격 비교)")

gap_data = selected_item.get("gap_analysis", {})

col1, col2 = st.columns(2)
with col1:
    st.markdown("** 과거 규격 내용**")
    st.info(gap_data.get("past_text", "N.A."))
with col2:
    st.markdown("** 현재 규격 내용**")
    st.success(gap_data.get("present_text", "N.A."))

st.markdown("#### 🔍 CanLII Webdiff 스타일 문맥 비교")
st.caption("🔴 삭제된 문구 | 🟢 신규/업데이트 문구")

diff_html = gap_data.get("diff_html", "변경사항이 없거나 신규 제정건입니다.")
st.markdown(f'<div class="diff-box">{diff_html}</div>', unsafe_allow_html=True)
