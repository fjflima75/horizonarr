"""Entry point: python -m horizonarr"""
import logging
import os
import sys

from . import __version__
from .app import App
from .config import Config
from .web import serve


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("horizonarr")
    cfg = Config()
    if not cfg.has_igdb:
        log.error("IGDB_CLIENT_ID and IGDB_CLIENT_SECRET are required (free Twitch developer app).")
        sys.exit(2)
    app = App(cfg)
    legacy = os.environ.get("LEGACY_RADAR_JSON")
    if legacy:
        n = app.store.import_radar_json(legacy)
        if n:
            log.info("imported %d games from %s", n, legacy)
    log.info("Horizonarr %s on :%d (RetroArr %s, Prowlarr %s, ntfy %s)", __version__, cfg.port,
             "on" if cfg.has_retroarr else "off", "on" if cfg.has_prowlarr else "off", "on" if cfg.has_ntfy else "off")
    app.start()
    serve(app, cfg.port)


if __name__ == "__main__":
    main()
