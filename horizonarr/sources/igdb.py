"""IGDB (games database, via a free Twitch developer app)."""
import threading
import time
import urllib.parse

from .. import net

STEAM_SOURCE = 1        # external_game_source id for Steam
GAME_TYPES = "0,8,9,10,11"  # main game, remake, remaster, expanded game, port (no DLC/bundles/mods)
LIST_FIELDS = ("fields name,url,summary,cover.image_id,genres.name,themes.name,total_rating,total_rating_count,"
               "hypes,first_release_date,platforms,release_dates.date,release_dates.platform,videos.video_id,"
               "external_games.uid,external_games.external_game_source;")
SORTS = {"popular": "total_rating_count desc", "rating": "total_rating desc", "date": "first_release_date asc",
         "hype": "hypes desc"}


class IGDB:
    def __init__(self, client_id, client_secret):
        self.client_id, self.client_secret = client_id, client_secret
        self._token, self._expires = None, 0
        self._lock = threading.Lock()
        self._last = 0.0

    def _auth(self):
        if time.time() > self._expires - 300:
            t = net.request("https://id.twitch.tv/oauth2/token?" + urllib.parse.urlencode(
                {"client_id": self.client_id, "client_secret": self.client_secret,
                 "grant_type": "client_credentials"}), method="POST")
            self._token, self._expires = t["access_token"], time.time() + t["expires_in"]
        return self._token

    def query(self, endpoint, body):
        with self._lock:  # IGDB allows 4 requests a second
            wait = 0.3 - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            token = self._auth()
        return net.request(f"https://api.igdb.com/v4/{endpoint}", "POST", raw=body,
                           headers={"Client-ID": self.client_id, "Authorization": f"Bearer {token}"})

    # ---- normalising ----
    @staticmethod
    def to_game(g, platforms=None, start=None, end=None):
        """IGDB record -> the small dict the app stores. With platforms/start/end, keep only matching dates."""
        dates = [(d["date"], d["platform"]) for d in g.get("release_dates", []) if d.get("date") and d.get("platform")]
        if platforms is not None:
            dates = [(d, p) for d, p in dates if p in platforms and (start is None or start <= d <= end)]
        plats = sorted({p for _, p in dates}) or sorted(g.get("platforms", []))
        date = min((d for d, _ in dates), default=g.get("first_release_date"))
        steam = next((e.get("uid") for e in g.get("external_games", [])
                      if e.get("external_game_source") == STEAM_SOURCE and e.get("uid")), None)
        return {
            "id": g["id"], "name": g["name"], "url": g.get("url"),
            "cover": (g.get("cover") or {}).get("image_id"),
            "genres": [x["name"] for x in g.get("genres", [])][:4],
            "themes": [x["name"] for x in g.get("themes", [])][:4],
            "summary": (g.get("summary") or "")[:600],
            "video": next((v.get("video_id") for v in g.get("videos", []) if v.get("video_id")), None),
            "rating": round(g["total_rating"]) if g.get("total_rating") else None,
            "rating_count": g.get("total_rating_count") or 0,
            "hypes": g.get("hypes") or 0,
            "platforms": plats, "date": date, "steam": steam,
        }

    # ---- lists ----
    def window(self, platforms, start, end, limit, sort="hypes desc"):
        """Games with a release on these platforms between start and end (unix seconds)."""
        games, offset = [], 0
        while len(games) < limit:
            batch = self.query("games", LIST_FIELDS +
                               f" where release_dates.date >= {start} & release_dates.date <= {end}"
                               f" & release_dates.platform = ({','.join(map(str, platforms))})"
                               f" & game_type = ({GAME_TYPES}); sort {sort};"
                               f" limit {min(500, limit - len(games))}; offset {offset};")
            games += [self.to_game(g, set(platforms), start, end) for g in batch]
            if len(batch) < 500:
                break
            offset += 500
        return [g for g in games if g["platforms"]]

    def genres(self):
        return sorted((g["id"], g["name"]) for g in self.query("genres", "fields name; limit 100;"))

    def explore(self, platforms, start, end, sort="popular", offset=0, limit=60, genre=None):
        """Games first released between start and end, on any of these platforms (empty = any)."""
        where = [f"first_release_date >= {start}", f"first_release_date < {end}", f"game_type = ({GAME_TYPES})"]
        if platforms:
            where.append(f"platforms = ({','.join(map(str, platforms))})")
        if genre:
            where.append(f"genres = ({int(genre)})")
        if sort == "rating":
            where.append("total_rating_count > 4")
        batch = self.query("games", LIST_FIELDS + f" where {' & '.join(where)}; sort {SORTS.get(sort, SORTS['popular'])};"
                                                  f" limit {limit}; offset {offset};")
        return [self.to_game(g) for g in batch]

    def search(self, text, limit=40):
        safe = text.replace('"', "").strip()[:80]
        batch = self.query("games", LIST_FIELDS + f' search "{safe}"; where game_type = ({GAME_TYPES}); limit {limit};')
        return [self.to_game(g) for g in batch]

    def details(self, gid):
        rows = self.query("games", "fields name,summary,storyline,url,cover.image_id,screenshots.image_id,"
                                   "videos.video_id,videos.name,involved_companies.company.name,"
                                   "involved_companies.developer,involved_companies.publisher,"
                                   "release_dates.human,release_dates.platform,release_dates.region,"
                                   f"game_modes.name,themes.name,franchises.name; where id = {int(gid)};")
        if not rows:
            return None
        g = rows[0]
        companies = g.get("involved_companies", [])
        return {
            "summary": g.get("summary") or g.get("storyline") or "",
            "screenshots": [s["image_id"] for s in g.get("screenshots", [])][:6],
            "videos": [{"id": v["video_id"], "name": v.get("name", "")} for v in g.get("videos", [])][:3],
            "developers": [c["company"]["name"] for c in companies if c.get("developer") and c.get("company")],
            "publishers": [c["company"]["name"] for c in companies if c.get("publisher") and c.get("company")],
            "releases": [{"human": d.get("human"), "platform": d.get("platform"), "region": d.get("region")}
                         for d in g.get("release_dates", [])][:20],
            "modes": [m["name"] for m in g.get("game_modes", [])],
            "themes": [t["name"] for t in g.get("themes", [])][:5],
            "franchises": [f["name"] for f in g.get("franchises", [])],
        }
