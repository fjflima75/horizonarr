"""Settings come from environment variables; secrets can also come from files (VAR_FILE)."""
import json
import os
from dataclasses import dataclass, field


def env(name, default=""):
    """Read NAME, or the contents of the file named by NAME_FILE (Docker secrets style)."""
    path = os.environ.get(f"{name}_FILE")
    if path:
        with open(path) as f:
            return f.read().strip()
    return os.environ.get(name, default).strip()


def _retroarr_key():
    """RetroArr keeps its key in config/apikey.json; accept either the key or that file."""
    key = env("RETROARR_API_KEY")
    if key:
        return key
    path = os.environ.get("RETROARR_API_KEY_JSON")
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)["Key"]
    return ""


@dataclass
class Config:
    data_dir: str = field(default_factory=lambda: env("DATA_DIR", "/data"))
    port: int = field(default_factory=lambda: int(env("PORT", "8080")))
    timezone: str = field(default_factory=lambda: env("TZ", "UTC"))
    country: str = field(default_factory=lambda: env("COUNTRY", "PT").upper())  # Steam prices

    igdb_client_id: str = field(default_factory=lambda: env("IGDB_CLIENT_ID"))
    igdb_client_secret: str = field(default_factory=lambda: env("IGDB_CLIENT_SECRET"))

    retroarr_url: str = field(default_factory=lambda: env("RETROARR_URL").rstrip("/"))
    retroarr_key: str = field(default_factory=_retroarr_key)
    retroarr_db: str = field(default_factory=lambda: env("RETROARR_DB"))  # optional: clears wishlist paths
    retroarr_steam_folder: str = field(default_factory=lambda: env("RETROARR_STEAM_FOLDER"))

    prowlarr_url: str = field(default_factory=lambda: env("PROWLARR_URL").rstrip("/"))
    prowlarr_key: str = field(default_factory=lambda: env("PROWLARR_API_KEY"))

    qbit_url: str = field(default_factory=lambda: env("QBIT_URL").rstrip("/"))
    qbit_user: str = field(default_factory=lambda: env("QBIT_USERNAME", "admin"))
    qbit_password: str = field(default_factory=lambda: env("QBIT_PASSWORD"))

    ntfy_url: str = field(default_factory=lambda: env("NTFY_URL").rstrip("/"))  # server, e.g. http://ntfy:80
    ntfy_topic: str = field(default_factory=lambda: env("NTFY_TOPIC", "horizonarr"))
    ntfy_token: str = field(default_factory=lambda: env("NTFY_TOKEN"))

    avail_per_day: int = field(default_factory=lambda: int(env("AVAILABILITY_PER_DAY", "150")))
    avail_gap_seconds: int = field(default_factory=lambda: int(env("AVAILABILITY_GAP_SECONDS", "60")))
    refresh_hour: int = field(default_factory=lambda: int(env("REFRESH_HOUR", "6")))
    digest_weekday: int = field(default_factory=lambda: int(env("DIGEST_WEEKDAY", "0")))  # 0 = Monday
    digest_hour: int = field(default_factory=lambda: int(env("DIGEST_HOUR", "9")))

    @property
    def has_igdb(self):
        return bool(self.igdb_client_id and self.igdb_client_secret)

    @property
    def has_retroarr(self):
        return bool(self.retroarr_url and self.retroarr_key)

    @property
    def has_prowlarr(self):
        return bool(self.prowlarr_url and self.prowlarr_key)

    @property
    def has_qbit(self):
        return bool(self.qbit_url and self.qbit_password)

    @property
    def has_ntfy(self):
        return bool(self.ntfy_url)
