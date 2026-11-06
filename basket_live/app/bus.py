"""Publication MQTT : découverte HA, états retenus, événements.

Les états retenus sont gardés en mémoire et republiés à chaque (re)connexion et au redémarrage
de HA (message `online` sur homeassistant/status). Les événements passent par une file bornée.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Callable

import aiomqtt

from . import VERSION

log = logging.getLogger("mqtt")

RACINE = "basket_live"
DISPO = f"{RACINE}/statut"
EVENEMENT = f"{RACINE}/evenement"
COMMANDE = f"{RACINE}/commande"
PRONO_SET = f"{RACINE}/prono/+/+/set"
STATUT_HA = "homeassistant/status"

APPAREIL = {
    "identifiers": ["basket_live"],
    "name": "Basket Live",
    "manufacturer": "FPoezevara",
    "model": "Add-on basket-live",
    "sw_version": VERSION,
}

# (composant, identifiant, attributs JSON ?, configuration propre)
# Les entity_id découlent du nom d'appareil + nom d'entité : sensor.basket_live_matchs_a_venir, etc.
ENTITES = [
    ("sensor", "matchs_a_venir", True, {"name": "Matchs à venir", "icon": "mdi:calendar-clock"}),
    ("sensor", "lives_en_cours", True, {"name": "Lives en cours", "icon": "mdi:basketball"}),
    ("sensor", "resultats", True, {"name": "Résultats", "icon": "mdi:scoreboard"}),
    ("sensor", "requetes_du_jour", False, {"name": "Requêtes du jour", "icon": "mdi:counter",
                                           "unit_of_measurement": "requêtes", "state_class": "measurement",
                                           "entity_category": "diagnostic"}),
    ("sensor", "dernier_calendrier", False, {"name": "Dernier calendrier", "device_class": "timestamp",
                                             "entity_category": "diagnostic"}),
    ("binary_sensor", "websocket", False, {"name": "WebSocket", "device_class": "connectivity",
                                           "entity_category": "diagnostic"}),
    ("sensor", "pronostics", True, {"name": "Pronostics", "icon": "mdi:crystal-ball"}),
    ("sensor", "classement", True, {"name": "Classement", "icon": "mdi:podium"}),
    ("button", "rafraichir_le_calendrier", False, {"name": "Rafraîchir le calendrier", "icon": "mdi:refresh",
                                                   "command_topic": COMMANDE, "payload_press": "rafraichir"}),
]


def topic_etat(objet: str) -> str:
    return f"{RACINE}/{objet}/etat"


def topic_attributs(objet: str) -> str:
    return f"{RACINE}/{objet}/attributs"


def decouverte() -> list[tuple[str, str]]:
    messages = []
    for composant, objet, attributs, propre in ENTITES:
        conf = {
            "unique_id": f"basket_live_{objet}",
            "availability_topic": DISPO,
            "device": APPAREIL,
            "origin": {"name": "basket-live", "sw_version": VERSION,
                       "support_url": "https://github.com/FPoezevara/basket-live-addon"},
            **propre,
        }
        if composant != "button":
            conf["state_topic"] = topic_etat(objet)
        if attributs:
            conf["json_attributes_topic"] = topic_attributs(objet)
        messages.append((f"homeassistant/{composant}/basket_live/{objet}/config",
                         json.dumps(conf, ensure_ascii=False)))
    return messages


class Bus:
    def __init__(self, host: str, port: int, user: str | None, password: str | None,
                 sur_commande: Callable[[str, str], None]):
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sur_commande = sur_commande
        self.retenus: dict[str, str] = {}
        self.a_publier: set[str] = set()
        self.evenements: deque[str] = deque(maxlen=200)
        self.signal = asyncio.Event()
        self.connecte = False

    def poser(self, topic: str, payload: str) -> None:
        if self.retenus.get(topic) != payload:
            self.retenus[topic] = payload
            self.a_publier.add(topic)
            self.signal.set()

    def emettre(self, payload: str) -> None:
        self.evenements.append(payload)
        self.signal.set()

    async def _publier_tout(self, client: aiomqtt.Client) -> None:
        for topic, payload in decouverte():
            await client.publish(topic, payload, qos=1, retain=True)
        self.a_publier = set(self.retenus)
        self.signal.set()

    async def _recevoir(self, client: aiomqtt.Client) -> None:
        async for message in client.messages:
            texte = message.payload.decode("utf-8", "replace") if isinstance(message.payload, bytes) else str(message.payload)
            if message.topic.matches(STATUT_HA) and texte == "online":
                log.info("Home Assistant redémarré : republication")
                await self._publier_tout(client)
            elif message.topic.matches(COMMANDE) or message.topic.matches(PRONO_SET):
                self.sur_commande(message.topic.value, texte)

    async def _vider(self, client: aiomqtt.Client) -> None:
        while self.evenements:
            await client.publish(EVENEMENT, self.evenements[0], qos=1, retain=False)
            self.evenements.popleft()
        for topic in list(self.a_publier):
            payload = self.retenus[topic]
            # Une nouvelle valeur peut arriver pendant l'attente MQTT : elle doit rester à publier.
            self.a_publier.discard(topic)
            try:
                await client.publish(topic, payload, qos=1, retain=True)
            except BaseException:
                self.a_publier.add(topic)
                self.signal.set()
                raise
            if payload == "" and self.retenus.get(topic) == payload:
                del self.retenus[topic]                 # retenu effacé chez le broker : inutile de le garder

    async def run(self) -> None:
        attente = 2
        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.host, port=self.port, username=self.user, password=self.password,
                    identifier="basket_live", keepalive=60,
                    will=aiomqtt.Will(DISPO, payload="offline", qos=1, retain=True),
                ) as client:
                    self.connecte = True
                    attente = 2
                    log.info("Connecté à MQTT %s:%s", self.host, self.port)
                    await client.publish(DISPO, "online", qos=1, retain=True)
                    await client.subscribe(COMMANDE, qos=1)
                    await client.subscribe(STATUT_HA, qos=1)
                    await client.subscribe(PRONO_SET, qos=1)
                    await self._publier_tout(client)
                    reception = asyncio.create_task(self._recevoir(client))
                    try:
                        while True:
                            attente_signal = asyncio.create_task(self.signal.wait())
                            fait, _ = await asyncio.wait({attente_signal, reception},
                                                         return_when=asyncio.FIRST_COMPLETED)
                            if reception in fait:
                                attente_signal.cancel()
                                reception.result()
                                raise aiomqtt.MqttError("réception interrompue")
                            self.signal.clear()
                            await self._vider(client)
                    finally:
                        reception.cancel()
            except aiomqtt.MqttError as e:
                self.connecte = False
                log.warning("MQTT indisponible (%s), nouvel essai dans %s s", e, attente)
                await asyncio.sleep(attente)
                attente = min(attente * 2, 60)
