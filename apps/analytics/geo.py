"""
Where a page view came from, derived from edge-proxy request headers.

No IP address is stored or logged. The frontend reaches the API through
Vercel's edge (see the /api rewrite in the frontend's vercel.json), and
Vercel resolves the visitor's location there and passes it along as request
headers. We keep only the coarse result - city, state, country - which is
what the dashboard reports on, and never the address it was derived from.

Cloudflare and Google Cloud's load balancer send the same information under
different header names; both are read too, so this keeps working if the
edge in front of the API ever changes.
"""

from urllib.parse import unquote

# ISO 3166-2:IN subdivision codes. The edge sends "RJ", not "Rajasthan",
# and a dashboard full of two-letter codes is not worth reading.
INDIA_STATES = {
    "AN": "Andaman and Nicobar Islands", "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh",
    "AS": "Assam", "BR": "Bihar", "CH": "Chandigarh", "CT": "Chhattisgarh", "DH": "Dadra and Nagar Haveli",
    "DL": "Delhi", "DN": "Dadra and Nagar Haveli", "GA": "Goa", "GJ": "Gujarat", "HP": "Himachal Pradesh",
    "HR": "Haryana", "JH": "Jharkhand", "JK": "Jammu and Kashmir", "KA": "Karnataka", "KL": "Kerala",
    "LA": "Ladakh", "LD": "Lakshadweep", "MH": "Maharashtra", "ML": "Meghalaya", "MN": "Manipur",
    "MP": "Madhya Pradesh", "MZ": "Mizoram", "NL": "Nagaland", "OR": "Odisha", "PB": "Punjab",
    "PY": "Puducherry", "RJ": "Rajasthan", "SK": "Sikkim", "TG": "Telangana", "TN": "Tamil Nadu",
    "TR": "Tripura", "UP": "Uttar Pradesh", "UT": "Uttarakhand", "WB": "West Bengal",
}


def _clean(value: str) -> str:
    # Vercel percent-encodes header values, so "New Delhi" arrives as "New%20Delhi".
    return unquote(value or "").strip()[:100]


def geo_from_request(request) -> dict:
    """
    Best-effort {city, region, country} for a request. Returns empty strings
    when the request didn't come through an edge that resolves location -
    local development, or a direct call to the Cloud Run URL - rather than
    guessing.
    """
    headers = request.headers

    city = _clean(headers.get("x-vercel-ip-city") or headers.get("cf-ipcity") or "")
    region_raw = _clean(
        headers.get("x-vercel-ip-country-region") or headers.get("cf-region-code") or headers.get("cf-region") or ""
    )
    country = _clean(
        headers.get("x-vercel-ip-country") or headers.get("cf-ipcountry") or ""
    ).upper()[:2]

    # Google Cloud's load balancer packs both into one header as "region,city".
    if not city and not region_raw:
        gcp = _clean(headers.get("x-client-geo-location") or "")
        if "," in gcp:
            region_raw, city = (part.strip() for part in gcp.split(",", 1))

    region = region_raw
    if country == "IN" and region_raw.upper() in INDIA_STATES:
        region = INDIA_STATES[region_raw.upper()]

    return {"city": city, "region": region[:100], "country": country}
