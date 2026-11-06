import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.api import Api
from app.bus import decouverte
from app.main import App
from fixtures import ELITE, EUROCUP, KAZ, FauxBus, config, equipe, evenement

TZ = ZoneInfo("Europe/Paris")
# Mercredi 4 novembre 2026, 19 h 00 à Paris
T = datetime(2026, 11, 4, 19, 0, tzinfo=TZ).timestamp()


class Horloge:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class FausseApi(Api):
    def __init__(self, calendriers=None, live=None):
        super().__init__("cle", "http://x", "ws://x", 100)
        self.calendriers = calendriers or {}
        self.live_ev = live or []
        self.appels = []
        self.secours = {}

    async def calendrier(self, jour, priorite="fond"):
        self.appels.append(("calendrier", jour, priorite))
        self.compter()
        return self.calendriers.get(jour, [])

    async def calendrier_secours(self, jour, priorite="fond"):
        self.appels.append(("secours", jour, priorite))
        self.compter()
        return self.secours.get(jour, [])

    async def live(self, priorite="fond", *, automatique=False):
        self.appels.append(("live", priorite))
        self.compter()
        return self.live_ev


def faire_app(tmp_path, api, h, **kw):
    bus = FauxBus()
    app = App(config(tmp_path, **kw), api, bus=bus, horloge=h)
    return app, bus


def ev_wroclaw(code=0, score=None):
    return evenement(16561673, EUROCUP, equipe(21, "Śląsk Wrocław", pays="PL", code="SLA"),
                     equipe(22, "JL Bourg Basket", code="BOU"), int(T), code, score)


def ev_elite_fini():
    return evenement(4846984, ELITE, equipe(10, "Cholet Basket", code="CHO"), equipe(11, "Paris Basketball", code="PAR"),
                     int(T) - 3 * 3600, 100, ([28, 15, 15, 21], [20, 20, 20, 19]))


def test_fusion_selectionne_et_rattrape_les_matchs_finis(tmp_path):
    h = Horloge(T)
    app, bus = faire_app(tmp_path, FausseApi(), h)
    kaz = evenement(1, KAZ, equipe(1, "A", "KZ"), equipe(2, "B", "KZ"), int(T))
    app.fusionner([ev_wroclaw(), ev_elite_fini(), kaz], datetime.fromtimestamp(T, TZ).date())
    assert set(app.matchs) == {16561673, 4846984}
    fini = app.matchs[4846984]
    assert fini.termine and fini.tardif
    assert [r.id for r in app.resultats] == [4846984]
    assert bus.types() == ["fin"] and bus.evenements[0]["match"]["tardif"] is True


def test_flottement_puis_confirmation_par_le_calendrier(tmp_path):
    h = Horloge(T + 2 * 3600)
    score = ([20, 18, 22, 25], [19, 21, 20, 20])
    api = FausseApi()
    app, bus = faire_app(tmp_path, api, h)
    jour = datetime.fromtimestamp(T, TZ).date()
    app.fusionner([ev_wroclaw(16)], jour)
    m = app.matchs[16561673]
    app.traiter_ws({"type": "update", "data": {"eventId": m.id, "status.code": 100}})
    assert bus.types()[-1] == "fin_provisoire"

    # Calendrier qui dit déjà « terminé » 30 s après : trop tôt, on ne valide pas
    h.t += 30
    app.fusionner([ev_wroclaw(100, score)], jour)
    assert not m.termine

    # Le statisticien rouvre, puis reclôt
    app.traiter_ws({"type": "update", "data": {"eventId": m.id, "status.code": 30}})
    h.t += 200
    app.traiter_ws({"type": "update", "data": {"eventId": m.id, "status.code": 100}})
    assert bus.types()[-2:] == ["reprise", "fin_provisoire"]

    # Après le délai, la vérification interroge le calendrier, qui confirme
    api.calendriers[jour.isoformat()] = [ev_wroclaw(100, score)]
    h.t += 301
    asyncio.run(app.verifier_fins())
    assert m.termine and not m.tardif
    assert (m.score_dom, m.score_ext) == (85, 80) and m.periodes_dom == [20, 18, 22, 25]
    assert bus.types()[-1] == "fin"
    assert api.appels[-1] == ("calendrier", jour.isoformat(), "essentiel")


