import json
from datetime import datetime
from zoneinfo import ZoneInfo

from app.main import App
from app.pronos import AUCUN, saison
from fixtures import ELITE, EUROCUP, NANTERRE, FauxBus, config, equipe, evenement
from test_app import FausseApi, Horloge

TZ = ZoneInfo("Europe/Paris")
T = datetime(2026, 11, 5, 20, 0, tzinfo=TZ).timestamp()
JOUR = datetime.fromtimestamp(T, TZ).date()


def ev_nanterre(code=0, score=None):
    return evenement(1, ELITE, equipe(NANTERRE, "Nanterre 92", code="NAN"), equipe(2, "JL Bourg Basket", code="JLB"),
                     int(T), code, score)


def ev_europe(code=0, score=None):
    return evenement(2, EUROCUP, equipe(21, "Śląsk Wrocław", pays="PL"), equipe(22, "JL Bourg Basket"),
                     int(T) + 3600, code, score)


def faire(tmp_path, h):
    bus = FauxBus()
    app = App(config(tmp_path), FausseApi(), bus=bus, horloge=h)
    app.fusionner([ev_nanterre(), ev_europe()], JOUR)
    return app, bus


def menus(bus):
    return {t: json.loads(p) for t, p in bus.retenus.items() if t.startswith("homeassistant/select/") and p}


def test_menus_ouverts_puis_fermes_a_lentre_deux(tmp_path):
    h = Horloge(T - 3600)
    app, bus = faire(tmp_path, h)
    app.publier()
    m = menus(bus)
    assert len(m) == 4                                      # 2 matchs x 2 joueurs
    conf = m["homeassistant/select/basket_live/prono_francis_1/config"]
    assert conf["name"] == "jeu. 20:00 · Nanterre - Bourg-en-Bresse"
    assert conf["options"] == [AUCUN, "Nanterre", "Bourg-en-Bresse"]
    attrs = json.loads(bus.retenus["basket_live/prono/francis/1/attributs"])
    assert attrs["joueur"] == "francis" and attrs["points_en_jeu"] == 3
    # Entre-deux du premier match : ses deux menus disparaissent (configuration retenue vidée)
    h.t = T + 60
    app.publier()
    assert bus.retenus["homeassistant/select/basket_live/prono_francis_1/config"] == ""
    assert len(menus(bus)) == 2


def test_saisie_verrou_points_et_classement(tmp_path):
    h = Horloge(T - 3600)
    app, bus = faire(tmp_path, h)
    app.sur_commande("basket_live/prono/francis/1/set", "Nanterre")
    app.sur_commande("basket_live/prono/ilona/1/set", "Bourg-en-Bresse")
    app.sur_commande("basket_live/prono/francis/2/set", "Śląsk Wrocław")
    app.sur_commande("basket_live/prono/ilona/2/set", "Śląsk Wrocław")
    app.sur_commande("basket_live/prono/ilona/2/set", AUCUN)          # Ilona se ravise : pas de prono
    app.sur_commande("basket_live/prono/ilona/1/set", "Inconnu")       # libellé invalide : ignoré
    app.publier()
    assert bus.retenus["basket_live/prono/francis/1/etat"] == "Nanterre"
    assert bus.retenus["basket_live/prono/ilona/2/etat"] == AUCUN
    # Rien n'est visible dans l'historique avant l'entre-deux
    assert json.loads(bus.retenus["basket_live/pronostics/attributs"])["matchs"] == []

    # Après l'entre-deux : saisie refusée, pronostics révélés
    h.t = T + 60
    app.traiter_ws({"type": "update", "data": {"eventId": 1, "status.code": 13}})
    app.sur_commande("basket_live/prono/ilona/1/set", "Nanterre")
    app.publier()
    revele = json.loads(bus.retenus["basket_live/pronostics/attributs"])["matchs"]
    assert revele[0]["pronos"] == {"francis": "Nanterre", "ilona": "Bourg-en-Bresse"}
    assert revele[0]["resultats"] == {"francis": None, "ilona": None}

    # Fins : Nanterre gagne en Élite (3 pts à Francis), Wrocław perd (0 pour Francis, Ilona n'avait pas joué)
    m1, m2 = app.matchs[1], app.matchs[2]
    m1.score_dom, m1.score_ext = 85, 80
    app.finaliser(m1)
    m2.code = 13
    m2.score_dom, m2.score_ext = 70, 75
    app.finaliser(m2)
    app.publier()
    histo = json.loads(bus.retenus["basket_live/pronostics/attributs"])
    assert [x["id"] for x in histo["matchs"]] == [2, 1]
    assert histo["matchs"][1]["resultats"] == {"francis": True, "ilona": False}
    assert histo["matchs"][1]["points"] == {"francis": 3, "ilona": 0}
    assert histo["matchs"][0]["pronos"]["ilona"] is None
    classement = json.loads(bus.retenus["basket_live/classement/attributs"])
    assert classement["joueurs"][0] == {"nom": "Francis", "points": 3, "bons": 1, "pronos": 2}
    assert classement["joueurs"][1] == {"nom": "Ilona", "points": 0, "bons": 0, "pronos": 1}
    assert bus.retenus["basket_live/classement/etat"] == "Francis"
    assert bus.retenus["basket_live/pronostics/etat"] == "2"

    # Persistance
    app.sauver_etat()
    app2 = App(config(tmp_path), FausseApi(), bus=FauxBus(), horloge=h)
    app2.charger_etat()
    assert len(app2.pronos.historique) == 2


