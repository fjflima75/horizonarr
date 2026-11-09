"""SQLite store: game details, lists (recent/upcoming/explore pages), availability, prices, follows."""
import json
import os
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS games  (id INTEGER PRIMARY KEY, data TEXT NOT NULL, updated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS lists  (name TEXT PRIMARY KEY, ids TEXT NOT NULL, updated INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS avail  (game_id INTEGER PRIMARY KEY, data TEXT, checked INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS price  (game_id INTEGER PRIMARY KEY, data TEXT, checked INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS follows (
    game_id INTEGER PRIMARY KEY, created INTEGER NOT NULL,
    notified_release INTEGER NOT NULL DEFAULT 0, notified_avail INTEGER NOT NULL DEFAULT 0, last_price REAL);
CREATE TABLE IF NOT EXISTS kv     (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Store:
    def __init__(self, data_dir):
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "horizonarr.db")
        self._lock = threading.Lock()
        self._db = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(SCHEMA)
        self._db.commit()

    def _q(self, sql, args=(), many=False):
        with self._lock:
            cur = self._db.executemany(sql, args) if many else self._db.execute(sql, args)
            rows = cur.fetchall()
            self._db.commit()
            return rows

    # ---- games ----
    def put_games(self, games):
        now = int(time.time())
        self._q("INSERT INTO games(id, data, updated) VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "data=excluded.data, updated=excluded.updated",
                [(g["id"], json.dumps(g), now) for g in games], many=True)

    def get_games(self, ids):
        if not ids:
            return []
        found = {}
        for chunk in range(0, len(ids), 500):
            part = ids[chunk:chunk + 500]
            rows = self._q(f"SELECT data FROM games WHERE id IN ({','.join('?' * len(part))})", part)
            for (data,) in rows:
                g = json.loads(data)
                found[g["id"]] = g
        return [found[i] for i in ids if i in found]

    def get_game(self, gid):
        got = self.get_games([gid])
        return got[0] if got else None

    # ---- named lists ----
    def put_list(self, name, ids):
        self._q("INSERT INTO lists(name, ids, updated) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET "
                "ids=excluded.ids, updated=excluded.updated", (name, json.dumps(ids), int(time.time())))

    def get_list(self, name, max_age=None):
        rows = self._q("SELECT ids, updated FROM lists WHERE name=?", (name,))
        if not rows or (max_age is not None and time.time() - rows[0][1] > max_age):
            return None, 0
        return json.loads(rows[0][0]), rows[0][1]

    # ---- availability / price ----
    def _put_check(self, table, gid, data):
        self._q(f"INSERT INTO {table}(game_id, data, checked) VALUES(?,?,?) ON CONFLICT(game_id) DO UPDATE SET "
                "data=excluded.data, checked=excluded.checked", (gid, json.dumps(data), int(time.time())))

    def _get_checks(self, table, ids):
        out = {}
        for chunk in range(0, len(ids), 500):
            part = ids[chunk:chunk + 500]
            for gid, data, checked in self._q(
                    f"SELECT game_id, data, checked FROM {table} WHERE game_id IN ({','.join('?' * len(part))})", part):
                out[gid] = (json.loads(data) if data else None, checked)
        return out

    def put_avail(self, gid, data):
        self._put_check("avail", gid, data)

    def get_avail(self, ids):
        return self._get_checks("avail", ids)

    def put_price(self, gid, data):
        self._put_check("price", gid, data)

    def get_price(self, ids):
        return self._get_checks("price", ids)

    # ---- follows ----
    def follow(self, gid, on=True):
        if on:
            self._q("INSERT OR IGNORE INTO follows(game_id, created) VALUES(?,?)", (gid, int(time.time())))
        else:
            self._q("DELETE FROM follows WHERE game_id=?", (gid,))

    def follows(self):
        rows = self._q("SELECT game_id, created, notified_release, notified_avail, last_price FROM follows")
        return {r[0]: {"created": r[1], "notified_release": r[2], "notified_avail": r[3], "last_price": r[4]}
                for r in rows}

    def update_follow(self, gid, **fields):
        sets = ", ".join(f"{k}=?" for k in fields)
        self._q(f"UPDATE follows SET {sets} WHERE game_id=?", (*fields.values(), gid))

    # ---- key/value ----
    def get(self, key, default=None):
        rows = self._q("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(rows[0][0]) if rows else default

    def set(self, key, value):
        self._q("INSERT INTO kv(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)))

    def counts(self):
        return {t: self._q(f"SELECT COUNT(*) FROM {t}")[0][0] for t in ("games", "avail", "price", "follows")}

    # ---- one-off import from the old game-radar JSON cache ----
    def import_radar_json(self, path):
        if not os.path.exists(path) or self.get("imported_radar_json"):
            return 0
        with open(path) as f:
            old = json.load(f).get("games", {})
        games, recent, upcoming, now = [], [], [], time.time()
        for g in old.values():
            games.append({k: g.get(k) for k in ("id", "name", "url", "cover", "genres", "rating", "hypes",
                                                 "platforms", "date", "steam")})
            (recent if g["date"] <= now else upcoming).append(g["id"])
            if "avail_checked" in g:
                self._q("INSERT OR REPLACE INTO avail VALUES(?,?,?)",
                        (g["id"], json.dumps(g.get("avail")), int(g["avail_checked"])))
            if "price_checked" in g:
                self._q("INSERT OR REPLACE INTO price VALUES(?,?,?)",
                        (g["id"], json.dumps(g.get("price")), int(g["price_checked"])))
        self.put_games(games)
        self.put_list("recent", recent)
        self.put_list("upcoming", upcoming)
        self.set("imported_radar_json", int(now))
        return len(games)
