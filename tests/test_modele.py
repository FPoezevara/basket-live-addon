from zoneinfo import ZoneInfo

from app.modele import (Criteres, appliquer, categorie, construire_match, normaliser, temps_restant, vue)
from fixtures import CDF, ELITE, EUROCUP, KAZ, NANTERRE, equipe, evenement

TZ = ZoneInfo("Europe/Paris")
C = Criteres(NANTERRE, {156}, {138, 141, 9357, 2165}, "FR")
T0 = 1_793_725_200


def match_elite(code=0):
    ev = evenement(1, ELITE, equipe(10, "Cholet Basket", code="CHO"), equipe(11, "Paris Basketball", code="PAR"), T0, code)
    return construire_match(ev, "elite")


def test_categories():
    nanterre = equipe(NANTERRE, "Nanterre 92", code="NAN")
    riga = equipe(20, "Rīgas Zeļļi", pays="LV")
    wroclaw = equipe(21, "Śląsk Wrocław", pays="PL")
    bourg = equipe(22, "JL Bourg Basket")
    assert categorie(evenement(1, EUROCUP, riga, nanterre, T0), C) == "nanterre"
    assert categorie(evenement(2, CDF, nanterre, bourg, T0), C) == "nanterre"
    assert categorie(evenement(4, ELITE, bourg, equipe(23, "Pau"), T0), C) == "elite"
    assert categorie(evenement(5, EUROCUP, wroclaw, bourg, T0), C) == "europe"
    assert categorie(evenement(6, EUROCUP, wroclaw, riga, T0), C) is None
    assert categorie(evenement(7, KAZ, riga, wroclaw, T0), C) is None
    assert categorie(evenement(8, CDF, bourg, equipe(23, "Pau"), T0), C) is None


def test_transitions_et_flottement_de_fin():
    m = match_elite()
    t = T0
    assert appliquer(m, {"status.code": 13}, t) == ["debut"]
    assert appliquer(m, {"homeScore.current": 2}, t) == []
    assert m.push_en_attente
    assert appliquer(m, {"status.code": 30}, t) == ["periode"]
    assert appliquer(m, {"status.code": 16}, t) == ["periode"]
    # Séquence réelle de Chalon - Kalev : 30, 100, 30, 100
    assert appliquer(m, {"status.code": 30}, t) == ["periode"]
    assert appliquer(m, {"status.code": 100}, t + 29) == ["fin_provisoire"]
    assert m.fin_provisoire_ts == t + 29
    assert appliquer(m, {"status.code": 100}, t + 30) == []
    assert appliquer(m, {"status.code": 30}, t + 73) == ["reprise"]
    assert m.fin_provisoire_ts is None
    assert appliquer(m, {"status.code": 100}, t + 268) == ["fin_provisoire"]
    assert m.fin_provisoire_ts == t + 268


def test_deltas_websocket_un_seul_cote():
    m = match_elite(13)
    m.code = 14
    appliquer(m, normaliser({"eventId": 1, "homeScore.period2": 0, "awayScore.period2": 3}), T0)
    appliquer(m, normaliser({"eventId": 1, "awayScore.current": 19, "awayScore.display": 19}), T0)
    appliquer(m, normaliser({"eventId": 1, "homeScore.current": 16}), T0)
    assert (m.score_dom, m.score_ext) == (16, 19)
    assert m.periodes_ext[1] == 3 and m.periodes_dom[1] == 0


def test_chrono_extrapolation_et_arret():
    m = match_elite()
    m.code = 14
    ref = "2026-11-03 22:37:08.696577"
    plat = normaliser({"time.played": 615, "time.clockRunning": True,
                       "time.playedLastUpdated": {"date": ref, "timezone_type": 3, "timezone": "UTC"}})
    t_ref = 1_793_745_428.696577
    appliquer(m, plat, t_ref + 1)
    assert temps_restant(m, t_ref, extrapoler=False) == 585
    assert temps_restant(m, t_ref + 10) == 575
    # Arrêt de l'horloge : le temps se fige à la valeur extrapolée
    appliquer(m, {"time.clockRunning": False}, t_ref + 20)
    assert temps_restant(m, t_ref + 100) == 565
    # Fin de quart-temps : borné à 0, pas négatif
    appliquer(m, {"time.clockRunning": True}, t_ref + 100)
    assert temps_restant(m, t_ref + 2000) == 0


def test_chrono_prolongation_et_incoherence():
    m = match_elite()
    appliquer(m, {"status.code": 17, "time.played": 2500}, T0)
    assert temps_restant(m, T0, extrapoler=False) == 200
    m2 = match_elite()
    appliquer(m2, {"status.code": 13, "time.played": 900}, T0)      # 15 min jouées « au 1er QT »
    assert temps_restant(m2, T0) is None


def test_normaliser_format_live():
    ev = {"id": 9, "homeTeam": "KK Teodo Tivat", "homeTeamId": 1, "homeScore": {"current": 86, "period4": 23},
          "awayScore": {"current": 76}, "status": "4th quarter", "statusCode": 16, "tournamentId": 24093}
    plat = normaliser(ev)
    assert plat["status.code"] == 16 and plat["status.description"] == "4th quarter"
    assert plat["homeScore.current"] == 86 and plat["homeScore.period4"] == 23


def test_vue():
    m = match_elite()
    appliquer(m, {"status.code": 16, "homeScore.current": 79, "awayScore.current": 75, "time.played": 2280}, T0)
    v = vue(m, TZ, T0, extrapoler=False)
    assert v["court"] == "CHO 79-75 PAR"
    assert v["resume"] == "79 - 75 · QT4 · 2:00"
    assert v["statut"] == "4e quart-temps"
    assert v["tournoi"] == "Betclic Élite"
    assert v["debut"].endswith("+01:00")


def test_noms_courts_et_progression():
    from app.modele import nom_court
    assert nom_court("JL Bourg Basket") == "Bourg-en-Bresse"
    assert nom_court("SIG Strasbourg") == "Strasbourg"
    assert nom_court("Le Mans Sarthe Basket") == "Le Mans"
    assert nom_court("SLUC Nancy Basket") == "Nancy"
    assert nom_court("Paris Basketball") == "Paris"
    assert nom_court("AS Monaco") == "Monaco"
    assert nom_court("Nanterre 92") == "Nanterre 92"
    assert nom_court("Śląsk Wrocław") == "Śląsk Wrocław"
    m = match_elite()
    appliquer(m, {"status.code": 15, "homeScore.current": 45, "awayScore.current": 42}, T0)
    v = vue(m, TZ, T0)
    assert (v["temps_joue"], v["duree_match"], v["statut_court"], v["tournoi_court"]) == (1200, 2400, "QT3", "Élite")
    appliquer(m, {"status.code": 17, "time.played": 2550}, T0)
    assert vue(m, TZ, T0, extrapoler=False)["duree_match"] == 2700


def test_progression_reglementaire():
    m = match_elite()
    for code, joue, attendu in ((13, 0, 0), (13, 300, 12), (14, 600, 25), (30, 1200, 50), (16, 2400, 100), (17, 2550, 100)):
        appliquer(m, {"status.code": code, "time.played": joue}, T0)
        assert vue(m, TZ, T0, extrapoler=False)["progression"] == attendu, (code, joue)
    m2 = match_elite()
    appliquer(m2, {"status.code": 15}, T0)                  # pas encore de chrono : début du QT3
    assert vue(m2, TZ, T0)["progression"] == 50
