"""
parser.py

Turns the raw Voyager `profileView` response into a clean, stable JSON shape.

IMPORTANT: LinkedIn's response shape drifts over time and varies by field
visibility. Every accessor below is defensive (.get(...) with fallbacks) so a
missing section degrades to null/[] instead of raising. Before you finalise the
mapping, capture one real response (see README) and confirm these key paths — a
couple of them WILL differ for your account/locale.
"""


def _time_period(tp: dict | None) -> dict | None:
    if not tp:
        return None

    def fmt(d):
        if not d:
            return None
        y, m = d.get("year"), d.get("month")
        if y and m:
            return f"{y}-{m:02d}"
        return str(y) if y else None

    return {"start": fmt(tp.get("startDate")), "end": fmt(tp.get("endDate"))}


def _image_url(picture: dict | None) -> str | None:
    """Profile/company images are stored as a vector image: a rootUrl plus a
    list of size artifacts. We stitch rootUrl + the largest artifact segment."""
    if not picture:
        return None
    ref = (picture.get("displayImageReference")
           or picture.get("vectorImage")
           or {})
    vector = ref.get("vectorImage") if "vectorImage" in ref else ref
    if not vector:
        return None
    root = vector.get("rootUrl")
    artifacts = vector.get("artifacts") or []
    if not root or not artifacts:
        return None
    largest = max(artifacts, key=lambda a: a.get("width", 0))
    return root + largest.get("fileIdentifyingUrlPathSegment", "")


def normalize_profile(raw: dict, public_id: str) -> dict:
    profile = raw.get("profile", {}) or {}

    location = (profile.get("geoLocationName")
                or profile.get("locationName")
                or (profile.get("location") or {}).get("basicLocation", {}).get("countryCode"))

    experience = [
        {
            "title": e.get("title"),
            "company": e.get("companyName"),
            "location": e.get("locationName"),
            "description": e.get("description"),
            "date_range": _time_period(e.get("timePeriod")),
        }
        for e in (raw.get("positionView", {}).get("elements") or [])
    ]

    education = [
        {
            "school": e.get("schoolName"),
            "degree": e.get("degreeName"),
            "field_of_study": e.get("fieldOfStudy"),
            "date_range": _time_period(e.get("timePeriod")),
        }
        for e in (raw.get("educationView", {}).get("elements") or [])
    ]

    skills = [
        e.get("name")
        for e in (raw.get("skillView", {}).get("elements") or [])
        if e.get("name")
    ]

    certifications = [
        {
            "name": e.get("name"),
            "authority": e.get("authority"),
            "url": e.get("url"),
            "date_range": _time_period(e.get("timePeriod")),
        }
        for e in (raw.get("certificationView", {}).get("elements") or [])
    ]

    languages = [
        {"name": e.get("name"), "proficiency": e.get("proficiency")}
        for e in (raw.get("languageView", {}).get("elements") or [])
    ]

    full_name = " ".join(
        p for p in [profile.get("firstName"), profile.get("lastName")] if p
    ) or None

    return {
        "profile_url": f"https://www.linkedin.com/in/{public_id}/",
        "name": full_name,
        "location": location,
        "about": profile.get("summary"),
        "profile_picture": _image_url(profile.get("profilePicture")),
        "experience": experience,
        "education": education,
        "certifications": certifications,
        "languages": languages,
    }
