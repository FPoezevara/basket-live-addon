"""Régressions : WebSocket vivant sans données et rafraîchissement manuel."""

import asyncio
from datetime import datetime

from app.main import CRENEAUX, INSTANTANE_MIN, SILENCE_MATCH
from app.modele import appliquer
from test_app import FausseApi, Horloge, T, TZ, ev_wroclaw, faire_app

JOUR = datetime.fromtimestamp(T, TZ).date()
ID = 16561673


def app_prete(tmp_path, code=0, maintenant=T + 600):
    h = Horloge(maintenant)
    api = FausseApi(live=[{"id": ID, "statusCode": 15,
                           "homeScore": {"current": 37}, "awayScore": {"current": 34}}])
    app, bus = faire_app(tmp_path, api, h)
    app.fusionner([ev_wroclaw(code)], JOUR)
    app.ws_etat(True)
    app.creneaux_faits = {f"{JOUR}-{heure}" for heure, _ in CRENEAUX}
    return app, bus, api, h


def test_match_attendu_rattrape_meme_avec_pongs(tmp_path):
    app, bus, api, h = app_prete(tmp_path)
    app.dernier_instantane = T - 900  # connexion 15 min avant le match
    app.traiter_ws({"type": "pong"})
    asyncio.run(app.planifier())
    assert app.ws_connecte
    assert app.matchs[ID].code == 15
    assert (app.matchs[ID].score_dom, app.matchs[ID].score_ext) == (37, 34)
    assert api.appels == [("live", "fond")]
    assert bus.types() == ["debut"]


def test_pas_de_requete_avant_debut_ou_si_donnees_recentes(tmp_path):
    app, _, api, h = app_prete(tmp_path, maintenant=T - 60)
    asyncio.run(app.verifier_live())
    assert not api.appels
    h.t = T + 600
    appliquer(app.matchs[ID], {"status.code": 13, "homeScore.current": 2}, h.t)
    asyncio.run(app.verifier_live())
    assert not api.appels


def test_match_en_cours_muet_et_limitation_des_essais(tmp_path):
    app, _, api, h = app_prete(tmp_path, code=13)
    api.live_ev = None  # panne REST : garder l'état et limiter les nouvelles tentatives
    h.t += SILENCE_MATCH
    asyncio.run(app.verifier_live())
    assert api.appels == [("live", "fond")]
    assert app.matchs[ID].code == 13
    h.t += INSTANTANE_MIN - 1
    asyncio.run(app.verifier_live())
    assert len(api.appels) == 1
    h.t += 1
    asyncio.run(app.verifier_live())
    assert len(api.appels) == 2


def test_rattrapage_respecte_quota_et_fin_provisoire(tmp_path):
    app, _, api, h = app_prete(tmp_path)
    api.compteur = api.quota - api.reserve
    asyncio.run(app.verifier_live())
    assert not api.appels
    api.compteur = 0
    appliquer(app.matchs[ID], {"status.code": 100}, h.t)
    h.t += SILENCE_MATCH
    asyncio.run(app.verifier_live())
    assert not api.appels  # la confirmation de fin reste à verifier_fins


def test_bouton_recupere_aussi_le_live_et_reste_limite(tmp_path):
    app, _, api, h = app_prete(tmp_path)
    app.demande_rafraichir = True
    asyncio.run(app.planifier())
    assert api.appels == [("calendrier", JOUR.isoformat(), "fond"),
                          ("calendrier", "2026-11-05", "fond"), ("live", "fond")]
    assert app.matchs[ID].code == 15
    app.demande_rafraichir = True
    asyncio.run(app.planifier())
    assert len(api.appels) == 3


def test_instantanes_simultanes_ne_comptent_qu_une_requete(tmp_path):
    app, _, api, _ = app_prete(tmp_path)

    async def scenario():
        async def live(priorite):
            api.appels.append(("live", priorite))
            await asyncio.sleep(0)
            return api.live_ev
        api.live = live
        await asyncio.gather(app.instantane(), app.instantane())
    asyncio.run(scenario())
    assert api.appels == [("live", "fond")]


def test_evenement_ancien_declenche_le_rattrapage(tmp_path):
    app, _, api, h = app_prete(tmp_path)
    app.traiter_ws({"type": "update", "data": {
        "eventId": ID, "status.code": 13, "homeScore.current": 2,
        "changes.changeTimestamp": int(h.t - 1800)}})
    assert app.matchs[ID].maj_ts == h.t - 1800
    asyncio.run(app.verifier_live())
    assert app.matchs[ID].code == 15
    assert api.appels == [("live", "fond")]


def test_evenement_plus_ancien_ne_fait_pas_regresser_le_match(tmp_path):
    app, _, _, h = app_prete(tmp_path)
    app.traiter_ws({"type": "update", "data": {
        "eventId": ID, "status.code": 15, "homeScore.current": 37,
        "changes.changeTimestamp": int(h.t)}})
    app.traiter_ws({"type": "update", "data": {
        "eventId": ID, "status.code": 13, "homeScore.current": 2,
        "changes.changeTimestamp": int(h.t - 1800)}})
    assert app.matchs[ID].code == 15 and app.matchs[ID].score_dom == 37
    # Deux deltas dans la même seconde peuvent compléter des champs distincts.
    app.traiter_ws({"type": "update", "data": {
        "eventId": ID, "awayScore.current": 34, "changes.changeTimestamp": int(h.t)}})
    assert app.matchs[ID].score_ext == 34