def test_fin_validee_sur_le_live_si_le_calendrier_ne_confirme_jamais(tmp_path):
    h = Horloge(T + 2 * 3600)
    api = FausseApi()
    app, bus = faire_app(tmp_path, api, h)
    jour = datetime.fromtimestamp(T, TZ).date()
    app.fusionner([ev_wroclaw(16)], jour)
    m = app.matchs[16561673]
    api.calendriers[jour.isoformat()] = [ev_wroclaw(16)]
    app.traiter_ws({"type": "update", "data": {"eventId": m.id, "status.code": 100, "homeScore.current": 70}})
    for _ in range(3):
        h.t += 400
        asyncio.run(app.verifier_fins())
    assert m.termine and m.score_dom == 70
    assert bus.types().count("fin") == 1


def test_cadence_des_maj(tmp_path):
    h = Horloge(T + 600)
    app, bus = faire_app(tmp_path, FausseApi(), h, intervalle_push=60)
    app.fusionner([ev_wroclaw(13)], datetime.fromtimestamp(T, TZ).date())
    m = app.matchs[16561673]
    m.dernier_push_ts = h.t
    for i in range(10):                                     # dix paniers en 50 s
        h.t += 5
        app.traiter_ws({"type": "update", "data": {"eventId": m.id, "homeScore.current": 2 * (i + 1)}})
        app.cadencer()
    assert bus.types().count("maj") == 0
    h.t += 15
    app.cadencer()
    assert bus.types().count("maj") == 1 and bus.evenements[-1]["match"]["score_dom"] == 20
    h.t += 120
    app.cadencer()
    assert bus.types().count("maj") == 1                    # rien de neuf, rien d'envoyé


def test_match_absent_du_live_passe_en_fin_provisoire(tmp_path):
    h = Horloge(T + 2 * 3600)
    app, bus = faire_app(tmp_path, FausseApi(), h)
    app.fusionner([ev_wroclaw(16)], datetime.fromtimestamp(T, TZ).date())
    app.appliquer_live([{"id": 999, "statusCode": 14}])
    assert bus.types() == ["fin_provisoire"]


def test_publication_et_persistance(tmp_path):
    h = Horloge(T + 600)
    api = FausseApi()
    app, bus = faire_app(tmp_path, api, h)
    jour = datetime.fromtimestamp(T, TZ).date()
    app.fusionner([ev_wroclaw(14), ev_elite_fini()], jour)
    app.publier()
    assert bus.retenus["basket_live/lives_en_cours/etat"] == "1"
    assert bus.retenus["basket_live/resultats/etat"] == "1"
    attrs = json.loads(bus.retenus["basket_live/lives_en_cours/attributs"])
    assert attrs["matchs"][0]["categorie"] == "europe"
    app.sauver_etat()
    app2, _ = faire_app(tmp_path, FausseApi(), h)
    app2.charger_etat()
    assert set(app2.matchs) == set(app.matchs) and [r.id for r in app2.resultats] == [4846984]


def test_report_retire_le_match(tmp_path):
    h = Horloge(T - 3600)
    app, _ = faire_app(tmp_path, FausseApi(), h)
    jour = datetime.fromtimestamp(T, TZ).date()
    autre = evenement(5, KAZ, equipe(1, "A", "KZ"), equipe(2, "B", "KZ"), int(T))
    app.fusionner([ev_wroclaw()], jour)
    app.fusionner([autre], jour)
    assert 16561673 not in app.matchs
    app.fusionner([ev_wroclaw()], jour)
    app.fusionner([], jour)                                 # réponse vide : on ne retire rien
    assert 16561673 in app.matchs


def test_quota_et_reserve():
    api = Api("cle", "http://x", "ws://x", 100)
    api.compteur = 84
    assert api.disponible("fond")
    api.compteur = 85
    assert not api.disponible("fond") and api.disponible("essentiel")
    api.compteur = 100
    assert not api.disponible("essentiel")


def test_decouverte():
    msgs = dict(decouverte())
    conf = json.loads(msgs["homeassistant/sensor/basket_live/lives_en_cours/config"])
    assert conf["name"] == "Lives en cours" and conf["device"]["name"] == "Basket Live"
    assert conf["json_attributes_topic"] == "basket_live/lives_en_cours/attributs"
    bouton = json.loads(msgs["homeassistant/button/basket_live/rafraichir_le_calendrier/config"])
    assert "state_topic" not in bouton and bouton["payload_press"] == "rafraichir"
