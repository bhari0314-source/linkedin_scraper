"""
app.py — public HTTPS API wrapping the Voyager client.

Interactive docs are auto-generated at /docs (Swagger) and /redoc.
"""

import os

from fastapi import FastAPI, HTTPException, Query

from linkedin_client import (
    LinkedInClient, public_id_from_url,
    AuthError, ProfileNotFound, LinkedInError,
)
from parser import normalize_profile

app = FastAPI(
    title="LinkedIn Profile API",
    version="0.1.0",
    description="Accepts a LinkedIn profile URL and returns structured JSON "
                "scraped from LinkedIn's internal Voyager API.",
)


def get_client() -> LinkedInClient:
    li_at = os.environ.get("LI_AT")
    jsessionid = os.environ.get("JSESSIONID")
    if not li_at or not jsessionid:
        # 500: this is a server misconfiguration, not the caller's fault.
        raise HTTPException(500, "Server missing LI_AT / JSESSIONID env vars.")
    return LinkedInClient(li_at, jsessionid)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/profile")
def profile(
    url: str = Query(
        ...,
        description="Full LinkedIn profile URL, e.g. "
                    "https://www.linkedin.com/in/some-person/",
        examples=["https://www.linkedin.com/in/williamhgates/"],
    )
):
    try:
        public_id = public_id_from_url(url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    client = get_client()
    try:
        raw = client.get_profile_view(public_id)
    except ProfileNotFound:
        raise HTTPException(404, "Profile not found or not visible to this account.")
    except AuthError as e:
        # 502: upstream (LinkedIn) rejected our session.
        raise HTTPException(502, f"Upstream auth error: {e}")
    except LinkedInError as e:
        raise HTTPException(502, str(e))

    return normalize_profile(raw, public_id)
