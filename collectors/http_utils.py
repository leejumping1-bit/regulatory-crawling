"""
공통 HTTP 유틸리티
- 모든 수집기가 공유
- 요청 전에 대상 사이트의 robots.txt를 확인하여, 명시적으로 차단된 경로는
  절대 요청하지 않는다 (사이트 운영정책 존중 원칙).
- 접속 실패가 반복되면 blocked=True 로 표시한다.
"""
import time
import requests
from urllib.parse import urlparse
from urllib import robotparser

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 RegulatoryWatchBot/1.0"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

_robots_cache = {}


class FetchResult:
    def __init__(self, ok, status_code=None, text=None, blocked=False,
                 robots_disallowed=False, error=None):
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self.blocked = blocked                  # 접속 실패(차단 추정)
        self.robots_disallowed = robots_disallowed  # robots.txt 로 명시적 차단
        self.error = error


def _robots_allowed(url: str, user_agent: str = "*") -> bool:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        rp = robotparser.RobotFileParser()
        rp.set_url(origin + "/robots.txt")
        try:
            rp.read()
        except Exception:
            # robots.txt를 읽을 수 없으면 안전하게 '허용'으로 간주하지 않고,
            # 보수적으로 허용(대부분 정부 공개정보 사이트는 robots.txt가 없거나 관대함)
            _robots_cache[origin] = None
            return True
        _robots_cache[origin] = rp
    rp = _robots_cache[origin]
    if rp is None:
        return True
    return rp.can_fetch(user_agent, url)


def fetch(url, timeout=15, retries=2, backoff=2.0, session=None,
          respect_robots=True, politeness_delay=0.0) -> FetchResult:
    if politeness_delay:
        time.sleep(politeness_delay)

    if respect_robots and not _robots_allowed(url):
        return FetchResult(False, blocked=False, robots_disallowed=True,
                            error=f"robots.txt 에 의해 접근이 차단된 URL: {url}")

    sess = session or requests
    last_err = None
    for attempt in range(retries + 1):
        try:
            resp = sess.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            if resp.status_code in (403, 999):
                return FetchResult(False, resp.status_code, blocked=True,
                                    error=f"HTTP {resp.status_code} (차단 추정)")
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or resp.encoding
            return FetchResult(True, resp.status_code, resp.text)
        except requests.exceptions.Timeout as e:
            last_err = e
        except requests.exceptions.ConnectionError as e:
            last_err = e
            if attempt == retries:
                return FetchResult(False, None, blocked=True, error=f"연결 실패(차단 추정): {e}")
        except requests.exceptions.RequestException as e:
            last_err = e
        time.sleep(backoff * (attempt + 1))
    return FetchResult(False, None, blocked=False, error=str(last_err))


def fetch_binary(url, timeout=25, respect_robots=True, politeness_delay=0.0):
    """첨부파일(PDF/DOCX/HWPX) 다운로드용. 성공 시 bytes, 실패 시 None."""
    if politeness_delay:
        time.sleep(politeness_delay)
    if respect_robots and not _robots_allowed(url):
        return None
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.content
    except requests.exceptions.RequestException:
        return None
