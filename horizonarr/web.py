"""HTTP server and page rendering (server-side HTML, no build step)."""
import html
import json
import logging
import os
import string
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, platforms
from .sources.igdb import MODES

log = logging.getLogger("horizonarr")
with open(os.path.join(os.path.dirname(__file__), "templates", "page.html"), encoding="utf-8") as _f:
    TEMPLATE = string.Template(_f.read())
IMG = "https://images.igdb.com/igdb/image/upload"
MONTHS = ["", "jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
TABS = [("recentes", "Recentes"), ("brevemente", "Brevemente"), ("calendario", "Calendário"), ("parati", "Para ti"),
        ("explorar", "Explorar"), ("seguir", "A seguir")]
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MONTH_NAMES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
               "Outubro", "Novembro", "Dezembro"]
DAY_S = 86400
PAGE_SIZE = 120
e = html.escape


def fdate(ts):
    if not ts:
        return "sem data"
    t = time.gmtime(ts)
    return f"{t.tm_mday} {MONTHS[t.tm_mon]} {t.tm_year}"


def fsize(b):
    return f"{b / 1e9:.1f} GB" if b >= 1e9 else f"{b / 1e6:.0f} MB"


class Page:
    def __init__(self, app, params):
        self.app, self.p = app, params

    def link(self, **kw):
        q = {k: v for k, v in {**self.p, **kw}.items() if v not in (None, "", "0", 0)}
        q.pop("page", None) if "page" not in kw else None
        return "/?" + urllib.parse.urlencode(q)

    # ---------- header / filters ----------
    def header(self):
        updated = self.app.store.get("releases_updated", 0)
        when = time.strftime("%d/%m %H:%M", time.localtime(updated)) if updated else "nunca"
        err = f' · <span style="color:var(--warn)">{e(self.app.last_error)}</span>' if self.app.last_error else ""
        q = e(self.p.get("q", ""))
        return (f'<header><h1><a href="/">🌅 Horizonarr</a></h1><span class="sub">atualizado {when}{err} · '
                f'<button class="btn" onclick="act(this,\'/refresh\')">Atualizar</button></span>'
                f'<form class="search" action="/"><input type="hidden" name="tab" value="pesquisa">'
                f'<input name="q" value="{q}" placeholder="Procurar um jogo…" aria-label="Procurar"></form></header>')

    def tabs(self):
        tab = self.p.get("tab", "recentes")
        return '<nav class="tabs">' + "".join(
            f'<a class="{"on" if tab == t else ""}" href="/?tab={t}">{label}</a>' for t, label in TABS) + "</nav>"

    def chip_filters(self, genres_present):
        group = self.p.get("p", "")
        genre = self.p.get("g", "")
        out = ['<div class="filters"><span class="label">Plataforma</span>',
               f'<a class="{"on" if not group else ""}" href="{self.link(p="")}">Todas</a>']
        out += [f'<a class="{"on" if group == g else ""}" href="{self.link(p=g)}">{g}</a>' for g in platforms.GROUPS]
        out.append("</div>")
        if genres_present:
            out.append('<div class="filters"><span class="label">Género</span>'
                       f'<a class="{"on" if not genre else ""}" href="{self.link(g="")}">Todos</a>')
            out += [f'<a class="{"on" if genre == g else ""}" href="{self.link(g=g)}">{e(g)}</a>'
                    for g in genres_present]
            out.append("</div>")
        avail, hide, sort = self.p.get("avail") == "1", self.p.get("hide") == "1", self.p.get("sort", "")
        out.append('<div class="filters"><span class="label">Mostrar</span>'
                   f'<a class="{"on" if avail else ""}" href="{self.link(avail="" if avail else "1")}">🟢 Só disponíveis</a>'
                   f'<a class="{"on" if hide else ""}" href="{self.link(hide="" if hide else "1")}">Esconder o que tenho</a>'
                   f'<a class="{"on" if sort != "data" else ""}" href="{self.link(sort="")}">Mais aguardados</a>'
                   f'<a class="{"on" if sort == "data" else ""}" href="{self.link(sort="data")}">Por data</a></div>')
        return "".join(out)

    def explore_form(self, genres, themes=()):
        p = self.p
        now_year = time.gmtime().tm_year
        decades = range(1970, now_year + 1, 10)
        years = range(now_year, 1971, -1)

        def opts(values, selected, labels=None):
            return "".join(f'<option value="{v}"{" selected" if str(v) == str(selected) else ""}>'
                           f'{e(str(labels[i] if labels else v))}</option>' for i, v in enumerate(values))

        plat_opts = '<option value="">Todas</option>' + "".join(
            f'<optgroup label="{e(grp)}">' + "".join(
                f'<option value="{pid}"{" selected" if str(pid) == p.get("plat", "") else ""}>{e(platforms.name(pid))}</option>'
                for pid in ids) + "</optgroup>" for grp, ids in platforms.EXPLORE.items())
        return ('<form class="filters" action="/"><input type="hidden" name="tab" value="explorar">'
                f'<span class="label">Década</span><select name="decade" onchange="this.form.year.value=\'\';this.form.submit()">'
                f'{opts(list(decades), p.get("decade", "1990"), [f"Anos {str(d)[2:]}" if d < 2000 else f"Anos {d}" for d in decades])}</select>'
                f'<span class="label">Ano</span><select name="year" onchange="this.form.submit()"><option value="">Toda a década</option>'
                f'{opts(list(years), p.get("year", ""))}</select>'
                f'<span class="label">Mês</span><select name="month" onchange="this.form.submit()"><option value="">Todos</option>'
                f'{opts(list(range(1, 13)), p.get("month", ""), MONTHS[1:])}</select>'
                f'<span class="label">Plataforma</span><select name="plat" onchange="this.form.submit()">{plat_opts}</select>'
                f'<span class="label">Género</span><select name="genre" onchange="this.form.submit()"><option value="">Todos</option>'
                f'{opts([g[0] for g in genres], p.get("genre", ""), [g[1] for g in genres])}</select>'
                f'<span class="label">Tema</span><select name="theme" onchange="this.form.submit()"><option value="">Todos</option>'
                f'{opts([t[0] for t in themes], p.get("theme", ""), [t[1] for t in themes])}</select>'
                f'<span class="label">Modo</span><select name="mode" onchange="this.form.submit()"><option value="">Todos</option>'
                f'{opts([m[0] for m in MODES], p.get("mode", ""), [m[1] for m in MODES])}</select>'
                f'<span class="label">Nota mín.</span><select name="minr" onchange="this.form.submit()"><option value="">Qualquer</option>'
                f'{opts([60, 70, 80, 90], p.get("minr", ""), ["60+", "70+", "80+", "90+"])}</select>'
                f'<span class="label">Ordem</span><select name="esort" onchange="this.form.submit()">'
                f'{opts(["popular", "rating", "date"], p.get("esort", "popular"), ["Mais populares", "Melhor avaliados", "Por data"])}'
                '</select></form>')

    # ---------- cards ----------
    def card(self, g, avail, price, status, following, because=None):
        now = time.time()
        cover = (f'<img loading="lazy" src="{IMG}/t_cover_big/{g["cover"]}.jpg" alt="">' if g.get("cover") else "")
        badges = []
        if status:
            if status["owned"]:
                badges.append('<span class="badge ok">📚 Tenho</span>')
            if status["downloading"] is not None:
                badges.append(f'<span class="badge dl">⏬ {status["downloading"]}%</span>')
            if status["wishlisted"]:
                badges.append('<span class="badge wish">⭐ Wishlist</span>')
            if status["monitored"] and not status["owned"] and status["downloading"] is None:
                badges.append('<span class="badge mon">👁 À procura</span>')
        play = f'<button class="play" onclick="play(\'{e(g["video"])}\')">▶ Trailer</button>' if g.get("video") else ""
        cover_play = play
        info = [fdate(g.get("date"))]
        if g.get("rating"):
            info.append(f"★ {g['rating']}")
        plats = "".join(f'<span class="chip">{e(platforms.name(x))}</span>' for x in platforms.known(g.get("platforms", []))[:6])
        genres = " · ".join(e(x) for x in g.get("genres", [])[:3])
        a_html = ""
        if avail is not None:
            a, checked = avail
            if a:
                a_html = (f'<div class="avail" title="{e(a["title"])}">🟢 Disponível · {fsize(a["size"])} · '
                          f'{a["seeders"]} fontes</div>')
            elif checked:
                a_html = f'<div class="noavail">Sem versão nos indexers ({time.strftime("%d/%m", time.localtime(checked))})</div>'
        p_html = ""
        if price and price[0]:
            pr = price[0]
            p_html = ('<div class="price">Steam: grátis</div>' if pr.get("free") else
                      f'<div class="price">Steam: {pr["final"]:.2f} €' + (f' <b>−{pr["discount"]}%</b>' if pr.get("discount") else "")
                      + "</div>")
        gid = g["id"]
        acts = []
        if self.app.retroarr and not (status and status["owned"]):
            acts.append(f'<button class="btn primary" onclick="act(this,\'/add?id={gid}\')">Adicionar</button>')
        if self.app.retroarr and g.get("steam") and not (status and status["wishlisted"]):
            acts.append(f'<button class="btn" onclick="act(this,\'/wishlist?id={gid}\')">⭐ Wishlist</button>')
        if self.app.prowlarr and g.get("date") and g["date"] <= now and not (avail and avail[0]):
            acts.append(f'<button class="btn" onclick="act(this,\'/check?id={gid}\',j=>this.closest(\'.card\')'
                        f'.querySelector(\'.acts\').insertAdjacentHTML(\'beforebegin\',j.html))">🔎 Ver versão</button>')
        acts.append(f'<button class="btn" onclick="act(this,\'/follow?id={gid}&on={0 if following else 1}\')">'
                    f'{"★ A seguir" if following else "☆ Seguir"}</button>')
        summary = f'<div class="summary" title="Clica para ler tudo">{e(g["summary"])}</div>' if g.get("summary") else ""
        if because:
            summary = f'<div class="meta">Porque tens <b>{e(because)}</b></div>' + summary
        return (f'<article class="card"><div class="cover"><a href="/game/{gid}">{cover}</a>'
                f'<span class="badges">{"".join(badges)}</span>{cover_play}</div>'
                f'<div class="body"><div class="name"><a href="/game/{gid}">{e(g["name"])}</a></div>'
                f'<div class="meta">{" · ".join(info)}{" · " + genres if genres else ""}</div>'
                f'<div class="chips">{plats}</div>{summary}{a_html}{p_html}'
                f'<div class="acts">{"".join(acts)}</div></div></article>')

    def calendar(self):
        """Upcoming releases (and followed games) grouped by day, compact rows."""
        now = time.time()
        ids, _ = self.app.store.get_list("upcoming")
        follows = self.app.store.follows()
        games = {g["id"]: g for g in self.app.store.get_games(list(dict.fromkeys((ids or []) + list(follows))))}
        games = [g for g in games.values() if g.get("date") and g["date"] >= now - DAY_S]
        genres_present = sorted({x for g in games for x in g.get("genres", [])})
        games = self.filtered(games)
        if self.p.get("seg") == "1":
            games = [g for g in games if g["id"] in follows]
        games.sort(key=lambda g: (g["date"], -g["hypes"]))
        seg = self.p.get("seg") == "1"
        out = [self.chip_filters(genres_present),
               f'<div class="filters"><a class="{"on" if not seg else ""}" href="{self.link(seg="")}">Todos</a>'
               f'<a class="{"on" if seg else ""}" href="{self.link(seg="1")}">★ Só os que sigo</a></div>']
        if not games:
            return "".join(out) + '<div class="empty">Nada marcado para os próximos 90 dias com estes filtros.</div>'
        day, month = None, None
        rows = []
        for g in games[:400]:
            t = time.gmtime(g["date"])
            if (t.tm_year, t.tm_mon) != month:
                month = (t.tm_year, t.tm_mon)
                rows.append(f'<h3 class="cal-month">{MONTH_NAMES[t.tm_mon]} {t.tm_year}</h3>')
            if t.tm_yday != day:
                day = t.tm_yday
                rows.append(f'<div class="cal-day">{WEEKDAYS[t.tm_wday]} {t.tm_mday}</div>')
            cover = f'<img loading="lazy" src="{IMG}/t_cover_small/{g["cover"]}.jpg" alt="">' if g.get("cover") else '<span></span>'
            plats = "".join(f'<span class="chip">{e(platforms.name(x))}</span>' for x in platforms.known(g["platforms"])[:5])
            star = "★ " if g["id"] in follows else ""
            hype = f'<span class="meta">🔥 {g["hypes"]}</span>' if g.get("hypes") else ""
            follow = (f'<button class="btn" onclick="act(this,\'/follow?id={g["id"]}&on={0 if g["id"] in follows else 1}\')">'
                      f'{"★" if g["id"] in follows else "☆"}</button>')
            rows.append(f'<div class="cal-row">{cover}<div><a class="name" href="/game/{g["id"]}">{star}{e(g["name"])}</a>'
                        f'<div class="chips">{plats}{hype}</div></div>{follow}</div>')
        return "".join(out) + f'<section class="cal">{"".join(rows)}</section>'

    def grid(self, games, more_link=None, because=None):
        if not games:
            return '<div class="empty">Nada para mostrar com estes filtros.</div>'
        ids = [g["id"] for g in games]
        avail = self.app.store.get_avail(ids)
        prices = self.app.store.get_price(ids)
        follows = self.app.store.follows()
        cards = []
        for g in games:
            status = self.app.retroarr.status(g) if self.app.retroarr else None
            cards.append(self.card(g, avail.get(g["id"], (None, 0)), prices.get(g["id"]), status, g["id"] in follows,
                                   (because or {}).get(str(g["id"]))))
        pager = f'<div class="pager"><a class="btn" href="{more_link}">Mostrar mais</a></div>' if more_link else ""
        return f'<section class="grid">{"".join(cards)}</section>{pager}'

    # ---------- filtering for the stored lists ----------
    def filtered(self, games):
        group, genre = self.p.get("p", ""), self.p.get("g", "")
        if group in platforms.GROUPS:
            games = [g for g in games if set(g["platforms"]) & set(platforms.GROUPS[group])]
        if genre:
            games = [g for g in games if genre in g.get("genres", [])]
        if self.p.get("avail") == "1":
            avail = self.app.store.get_avail([g["id"] for g in games])
            games = [g for g in games if (avail.get(g["id"]) or (None,))[0]]
        if self.p.get("hide") == "1" and self.app.retroarr:
            games = [g for g in games if not (st := self.app.retroarr.status(g))["owned"] and st["downloading"] is None]
        return games

    def render(self):
        tab = self.p.get("tab", "recentes")
        limit = int(self.p.get("n", PAGE_SIZE))
        parts = [self.header(), self.tabs()]
        if tab in ("recentes", "brevemente"):
            ids, _ = self.app.store.get_list("recent" if tab == "recentes" else "upcoming")
            games = self.app.store.get_games(ids or [])
            genres_present = sorted({x for g in games for x in g.get("genres", [])})
            games = self.filtered(games)
            if self.p.get("sort") == "data":
                games.sort(key=lambda g: g["date"] or 0, reverse=(tab == "recentes"))
            else:
                games.sort(key=lambda g: -g["hypes"])
            title = (f"Saíram nos últimos 30 dias · {len(games)} jogos" if tab == "recentes"
                     else f"Saem nos próximos 90 dias · {len(games)} jogos")
            parts += [self.chip_filters(genres_present), f'<p class="sub">{title}</p>',
                      self.grid(games[:limit], self.link(n=limit + PAGE_SIZE) if len(games) > limit else None)]
        elif tab == "explorar":
            genres = self.app.genres() if self.app.igdb else []
            page = int(self.p.get("page", 0))
            plat = int(self.p["plat"]) if self.p.get("plat") else None
            year = int(self.p["year"]) if self.p.get("year") else None
            month = int(self.p["month"]) if self.p.get("month") else None
            games = self.app.explore(plat, year=year, decade=int(self.p.get("decade", 1990)), month=month,
                                     sort=self.p.get("esort", "popular"), page=page,
                                     genre=self.p.get("genre") or None, min_rating=self.p.get("minr") or None,
                                     mode=self.p.get("mode") or None, theme=self.p.get("theme") or None)
            nav = '<div class="pager">'
            if page:
                nav += f'<a class="btn" href="{self.link(page=page - 1)}">← Anteriores</a>'
            if len(games) == 60:
                nav += f'<a class="btn" href="{self.link(page=page + 1)}">Seguintes →</a>'
            themes = self.app.themes() if self.app.igdb else []
            parts += [self.explore_form(genres, themes), self.grid(games), nav + "</div>"]
        elif tab == "parati":
            ids, updated = self.app.store.get_list("foryou")
            because = self.app.store.get("foryou_because", {})
            games = self.app.store.get_games(ids or [])
            genres_present = sorted({x for g in games for x in g.get("genres", [])})
            games = self.filtered(games)
            if not ids:
                parts.append('<div class="empty">Ainda a preparar sugestões a partir da tua biblioteca do RetroArr…</div>')
            else:
                parts += [self.chip_filters(genres_present),
                          f'<p class="sub">Parecidos com jogos que tens · {len(games)} sugestões · '
                          f'atualizado {time.strftime("%d/%m", time.localtime(updated))}</p>',
                          self.grid(games[:limit], self.link(n=limit + PAGE_SIZE) if len(games) > limit else None,
                                    because=because)]
        elif tab == "calendario":
            parts.append(self.calendar())
        elif tab == "seguir":
            follows = self.app.store.follows()
            games = sorted(self.app.store.get_games(list(follows)), key=lambda g: g.get("date") or 0, reverse=True)
            parts += ['<p class="sub">Jogos que segues: avisos no ntfy quando saem, ficam disponíveis ou baixam de preço.</p>',
                      self.grid(games)]
        elif tab == "pesquisa":
            q = self.p.get("q", "").strip()
            games = self.app.search(q) if q and self.app.igdb else []
            parts += [f'<p class="sub">Resultados para “{e(q)}”</p>', self.grid(games)]
        return TEMPLATE.substitute(title="Horizonarr", body="".join(parts))

    def render_game(self, gid):
        g = self.app.store.get_game(gid)
        if not g:
            return None
        d = self.app.details(gid) if self.app.igdb else {}
        card = self.grid([g])  # reuse the badges, buttons and availability of the list card
        shots = "".join(f'<a href="{IMG}/t_1080p/{s}.jpg" target="_blank"><img loading="lazy" src="{IMG}/t_screenshot_big/{s}.jpg" alt=""></a>'
                        for s in d.get("screenshots", []))
        videos = "".join(f'<div class="video"><iframe loading="lazy" src="https://www.youtube-nocookie.com/embed/{e(v["id"])}" '
                         f'title="{e(v["name"])}" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe></div>'
                         for v in d.get("videos", []))
        facts = [("Lançamento", fdate(g.get("date"))), ("Plataformas", ", ".join(platforms.name(p) for p in g["platforms"])),
                 ("Géneros", ", ".join(g.get("genres", []))), ("Temas", ", ".join(d.get("themes", []))),
                 ("Modos", ", ".join(d.get("modes", []))), ("Produção", ", ".join(d.get("developers", []))),
                 ("Editora", ", ".join(d.get("publishers", []))), ("Série", ", ".join(d.get("franchises", []))),
                 ("Nota IGDB", f"{g['rating']} ({g.get('rating_count', 0)} avaliações)" if g.get("rating") else "")]
        facts_html = "".join(f"<dt>{k}</dt><dd>{e(v)}</dd>" for k, v in facts if v)
        summary = e(d.get("summary") or g.get("summary") or "Sem sinopse no IGDB.").replace("\n", "<br>")
        cover = f'<img class="big" src="{IMG}/t_720p/{g["cover"]}.jpg" alt="">' if g.get("cover") else ""
        body = (f'{self.header()}{self.tabs()}<div class="detail"><div>{cover}{card.replace("grid", "grid one", 1)}</div>'
                f'<div><h2>{e(g["name"])}</h2><p>{summary}</p><dl class="facts">{facts_html}</dl>'
                f'{videos}<div class="shots">{shots}</div>'
                f'<p class="sub"><a href="{e(g.get("url") or "#")}" target="_blank">Ver no IGDB ↗</a></p></div></div>')
        return TEMPLATE.substitute(title=f"{g['name']} · Horizonarr", body=body.replace(
            '<section class="grid one">', '<section class="grid" style="grid-template-columns:1fr">'))


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"Horizonarr/{__version__}"

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

        def reply(self, code, body, ctype="text/html; charset=utf-8"):
            data = body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def json(self, code, obj):
            self.reply(code, json.dumps(obj), "application/json")

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            params = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            try:
                if url.path == "/health":
                    return self.json(200, {"version": __version__, "updated": app.store.get("releases_updated", 0),
                                           **app.store.counts(), "error": app.last_error})
                if url.path.startswith("/game/"):
                    page = Page(app, params).render_game(int(url.path.rsplit("/", 1)[1]))
                    return self.reply(200, page) if page else self.reply(404, "Jogo não encontrado")
                if url.path == "/":
                    return self.reply(200, Page(app, params).render())
                self.reply(404, "Not found")
            except Exception as ex:
                log.exception("GET %s failed", self.path)
                self.reply(500, f"<pre>Erro: {e(str(ex))}</pre>")

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            params = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
            try:
                gid = int(params["id"]) if "id" in params else None
                if url.path == "/refresh":
                    import threading
                    threading.Thread(target=app._safe, args=(app.refresh_releases,), daemon=True).start()
                    return self.json(200, {"ok": True, "msg": "a atualizar"})
                if url.path == "/digest":
                    return self.json(200, {"ok": True, "msg": app.digest()})
                if url.path == "/add":
                    return self.json(200, {"ok": True, "msg": app.add(gid)})
                if url.path == "/wishlist":
                    return self.json(200, {"ok": True, "msg": app.wishlist(gid)})
                if url.path == "/follow":
                    on = params.get("on", "1") == "1"
                    app.store.follow(gid, on)
                    return self.json(200, {"ok": True, "msg": "a seguir" if on else "deixaste de seguir"})
                if url.path == "/check":
                    best = app.check_availability(app.store.get_game(gid))
                    snippet = (f'<div class="avail">🟢 Disponível · {fsize(best["size"])} · {best["seeders"]} fontes</div>'
                               if best else '<div class="noavail">Sem versão nos indexers agora</div>')
                    return self.json(200, {"ok": True, "msg": "disponível" if best else "não há", "html": snippet})
                self.json(404, {"ok": False, "msg": "?"})
            except Exception as ex:
                log.exception("POST %s failed", self.path)
                self.json(500, {"ok": False, "msg": str(ex)[:90]})

    return Handler


def serve(app, port):
    ThreadingHTTPServer(("0.0.0.0", port), make_handler(app)).serve_forever()
