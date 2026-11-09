"""ntfy push notifications (JSON publish, so titles keep accents)."""
import logging

from .. import net

log = logging.getLogger("horizonarr")


class Ntfy:
    def __init__(self, url, topic, token=""):
        self.url, self.topic, self.token = url, topic, token

    def send(self, title, message, tags=("video_game",), priority=3, click=None):
        body = {"topic": self.topic, "title": title, "message": message, "tags": list(tags), "priority": priority}
        if click:
            body["click"] = click
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        try:
            net.request(self.url + "/", "POST", body, headers=headers, timeout=20)
        except Exception as e:  # a missed notification must never break a job
            log.warning("ntfy failed: %s", e)
