import streamlit as st
import pandas as pd
import json
import os
import subprocess
from datetime import datetime

# 페이지 설정
st.set_page_config(
    page_title="의료기기 규격 및 규제 모니터링 시스템",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS (테이블 가로 스크롤 방지, 줄바꿈 처리, Diff 스타일링)
st.markdown("""
<style>
    /* 테이블 줄바꿈 및 가로 너비 최적화 */
    .dataframe {
        width: 100% !important;
        white-space: normal !important;
        word-wrap: break-word !important;
        font-size: 13px;
    }
    .dataframe th {
        background-color: #f0f2f6;
        text-align: center !important;
    }
    
    /* CanLII 스타일 Gap 분석 스타일링 */
    .diff-box {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 16px;
        font-family: 'Courier New', monospace;
        line-height: 1.6;
        font-size: 14px;
    }
    .diff-del {
        background-color: #ffeef0;
        color: #b31d28;
        text-decoration: line-through;
        padding: 2px 4px;
        border-radius: 3px;
    }
    .diff-add {
        background-color: #e6ffec;
        color: #22863a;
        font-weight: bold;
        padding: 2px 4px;
        border-radius: 3px;
    }
    .diff-omit {
        color: #888888;
        font-style: italic;
        margin: 8px 0;
    }
    .summary-card {
        background-color: #f8f9fa;
        border-left: 4px solid #1f77b4;
        padding: 15px;
        border-radius: 4px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# 데이터 로드
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

# 1. 월별 필터
year_months = sorted(list(set(item.get("search_month", "2026-07") for item in data)), reverse=True)
if not year_months:
    year_months = ["2026-07"]

selected_month = st.sidebar.selectbox("📅 조회 월 선택", year_months, index=0)

# 2. 엑셀 다운로드 버튼
filtered_data = [d for d in data if d.get("search_month") == selected_month]

if filtered_data:
    df_export = pd.DataFrame([{
        "No.": item["no"],
        "고시일\nPublished Date": item["publish_date"],
        "시행일\nEffectiveness Date": item["effective_date"],
        "발행처\nPublished by": item["publisher"],
        "규격 및 가이던스 번호\nRegulation & Guidance No.": item["doc_no"],
        "제목\nTitle": item["title"],
        "내용요약\nSummary": item["summary"],
        "적용 범위\nScope": item["scope"],
        "SOP": item["sop_required"]
    } for item in filtered_data])
    
    # 엑셀 파일 변환
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

# 3. 수동 업데이트 버튼
st.sidebar.markdown("---")
if st.sidebar.button("🔄 크롤링 수동 업데이트"):
    with st.spinner("8개 기관 사이트를 수집 중입니다..."):
        try:
            subprocess.run(["python", "crawler.py"], check=True)
            st.cache_data.clear()
            st.sidebar.success("업데이트가 완료되었습니다!")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"업데이트 실패: {e}")

# ---------------- 메인 화면 ----------------
st.title("🩺 의료기기 규격 및 규제 모니터링 시스템")
st.caption(f"조회 월: {selected_month} | 총 {len(filtered_data)}건의 개정 사항이 검색되었습니다.")

if not filtered_data:
    st.info("해당 월의 데이터가 없습니다. 좌측 사이드바에서 수동 업데이트를 실행해 주세요.")
    st.stop()

# --- Section 1: 국내외 규격 및 가이던스 검토 대장 ---
st.subheader("📋 국내외 규격 및 가이던스 업데이트 검토 대장")

# 화면 가로 넘침 방지를 위한 UI 테이블 구성
table_rows = []
for item in filtered_data:
    link_type = f"[{item['title']}]({item['url']})" if item.get('url') else item['title']
    if item.get('is_fallback_link'):
        link_type += " ⚠️*(목록 링크)*"
    else:
        link_type += " 🔗*(직접 링크)*"

    table_rows.append({
        "No.": item["no"],
        "고시일": item["publish_date"],
        "시행일": item["effective_date"],
        "발행처": item["publisher"],
        "규격/가이던스 번호": item["doc_no"],
        "제목 (클릭시 이동)": link_type,
        "적용 범위": item["scope"],
        "SOP": item["sop_required"]
    })

df_display = pd.DataFrame(table_rows)
st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)

st.markdown("---")

# --- Section 2: 규격 선택 및 심사원 관점 요약 Box ---
st.subheader("🔍 선택 규격 영향도 요약 (의료기기 심사원 관점)")

selected_no = st.selectbox(
    "GAP 분석 및 세부 요약을 확인할 규격의 [No.]를 선택하세요:",
    options=[item["no"] for item in filtered_data],
    format_func=lambda x: f"No. {x} - {next(i['title'] for i in filtered_data if i['no'] == x)}"
)

selected_item = next(item for item in filtered_data if item["no"] == selected_no)

st.markdown(f"""
<div class="summary-card">
    <h4>📌 심사원 판단 주요 반영 필요 요소</h4>
    <p><b>[규격명]</b> {selected_item['title']} ({selected_item['doc_no']})</p>
    <p><b>[SOP 반영 필요 여부]</b> <span style="color:red; font-weight:bold;">{selected_item['sop_required']}</span> (★ 표시 시 품질절차서/지침서 개정 필수)</p>
    <p><b>[요약 내용]</b> {selected_item['summary']}</p>
    <p><b>[QA/RA 가이드]</b> 본 개정 사항은 <b>{selected_item['scope']}</b> 대상 제품군에 적용되며, 개정 시행일({selected_item['effective_date']}) 이전 자사 설계개발 검토 및 변경관리 절차(SOP) 반영이 필요합니다.</p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# --- Section 3: CanLII 스타일 Gap 분석 Table ---
st.subheader("🔄 Gap 분석 표 (과거 vs 현재 규격 비교)")

gap_data = selected_item.get("gap_analysis", {})

col1, col2 = st.columns(2)
with col1:
    st.markdown("** 과거 규격 내용**")
    st.info(gap_data.get("past_text", "N.A."))
with col2:
    st.markdown("** 현재 규격 내용**")
    st.success(gap_data.get("present_text", "N.A."))

st.markdown("#### 🔍 문맥 Diff 비교 (CanLII Webdiff Style)")
st.caption("🔴 삭제된 내용 | 🟢 신규/업데이트 내용 | ... 동일 내용 생략")

diff_html = gap_data.get("diff_html", "변경사항이 없거나 신규 제정건입니다.")
st.markdown(f'<div class="diff-box">{diff_html}</div>', unsafe_allow_html=True)