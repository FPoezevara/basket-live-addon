"""Fins V1 indépendantes de V2 et budgets REST bornés."""
import asyncio
from copy import deepcopy
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import patch

from app.api import Api, ESSENTIEL, FOND
from app.bus import Bus
from app import main as module
from app.main import VERIF_SECOURS_MIN
from app.secours import resultat_correspondant
from fixtures import ELITE, equipe, evenement
from test_app import FausseApi, Horloge, T, TZ, faire_app

JOUR = datetime.fromtimestamp(T, TZ).date()
ID = 16989038


def v1(score=(80, 74), statut=4):
    return {"id": 4846933, "sportId": 2, "competitionId": 38,
            "startTime": datetime.fromtimestamp(T, TZ).isoformat(), "statusGroup": statut,
            "homeCompetitor": {"id": 9987, "name": "Boulazac", "score": score[0]},
            "awayCompetitor": {"id": 555, "name": "Gravelines", "score": score[1]}}


def preparer(tmp_path):
    h = Horloge(T + 7200)
    api = FausseApi()
    app, bus = faire_app(tmp_path, api, h)
    app.fusionner([evenement(ID, ELITE, equipe(75779, "Boulazac Basket"),
                            equipe(3532, "BCM Gravelines-Dunkerque"), int(T), 15,
                            ([15, 22, 0, 0], [23, 11, 0, 0]))], JOUR)
    app.matchs[ID].progression_ts = T + 3600
    api.secours[JOUR.isoformat()] = [v1()]
    app.ws_etat(True)
    return app, bus, api, h


def test_fin_v1_retire_le_live_et_publie_un_seul_resultat(tmp_path):
    app, bus, api, h = preparer(tmp_path)
    m = app.matchs[ID]
    app.pronos.choix[ID] = {"francis": "dom"}
    asyncio.run(app.verifier_secours())
    assert not m.termine and m.code == 15
    assert m.fin_secours_resultat == [4846933, 80, 74]
    # Les pongs et un vieux score V2 ne constituent pas une preuve de fin.
    h.t += VERIF_SECOURS_MIN
    app.traiter_ws({"type": "update", "data": {"eventId": ID, "status.code": 15,
                                             "homeScore.current": 37, "awayScore.current": 34}})
    asyncio.run(app.verifier_secours())
    app.publier()
    assert m.termine and (m.score_dom, m.score_ext) == (80, 74)
    assert bus.types() == ["fin"]
    assert bus.evenements[0]["match"]["id"] == ID
    assert bus.evenements[0]["match"]["statut"] == "Terminé"
    assert bus.retenus["basket_live/lives_en_cours/etat"] == "0"
    assert json.loads(bus.retenus["basket_live/lives_en_cours/attributs"])["matchs"] == []
    assert bus.retenus["basket_live/resultats/etat"] == "1"
    assert len(app.pronos.historique) == 1
    assert app.pronos.historique[0]["points"]["francis"] == 2
    assert m.periodes_dom == [None] * 4
    # Une donnée V2 en retard ne rouvre jamais une fin confirmée.
    app.traiter_ws({"type": "update", "data": {"eventId": ID, "status.code": 15}})
    asyncio.run(app.verifier_secours())
    assert m.termine and bus.types() == ["fin"]
    assert api.appels == [("secours", JOUR.isoformat(), FOND),
                          ("secours", JOUR.isoformat(), ESSENTIEL)]


def test_resultat_secours_rejete_ambiguite_mauvais_match_et_scores_invalides(tmp_path):
    app, _, _, _ = preparer(tmp_path)
    m = app.matchs[ID]
    assert resultat_correspondant(m, [v1()]) == (4846933, 80, 74)
    assert resultat_correspondant(m, [v1(), v1()]) is None
    for champ, valeur in [("sportId", 1), ("competitionId", 569), ("startTime", "sans_date"),
                           ("startTime", datetime.fromtimestamp(T + 86400, TZ).isoformat()),
                           ("statusGroup", 3), ("isHomeAwayInverted", True)]:
        ev = v1()
        ev[champ] = valeur
        assert resultat_correspondant(m, [ev]) is None, (champ, valeur)
    ev = v1()
    ev["awayCompetitor"]["name"] = "Gravelines (W)"
    assert resultat_correspondant(m, [ev]) is None
    for score in [(80, 80), (None, 74), (-1, 74), (80.5, 74), (True, 74)]:
        assert resultat_correspondant(m, [v1(score)]) is None, score


