import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.badges import CATALOGUE, PAR_ID, Badges
from app.main import App
from app.notifications import Notifications
from app.pronos import libelles_noms
from fixtures import ELITE, NANTERRE, FauxBus, config, equipe, evenement
from test_app import FausseApi, Horloge

TZ = ZoneInfo("Europe/Paris")
SAISON = "2026-2027"
EUROCUP = 141
JOUEURS = ["francis", "ilona"]


def entree(i, jour, dom, ext, score, pronos, tournoi=ELITE, rangs=None):
    """Entrée d'historique telle que Pronos.entree la fige ; pronos : joueur -> 'dom' | 'ext'."""
    noms = libelles_noms(dom, ext)
    sd, se = score
    g = "dom" if sd > se else "ext"
    e = {"id": i, "debut": f"2026-11-{jour:02d}T20:00:00+01:00", "saison": SAISON, "tournoi": "",
         "tournoi_id": tournoi, "categorie": "", "domicile": dom, "exterieur": ext,
         "score": f"{sd} - {se}", "termine": True, "points_en_jeu": 2, "vainqueur": noms[g],
         "pronos": {j: noms[c] for j, c in pronos.items()},
         "resultats": {j: c == g for j, c in pronos.items()},
         "points": {j: 2 if c == g else 0 for j, c in pronos.items()}}
    if rangs:
        e["rangs"] = rangs
    return e


def moteur():
    return Badges(JOUEURS, ["ilona"], {ELITE}, {138, EUROCUP, 9357, 2165})


HISTO = [
    # Nanterre gagne d'un point à l'extérieur : Francis avec Nanterre, Ilona contre
    entree(1, 2, "Cholet Basket", "Nanterre 92", (80, 81), {"francis": "ext", "ilona": "dom"}),
    # Victoire de 25 points à domicile, même choix réussi pour les deux
    entree(2, 2, "Le Mans Sarthe Basket", "JL Bourg Basket", (100, 75), {"francis": "dom", "ilona": "dom"}),
    # Coupe d'Europe, le moins bien classé n'a pas de sens ici ; Ilona seule
    entree(3, 2, "Śląsk Wrocław", "JL Bourg Basket", (70, 75), {"ilona": "ext"}, tournoi=EUROCUP),
    # Élite : l'équipe classée 12e bat la 3e ; Francis l'avait vu
    entree(4, 3, "Paris Basketball", "Limoges CSP", (78, 84), {"francis": "ext", "ilona": "dom"},
           rangs={"dom": 3, "ext": 12}),
    # Nanterre perd ; Francis avec Nanterre, perdu d'un point
    entree(5, 4, "Nanterre 92", "AS Monaco", (90, 91), {"francis": "dom"}),
]


def test_valeurs_par_badge():
    b = moteur()
    f = b.valeurs(HISTO, SAISON, "francis")
    i = b.valeurs(HISTO, SAISON, "ilona")
    assert f["assidu"] == 4 and i["assidu"] == 4
    assert f["ultra"] == 1 and i["ultra"] == 0
    assert f["judas"] == 0 and i["judas"] == 1
    assert f["chanceux"] == 1 and i["malchanceux"] == 1 and f["malchanceux"] == 1
    assert f["rouleau"] == 1 and i["rouleau"] == 1
    assert f["ames_soeurs"] == 1 and i["ames_soeurs"] == 1
    assert f["duelliste"] == 2 and i["duelliste"] == 0            # matchs 1 et 4
    assert i["europeen"] == 1 and i["globe_trotter"] == 1 and f["globe_trotter"] == 2
    assert f["visionnaire"] == 1 and i["visionnaire"] == 0
    assert f["lucky_streak"] == 3 and f["chat_noir"] == 1          # 3 réussis puis un échec
    assert i["lucky_streak"] == 2 and i["chat_noir"] == 1
    # Journée du 2 : 3 pronostics d'Ilona, dont l'échec du match 1 ; Francis n'en a que 2
    assert i["sans_faute"] == 0 and f["sans_faute"] == 0


def test_sans_faute_et_series():
    b = moteur()
    histo = [entree(10 + k, 6, "Cholet Basket", "Limoges CSP", (80, 70), {"francis": "dom"}) for k in range(3)]
    histo += [entree(20 + k, 7, "Cholet Basket", "Limoges CSP", (60, 70), {"francis": "dom"}) for k in range(2)]
    v = b.valeurs(histo, SAISON, "francis")
    assert v["sans_faute"] == 1 and v["lucky_streak"] == 3 and v["chat_noir"] == 2
    # Les autres saisons ne comptent pas
    autre = [{**h, "saison": "2025-2026"} for h in histo]
    assert b.valeurs(autre, SAISON, "francis")["assidu"] == 0


def test_noms_genres_icones_et_ordre():
    obtenus = moteur().calculer(HISTO, SAISON)
    f = {x["id"]: x for x in obtenus["francis"]}
    i = {x["id"]: x for x in obtenus["ilona"]}
    assert f["ultra"]["nom"] == "Ultra Nanterrien"
    assert i["judas"]["nom"] == "Judas" and i["judas"]["negatif"] is True
    assert i["malchanceux"]["nom"] == "Malchanceuse" and f["malchanceux"]["nom"] == "Malchanceux"
    assert f["duelliste"]["description"] == "2 fois raison contre Ilona sur un pronostic opposé."
    assert "ames_soeurs" not in f                                    # 1 < 5 : pas encore d'étoile
    for cle in set(f) & set(i):                                      # même badge, même icône
        assert f[cle]["icone"] == i[cle]["icone"]
    ordre = [b.id for b in CATALOGUE]
    for liste in obtenus.values():                                   # catalogue, négatifs regroupés à la fin
        ids = [x["id"] for x in liste]
        assert ids == sorted(ids, key=lambda i: (PAR_ID[i].negatif, ordre.index(i)))
    assert [x["negatif"] for x in obtenus["ilona"]][-3:] == [True, True, True]
    assert all(x["niveau"] >= 1 for x in obtenus["francis"] + obtenus["ilona"])
    assert "lucky_streak" not in f                                   # 3 < 5 : pas encore d'étoile
    noms = {b.id: (b.masculin, b.feminin) for b in CATALOGUE}
    assert noms["lucky_streak"] == ("Lucky Streak", "Lucky Streak")
    assert len(CATALOGUE) == 14


