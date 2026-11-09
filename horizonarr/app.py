"""The app: services, background jobs and the actions behind the page's buttons."""
import calendar
import logging
import threading
import time

from . import platforms
from .sources import steam
from .sources.igdb import IGDB
from .store import Store
from .targets.ntfy import Ntfy
from .targets.prowlarr import Prowlarr
from .targets.retroarr import RetroArr

log = logging.getLogger("horizonarr")
DAY = 86400
PAST_DAYS, FUTURE_DAYS, MAX_PER_WINDOW = 30, 90, 300


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.store = Store(cfg.data_dir)
        self.igdb = IGDB(cfg.igdb_client_id, cfg.igdb_client_secret) if cfg.has_igdb else None
        self.retroarr = RetroArr(cfg.retroarr_url, cfg.retroarr_key, cfg.retroarr_db,
                                 cfg.retroarr_steam_folder) if cfg.has_retroarr else None
        self.prowlarr = Prowlarr(cfg.prowlarr_url, cfg.prowlarr_key) if cfg.has_prowlarr else None
        self.ntfy = Ntfy(cfg.ntfy_url, cfg.ntfy_topic, cfg.ntfy_token) if cfg.has_ntfy else None
        self.search_lock = threading.Lock()  # one Prowlarr search at a time, page or background
        self.last_error = None

    # ---------- data refresh ----------
    def refresh_releases(self):
        now = int(time.time())
        start, end = now - PAST_DAYS * DAY, now + FUTURE_DAYS * DAY
        recent = self.igdb.window(platforms.MODERN, start, now, MAX_PER_WINDOW)
        upcoming = self.igdb.window(platforms.MODERN, now, end, MAX_PER_WINDOW)
        retro = self.igdb.window(platforms.GROUPS["Retro"], start, end, 300)
        self.store.put_games(recent + upcoming + retro)
        self.store.put_list("recent", [g["id"] for g in recent] + [g["id"] for g in retro if g["date"] <= now])
        self.store.put_list("upcoming", [g["id"] for g in upcoming] + [g["id"] for g in retro if g["date"] > now])
        self.store.set("releases_updated", now)
        self.last_error = None
        log.info("releases: %d recent, %d upcoming, %d retro", len(recent), len(upcoming), len(retro))

    def genres(self):
        """IGDB genres as [(id, name)], cached for a week (used by the Explore filter)."""
        cached = self.store.get("genres")
        if cached and time.time() - cached["at"] < 7 * DAY:
            return [tuple(x) for x in cached["list"]]
        lst = self.igdb.genres()
        self.store.set("genres", {"at": int(time.time()), "list": lst})
        return lst

    def themes(self):
        cached = self.store.get("themes")
        if cached and time.time() - cached["at"] < 7 * DAY:
            return [tuple(x) for x in cached["list"]]
        lst = self.igdb.themes()
        self.store.set("themes", {"at": int(time.time()), "list": lst})
        return lst

    def refresh_for_you(self):
        """'Parecidos com o que tens': games IGDB lists as similar to the ones you own, most mentioned first."""
        if not self.retroarr:
            return
        seeds, owned = self.retroarr.owned_seeds()
        if not seeds:
            return
        votes, because = {}, {}
        for src, similar in self.igdb.similar(seeds).items():
            for gid in similar:
                if gid in owned:
                    continue
                votes[gid] = votes.get(gid, 0) + 1
                because.setdefault(gid, src)
        ranked = sorted(votes, key=lambda g: -votes[g])[:240]
        games = self.igdb.by_ids(ranked)
        self.store.put_games(games)
        names = {g["id"]: g["name"] for g in self.igdb.by_ids(list({because[g] for g in ranked}))}
        by_id = {g["id"]: g for g in games}
        ordered = sorted((g for g in ranked if g in by_id), key=lambda g: (-votes[g], -by_id[g]["rating_count"]))
        self.store.put_list("foryou", ordered)
        self.store.set("foryou_because", {str(g): names.get(because[g], "") for g in ordered})
        log.info("for you: %d suggestions from %d owned games", len(ordered), len(seeds))

    def explore(self, platform, year=None, decade=None, month=None, sort="popular", page=0, genre=None,
                min_rating=None, mode=None, theme=None):
        if month and year:
            start = calendar.timegm((year, month, 1, 0, 0, 0))
            end = calendar.timegm((year + (month == 12), month % 12 + 1, 1, 0, 0, 0))
        elif year:
            start, end = calendar.timegm((year, 1, 1, 0, 0, 0)), calendar.timegm((year + 1, 1, 1, 0, 0, 0))
        else:
            decade = decade or 1990
            start, end = calendar.timegm((decade, 1, 1, 0, 0, 0)), calendar.timegm((decade + 10, 1, 1, 0, 0, 0))
        plats = [platform] if platform else []
        key = f"explore:{platform}:{start}:{end}:{sort}:{page}:{genre}:{min_rating}:{mode}:{theme}"
        ids, _ = self.store.get_list(key, max_age=7 * DAY)
        if ids is None:
            games = self.igdb.explore(plats, start, end, sort=sort, offset=page * 60, genre=genre,
                                      min_rating=min_rating, mode=mode, theme=theme)
            self.store.put_games(games)
            ids = [g["id"] for g in games]
            self.store.put_list(key, ids)
        return self.store.get_games(ids)

    def search(self, text):
        key = f"search:{text.lower().strip()}"
        ids, _ = self.store.get_list(key, max_age=DAY)
        if ids is None:
            games = self.igdb.search(text)
            self.store.put_games(games)
            ids = [g["id"] for g in games]
            self.store.put_list(key, ids)
        return self.store.get_games(ids)

    def details(self, gid):
        cached = self.store.get(f"details:{gid}")
        if cached and time.time() - cached.get("_at", 0) < 7 * DAY:
            return cached
        d = self.igdb.details(gid) or {}
        d["_at"] = int(time.time())
        self.store.set(f"details:{gid}", d)
        return d

    # ---------- checks ----------
    def check_availability(self, game):
        with self.search_lock:
            best = self.prowlarr.availability(game)
        self.store.put_avail(game["id"], best)
        log.info("availability %s -> %s", game["name"], best["title"] if best else "none")
        return best

    def check_price(self, game):
        try:
            p = steam.price(game["steam"], self.cfg.country)
        except Exception as e:
            log.warning("steam price failed for %s: %s", game["name"], e)
            return None
        self.store.put_price(game["id"], p)
        return p

    # ---------- actions ----------
    def add(self, gid, download=True, platform=None):
        """Add to RetroArr (monitored) and, if the game is out, download it now instead of waiting for the sweep.
        `platform` (IGDB id) picks the system; it must be one the game is on."""
        game = self.store.get_game(gid)
        if platform is not None and platform not in game["platforms"]:
            raise ValueError(f"{game['name']} não existe em {platforms.name(platform)}")
        rid, igdb_platform = self.retroarr.add(game, platform)
        self.store.follow(gid)  # anything you add, you'll hear about
        msg = f"no RetroArr ({platforms.name(igdb_platform)})"
        if download and game.get("date") and game["date"] <= time.time():
            msg = self.retroarr.grab(rid, game["name"])
        self._refresh_library_soon()
        return msg

    def grab_pending(self):
        """Download now every followed, released game that RetroArr has but isn't owned or downloading."""
        done = []
        for g in self.store.get_games(list(self.store.follows())):
            if not g.get("date") or g["date"] > time.time():
                continue
            st = self.retroarr.status(g)
            if st["owned"] or st["downloading"] is not None or not st["monitored"]:
                continue
            done.append(f"{g['name']}: {self.add(g['id'])}")
        return done

    def wishlist(self, gid):
        self.retroarr.wishlist(self.store.get_game(gid))
        self._refresh_library_soon()
        return "no wishlist"

    def _refresh_library_soon(self):
        threading.Thread(target=self._safe, args=(self.retroarr.refresh,), daemon=True).start()

    # ---------- follows & notifications ----------
    def check_follows(self):
        follows = self.store.follows()
        if not follows or not self.ntfy:
            return
        now = time.time()
        games = {g["id"]: g for g in self.store.get_games(list(follows))}
        avail = self.store.get_avail(list(follows))
        prices = self.store.get_price(list(follows))
        for gid, f in follows.items():
            g = games.get(gid)
            if not g:
                continue
            link = g.get("url")
            if g.get("date") and g["date"] <= now and not f["notified_release"] and g["date"] > f["created"] - DAY:
                self.ntfy.send(f"Saiu: {g['name']}", "Um jogo que segues já foi lançado.", ("tada",), click=link)
                self.store.update_follow(gid, notified_release=int(now))
            a = (avail.get(gid) or (None, 0))[0]
            if a and not f["notified_avail"]:
                self.ntfy.send(f"Disponível: {g['name']}",
                               f"{a['title']}\n{a['size'] / 1e9:.1f} GB · {a['seeders']} fontes · {a.get('indexer') or ''}",
                               ("inbox_tray",), priority=4, click=link)
                self.store.update_follow(gid, notified_avail=int(now))
            p = (prices.get(gid) or (None, 0))[0]
            if p and p.get("final") is not None:
                last = f["last_price"]
                if last is not None and p["final"] < last - 0.009:
                    self.ntfy.send(f"Preço desceu: {g['name']}", f"{last:.2f} € → {p['final']:.2f} € na Steam"
                                   + (f" (−{p['discount']}%)" if p.get("discount") else ""), ("moneybag",), click=link)
                if last is None or abs(p["final"] - last) > 0.009:
                    self.store.update_follow(gid, last_price=p["final"])

    def digest(self):
        if not self.ntfy:
            return "ntfy não configurado"
        now = time.time()
        recent, _ = self.store.get_list("recent")
        upcoming, _ = self.store.get_list("upcoming")
        week = [g for g in self.store.get_games(recent or []) if g["date"] >= now - 7 * DAY]
        week.sort(key=lambda g: -g["hypes"])
        follows = self.store.follows()
        soon = [g for g in self.store.get_games(list(follows)) if g.get("date") and now < g["date"] <= now + 7 * DAY]
        avail = self.store.get_avail([g["id"] for g in week])
        lines = ["Saíram esta semana:"]
        for g in week[:8]:
            mark = " 🟢" if (avail.get(g["id"]) or (None,))[0] else ""
            lines.append(f"• {g['name']} ({', '.join(platforms.name(p) for p in g['platforms'][:3])}){mark}")
        if soon:
            lines.append("\nQue segues, saem nos próximos 7 dias:")
            lines += [f"• {g['name']} — {time.strftime('%d/%m', time.gmtime(g['date']))}" for g in soon]
        upcoming_games = self.store.get_games((upcoming or [])[:300])
        nxt = sorted((g for g in upcoming_games if g["date"] <= now + 7 * DAY), key=lambda g: -g["hypes"])[:5]
        if nxt:
            lines.append("\nEm destaque na próxima semana:")
            lines += [f"• {g['name']} — {time.strftime('%d/%m', time.gmtime(g['date']))}" for g in nxt]
        self.ntfy.send("Horizonarr: resumo da semana", "\n".join(lines), ("calendar",))
        self.store.set("digest_sent", int(now))
        return "resumo enviado"

    # ---------- background loops ----------
    def _safe(self, fn, *a):
        try:
            return fn(*a)
        except Exception as e:
            self.last_error = f"{fn.__name__}: {e}"
            log.exception("%s failed", fn.__name__)

    def _scheduler(self):
        last_library = 0
        while True:
            now = time.time()
            local = time.localtime()
            updated = self.store.get("releases_updated", 0)
            if self.igdb and (now - updated > 26 * 3600 or (local.tm_hour == self.cfg.refresh_hour and now - updated > 3600)):
                self._safe(self.refresh_releases)
            if self.retroarr and now - last_library > 600:
                self._safe(self.retroarr.refresh)
                last_library = now
                if self.igdb and now - self.store.get("foryou_updated", 0) > DAY:
                    self._safe(self.refresh_for_you)
                    self.store.set("foryou_updated", int(now))
            self._safe(self.check_follows)
            sent = self.store.get("digest_sent", 0)
            if (local.tm_wday == self.cfg.digest_weekday and local.tm_hour == self.cfg.digest_hour
                    and now - sent > 6 * DAY):
                self._safe(self.digest)
            time.sleep(120)

    def _worker(self):
        """Availability (paced, daily budget) and Steam prices, newest and followed games first."""
        done, day = 0, time.strftime("%F")
        while True:
            try:
                if time.strftime("%F") != day:
                    done, day = 0, time.strftime("%F")
                now = time.time()
                follows = list(self.store.follows())
                recent, _ = self.store.get_list("recent")
                upcoming, _ = self.store.get_list("upcoming")
                pool = self.store.get_games(follows + (recent or []) + (upcoming or []))
                checks = self.store.get_avail([g["id"] for g in pool])
                prices = self.store.get_price([g["id"] for g in pool])
                released = [g for g in pool if g.get("date") and g["date"] <= now]
                released.sort(key=lambda g: (g["id"] not in follows, -g["hypes"]))
                todo = next((g for g in released if now - (checks.get(g["id"]) or (None, 0))[1] > DAY), None)
                price_todo = next((g for g in pool if g.get("steam")
                                   and now - (prices.get(g["id"]) or (None, 0))[1] > DAY), None)
                if price_todo:
                    self.check_price(price_todo)
                    time.sleep(2)
                if self.prowlarr and todo and done < self.cfg.avail_per_day:
                    self._safe(self.check_availability, todo)
                    done += 1
                    time.sleep(self.cfg.avail_gap_seconds)
                elif not price_todo:
                    time.sleep(60)
            except Exception:
                log.exception("worker error")
                time.sleep(60)

    def start(self):
        threading.Thread(target=self._scheduler, daemon=True, name="scheduler").start()
        if self.prowlarr or self.igdb:
            threading.Thread(target=self._worker, daemon=True, name="worker").start()
