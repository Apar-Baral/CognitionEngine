# XSS Finder — Discovery (PHASE_01)

## Scope

| Area | Decision |
|------|----------|
| Inputs | URL fetch + raw HTML paste |
| Checks v1 | Reflected XSS (payload echoed unescaped), stored XSS (payload persisted then rendered) |
| Output | Severity (low / medium / high), evidence (parameter, snippet, match type) |
| Non-goals | Blind SSRF, auth bypass, WAF evasion, full-site spider |
| Safety | User confirms target ownership; rate limits; no aggressive crawling |

## Stack

- **API:** Python 3.11+, FastAPI
- **HTTP:** httpx (timeouts, size cap)
- **HTML:** beautifulsoup4 for reflection checks
- **UI:** Static page served by FastAPI (single form: URL or HTML)
- **Tests:** pytest + fixtures under `tests/fixtures/`

## API sketch (v1)

- `POST /api/scan/url` — body: `{ "url": "https://..." }`
- `POST /api/scan/html` — body: `{ "html": "<html>..." }`
- `GET /api/health`

## Fixtures (Phase 2+)

| File | Purpose |
|------|---------|
| `tests/fixtures/safe_page.html` | No reflection |
| `tests/fixtures/reflected_vuln.html` | Echoes query without encoding |
| `tests/fixtures/stored_vuln.html` | Simulated stored echo |

## Constraints

- Request timeout: 5s
- Max response body: 2 MB
- Canonical payload set: ~15 probes for v1
