"""
linkedin_client.py

A minimal, no-browser client for LinkedIn's internal "Voyager" API.

Auth model: we reuse an already-authenticated browser session by carrying its
cookies. The two that matter:
  - li_at:      the session auth token
  - JSESSIONID: doubles as the CSRF token (its value, quotes stripped, is sent
                in the `csrf-token` header)

We deliberately do NOT do a programmatic username/password login. LinkedIn
guards /uas/authenticate with CAPTCHAs, e-mail challenges and 2FA that are
fragile to automate and are the fastest route to getting an account flagged.
Capturing li_at + JSESSIONID from a logged-in browser once (and refreshing them
when they expire) is far more stable.
"""

import re
import requests


class LinkedInError(Exception):
    """Base error."""


class AuthError(LinkedInError):
    """Cookies expired, missing, or the session was challenged/flagged."""


class ProfileNotFound(LinkedInError):
    """Profile does not exist or is not visible to this account."""


VOYAGER_BASE = "https://www.linkedin.com/voyager/api"

# Keep this reasonably current. An obviously-stale or bot-like UA raises your
# odds of being served a challenge.
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def public_id_from_url(url: str) -> str:
    """Extract the vanity/public id from a profile URL.

    https://www.linkedin.com/in/some-person-123/  ->  some-person-123
    """
    m = re.search(r"/in/([^/?#]+)", url.strip())
    if not m:
        raise ValueError(f"No '/in/<id>' segment found in URL: {url!r}")
    return m.group(1)


class LinkedInClient:
    def __init__(self, li_at: str, jsessionid: str, user_agent: str = DEFAULT_UA,
                 timeout: int = 15):
        if not li_at or not jsessionid:
            raise AuthError("Both li_at and JSESSIONID are required.")

        # JSESSIONID usually arrives wrapped in quotes: "ajax:1234...".
        self.jsessionid = jsessionid.strip('"')
        self.timeout = timeout

        self.session = requests.Session()
        self.session.cookies.set("li_at", li_at, domain=".linkedin.com")
        self.session.cookies.set(
            "JSESSIONID", f'"{self.jsessionid}"', domain=".linkedin.com"
        )
        self.session.headers.update({
            "User-Agent": user_agent,
            "Accept": "application/json",
            "csrf-token": self.jsessionid,
            "x-restli-protocol-version": "2.0.0",
            "x-li-lang": "en_US",
            "Referer": "https://www.linkedin.com/feed/",
        })

    def _get(self, path: str, **kwargs) -> dict:
        url = f"{VOYAGER_BASE}{path}"
        resp = self.session.get(url, timeout=self.timeout, **kwargs)

        # LinkedIn redirects flagged sessions to a challenge/checkpoint page.
        if "checkpoint" in resp.url or "challenge" in resp.url:
            raise AuthError("Redirected to a LinkedIn challenge/checkpoint — "
                            "session is flagged.")
        if resp.status_code in (401, 403):
            raise AuthError(f"Auth failed ({resp.status_code}). Cookies likely "
                            "expired or session flagged — refresh li_at / JSESSIONID.")
        if resp.status_code == 404:
            raise ProfileNotFound(f"404 for {path}")
        resp.raise_for_status()
        return resp.json()

    def get_profile_view(self, public_id: str) -> dict:
        """Classic high-coverage endpoint. One call returns the profile plus
        positionView / educationView / skillView / certificationView /
        languageView collections."""
        return self._get(f"/identity/profiles/{public_id}/profileView")

    # NOTE ON THE NEWER SURFACE
    # LinkedIn is migrating profile reads to /identity/dash/profiles and a
    # GraphQL endpoint (/voyager/api/graphql?queryId=...). Those need a
    # decorationId / queryId that LinkedIn rotates periodically, so hard-coding
    # one guarantees future breakage. Capture the current value from DevTools
    # (Network tab, filter "voyager") when profileView stops returning a field
    # you need, and add a method here mirroring get_profile_view.
