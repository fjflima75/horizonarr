"""RetroArr: what you already have, what is downloading, and adding games/wishlist entries."""
import logging
import os
import sqlite3
import threading
import time

from .. import net
from ..platforms import pick_for_add

log = logging.getLogger("horizonarr")
STEAM_PLATFORM = 125
STORE_PLATFORMS = {125, 126, 190}  # Steam, GOG Galaxy, Epic Games (RetroArr platform ids)
COLLECTION = "Novidades"


class RetroArr:
    def __init__(self, url, key, db_path="", steam_folder=""):
        self.url, self.key = url, key
        self.db_path, self.steam_folder = db_path, steam_folder
        self._platforms = {}
        self._snapshot = {"by_igdb": {}, "by_steam": {}, "taken": 0}
        self._lock = threading.Lock()

    def call(self, method, path, body=None, timeout=120):
        return net.request(f"{self.url}/api/v3{path}", method, body, headers={"X-Api-Key": self.key}, timeout=timeout)

    # ---- platforms ----
    def platform_id(self, igdb_platform):
        if not self._platforms:
            for p in sorted(self.call("GET", "/platform"), key=lambda p: p["id"]):
                if p.get("igdbPlatformId"):
                    self._platforms.setdefault(p["igdbPlatformId"], p["id"])
        return self._platforms.get(igdb_platform)

    # ---- library snapshot (refreshed every few minutes) ----
    def refresh(self):
        games = self.call("GET", "/game", timeout=300)
        wished = {w["id"] for w in (self.call("GET", "/review/wishlist") or [])}
        queue = {}
        for q in self.call("GET", "/downloadclient/queue") or []:
            if q.get("gameId") and q.get("trackedState") != "Imported":
                queue[q["gameId"]] = round(q.get("progress") or 0)
        by_igdb, by_steam, owned = {}, {}, []
        for g in games:
            if g.get("igdbId") and g["id"] not in wished and (
                    g.get("status") in ("Downloaded", "Installed") or g.get("platformId") in STORE_PLATFORMS):
                owned.append({"igdb": g["igdbId"], "rating": g.get("rating") or 0, "id": g["id"]})
            entry = {"id": g["id"], "status": g.get("status"), "monitored": g.get("monitored"),
                     "platform": g.get("platformName"), "store": g.get("platformId") in STORE_PLATFORMS,
                     "wishlisted": g["id"] in wished,
                     "downloading": queue.get(g["id"])}
            if g.get("igdbId"):
                by_igdb.setdefault(g["igdbId"], []).append(entry)
            if g.get("steamId"):
                by_steam.setdefault(g["steamId"], []).append(entry)
        with self._lock:
            self._snapshot = {"by_igdb": by_igdb, "by_steam": by_steam, "owned": owned, "taken": int(time.time())}
        log.info("retroarr snapshot: %d games, %d downloading", len(games), len(queue))

    def owned_seeds(self, top_rated=40, newest=20):
        """IGDB ids of owned games to base recommendations on: the best rated plus the latest added."""
        with self._lock:
            owned = list(self._snapshot.get("owned", []))
        best = sorted(owned, key=lambda o: -o["rating"])[:top_rated]
        latest = sorted(owned, key=lambda o: -o["id"])[:newest]
        return list(dict.fromkeys(o["igdb"] for o in best + latest)), {o["igdb"] for o in owned}

    def status(self, game):
        """Badges for a game: owned / downloading / wishlisted / monitored."""
        with self._lock:
            snap = self._snapshot
        entries = list(snap["by_igdb"].get(game["id"], []))
        if game.get("steam"):
            try:
                entries += snap["by_steam"].get(int(game["steam"]), [])
            except ValueError:
                pass
        # Files on disk, or a store library entry (Steam/GOG/Epic sync) that isn't just a wishlist item
        owned = any((e["status"] in ("Downloaded", "Installed") or e["store"]) and not e["wishlisted"] for e in entries)
        downloading = next((e["downloading"] for e in entries if e["downloading"] is not None), None)
        return {"owned": owned, "downloading": downloading, "wishlisted": any(e["wishlisted"] for e in entries),
                "monitored": any(e["monitored"] and not e["wishlisted"] for e in entries),
                "ids": [e["id"] for e in entries]}

    # ---- actions ----
    def _collection(self):
        for c in self.call("GET", "/collection"):
            if c["name"] == COLLECTION:
                return c["id"]
        return self.call("POST", "/collection", {"name": COLLECTION, "color": "#22d3ee",
                                                 "description": "Added from Horizonarr"})["id"]

    @staticmethod
    def _cover(game):
        return {"coverUrl": f"https://images.igdb.com/igdb/image/upload/t_cover_big/{game['cover']}.jpg"} \
            if game.get("cover") else None

    def add(self, game):
        """Monitored entry on the best platform + the Novidades collection. Returns (id, igdb platform)."""
        igdb_platform = pick_for_add(game["platforms"])
        pid = self.platform_id(igdb_platform)
        if not pid:
            raise ValueError("RetroArr has no matching platform")
        existing = next((g for g in self.call("GET", "/game", timeout=300)
                         if g.get("igdbId") == game["id"] and g.get("platformId") == pid), None)
        if existing:
            gid = existing["id"]
            self.call("PUT", f"/games/{gid}/monitored", {"monitored": True})
        else:
            body = {"title": game["name"], "igdbId": game["id"], "platformId": pid, "monitored": True,
                    "genres": game.get("genres", [])}
            if game.get("date"):
                body["year"] = int(time.strftime("%Y", time.gmtime(game["date"])))
                body["releaseDate"] = time.strftime("%Y-%m-%dT00:00:00Z", time.gmtime(game["date"]))
            if self._cover(game):
                body["images"] = self._cover(game)
            gid = self.call("POST", "/game", body)["id"]
        try:
            self.call("POST", f"/collection/{self._collection()}/games", {"gameId": gid})
        except net.HTTPError:
            pass  # already in it
        return gid, igdb_platform

    def wishlist(self, game):
        """Steam entry (not owned) + wishlist + Steam price watch."""
        steam = int(game["steam"])
        existing = next((g for g in self.call("GET", "/game", timeout=300)
                         if g.get("steamId") == steam and g.get("platformId") == STEAM_PLATFORM), None)
        if existing:
            gid = existing["id"]
        else:
            body = {"title": game["name"], "steamId": steam, "platformId": STEAM_PLATFORM, "status": "Announced",
                    "isExternal": True, "monitored": False, "igdbId": game["id"], "genres": game.get("genres", [])}
            if self._cover(game):
                body["images"] = self._cover(game)
            gid = self.call("POST", "/game", body)["id"]
            self._clear_path(gid)
        if not (self.call("GET", f"/review/game/{gid}") or {}).get("isWishlisted"):
            self.call("POST", f"/review/game/{gid}/wishlist")
        self.call("POST", f"/wishlist/{gid}/watch", {"provider": "steam", "externalId": str(steam),
                                                     "notifyOnAnyDrop": True})
        return gid

    def _clear_path(self, gid):
        """RetroArr makes an empty folder for every new game. A wishlist entry has no files: with
        RETROARR_DB set, clear its path (empty = unknown, never 'missing') and remove that empty folder."""
        if not self.db_path:
            return
        con = sqlite3.connect(self.db_path, timeout=30)
        try:
            path = (con.execute("SELECT Path FROM Games WHERE Id=?", (gid,)).fetchone() or [None])[0]
            con.execute("UPDATE Games SET Path=NULL WHERE Id=?", (gid,))
            con.commit()
        finally:
            con.close()
        if path and self.steam_folder:
            local = os.path.join(self.steam_folder, os.path.basename(path.rstrip("/")))
            if os.path.isdir(local) and not os.listdir(local):
                os.rmdir(local)
