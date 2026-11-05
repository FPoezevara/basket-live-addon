"""Données au format observé sur SportsAPI Pro V2 (calendrier, live, WebSocket) le 3 et le 4 novembre 2026."""

from pathlib import Path

from app.config import Config

NANTERRE = 53125


def equipe(id_, nom, pays="FR", code=None):
    return {"id": id_, "name": nom, "shortName": nom, "nameCode": code or nom[:3].upper(),
            "country": {"alpha2": pays}}


def evenement(id_, tournoi, dom, ext, debut, code=0, score=None):
    ev = {
        "id": id_,
        "tournament": {"name": tournoi[1], "uniqueTournament": {"id": tournoi[0], "name": tournoi[1]},
                       "category": {"name": "France"}},
        "homeTeam": dom,
        "awayTeam": ext,
        "startTimestamp": debut,
        "status": {"code": code, "description": "x", "type": "x"},
    }
    if score:
        (h, a) = score
        ev["homeScore"] = {"current": sum(h), "display": sum(h), **{f"period{i+1}": v for i, v in enumerate(h)}}
        ev["awayScore"] = {"current": sum(a), "display": sum(a), **{f"period{i+1}": v for i, v in enumerate(a)}}
    return ev


ELITE = (156, "LNB Élite")
EUROCUP = (141, "Eurocup")
CDF = (1666, "French Basketball Cup")
KAZ = (29868, "National League")


def config(dossier: Path, **kw) -> Config:
    base = dict(
        api_key="cle-test", equipe_nanterre=NANTERRE, tournois_elite=[156], tournois_europe=[138, 141, 9357, 2165],
        pays_europe="FR", delai_fin=300, intervalle_push=60, historique_jours=7, quota_jour=100, log_level="DEBUG", joueurs=["francis", "ilona"],
        mqtt_host="localhost", mqtt_port=1883, mqtt_user=None, mqtt_password=None, dossier_donnees=dossier,
        fuseau="Europe/Paris", api_base="http://127.0.0.1:1", ws_url="ws://127.0.0.1:1/ws",
    )
    base.update(kw)
    return Config(**base)


class FauxBus:
    def __init__(self):
        self.retenus = {}
        self.evenements = []

    def poser(self, topic, payload):
        self.retenus[topic] = payload

    def emettre(self, payload):
        import json
        self.evenements.append(json.loads(payload))

    def types(self):
        return [e["type"] for e in self.evenements]

    async def run(self):
        pass