def test_correction_a_posteriori(tmp_path):
    h = Horloge(T - 3600)
    app, bus = faire(tmp_path, h)
    app.sur_commande("basket_live/prono/francis/1/set", "Nanterre")
    app.sur_commande("basket_live/prono/ilona/1/set", "Bourg-en-Bresse")
    app.sur_commande("basket_live/prono/ilona/1/set", AUCUN)          # pronostic perdu avant l'entre-deux
    cmd = lambda **d: app.sur_commande("basket_live/commande", json.dumps({"action": "corriger_prono", **d}))
    # Refusée tant que le match n'est pas terminé
    cmd(match_id=1, joueur="ilona", choix="Bourg-en-Bresse")
    assert "ilona" not in app.pronos.choix[1]

    h.t = T + 60
    m1, m2 = app.matchs[1], app.matchs[2]
    m1.code, m1.score_dom, m1.score_ext = 13, 78, 84                   # Bourg gagne en Élite : 2 points
    app.finaliser(m1)
    m2.code, m2.score_dom, m2.score_ext = 13, 70, 75                   # personne n'avait pronostiqué
    app.finaliser(m2)
    assert app.pronos.historique[0]["points"] == {"francis": 0, "ilona": 0}

    cmd(match_id=1, joueur="ilona", choix="Inconnu")                  # libellé invalide : ignoré
    cmd(match_id=1, joueur="renaud", choix="Bourg-en-Bresse")          # joueur inconnu : ignoré
    cmd(match_id=1, joueur="ilona", choix="Bourg-en-Bresse")
    e = app.pronos.historique[0]
    assert e["pronos"]["ilona"] == "Bourg-en-Bresse"
    assert e["resultats"] == {"francis": False, "ilona": True}
    assert e["points"] == {"francis": 0, "ilona": 3}

    cmd(match_id=2, joueur="ilona", choix="Bourg-en-Bresse")          # entrée créée à partir du résultat
    assert [x["id"] for x in app.pronos.historique] == [1, 2]
    assert app.pronos.historique[1]["points"]["ilona"] == 1
    app.publier()
    classement = json.loads(bus.retenus["basket_live/classement/attributs"])
    assert classement["joueurs"][0] == {"nom": "Ilona", "points": 4, "bons": 2, "pronos": 2}

    cmd(match_id=1, joueur="ilona", choix=AUCUN)                       # retour arrière possible
    assert app.pronos.historique[0]["points"]["ilona"] == 0
    assert app.pronos.historique[0]["pronos"]["ilona"] is None

    app2 = App(config(tmp_path), FausseApi(), bus=FauxBus(), horloge=h)
    app2.charger_etat()
    assert app2.pronos.historique[1]["pronos"]["ilona"] == "Bourg-en-Bresse"


def test_saison():
    assert saison(datetime(2026, 11, 5, tzinfo=TZ).timestamp(), TZ) == "2026-2027"
    assert saison(datetime(2027, 6, 10, tzinfo=TZ).timestamp(), TZ) == "2026-2027"
    assert saison(datetime(2027, 7, 1, 12, tzinfo=TZ).timestamp(), TZ) == "2027-2028"


def test_bareme():
    from app.modele import Match
    from app.pronos import points_en_jeu
    def m(cat, tid):
        return Match(id=1, categorie=cat, tournoi_id=tid, tournoi="x", domicile="a", domicile_id=1, domicile_code=None,
                     exterieur="b", exterieur_id=2, exterieur_code=None, debut_ts=0)
    elite = {156}
    assert points_en_jeu(m("nanterre", 156), elite) == 3
    assert points_en_jeu(m("nanterre", 141), elite) == 2      # Nanterre en EuroCup
    assert points_en_jeu(m("nanterre", 1666), elite) == 2     # Nanterre en Coupe de France
    assert points_en_jeu(m("elite", 156), elite) == 2
    assert points_en_jeu(m("europe", 138), elite) == 1
