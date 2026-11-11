"""Lecture des options de l'add-on (/data/options.json) et de l'environnement."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    api_key: str
    equipe_nanterre: int
    tournois_elite: list[int]
    tournois_europe: list[int]
    pays_europe: str
    delai_fin: int
    intervalle_push: int
    historique_jours: int
    quota_jour: int
    log_level: str
    joueurs: list[str]
    mqtt_host: str
    mqtt_port: int
    mqtt_user: str | None
    mqtt_password: str | None
    dossier_donnees: Path
    fuseau: str
    api_base: str
    ws_url: str
    api_v1_base: str = "https://api.sportsapipro.com/v1"
    joueuses: list[str] = field(default_factory=lambda: ["ilona"])


def charger() -> Config:
    dossier = Path(os.environ.get("BASKET_DATA", "/data"))
    options = json.loads((dossier / "options.json").read_text(encoding="utf-8"))
    return Config(
        api_key=options.get("api_key", ""),
        equipe_nanterre=int(options.get("equipe_nanterre", 53125)),
        tournois_elite=[int(x) for x in options.get("tournois_elite", [156])],
        tournois_europe=[int(x) for x in options.get("tournois_europe", [138, 141, 9357, 2165])],
        pays_europe=str(options.get("pays_europe", "FR")).upper(),
        delai_fin=int(options.get("delai_fin", 300)),
        intervalle_push=int(options.get("intervalle_push", 60)),
        historique_jours=int(options.get("historique_jours", 7)),
        quota_jour=int(options.get("quota_jour", 100)),
        log_level=str(options.get("log_level", "info")).upper(),
        joueurs=[str(j).strip().lower() for j in options.get("joueurs", ["francis", "ilona"])],
        joueuses=[str(j).strip().lower() for j in options.get("joueuses", ["ilona"])],
        mqtt_host=os.environ.get("MQTT_HOST", "core-mosquitto"),
        mqtt_port=int(os.environ.get("MQTT_PORT") or 1883),
        mqtt_user=os.environ.get("MQTT_USER") or None,
        mqtt_password=os.environ.get("MQTT_PASSWORD") or None,
        dossier_donnees=dossier,
        fuseau=os.environ.get("TZ") or "Europe/Paris",
        api_base=os.environ.get("BASKET_API_BASE", "https://api.sportsapipro.com/v2/basketball"),
        api_v1_base=os.environ.get("BASKET_API_V1_BASE", "https://api.sportsapipro.com/v1"),
        ws_url=os.environ.get("BASKET_WS_URL", "wss://api.sportsapipro.com/v2/basketball/ws"),
    )