def test_pas_de_fin_sur_absence_panne_ou_score_changeant(tmp_path):
    app, _, api, h = preparer(tmp_path)
    m = app.matchs[ID]
    asyncio.run(app.verifier_secours())
    premier = m.fin_secours_ts
    # Une correction de score redémarre le délai de stabilité.
    h.t += VERIF_SECOURS_MIN
    api.secours[JOUR.isoformat()] = [v1((81, 74))]
    asyncio.run(app.verifier_secours())
    assert not m.termine and m.fin_secours_ts > premier
    # Une panne ne confirme rien.
    h.t += VERIF_SECOURS_MIN
    api.secours[JOUR.isoformat()] = None
    asyncio.run(app.verifier_secours())
    assert not m.termine
    # Une réponse valide qui ne trouve plus le résultat annule la preuve.
    h.t += VERIF_SECOURS_MIN
    api.secours[JOUR.isoformat()] = []
    asyncio.run(app.verifier_secours())
    assert not m.termine and m.fin_secours_ts is None


def test_verifications_partagees_limitees_et_sans_quota(tmp_path):
    app, _, api, h = preparer(tmp_path)
    asyncio.run(app.verifier_secours())
    asyncio.run(app.verifier_secours())
    assert len(api.appels) == 1
    h.t += VERIF_SECOURS_MIN
    api.compteur = 100
    asyncio.run(app.verifier_secours())
    assert len(api.appels) == 1
    assert not app.matchs[ID].termine


def test_pas_de_verification_v1_si_match_recent_ou_en_progression(tmp_path):
    app, _, api, h = preparer(tmp_path)
    app.matchs[ID].progression_ts = h.t
    asyncio.run(app.verifier_secours())
    assert not api.appels
    h.t = T + 3600
    app.matchs[ID].progression_ts = T
    asyncio.run(app.verifier_secours())
    assert not api.appels


def test_compteurs_et_preuve_de_fin_survivent_au_redemarrage(tmp_path):
    app, _, api, h = preparer(tmp_path)
    asyncio.run(app.verifier_secours())
    api.compteur_secours, api.compteur_instantanes = 4, 7
    app.sauver_etat()
    copie, _ = faire_app(tmp_path, FausseApi(), h)
    copie.charger_etat()
    assert copie.api.compteur_secours == 4 and copie.api.compteur_instantanes == 7
    assert copie.matchs[ID].fin_secours_ts == app.matchs[ID].fin_secours_ts
    copie.api.secours = deepcopy(api.secours)
    h.t += VERIF_SECOURS_MIN
    asyncio.run(copie.verifier_secours())
    assert copie.matchs[ID].termine


def test_v1_retrouve_match_de_la_veille_par_date_utc(tmp_path):
    app, _, api, h = preparer(tmp_path)
    h.t = T + 24 * 3600
    asyncio.run(app.verifier_secours())
    assert api.appels == [("secours", JOUR.isoformat(), FOND)]


class Reponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self, **kw):
        return {"success": True, "events": [], "data": {"games": [v1()]}}


class Session:
    def __init__(self):
        self.urls = []

    def get(self, url):
        self.urls.append(url)
        return Reponse()


def test_budget_partage_sans_sous_plafonds_arbitraires_et_plafond_100():
    api = Api("test", "http://v2", "ws://v2", 100, "http://v1")
    api.session = Session()

    async def scenario():
        for _ in range(20):
            await api.live(automatique=True)
        assert api.compteur == api.compteur_instantanes == 20
        for _ in range(20):
            await api.calendrier_secours("2026-11-06")
        assert api.compteur_secours == 20 and api.compteur == 40
        assert api.session.urls[-1] == 'http://v1/games?startDate=2026-11-06&endDate=2026-11-06&sportId=2'
        for _ in range(150):
            await api.get('/test', FOND)
        assert api.compteur == 85
        for _ in range(150):
            await api.get('/fin', ESSENTIEL)
        assert api.compteur == 100 and len(api.session.urls) == 100
        api.jour = "jour précédent"
        assert api.disponible()
        assert (api.compteur, api.compteur_secours, api.compteur_instantanes) == (0, 0, 0)
    asyncio.run(scenario())


