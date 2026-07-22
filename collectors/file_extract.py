"""
첨부파일 원문 텍스트 추출
- PDF  : pypdf
- DOCX : python-docx
- HWPX : 한글 신형식(.hwpx) — 내부적으로 zip+xml 구조이므로 zipfile로 열어 텍스트 노드만 추출
- HWP  : 구형 바이너리 포맷은 이 프로젝트 범위에서 지원하지 않음(별도 변환 필요) — 실패 시 이유를 명확히 반환
"""
import io
import zipfile
import re


def extract_text(content: bytes, filename: str) -> tuple[str, str]:
    """
    반환: (추출된 텍스트, 상태메시지)
    추출 실패 시 텍스트는 빈 문자열이며 상태메시지에 사유가 담긴다.
    """
    lower = filename.lower()
    try:
        if lower.endswith(".pdf"):
            return _extract_pdf(content)
        if lower.endswith(".docx"):
            return _extract_docx(content)
        if lower.endswith(".hwpx"):
            return _extract_hwpx(content)
        if lower.endswith(".hwp"):
            return "", "구형 HWP(바이너리) 포맷은 이 시스템에서 자동 추출을 지원하지 않습니다. hwpx/pdf본이 있는지 확인하세요."
        return "", f"지원하지 않는 파일 형식: {filename}"
    except Exception as e:
        return "", f"추출 실패: {e}"


def _extract_pdf(content: bytes):
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", "pypdf 미설치 (requirements.txt 확인)"
    reader = PdfReader(io.BytesIO(content))
    texts = []
    for page in reader.pages:
        t = page.extract_text() or ""
        texts.append(t)
    full = "\n".join(texts).strip()
    if not full:
        return "", "PDF에서 텍스트를 추출하지 못했습니다 (스캔 이미지 PDF일 가능성 - OCR 필요)"
    return full, "OK"


def _extract_docx(content: bytes):
    try:
        import docx
    except ImportError:
        return "", "python-docx 미설치 (requirements.txt 확인)"
    doc = docx.Document(io.BytesIO(content))
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    full = "\n".join(paras).strip()
    if not full:
        return "", "DOCX에서 텍스트를 추출하지 못했습니다"
    return full, "OK"


def _extract_hwpx(content: bytes):
    """
    HWPX는 zip 컨테이너 안에 Contents/section0.xml 등으로 본문이 들어있다.
    <hp:t>텍스트</hp:t> 형태의 텍스트 노드를 정규식으로 추출한다(전용 라이브러리 없이 최소 구현).
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        return "", "HWPX 파일 형식이 올바르지 않습니다 (zip 컨테이너 아님)"

    section_files = sorted([n for n in zf.namelist() if re.match(r"Contents/section\d+\.xml", n)])
    if not section_files:
        return "", "HWPX 내부에 Contents/section*.xml 을 찾을 수 없습니다"

    texts = []
    tag_re = re.compile(r"<hp:t[^>]*>(.*?)</hp:t>", re.DOTALL)
    for name in section_files:
        xml = zf.read(name).decode("utf-8", errors="ignore")
        for m in tag_re.finditer(xml):
            t = re.sub(r"<[^>]+>", "", m.group(1))
            if t.strip():
                texts.append(t.strip())
    full = "\n".join(texts).strip()
    if not full:
        return "", "HWPX에서 텍스트 노드를 찾지 못했습니다"
    return full, "OK"
