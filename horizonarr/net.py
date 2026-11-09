"""Small HTTP helpers on top of urllib."""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

USER_AGENT = "Horizonarr (+https://github.com/fjflima75/horizonarr)"
log = logging.getLogger("horizonarr")


def request(url, method="GET", body=None, headers=None, timeout=60, raw=None, form=None, opener=None):
    """Send a request and return the decoded JSON (or text, or None for an empty body)."""
    data = None
    h = {"User-Agent": USER_AGENT, **(headers or {})}
    if raw is not None:
        data = raw.encode()
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
    elif body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with (opener or urllib.request.build_opener()).open(req, timeout=timeout) as r:
        payload = r.read()
    if not payload:
        return None
    try:
        return json.loads(payload)
    except ValueError:
        return payload.decode(errors="replace")


def session():
    """An opener that keeps cookies, for apps that sign in with a session."""
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))


HTTPError = urllib.error.HTTPError
