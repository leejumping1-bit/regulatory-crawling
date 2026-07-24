"""
공통 HTTP 유틸리티
- 모든 수집기가 공유
- 요청 전에 대상 사이트의 robots.txt를 확인하여, 명시적으로 차단된 경로는
  절대 요청하지 않는다 (사이트 운영정책 존중 원칙).
- 접속 실패가 반복되면 blocked=True 로 표시한다.
"""
import time
import requests
from urllib.parse import urljoin, urlparse
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
    """
    urllib.robotparser.read()는 내부적으로 자체 User-Agent("Python-urllib/x.y")로
    robots.txt를 요청하는데, 이게 일부 사이트(특히 EU 기관 사이트)의 방화벽에 막혀 403을
    받으면 robotparser가 "이 사이트는 전면 차단"으로 잘못 해석해버리는 알려진 동작이 있다
    (실제 robots.txt 내용과 무관하게 disallow_all=True가 되어버림).

    이를 피하기 위해 robots.txt를 우리가 쓰는 일반 브라우저형 User-Agent(requests,
    DEFAULT_HEADERS)로 직접 가져온 뒤, 그 텍스트를 robotparser에 넘겨(parse) 판단한다.
    """
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        rp = None
        try:
            resp = requests.get(origin + "/robots.txt", headers=DEFAULT_HEADERS, timeout=10)
            if resp.status_code == 200:
                rp = robotparser.RobotFileParser()
                rp.parse(resp.text.splitlines())
            # 404 등 robots.txt가 없거나, 403 등 애매한 상태코드는 규칙 없음(허용)으로 처리.
            # (403은 robots.txt 정책 자체가 아니라 우리 요청이 방화벽에 걸렸을 가능성이 높다 —
            #  실제 정책 차단이 아닌 것을 차단으로 오판하지 않기 위한 보수적 선택.)
        except Exception:
            rp = None
        _robots_cache[origin] = rp

    rp = _robots_cache[origin]
    if rp is None:
        return True
    return rp.can_fetch(user_agent, url)


def _allowed_redirect(url, allowed_hosts):
    if allowed_hosts is None:
        return True
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in allowed_hosts


def fetch(url, timeout=15, retries=2, backoff=2.0, session=None,
          respect_robots=True, politeness_delay=0.0, allowed_hosts=None) -> FetchResult:
    if politeness_delay:
        time.sleep(politeness_delay)

    if respect_robots and not _robots_allowed(url):
        return FetchResult(False, blocked=False, robots_disallowed=True,
                            error=f"robots.txt 에 의해 접근이 차단된 URL: {url}")

    sess = session or requests
    last_err = None
    for attempt in range(retries + 1):
        try:
            if allowed_hosts is None:
                resp = sess.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
            else:
                current_url = url
                for _ in range(5):
                    resp = sess.get(
                        current_url,
                        headers=DEFAULT_HEADERS,
                        timeout=timeout,
                        allow_redirects=False,
                    )
                    if resp.status_code not in (301, 302, 303, 307, 308):
                        break
                    location = resp.headers.get("Location")
                    if not location:
                        return FetchResult(False, resp.status_code, error="redirect Location 없음")
                    current_url = urljoin(current_url, location)
                    if not _allowed_redirect(current_url, allowed_hosts):
                        return FetchResult(
                            False,
                            resp.status_code,
                            error=f"허용되지 않은 redirect 차단: {current_url}",
                        )
                else:
                    return FetchResult(False, resp.status_code, error="redirect 횟수 초과")
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


def fetch_binary(url, timeout=25, respect_robots=True, politeness_delay=0.0,
                 allowed_hosts=None):
    """첨부파일(PDF/DOCX/HWPX) 다운로드용. 성공 시 bytes, 실패 시 None."""
    if politeness_delay:
        time.sleep(politeness_delay)
    if respect_robots and not _robots_allowed(url):
        return None
    try:
        if allowed_hosts is None:
            resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        else:
            current_url = url
            for _ in range(5):
                resp = requests.get(
                    current_url,
                    headers=DEFAULT_HEADERS,
                    timeout=timeout,
                    allow_redirects=False,
                )
                if resp.status_code not in (301, 302, 303, 307, 308):
                    break
                location = resp.headers.get("Location")
                if not location:
                    return None
                current_url = urljoin(current_url, location)
                if not _allowed_redirect(current_url, allowed_hosts):
                    return None
            else:
                return None
        resp.raise_for_status()
        return resp.content
    except requests.exceptions.RequestException:
        return None
