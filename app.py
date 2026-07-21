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

# Custom CSS: CanLII Diff 스타일 및 가로스크롤 방지
st.markdown("""
<style>
    .diff-box {
        background-color: #ffffff;
        border: 1px solid #d0d7de;
        border-radius: 6px;
        padding: 16px;
        font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
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

@st.cache_data(ttl=60)
def load_data():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

data = load_data()

# ---------------- 사이드바 ----------------
st.sidebar.title("⚙️ 규제 모니터링 제어")

# 1. 2026년 1월부터의 월 선택
year_months = sorted(list(set(item.get("search_month", "2026-07") for item in data)), reverse=True)
if not year_months:
    year_months = ["2026-07", "2026-06", "2026-05", "2026-04", "2026-03", "2026-02", "2026-01"]

selected_month = st.sidebar.selectbox("📅 조회 월 선택", year_months, index=0)

filtered_data = [d for d in data if d.get("search_month") == selected_month]

# 2. 엑셀 다운로드
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

# 3. 수동 업데이트
st.sidebar.markdown("---")
if st.sidebar.button("🔄 데이터 수동 업데이트"):
    with st.spinner("8개 기관 데이터를 수집 및 분석 중입니다..."):
        try:
            subprocess.run(["python", "crawler.py"], check=True)
            st.cache_data.clear()
            st.sidebar.success("업데이트가 완료되었습니다!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"업데이트 실패: {e}")

# ---------------- 메인 화면 ----------------
st.title("🩺 의료기기 규격 및 규제 모니터링 시스템")
st.caption(f"조회 월: {selected_month} | 총 {len(filtered_data)}건의 법규/규격 개정 사항이 수집되었습니다.")

if not filtered_data:
    st.info("해당 월의 수집 데이터가 없습니다. 좌측 사이드바에서 수동 업데이트를 실행해 주세요.")
    st.stop()

# --- Section 1: 검토 대장 (LinkColumn 및 너비 조절 적용) ---
st.subheader("📋 국내외 규격 및 가이던스 업데이트 검토 대장")

# app.py 의 DataFrame 표시 부분
df_display = pd.DataFrame([{
    "No.": item["no"],
    "고시일": item["publish_date"],
    "시행일": item["effective_date"],
    "발행처": item["publisher"],
    "규격/가이던스 번호": item["doc_no"],
    "제목 (클릭 시 이동)": item["url"],
    "적용범위": item["scope"],
    "SOP": item["sop_required"]
} for item in filtered_data])

st.dataframe(
    df_display,
    column_config={
        "No.": st.column_config.NumberColumn("No.", width="small"),
        "고시일": st.column_config.TextColumn("고시일", width="small"),
        "시행일": st.column_config.TextColumn("시행일", width="small"),
        "발행처": st.column_config.TextColumn("발행처", width="small"),
        "규격/가이던스 번호": st.column_config.TextColumn("규격/가이던스 번호", width="medium"),
        "제목 (클릭 시 이동)": st.column_config.LinkColumn(
            "제목 (클릭 시 이동)",
            width="large"
        ),
        "적용범위": st.column_config.TextColumn("적용범위", width="small"),
        "SOP": st.column_config.TextColumn("SOP", width="small")
    },
    hide_index=True,
    use_container_width=True
)

st.markdown("---")

# --- Section 2: 규격 선택 및 Gemini 한글 요약 ---
st.subheader("📄 수집 문서(PDF/Word) Gemini 자동 요약 (한글)")

selected_no = st.selectbox(
    "GAP 분석 및 요약을 확인할 규격 [No.]를 선택하세요:",
    options=[item["no"] for item in filtered_data],
    format_func=lambda x: f"No. {x} - {next(i['title'] for i in filtered_data if i['no'] == x)}"
)

selected_item = next(item for item in filtered_data if item["no"] == selected_no)

st.markdown(f"""
<div class="summary-card">
    <h4>📌 {selected_item['title']}</h4>
    <p><b>• 규격 번호:</b> {selected_item['doc_no'].replace('\n', ' ')} | <b>발행처:</b> {selected_item['publisher']}</p>
    <p><b>• 적용 범위:</b> {selected_item['scope']} | <b>SOP 개정 필요:</b> <span style="color:red; font-weight:bold;">{selected_item['sop_required']}</span></p>
    <hr>
    <p><b>[Gemini 한글 요약본]</b></p>
    <p>{selected_item['summary']}</p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# --- Section 3: CanLII 스타일 Gap 분석 Table (원문 비교) ---
st.subheader("🔄 Gap 분석 (과거 vs 현재 규격 원문 비교)")

gap_data = selected_item.get("gap_analysis", {})

col1, col2 = st.columns(2)
with col1:
    st.markdown("** 과거 규격 원문 (Past Text)**")
    st.info(gap_data.get("past_text", "N.A."))
with col2:
    st.markdown("** 현재 규격 원문 (Present Text)**")
    st.success(gap_data.get("present_text", "N.A."))

st.markdown("#### 🔍 CanLII Webdiff 비교")
st.caption("🔴 삭제된 문구 | 🟢 신규/업데이트 문구")

diff_html = gap_data.get("diff_html", "변경사항이 없거나 신규 제정건입니다.")
st.markdown(f'<div class="diff-box">{diff_html}</div>', unsafe_allow_html=True)
