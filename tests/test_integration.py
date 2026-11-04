"""Bout en bout : faux serveur SportsAPI Pro (REST + WebSocket) et vrai broker MQTT (amqtt).

Rejoue la fin de Chalon - Kalev observée le 4 novembre : 100, 30, 100, puis confirmation par le
calendrier. Ignoré si amqtt n'est pas installé (pip install amqtt).
"""

import asyncio
import json
import time

import pytest

amqtt_broker = pytest.importorskip("amqtt.broker")

import aiomqtt
from aiohttp import web

from app import main as appmain
from app.api import Api
from app.bus import Bus
from fixtures import EUROCUP, config, equipe, evenement

PORT_MQTT = 18831
ID = 16561673


def faux_serveur(etat):
    async def schedule(request):
        assert request.headers.get("x-api-key") == "cle-test"
        etat["appels"].append(request.path)
        return web.json_response({"success": True, "events": [etat["evenement"]()]})

    async def live(request):
        etat["appels"].append(request.path)
        return web.json_response({"success": True, "events": []})

    async def ws(request):
        assert request.query.get("x-api-key") == "cle-test"
        etat["appels"].append("ws")
        sock = web.WebSocketResponse()
        await sock.prepare(request)
        await sock.send_json({"type": "welcome"})
        async for msg in sock:
            data = json.loads(msg.data)
            if data.get("action") == "subscribe":
                await sock.send_json({"type": "subscribed", "channel": "live-scores:basketball", "mode": "realtime"})
                for delta in etat["sequence"]:
                    if "_pause" in delta:
                        await asyncio.sleep(delta["_pause"])
                        continue
                    await asyncio.sleep(0.3)
                    await sock.send_json({"channel": "live-scores:basketball", "type": "update",
                                          "data": {"eventId": ID, **delta}})
                etat["sequence_finie"] = True
            elif data.get("action") == "ping":
                await sock.send_json({"type": "pong"})
        return sock

    app = web.Application()
    app.router.add_get("/api/schedule/{jour}", schedule)
    app.router.add_get("/api/live", live)
    app.router.add_get("/ws", ws)
    return app


@pytest.mark.timeout(60)
def test_bout_en_bout(tmp_path, monkeypatch):
    monkeypatch.setattr(appmain, "PERIODE_PLANIF", 1)
    monkeypatch.setattr(appmain, "INSTANTANE_MIN", 0)
    monkeypatch.setattr(appmain, "ATTENTE_INACTIF", 0.5)

    async def scenario():
        broker = amqtt_broker.Broker({
            "listeners": {"default": {"type": "tcp", "bind": f"127.0.0.1:{PORT_MQTT}"}},
            "sys_interval": 0,
            "auth": {"allow-anonymous": True, "plugins": ["auth_anonymous"]},
            "topic-check": {"enabled": False},
        })
        await broker.start()

        debut = int(time.time()) - 2 * 3600
        etat = {"appels": [], "sequence_finie": False,
                "sequence": [{"homeScore.current": 81}, {"awayScore.current": 78}, {"_pause": 2.5},
                             {"status.code": 30}, {"status.code": 100}, {"status.code": 30}, {"status.code": 100}]}

        def ev():
            fini = etat["sequence_finie"]
            return evenement(ID, EUROCUP, equipe(21, "Śląsk Wrocław", pays="PL", code="SLA"),
                             equipe(22, "JL Bourg Basket", code="BOU"), debut, 100 if fini else 16,
                             ([20, 18, 22, 21], [19, 21, 20, 18]) if fini else None)
        etat["evenement"] = ev

        runner = web.AppRunner(faux_serveur(etat))
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = runner.addresses[0][1]

        cfg = config(tmp_path, api_base=f"http://127.0.0.1:{port}", ws_url=f"ws://127.0.0.1:{port}/ws",
                     mqtt_port=PORT_MQTT, delai_fin=2, intervalle_push=1)
        api = Api(cfg.api_key, cfg.api_base, cfg.ws_url, cfg.quota_jour)
        app = appmain.App(cfg, api)
        app.bus = Bus(cfg.mqtt_host, cfg.mqtt_port, None, None, app.sur_commande)

        recus = {}
        evenements = []

        async def ecouter():
            async with aiomqtt.Client("127.0.0.1", PORT_MQTT, identifier="test") as c:
                await c.subscribe("basket_live/#")
                await c.subscribe("homeassistant/#")
                async for msg in c.messages:
                    texte = msg.payload.decode()
                    if msg.topic.value == "basket_live/evenement":
                        evenements.append(json.loads(texte))
                    else:
                        recus[msg.topic.value] = texte

        ecoute = asyncio.create_task(ecouter())
        await asyncio.sleep(0.5)
        arret = asyncio.Event()
        tache = asyncio.create_task(app.run(arret))
        for _ in range(400):
            await asyncio.sleep(0.1)
            if any(e["type"] == "fin" for e in evenements):
                break
        await asyncio.sleep(1.5)
        arret.set()
        await tache
        ecoute.cancel()
        await runner.cleanup()
        await broker.shutdown()
        return etat, recus, evenements, app

    etat, recus, evenements, app = asyncio.run(scenario())

    types = [e["type"] for e in evenements]
    assert types[:1] == ["maj"]
    assert types[-1] == "fin" and types.count("fin") == 1
    assert ["periode", "fin_provisoire", "reprise", "fin_provisoire"] == [t for t in types if t not in ("maj", "fin")]
    fin = evenements[-1]["match"]
    assert fin["score"] == "81 - 78" and fin["quarts_dom"] == [20, 18, 22, 21] and fin["tardif"] is False
    assert "homeassistant/sensor/basket_live/lives_en_cours/config" in recus
    assert recus["basket_live/statut"] in ("online", "offline")
    assert recus["basket_live/resultats/etat"] == "1"
    assert recus["basket_live/lives_en_cours/etat"] == "0"
    assert "ws" in etat["appels"]
    assert app.api.compteur <= 6
