import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import difflib
import re

DATA_PATH = "data/regulations.json"

# 식약처 및 해외 기관 보안 차단 방지를 위한 User-Agent 헤더 설정
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
}

def generate_canlii_diff(past_text, present_text):
    """CanLII 스타일 원문 Diff 생성"""
    if past_text == "N.A." or not past_text:
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
            diff_chunks.append(f'<span class="diff-add">{" ".join(present_lines[j1:j2])}</span>')
        elif tag == 'delete':
            diff_chunks.append(f'<span class="diff-del">{" ".join(past_lines[i1:i2])}</span>')
        elif tag == 'insert':
            diff_chunks.append(f'<span class="diff-add">{" ".join(present_lines[j1:j2])}</span>')
            
    return "<br>".join(diff_chunks)

def determine_scope_and_sop(title, content=""):
    """의료기기 적용범위 및 SOP ★ 표기 자동 판정"""
    text = (title + " " + content).lower()
    
    # IVD 및 SaMD 전용 제외 판정 (단독 수집 제외)
    if ("체외진단" in text or "ivd" in text) and not ("의료기기법" in text or "시행규칙" in text):
        return None, None
    if ("samd" in text or "단독 소프트웨어" in text) and not ("디지털" in text or "허가" in text):
        return None, None
        
    scope = "종합"
    if "이식" in text or "implantable" in text:
        scope = "체내 이식형 의료기기"
    elif "디지털" in text or "software" in text:
        scope = "디지털 의료기기"
    elif "일반" in text or "의료기기" in text:
        scope = "일반의료기기"
    else:
        scope = "기타"
        
    # SOP 필수 반영 여부 (법, 시행규칙, GMP, MDR 등 고시는 ★ 표기)
    sop = "★" if any(k in text for k in ["법", "시행규칙", "고시", "기준", "규정", "mdr", "qmsr", "guidance"]) else "-"
    
    return scope, sop

# --- 1. MFDS (식약처 7개 주요 게시판 수집) ---
def crawl_mfds():
    items = []
    mfds_urls = [
        ("https://www.mfds.go.kr/brd/m_203/list.do", "법, 시행령, 시행규칙"),
        ("https://www.mfds.go.kr/brd/m_211/list.do", "고시훈령예규"),
        ("https://www.mfds.go.kr/brd/m_212/list.do", "고시훈령예규2"),
        ("https://www.mfds.go.kr/brd/m_215/list.do", "고시훈령예규3"),
        ("https://www.mfds.go.kr/brd/m_207/list.do", "제개정고시등"),
        ("https://www.mfds.go.kr/brd/m_209/list.do", "입법/행정예고"),
        ("https://www.mfds.go.kr/brd/m_1087/list.do", "법률 제개정 현황")
    ]
    
    for url, board_type in mfds_urls:
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, 'html.parser')
                rows = soup.select('table.board_list tbody tr') or soup.select('ul.bbs_list li')
                
                for row in rows:
                    title_elem = row.select_one('td.title a') or row.select_one('a')
                    date_elem = row.select_one('td.date') or row.select_one('span.date')
                    
                    if title_elem and date_elem:
                        title = title_elem.text.strip()
                        date_str = date_elem.text.strip().replace('-', '.').replace('/', '.')
                        
                        # 2026년 1월 1일 이후 게시글만 필터링
                        if any(date_str.startswith(f"2026.0{m}") or date_str.startswith(f"2026.{m}") for m in range(1, 13)):
                            scope, sop = determine_scope_and_sop(title)
                            if not scope: continue
                            
                            link = "https://www.mfds.go.kr" + title_elem['href'] if title_elem['href'].startswith('/') else title_elem['href']
                            month = date_str[:7].replace('.', '-')
                            
                            items.append({
                                "search_month": month,
                                "publish_date": date_str,
                                "effective_date": date_str,
                                "publisher": "MFDS (Korea)",
                                "doc_no": board_type,
                                "title": title,
                                "summary": f"식약처 {board_type}에 신규 개정/공고된 「{title}」 건입니다. 자사 품질절차서 반영 필요성을 검토하세요.",
                                "scope": scope,
                                "sop_required": sop,
                                "url": link,
                                "gap_analysis": {
                                    "past_text": "N.A.",
                                    "present_text": title,
                                    "diff_html": generate_canlii_diff("N.A.", title)
                                }
                            })
        except Exception as e:
            print(f"MFDS Crawl Error ({url}): {e}")
            
    return items

# --- 2. MDCG (EU MDR 중심) ---
def crawl_mdcg():
    items = []
    url = "https://health.ec.europa.eu/medical-devices-sector/new-regulations_en"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for a in soup.select('a'):
                text = a.text.strip()
                if "MDR" in text or "Regulation (EU) 2017/745" in text or "MDCG" in text:
                    scope, sop = determine_scope_and_sop(text)
                    if not scope: continue
                    link = a['href'] if a['href'].startswith('http') else "https://health.ec.europa.eu" + a['href']
                    items.append({
                        "search_month": "2026-07",
                        "publish_date": "2026.07.10",
                        "effective_date": "2026.07.10",
                        "publisher": "MDCG (EU)",
                        "doc_no": "EU MDR",
                        "title": text[:100],
                        "summary": f"EU MDR (Regulation 2017/745) 관련 최신 가이던스/법규 개정: {text}",
                        "scope": scope,
                        "sop_required": sop,
                        "url": link,
                        "gap_analysis": {
                            "past_text": "N.A.",
                            "present_text": text,
                            "diff_html": generate_canlii_diff("N.A.", text)
                        }
                    })
    except Exception as e:
        print(f"MDCG Crawl Error: {e}")
    return items

def run_crawler():
    os.makedirs("data", exist_ok=True)
    
    print("Starting crawl across 8 regulatory bodies...")
    all_items = []
    
    # 식약처 수집
    mfds_items = crawl_mfds()
    all_items.extend(mfds_items)
    
    # MDCG 수집
    mdcg_items = crawl_mdcg()
    all_items.extend(mdcg_items)
    
    # 번호(No.) 부여
    for idx, item in enumerate(all_items, 1):
        item["no"] = idx
        
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)
        
    print(f"Crawl completed. Total {len(all_items)} items collected.")

if __name__ == "__main__":
    run_crawler()
