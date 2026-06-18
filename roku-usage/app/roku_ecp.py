from __future__ import annotations

import json
import socket
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


SSDP_GROUP = "239.255.255.250"
SSDP_PORT = 1900
ROKU_ECP_PORT = 8060
USER_AGENT = "sbc-roku-usage/1.0"
STREAMING_APP_HINTS = (
    "tubi",
    "netflix",
    "hulu",
    "disney",
    "prime video",
    "primevideo",
    "youtube",
    "peacock",
    "paramount",
    "plex",
    "max",
    "roku channel",
)


@dataclass(slots=True)
class RokuDevice:
    host: str
    port: int = ROKU_ECP_PORT
    name: str = ""
    model: str = ""
    serial: str = ""
    mac: str = ""
    vendor: str = ""
    location: str = ""

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict[str, str | int]:
        return {
            "host": self.host,
            "port": self.port,
            "name": self.name,
            "model": self.model,
            "serial": self.serial,
            "mac": self.mac,
            "vendor": self.vendor,
            "location": self.location,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _normalize_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _xml_payload(element: ET.Element) -> dict[str, Any]:
    payload: dict[str, Any] = {"tag": _local_name(element.tag)}
    payload.update({f"@{key}": value for key, value in element.attrib.items()})
    text = _normalize_text(element.text)
    if text:
        payload["text"] = text
    for child in element:
        child_payload = _xml_payload(child)
        key = _local_name(child.tag)
        value: Any = child_payload if len(child_payload) > 1 else child_payload.get("text", "")
        if key in payload:
            existing = payload[key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                payload[key] = [existing, value]
        else:
            payload[key] = value
    return payload


def _http_get_bytes(url: str, timeout: float = 3.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _http_get_xml(url: str, timeout: float = 3.0) -> dict[str, Any]:
    try:
        payload = _http_get_bytes(url, timeout=timeout)
        return _xml_payload(ET.fromstring(payload))
    except (urllib.error.URLError, ET.ParseError, TimeoutError, OSError, ValueError):
        return {}


def _ssdp_headers(raw_response: bytes) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in raw_response.decode("utf-8", errors="ignore").split("\r\n"):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return headers


def fetch_device_info(base_url: str, timeout: float = 3.0) -> dict[str, Any]:
    return _http_get_xml(f"{base_url}/query/device-info", timeout=timeout)


def fetch_active_app(base_url: str, timeout: float = 3.0) -> dict[str, Any]:
    return _http_get_xml(f"{base_url}/query/active-app", timeout=timeout)


def fetch_media_player(base_url: str, timeout: float = 3.0) -> dict[str, Any]:
    return _http_get_xml(f"{base_url}/query/media-player", timeout=timeout)


def _unwrap_active_app(active_app: dict[str, Any]) -> dict[str, Any]:
    app = active_app.get("app")
    if isinstance(app, dict):
        return app
    return active_app


def classify_system_state(status: dict[str, Any]) -> dict[str, str]:
    device_info = status.get("device_info", {}) or {}
    active_app = _unwrap_active_app(status.get("active_app", {}) or {})
    media_player = status.get("media_player", {}) or {}

    power_mode = _normalize_text(device_info.get("power-mode")).lower()
    active_app_id = _normalize_text(active_app.get("@id") or active_app.get("id"))
    active_app_name = _normalize_text(active_app.get("text") or active_app.get("name") or active_app.get("@name"))
    media_state = _normalize_text(media_player.get("state") or media_player.get("text")).lower()
    media_title = _normalize_text(media_player.get("title") or media_player.get("content-title") or media_player.get("text"))
    app_signature = f"{active_app_id} {active_app_name}".strip().lower()
    looks_like_streaming_app = any(hint in app_signature for hint in STREAMING_APP_HINTS)

    if power_mode in {"power off", "standby", "off"}:
        system_state = "OFF"
    elif media_state in {"play", "playing", "buffering", "pause", "paused"} or looks_like_streaming_app:
        system_state = "STREAMING"
    else:
        system_state = "IDLE"

    return {
        "system_state": system_state,
        "power_mode": power_mode,
        "active_app_id": active_app_id,
        "active_app_name": active_app_name,
        "media_state": media_state,
        "media_title": media_title,
        "app_signature": app_signature,
    }


def poll_roku_device(device: RokuDevice, timeout: float = 3.0) -> dict[str, Any] | None:
    base_url = device.base_url
    device_info = fetch_device_info(base_url, timeout=timeout)
    if not device_info:
        return None

    active_app = fetch_active_app(base_url, timeout=timeout)
    media_player = fetch_media_player(base_url, timeout=timeout)

    return {
        "observed_at": _now_iso(),
        "device": device.to_dict(),
        "device_info": device_info,
        "active_app": active_app,
        "media_player": media_player,
        "system": classify_system_state(
            {
                "device_info": device_info,
                "active_app": active_app,
                "media_player": media_player,
            }
        ),
    }


def discover_roku_devices(timeout: float = 2.0, retries: int = 1) -> list[RokuDevice]:
    seen: dict[tuple[str, int], RokuDevice] = {}
    probe = "\r\n".join(
        [
            "M-SEARCH * HTTP/1.1",
            f"HOST: {SSDP_GROUP}:{SSDP_PORT}",
            'MAN: "ssdp:discover"',
            "MX: 1",
            "ST: roku:ecp",
            "",
            "",
        ]
    ).encode("ascii")

    deadline = time.monotonic() + max(timeout, 0.1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP) as sock:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(0.2)
        for _ in range(max(retries, 1)):
            try:
                sock.sendto(probe, (SSDP_GROUP, SSDP_PORT))
            except OSError:
                break

        while time.monotonic() < deadline:
            try:
                raw_response, address = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break

            headers = _ssdp_headers(raw_response)
            host = address[0]
            port = ROKU_ECP_PORT
            location = headers.get("location", "")
            if location:
                parsed = urllib.parse.urlparse(location)
                if parsed.hostname:
                    host = parsed.hostname
                if parsed.port:
                    port = parsed.port

            device = RokuDevice(host=host, port=port, location=location)
            details = fetch_device_info(device.base_url)
            if details:
                device.name = _normalize_text(details.get("friendly-device-name") or details.get("user-device-name"))
                device.model = _normalize_text(details.get("model-name") or details.get("model-number"))
                device.serial = _normalize_text(details.get("serial-number"))
                device.mac = _normalize_text(details.get("mac-address"))
                device.vendor = _normalize_text(details.get("vendor-name"))
            seen[(device.host, device.port)] = device

    return sorted(seen.values(), key=lambda device: (device.name or device.host).lower())


def ensure_database(path: Path | str) -> sqlite3.Connection:
    database_path = Path(path)
    if database_path.parent != Path(""):
        database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    _create_schema(connection)
    connection.commit()
    return connection


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 8060,
            name TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            serial TEXT NOT NULL DEFAULT '',
            mac TEXT NOT NULL DEFAULT '',
            vendor TEXT NOT NULL DEFAULT '',
            location TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(host, port)
        );

        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            observed_at TEXT NOT NULL,
            power_mode TEXT NOT NULL DEFAULT '',
            active_app_id TEXT NOT NULL DEFAULT '',
            active_app_name TEXT NOT NULL DEFAULT '',
            media_state TEXT NOT NULL DEFAULT '',
            media_title TEXT NOT NULL DEFAULT '',
            raw_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            state_key TEXT NOT NULL,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            sample_count INTEGER NOT NULL DEFAULT 1,
            power_mode TEXT NOT NULL DEFAULT '',
            active_app_id TEXT NOT NULL DEFAULT '',
            active_app_name TEXT NOT NULL DEFAULT '',
            media_state TEXT NOT NULL DEFAULT '',
            media_title TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_samples_device_observed ON samples(device_id, observed_at);
        CREATE INDEX IF NOT EXISTS idx_sessions_device_started ON sessions(device_id, started_at);
        """
    )


def _device_fields(device: RokuDevice) -> tuple[str, int, str, str, str, str, str, str, str]:
    return (
        device.host,
        device.port,
        device.name,
        device.model,
        device.serial,
        device.mac,
        device.vendor,
        device.location,
        _now_iso(),
    )


def _upsert_device(connection: sqlite3.Connection, device: RokuDevice) -> int:
    connection.execute(
        """
        INSERT INTO devices(host, port, name, model, serial, mac, vendor, location, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(host, port) DO UPDATE SET
            name=excluded.name,
            model=excluded.model,
            serial=excluded.serial,
            mac=excluded.mac,
            vendor=excluded.vendor,
            location=excluded.location,
            updated_at=excluded.updated_at
        """,
        _device_fields(device),
    )
    row = connection.execute("SELECT id FROM devices WHERE host = ? AND port = ?", (device.host, device.port)).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert Roku device")
    return int(row["id"])


def _session_key(status: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    system = status.get("system", {}) or classify_system_state(status)
    state_key = _normalize_text(system.get("system_state")).upper() or "IDLE"
    return (
        state_key,
        _normalize_text(system.get("power_mode")).lower(),
        _normalize_text(system.get("active_app_id")),
        _normalize_text(system.get("active_app_name")),
        _normalize_text(system.get("media_state")).lower(),
        _normalize_text(system.get("media_title")),
    )


def store_usage_sample(connection: sqlite3.Connection, device: RokuDevice, status: dict[str, Any]) -> None:
    observed_at = _normalize_text(status.get("observed_at")) or _now_iso()

    device_id = _upsert_device(connection, device)
    state_key, power_mode, active_app_id, active_app_name, media_state, media_title = _session_key(status)

    connection.execute(
        """
        INSERT INTO samples(device_id, observed_at, power_mode, active_app_id, active_app_name, media_state, media_title, raw_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            device_id,
            observed_at,
            power_mode,
            active_app_id,
            active_app_name,
            media_state,
            media_title,
            json.dumps(status, sort_keys=True),
            _now_iso(),
        ),
    )

    current = connection.execute(
        """
        SELECT id, state_key
        FROM sessions
        WHERE device_id = ? AND ended_at IS NULL
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (device_id,),
    ).fetchone()

    if current and current["state_key"] == state_key:
        connection.execute(
            """
            UPDATE sessions
            SET ended_at = ?, sample_count = sample_count + 1,
                power_mode = ?, active_app_id = ?, active_app_name = ?, media_state = ?, media_title = ?
            WHERE id = ?
            """,
            (observed_at, power_mode, active_app_id, active_app_name, media_state, media_title, int(current["id"])),
        )
        connection.commit()
        return

    if current:
        connection.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?",
            (observed_at, int(current["id"])),
        )

    if state_key != "off":
        connection.execute(
            """
            INSERT INTO sessions(device_id, state_key, started_at, ended_at, sample_count, power_mode, active_app_id, active_app_name, media_state, media_title)
            VALUES (?, ?, ?, NULL, 1, ?, ?, ?, ?, ?)
            """,
            (device_id, state_key, observed_at, power_mode, active_app_id, active_app_name, media_state, media_title),
        )

    connection.commit()


def format_usage_report(connection: sqlite3.Connection, days: int = 7) -> str:
    threshold = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=days)
    threshold_text = threshold.isoformat().replace("+00:00", "Z")
    now_text = _now_iso()
    rows = connection.execute(
        """
        SELECT state_key AS label,
               COUNT(*) AS sessions,
               SUM(
                   CAST(strftime('%s', COALESCE(ended_at, ?)) AS INTEGER) - CAST(strftime('%s', started_at) AS INTEGER)
               ) AS seconds
        FROM sessions
        WHERE started_at >= ?
        GROUP BY label
        ORDER BY seconds DESC, sessions DESC, label ASC
        """,
        (now_text, threshold_text),
    ).fetchall()

    if not rows:
        return f"No sessions recorded in the last {days} days."

    lines = [f"Usage report for the last {days} days:"]
    for row in rows:
        seconds = int(row["seconds"] or 0)
        lines.append(f"- {row['label']}: {seconds // 60}m {seconds % 60:02d}s across {row['sessions']} sessions")
    return "\n".join(lines)