def test_paliers_et_niveaux():
    paliers = {b.id: b.paliers for b in CATALOGUE}
    assert paliers["lucky_streak"] == (5, 10, 25, 50, 100)
    assert paliers["assidu"] == (10, 50, 100, 200, 300)
    assert paliers["ames_soeurs"] == (5, 15, 30, 50, 80)
    b = next(x for x in CATALOGUE if x.id == "chat_noir")
    assert [b.niveau(v) for v in (0, 1, 4, 5, 19, 20, 99)] == [0, 1, 2, 3, 4, 5, 5]


def test_premier_calcul_silencieux_puis_annonces():
    b = moteur()
    obtenus = b.calculer(HISTO, SAISON)
    assert b.nouvelles_etoiles(obtenus, SAISON) == {}                # installation : rien n'est annoncé
    assert b.nouvelles_etoiles(obtenus, SAISON) == {}
    plus = HISTO + [entree(6, 5, "Nanterre 92", "AS Monaco", (91, 80), {"ilona": "dom"})]
    nouveaux = b.nouvelles_etoiles(b.calculer(plus, SAISON), SAISON)
    assert [x["id"] for x in nouveaux["ilona"]] == ["ultra"] and "francis" not in nouveaux
    # Une baisse (correction) puis la même hausse ne réannonce pas
    b.nouvelles_etoiles(b.calculer(HISTO, SAISON), SAISON)
    assert b.nouvelles_etoiles(b.calculer(plus, SAISON), SAISON) == {}
    copie = moteur()
    copie.charger(json.loads(json.dumps(b.vers_dict())))
    assert copie.notifiees == b.notifiees


def test_annonces_fusionnees_puis_acquittees():
    n = Notifications(JOUEURS)
    badge = lambda i, niveau: {"id": i, "nom": i, "icone": "mdi:cat", "niveau": niveau, "negatif": False,
                               "description": "", "valeur": 1, "paliers": [1, 2, 5, 10, 20]}
    n.ajouter_badges("ilona", [badge("ultra", 1)], 100.0)
    n.ajouter_badges("ilona", [badge("ultra", 2), badge("rouleau", 1)], 150.0)
    annonces = [e for e in n.echeances.values() if e["type"] == "badge"]
    assert len(annonces) == 1
    assert {b["id"]: b["niveau"] for b in annonces[0]["badges"]} == {"ultra": 2, "rouleau": 1}
    cle = annonces[0]["cle"]
    copie = Notifications(JOUEURS)
    copie.charger(json.loads(json.dumps(n.vers_dict())))
    assert cle in copie.echeances
    assert n.acquitter(cle, 200.0)
    n.ajouter_badges("ilona", [badge("ultra", 3)], 300.0)
    assert len([e for e in n.echeances.values() if e["type"] == "badge"]) == 1 and cle not in n.echeances


def test_bout_en_bout_dans_l_app(tmp_path):
    t = datetime(2026, 11, 12, 20, 0, tzinfo=TZ).timestamp()
    h = Horloge(t - 3600)
    bus = FauxBus()
    app = App(config(tmp_path), FausseApi(), bus=bus, horloge=h)
    jour = datetime.fromtimestamp(t, TZ).date()
    evs = [evenement(k, ELITE, equipe(NANTERRE if k == 1 else 100 + k, "Nanterre 92" if k == 1 else f"Club {k}"),
                     equipe(200 + k, f"Rival {k}"), int(t) + 600 * k, 0, None) for k in (1, 2)]
    app.fusionner(evs, jour)
    app.sur_commande("basket_live/prono/ilona/1/set", "Nanterre")
    app.sur_commande("basket_live/prono/ilona/2/set", f"Rival 2")
    app.publier()                                                    # premier calcul : silencieux
    h.t = t + 7200
    m1 = app.matchs[1]
    m1.code, m1.score_dom, m1.score_ext = 13, 85, 84
    app.finaliser(m1)
    app.publier()
    classement = json.loads(bus.retenus["basket_live/classement/attributs"])["joueurs"]
    ilona = next(j for j in classement if j["id"] == "ilona")
    assert {b["id"] for b in ilona["badges"]} == {"ultra", "chanceux"}
    assert next(j for j in classement if j["id"] == "francis")["badges"] == []
    echeances = json.loads(bus.retenus["basket_live/notifications/attributs"])["echeances"]
    annonce = next(e for e in echeances if e["type"] == "badge")
    assert annonce["personne"] == "ilona"
    assert {b["nom"] for b in annonce["badges"]} == {"Ultra Nanterrienne", "Chanceuse"}
    assert app.pronos.historique[-1]["nanterre"] == "dom"
    # Persistance : rien n'est réannoncé après redémarrage
    app.sauver_etat()
    app2 = App(config(tmp_path), FausseApi(), bus=FauxBus(), horloge=h)
    app2.charger_etat()
    assert app2.badges.nouvelles_etoiles(app2.badges.calculer(app2.pronos.historique, SAISON), SAISON) == {}
