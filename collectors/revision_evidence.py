"""Conservative revision evidence, independent of collector summaries and storage.

No network search or source authentication is performed here. The caller must
verify the issuing official URL, document identity/revision, complete discovery,
and that explicit spans describe changes to this document (not a blank template).
Pages are complete extracted text: tuples preserve page numbering and raw quotes.
A numeric gap is intentionally considered ambiguous rather than guessed across.
"""
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from io import BytesIO
from urllib.parse import urlsplit


@dataclass(frozen=True)
class DocumentVersion:
    document_id: str
    revision: int
    url: str
    pages: tuple[str, ...]

    def __post_init__(self):
        object.__setattr__(self, 'pages', tuple(self.pages))

    @property
    def content_sha256(self):
        # Length-prefix pages so different page boundaries cannot collide.
        digest = sha256()
        for page in self.pages:
            data = page.encode('utf-8')
            digest.update(len(data).to_bytes(8, 'big'))
            digest.update(data)
        return digest.hexdigest()


@dataclass(frozen=True)
class Quote:
    url: str
    page: int
    text: str


@dataclass(frozen=True)
class Change:
    before: str
    after: str
    before_page: int | None
    after_page: int | None


@dataclass(frozen=True)
class Evidence:
    status: str
    previous: str = '찾을 수 없음'
    quotes: tuple[Quote, ...] = ()
    changes: tuple[Change, ...] = ()
    detail: str = ''
    current_sha256: str = ''
    previous_sha256: str = ''


def pdf_pages(content: bytes) -> tuple[str, ...]:
    """Extract per-page PDF text. Raises ValueError on invalid/image-only PDFs.

    A PDF with an unextractable page is rejected, not partially compared. OCR is
    deliberately not attempted: extracted text is not guaranteed visual fidelity.
    """
    try:
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(content))
        pages = tuple(page.extract_text() or '' for page in reader.pages)
    except Exception as exc:
        raise ValueError(f'PDF extraction failed: {exc}') from exc
    if not pages or any(not page.strip() for page in pages):
        raise ValueError('PDF has an empty or unextractable page')
    return pages


def _host(url):
    try:
        p = urlsplit(url)
        if p.scheme.lower() != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return None
        return p.hostname.lower().rstrip('.')
    except ValueError:
        return None


def _lines(pages):
    return [(line, page) for page, text in enumerate(pages, 1)
            for line in text.splitlines(keepends=True)]


def build_evidence(current, *, explicit_spans=(), candidates=(), discovery_complete=False):
    """Analyze *provided* versions; discovery_complete is caller-attested.

    Spans are (1-based page, 0-based start, exclusive end) and must be reviewed
    as actual revision content. Comparison is raw extracted-text diff, not a
    finding of legal/substantive change. A complete search must include the full
    same-site revision list, not merely a successful HTTP request.
    """
    def result(status, **kw):
        if 'previous' not in kw:
            kw['previous'] = ('찾을 수 없음' if status == 'previous_not_found' else
                              '확인하지 않음' if status == 'explicit_change' else '확인 실패')
        return Evidence(status, current_sha256=current.content_sha256, **kw)

    if not _host(current.url) or not current.document_id or type(current.revision) is not int or current.revision < 0:
        return result('version_ambiguous', detail='Invalid current source or version identity')
    if not current.pages or any(not isinstance(p, str) or not p.strip() for p in current.pages):
        return result('extraction_failed', detail='Current text missing or incomplete')
    if explicit_spans:
        quotes = []
        for page, start, end in explicit_spans:
            if (type(page) is not int or type(start) is not int or type(end) is not int
                    or not 1 <= page <= len(current.pages)
                    or not 0 <= start < end <= len(current.pages[page - 1])
                    or not current.pages[page - 1][start:end].strip()):
                return result('extraction_failed', detail='Invalid explicit evidence span')
            quotes.append(Quote(current.url, page, current.pages[page - 1][start:end]))
        return result('explicit_change', quotes=tuple(quotes), detail='Caller-validated explicit change text')
    if not discovery_complete:
        return result('discovery_incomplete', detail='Official-site discovery not completed')
    same = [c for c in candidates if _host(c.url) == _host(current.url)
            and c.document_id == current.document_id and type(c.revision) is int
            and 0 <= c.revision < current.revision]
    if not same:
        return result('previous_not_found', detail='No previous version supplied from issuing host')
    highest = max(c.revision for c in same)
    matches = [c for c in same if c.revision == highest]
    if len(matches) != 1 or highest != current.revision - 1 or matches[0].url == current.url:
        return result('version_ambiguous', detail='Immediate predecessor or immutable source cannot be established')
    previous = matches[0]
    if not previous.pages or any(not isinstance(p, str) or not p.strip() for p in previous.pages):
        return result('extraction_failed', previous=previous.url, detail='Previous text missing or incomplete')
    old, new = _lines(previous.pages), _lines(current.pages)
    changes = []
    matcher = SequenceMatcher(None, [x[0] for x in old], [x[0] for x in new], autojunk=False)
    for tag, i, j, k, l in matcher.get_opcodes():
        if tag == 'equal':
            continue
        # Separate pages to retain an unambiguous page for each excerpt.
        old_groups = [(t, p) for t, p in old[i:j]]
        new_groups = [(t, p) for t, p in new[k:l]]
        for page in sorted({p for _, p in old_groups} | {p for _, p in new_groups}):
            before = ''.join(t for t, p in old_groups if p == page).rstrip('\n\r')
            after = ''.join(t for t, p in new_groups if p == page).rstrip('\n\r')
            changes.append(Change(before, after, page if before else None, page if after else None))
    common = dict(previous=previous.url, previous_sha256=previous.content_sha256)
    if not changes:
        return result('verified_no_change', detail='Extracted text is identical', **common)
    return result('verified_change', changes=tuple(changes), detail='Raw extracted-text differences; not a substantive-change determination', **common)
