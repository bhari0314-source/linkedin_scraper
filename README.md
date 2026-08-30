# LinkedIn Profile API

A small HTTPS service that accepts a LinkedIn profile URL and returns the
profile as structured JSON. It works by replaying requests to LinkedIn's
**internal Voyager API** directly — no headless browser, no Selenium.

```
GET /profile?url=https://www.linkedin.com/in/some-person/
```

---

## Approach

LinkedIn's web client renders from a private JSON API served under
`https://www.linkedin.com/voyager/api/`. Rather than load pages and scrape the
DOM (LinkedIn obfuscates class names, so DOM scraping is brittle), this service
calls Voyager the same way the website does and reshapes the response.

**Authentication.** Voyager is authenticated with session cookies, not an API
key. Two cookies matter:

| Cookie       | Role                                                        |
|--------------|-------------------------------------------------------------|
| `li_at`      | Session auth token                                          |
| `JSESSIONID` | Also used as the CSRF token, sent in the `csrf-token` header |

The service carries these cookies plus a handful of headers LinkedIn requires
(`x-restli-protocol-version: 2.0.0`, `x-li-lang`, a realistic `User-Agent`).
There is **no programmatic username/password login** — that path is guarded by
CAPTCHAs and checkpoints and is the quickest way to get an account flagged.
Cookies are captured once from a logged-in browser and supplied via environment
variables.

**Primary endpoint.** `GET /identity/profiles/{public_id}/profileView` returns
the profile plus experience, education, skills, certifications and languages in
a single call. `parser.py` flattens that into a stable schema.

---

## Setup

Requires Python 3.11+.

```bash
git clone <your-repo-url>
cd linkedin-profile-api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Provide credentials (kept out of the repo)

1. Log into LinkedIn in a browser using a **throwaway account** (see limitations).
2. DevTools → **Application → Cookies → `https://www.linkedin.com`**.
3. Copy the values of `li_at` and `JSESSIONID`.

```bash
cp .env.example .env      # then edit .env with your values
export $(grep -v '^#' .env | xargs)   # or use a process manager that loads .env
```

`.env` is git-ignored. Secrets are read only from environment variables, so
nothing sensitive lives in the source tree.

### Run

```bash
uvicorn app:app --reload
```

Interactive docs: <http://localhost:8000/docs>

---

## API

### `GET /profile`

| Param | In    | Required | Description                    |
|-------|-------|----------|--------------------------------|
| `url` | query | yes      | Full LinkedIn profile URL      |

**200** — example (fields are `null`/`[]` when unavailable):

```json
{
  "public_id": "some-person",
  "profile_url": "https://www.linkedin.com/in/some-person/",
  "name": "Some Person",
  "headline": "Software Engineer at Example",
  "location": "New York, United States",
  "about": "…",
  "profile_picture": "https://media.licdn.com/…",
  "background_image": null,
  "experience": [
    {
      "title": "Software Engineer",
      "company": "Example Inc.",
      "location": "New York",
      "description": "…",
      "date_range": { "start": "2022-01", "end": null }
    }
  ],
  "education":      [ { "school": "…", "degree": "…", "field_of_study": "…", "date_range": {…} } ],
  "skills":         [ "Python", "Distributed Systems" ],
  "certifications": [ { "name": "…", "authority": "…", "url": "…", "date_range": {…} } ],
  "languages":      [ { "name": "English", "proficiency": "NATIVE_OR_BILINGUAL" } ]
}
```

**Errors:** `400` malformed URL · `404` profile not found / not visible to the
backend account · `502` upstream auth failure (cookies expired or session
flagged) · `500` server missing credentials.

### `GET /health`
Liveness probe → `{"status": "ok"}`.

---

## Deployment

Deploy the Dockerfile to any HTTPS platform (Render, Railway, Fly.io, a VPS
behind Caddy/nginx). Set `LI_AT` and `JSESSIONID` as environment secrets in the
platform dashboard — never in the repo.

```bash
docker build -t linkedin-profile-api .
docker run -p 8000:8000 -e LI_AT=… -e JSESSIONID=… linkedin-profile-api
```

---

## Known limitations

- **Terms of Service.** Automated access violates LinkedIn's User Agreement. The
  account behind the cookies can be restricted or banned. Use a disposable
  account, expect to rotate it, and never point this at your primary account.
- **Cookie lifetime.** `li_at` can last months but is invalidated by password
  changes, session revocation, or automation detection. When it dies, requests
  return `502`; refresh the cookies.
- **Rate limits / detection.** High request volume from one session triggers
  challenges and bans. Add throttling, caching, and jitter before any real load.
- **Datacenter IPs.** LinkedIn treats cloud/datacenter IP ranges with suspicion;
  a session that's healthy at home may get challenged from a deploy host.
  Residential/proxy egress is more stable (and its own can of worms).
- **Schema drift.** Voyager is private and unversioned. Field paths in
  `parser.py` are defensive but *will* shift; verify them against a live
  response. LinkedIn is also migrating profile reads to `/identity/dash/profiles`
  and a GraphQL endpoint whose `queryId`/`decorationId` rotates — hard-coding one
  guarantees eventual breakage.
- **Visibility.** You only get what the backend account can see. Out-of-network
  profiles, or fields the target restricted, come back partial or empty.
- **Not all fields on every profile** — anything the user didn't fill in is absent.

## Capturing a real response to finalise field mapping

To confirm/adjust `parser.py`, dump one raw `profileView` payload and inspect it:

```python
import os, json
from linkedin_client import LinkedInClient
c = LinkedInClient(os.environ["LI_AT"], os.environ["JSESSIONID"])
json.dump(c.get_profile_view("williamhgates"), open("sample.json", "w"), indent=2)
```
