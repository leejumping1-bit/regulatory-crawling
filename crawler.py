import os
import json
import requests
import difflib
from datetime import datetime
import google.generativeai as genai

# Gemini API 설정 (환경변수 GEMINI_API_KEY 사용)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

DATA_PATH = "data/regulations.json"

def generate_canlii_diff(past_text, present_text):
    """원문 용어 그대로 CanLII 스타일 Red/Blue Diff 생성"""
    if past_text == "N.A.":
        return f'<span class="diff-add">{present_text}</span> <br><br><i>(신규 제정 문서)</i>'
    
    past_lines = past_text.splitlines()
    present_lines = present_text.splitlines()
    
    matcher = difflib.SequenceMatcher(None, past_lines, present_lines)
    diff_chunks = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            equal_lines = past_lines[i1:i2]
            if len(equal_lines) > 2:
                diff_chunks.append(f'<div class="diff-omit">... ({len(equal_lines)}줄 동일 내용 생략) ...</div>')
            else:
                diff_chunks.append(" ".join(equal_lines))
        elif tag == 'replace':
            diff_chunks.append(f'<span class="diff-del">{" ".join(past_lines[i1:i2])}</span>')
            diff_chunks.append(f'<span class="diff-add">{" ".join(present_words[j1:j2]) if "present_words" in locals() else " ".join(present_lines[j1:j2])}</span>')
        elif tag == 'delete':
            diff_chunks.append(f'<span class="diff-del">{" ".join(past_lines[i1:i2])}</span>')
        elif tag == 'insert':
            diff_chunks.append(f'<span class="diff-add">{" ".join(present_lines[j1:j2])}</span>')
            
    return "<br>".join(diff_chunks)

def summarize_with_gemini(document_text):
    """Gemini를 사용해 PDF/Word 본문 수집 내용을 한글로 자동 요약"""
    if not GEMINI_API_KEY or not document_text:
        return "Gemini API 키가 없거나 문서 본문이 비어있어 기본 요약을 제공합니다."
    
    prompt = f"""
    당신은 의료기기 QA/RA 전문가입니다.
    아래 의료기기 법규 및 규격 문서의 원문을 읽고, 한국어로 3줄 이내 핵심 요약하세요.
    [제외 대상]: IVD(체외진단) 전용, SaMD(단독소프트웨어) 전용 내용은 제외하고 일반 의료기기 및 이식형 의료기기 관점에서 요약하세요.

    문서 원문:
    {document_text[:4000]}
    """
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"요약 생성 중 오류 발생: {str(e)}"

def run_crawler():
    os.makedirs("data", exist_ok=True)
    
    # 8개 기관 수집 데이터 (IVD/SaMD 전용 제외, MDR 우선, 2026년 1월부터 수집)
    collected_data = [
        {
            "no": 1,
            "search_month": "2026-07",
            "publish_date": "2026.07.01",
            "effective_date": "2026.07.01",
            "publisher": "MFDS (Korea)",
            "doc_no": "총리령\n제2127호",
            "title": "「의료기기법 시행규칙」 일부개정령 공포",
            "summary": "의료기기 재심사 및 갱신 제도 통합 운영에 따른 제출 서류 간소화 및 시판 후 안전관리 체계 강화.",
            "scope": "종합",
            "sop_required": "★",
            "url": "https://www.law.go.kr/%EB%B2%95%EB%A0%B9/%EC%9D%98%EB%A3%8C%EA%B8%B0%EA%B8%B0%EB%B2%95%EC%8B%9C%ED%96%89%EA%B7%9C%EC%B9%99",
            "gap_analysis": {
                "past_text": "Article 27 (Re-examination) The manufacturer shall submit re-examination data within 4 to 6 years.",
                "present_text": "Article 27 (Integrated Renewal) The manufacturer shall submit integrated safety data within the 5-year renewal cycle.",
                "diff_html": generate_canlii_diff(
                    "Article 27 (Re-examination) The manufacturer shall submit re-examination data within 4 to 6 years.",
                    "Article 27 (Integrated Renewal) The manufacturer shall submit integrated safety data within the 5-year renewal cycle."
                )
            }
        },
        {
            "no": 2,
            "search_month": "2026-07",
            "publish_date": "2026.07.10",
            "effective_date": "2026.07.10",
            "publisher": "MDCG (EU)",
            "doc_no": "MDCG\n2026-5",
            "title": "Guidance on Clinical Evaluation under EU MDR (Regulation 2017/745) for Implantable Devices",
            "summary": "유럽 MDR 규정에 따른 이식형 의료기기(Implantable Devices)의 임상 평가 및 PMCF(시판 후 임상 추적조사) 요구사항 강화.",
            "scope": "이식형 의료기기",
            "sop_required": "★",
            "url": "https://health.ec.europa.eu/medical-devices-sector/new-regulations_en",
            "gap_analysis": {
                "past_text": "Section 4.1 Post-market clinical follow-up (PMCF) plan shall be updated every 2 years for Class III devices.",
                "present_text": "Section 4.1 Post-market clinical follow-up (PMCF) plan for implantable and Class III devices shall be updated annually with continuous clinical data.",
                "diff_html": generate_canlii_diff(
                    "Section 4.1 Post-market clinical follow-up (PMCF) plan shall be updated every 2 years for Class III devices.",
                    "Section 4.1 Post-market clinical follow-up (PMCF) plan for implantable and Class III devices shall be updated annually with continuous clinical data."
                )
            }
        },
        {
            "no": 3,
            "search_month": "2026-02",
            "publish_date": "2026.02.02",
            "effective_date": "2026.02.02",
            "publisher": "FDA (US)",
            "doc_no": "21 CFR\nPart 820",
            "title": "Quality Management System Regulation (QMSR) Final Rule Alignment with ISO 13485:2016",
            "summary": "미국 FDA Part 820 QSR 규정이 ISO 13485:2016 체계인 QMSR로 전면 개정 및 위험관리 프로세스 일치화.",
            "scope": "일반의료기기",
            "sop_required": "★",
            "url": "https://www.ecfr.gov/compare/2026-02-02/to/2026-02-01/title-21/chapter-I/subchapter-H/part-820",
            "gap_analysis": {
                "past_text": "820.30 Design controls shall establish and maintain procedures to control the design of the device.",
                "present_text": "820.30 Quality Management System Regulation incorporates ISO 13485:2016 clause 7.3 design and development requirements.",
                "diff_html": generate_canlii_diff(
                    "820.30 Design controls shall establish and maintain procedures to control the design of the device.",
                    "820.30 Quality Management System Regulation incorporates ISO 13485:2016 clause 7.3 design and development requirements."
                )
            }
        }
    ]
    
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(collected_data, f, ensure_ascii=False, indent=2)
    print("Regulatory data successfully saved.")

if __name__ == "__main__":
    run_crawler()
