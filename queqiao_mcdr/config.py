"""Validated configuration with atomic persistence and retained last-known-good state."""
import copy
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from queqiao_mcdr.reconnect_backoff import ReconnectBackoff, finite_number


class Config:
    DEFAULT_CONFIG = {
        "mode": "server",
        "websocket": {
            "host": "0.0.0.0", "port": 8080, "path": "/minecraft/ws",
            "auto_start": True, "url": "ws://127.0.0.1:8080/minecraft/ws",
            "reconnect_interval": 5, "reconnect_max_times": 0,
            "reconnect_max_delay": 60, "reconnect_multiplier": 2,
            "reconnect_jitter_ratio": 0.1, "reconnect_reset_after": 30,
        },
        "server": {"name": "MCDR Server", "type": "mcdr"},
        "security": {"access_token": ""},
    }

    def __init__(self, server):
        self.server, self.logger = server, server.logger
        self.config_path = os.path.join(server.get_data_folder(), "config.json")
        self.config = copy.deepcopy(self.DEFAULT_CONFIG)
        self._apply_config()

    @staticmethod
    def _text(value, name, maximum=1000, empty=False):
        if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > maximum or "\x00" in value:
            raise ValueError(f"{name} must be a bounded string")
        return value

    @classmethod
    def _validated(cls, candidate):
        if not isinstance(candidate, dict) or candidate.get("mode") not in {"server", "client"}:
            raise ValueError("mode must be server or client")
        for section in ("websocket", "server", "security"):
            if not isinstance(candidate.get(section), dict):
                raise ValueError(f"{section} must be an object")
        ws, game, security = candidate["websocket"], candidate["server"], candidate["security"]
        host = cls._text(ws.get("host"), "host", 253)
        port = ws.get("port")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("port must be an integer from 1 to 65535")
        path = cls._text(ws.get("path"), "path")
        if not path.startswith("/") or "?" in path or "#" in path:
            raise ValueError("path must be an absolute URL path without query or fragment")
        auto_start = ws.get("auto_start")
        if type(auto_start) is not bool:
            raise ValueError("auto_start must be a boolean")
        url = cls._text(ws.get("url"), "url", 4096)
        parsed = urlsplit(url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.hostname or parsed.fragment:
            raise ValueError("url must be a ws/wss endpoint without fragment")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError("url has an invalid port")
        attempts = ws.get("reconnect_max_times")
        if type(attempts) is not int or not 0 <= attempts <= 1000000:
            raise ValueError("reconnect_max_times must be an integer from 0 to 1000000")
        policy = ReconnectBackoff(
            ws.get("reconnect_interval"), ws.get("reconnect_max_delay"),
            ws.get("reconnect_multiplier"), ws.get("reconnect_jitter_ratio"),
        )
        return {
            "mode": candidate["mode"], "websocket_host": host, "websocket_port": port,
            "websocket_path": path, "auto_start": auto_start, "websocket_url": url,
            "reconnect_interval": policy.initial_delay, "reconnect_max_times": attempts,
            "reconnect_max_delay": policy.max_delay, "reconnect_multiplier": policy.multiplier,
            "reconnect_jitter_ratio": policy.jitter_ratio,
            "reconnect_reset_after": finite_number(ws.get("reconnect_reset_after"), "reconnect_reset_after", 0, 3600),
            "server_name": cls._text(game.get("name"), "server name", 200),
            "server_type": cls._text(game.get("type"), "server type", 100),
            "access_token": cls._text(security.get("access_token"), "access token", 8192, empty=True),
        }

    def load_candidate(self):
        """Parse and validate a complete prospective configuration without changing runtime state."""
        candidate = copy.deepcopy(self.DEFAULT_CONFIG)
        path = Path(self.config_path)
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("configuration must be an object")
            self._update_dict(candidate, loaded)
        self._validated(candidate)
        return candidate

    def install(self, candidate, *, persist=True):
        """Persist before publishing the validated attribute set; invalid input changes nothing."""
        candidate = copy.deepcopy(candidate)
        attributes = self._validated(candidate)
        if persist:
            self.persist(candidate)
        self.config = candidate
        self.__dict__.update(attributes)

    def persist(self, candidate=None):
        """Atomically persist a validated candidate without publishing it in memory.

        Reload transactions use this after the replacement endpoint has started.
        Keeping persistence separate from publication prevents a failed endpoint
        handover from exposing a configuration that no live generation owns.
        """
        candidate = copy.deepcopy(self.config if candidate is None else candidate)
        self._validated(candidate)
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".queqiao-", suffix=".json", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(candidate, stream, ensure_ascii=False, indent=4, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def load_config(self):
        try:
            self.install(self.load_candidate())
            self.logger.info("QueQiao configuration validated and loaded")
            return True
        except (OSError, ValueError, TypeError) as exc:
            self.logger.error(f"QueQiao configuration rejected; previous state retained ({type(exc).__name__})")
            return False

    def reload_config(self):
        return self.load_config()

    def save_config(self):
        try:
            self.install(self.config)
            return True
        except (OSError, ValueError, TypeError) as exc:
            self.logger.error(f"QueQiao configuration save failed ({type(exc).__name__})")
            return False

    def _apply_config(self):
        self.__dict__.update(self._validated(self.config))

    def _update_dict(self, target, source):
        for key, value in source.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                self._update_dict(target[key], value)
            else:
                target[key] = value