def test_websocket_hors_quota_meme_quand_rest_epuise(tmp_path):
    app, _, api, h = preparer(tmp_path)
    api.compteur = 100
    app.dernier_instantane = h.t
    connexions = []

    class FauxWS:
        async def __aenter__(self):
            connexions.append(True)
            return self
        async def __aexit__(self, *args):
            pass
        async def send_json(self, msg):
            pass
        async def receive(self, **kw):
            return SimpleNamespace(type="close")

    class SessionWS:
        def __init__(self, **kw):
            pass
        def ws_connect(self, *args, **kw):
            return FauxWS()
        async def close(self):
            pass

    async def interrompre(*args):
        raise asyncio.CancelledError

    async def scenario():
        with patch.object(module.aiohttp, 'ClientSession', SessionWS, create=True), \
             patch.object(module.aiohttp, 'ClientTimeout', lambda **kw: None, create=True), \
             patch.object(module.aiohttp, 'ClientError', Exception, create=True), \
             patch.object(module.aiohttp, 'WSMsgType', SimpleNamespace(TEXT='text', CLOSE='close', CLOSED='closed', CLOSING='closing', ERROR='error'), create=True), \
             patch.object(module.asyncio, 'sleep', interrompre):
            try:
                await app.boucle_ws()
            except asyncio.CancelledError:
                pass
    for compteur in (0, 84, 85, 100):
        api.compteur = compteur
        asyncio.run(scenario())
        assert api.compteur == compteur
    assert connexions == [True] * 4


def test_mqtt_ne_perd_pas_le_passage_a_zero_pendant_envoi():
    bus = Bus('localhost', 1883, None, None, lambda *_: None)
    topic = 'basket_live/lives_en_cours/etat'
    bus.poser(topic, '1')
    envoyes = []

    class Client:
        async def publish(self, topic, payload, **kw):
            envoyes.append(payload)
            if payload == '1':
                bus.poser(topic, '0')

    async def scenario():
        await bus._vider(Client())
        assert topic in bus.a_publier
        await bus._vider(Client())
    asyncio.run(scenario())
    assert envoyes == ['1', '0'] and topic not in bus.a_publier


def test_budget_sauvegarde_avant_requete_http_meme_si_la_reponse_echoue(tmp_path):
    h = Horloge(T + 7200)
    api = Api("test", "http://v2", "ws://v2", 100, "http://v1")
    app, _ = faire_app(tmp_path, api, h)

    class SessionEnEchec:
        def get(self, url):
            etat = json.loads(app.fichier_etat.read_text())["api"]
            assert etat["compteur"] == 1
            assert etat["compteur_secours"] == 1
            raise OSError("incident simulé avant la réponse")
    api.session = SessionEnEchec()
    async def scenario():
        with patch.object(module.aiohttp, 'ClientError', OSError, create=True):
            assert await api.calendrier_secours("2026-11-06") is None
    asyncio.run(scenario())
    copie, _ = faire_app(tmp_path, FausseApi(), h)
    copie.charger_etat()
    assert copie.api.compteur == 1 and copie.api.compteur_secours == 1


def test_secours_partage_une_requete_pour_plusieurs_matchs(tmp_path):
    app, _, api, h = preparer(tmp_path)
    ev = evenement(123, ELITE, equipe(3, "Cholet"), equipe(4, "Paris"), int(T), 16)
    app.fusionner([ev], JOUR)
    app.matchs[123].progression_ts = T + 3600
    second = v1((90, 88))
    second["id"] = 999
    second["homeCompetitor"]["name"] = "Cholet"
    second["awayCompetitor"]["name"] = "Paris"
    api.secours[JOUR.isoformat()].append(second)
    asyncio.run(app.verifier_secours())
    h.t += VERIF_SECOURS_MIN
    asyncio.run(app.verifier_secours())
    assert len(api.appels) == 2
    assert app.matchs[ID].termine and app.matchs[123].termine


def test_reserve_reste_disponible_pour_confirmer_une_fin_v1(tmp_path):
    app, _, api, h = preparer(tmp_path)
    api.compteur = 85
    asyncio.run(app.verifier_secours())
    assert not api.appels  # une recherche sans preuve ne consomme pas la réserve
    api.compteur = 84
    asyncio.run(app.verifier_secours())
    assert api.appels == [("secours", JOUR.isoformat(), FOND)]
    assert api.compteur == 85
    h.t += VERIF_SECOURS_MIN
    asyncio.run(app.verifier_secours())
    assert api.appels[-1] == ("secours", JOUR.isoformat(), ESSENTIEL)
    assert api.compteur == 86 and app.matchs[ID].termine
