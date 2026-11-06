import asyncio
from copy import deepcopy
from datetime import datetime
import json
from zoneinfo import ZoneInfo

from app.archives import (Archives, DELAI_STATISTIQUES, INTERVALLE_COLLECTE, ecrire,
                          saison_compatible)
from app.modele import appliquer, construire_match, finaliser
from fixtures import ELITE, EUROCUP, NANTERRE, equipe, evenement
from test_app import FausseApi, Horloge, faire_app

TZ = ZoneInfo('Europe/Paris')
T = datetime(2026, 11, 7, 20, tzinfo=TZ).timestamp()


def ev(id=1, nanterre=True, debut=T, code=100):
    return evenement(id, ELITE, equipe(NANTERRE if nanterre else 10, 'Nanterre 92' if nanterre else 'Roanne'),
                     equipe(3, 'Paris'), int(debut), code, ([20, 20, 20, 20], [19, 19, 19, 19]))


def match(id=1, nanterre=True, debut=T, fin=T+7200):
    e = ev(id, nanterre, debut)
    m = construire_match(e, 'nanterre' if nanterre else 'elite')
    appliquer(m, __import__('app.modele',fromlist=['normaliser']).normaliser(e), fin)
    finaliser(m, fin)
    return m


class ApiArchives(FausseApi):
    def __init__(self):
        super().__init__()
        self.reponses = {}
        self.archive_appels = []

    async def details_match(self, mid, ressource):
        self.archive_appels.append((ressource, mid))
        self.compter()
        return self.reponses.get((ressource, mid), {'success': True, 'data': {'test': ressource}})

    async def historique_equipe(self, identifiant, page):
        self.archive_appels.append(('equipe', identifiant, page))
        self.compter()
        return self.reponses.get(('equipe', identifiant, page), {'events': [], 'hasNextPage': False})

    async def saisons_tournoi(self, identifiant):
        self.archive_appels.append(('saisons', identifiant))
        self.compter()
        return self.reponses.get(('saisons', identifiant), {'seasons': [{'id': 999, 'year': '26/27'}]})

    async def historique_tournoi(self, identifiant, sid, page):
        self.archive_appels.append(('tournoi', identifiant, sid, page))
        self.compter()
        return self.reponses.get(('tournoi', identifiant, sid, page), {'events': [], 'hasNextPage': False})


def faire(tmp_path, t=T+7200):
    h = Horloge(t)
    api = ApiArchives()
    app, bus = faire_app(tmp_path, api, h)
    return app, bus, api, h


def traiter(app, api, h, autorise):
    h.t = max(h.t + INTERVALLE_COLLECTE, app.archives.prochain)
    return asyncio.run(app.archives.traiter(api, import_autorise=autorise, maintenant=h.t))


def test_stats_deux_requetes_uniques_apres_fin_nanterre_et_reutilisation_cache(tmp_path):
    app, _, api, h = faire(tmp_path)
    m = match()
    app.archives.ajouter(m, historique=False, maintenant=h.t)
    assert not traiter(app, api, h, False)
    assert not api.archive_appels
    h.t = m.termine_ts + DELAI_STATISTIQUES
    assert traiter(app, api, h, False)
    assert traiter(app, api, h, False)
    for _ in range(5):
        assert not traiter(app, api, h, False)
    assert api.archive_appels == [('statistics', 1), ('lineups', 1)]
    fichier = tmp_path/'archives/2026-2027/statistiques/1.json'
    assert json.loads(fichier.read_text())['lineups']['etat'] == 'enregistre'
    autre, _ = faire_app(tmp_path, ApiArchives(), h)
    assert not traiter(autre, autre.api, h, False)
    assert not autre.api.archive_appels
    assert autre.archives.details[1]['statistics']['reponse'] == app.archives.details[1]['statistics']['reponse']


def test_pas_de_statistiques_non_nanterre_ni_avant_fin(tmp_path):
    app, _, api, h = faire(tmp_path)
    assert app.archives.ajouter(match(nanterre=False), historique=False, maintenant=h.t)
    m = match(id=2)
    m.termine = False
    assert not app.archives.ajouter(m, historique=False, maintenant=h.t)
    assert not app.archives.details
    assert not traiter(app, api, h, False)
    assert not api.archive_appels


def test_echec_et_interruption_ne_declenchent_pas_de_nouvel_appel(tmp_path):
    app, _, api, h = faire(tmp_path)
    app.archives.ajouter(match(), historique=False, maintenant=h.t)
    h.t += DELAI_STATISTIQUES
    api.reponses[('statistics', 1)] = None
    traiter(app, api, h, False)
    traiter(app, api, h, False)
    assert app.archives.details[1]['statistics']['etat'] == 'indisponible'
    app.archives.details[1]['lineups'] = {'etat': 'reserve', 'tente_le': h.t}
    ecrire(tmp_path/'archives/2026-2027/statistiques/1.json', app.archives.details[1])
    copie = Archives(tmp_path, TZ, app.criteres, h.t)
    h.t += 3600
    asyncio.run(copie.traiter(api, import_autorise=False, maintenant=h.t))
    assert copie.details[1]['lineups']['etat'] == 'interrompu'
    assert api.archive_appels.count(('statistics', 1)) == 1
    assert api.archive_appels.count(('lineups', 1)) == 1


def test_saison_conservee_au_dela_des_sept_jours_sans_modifier_tuile_recente(tmp_path):
    app, bus, _, h = faire(tmp_path)
    m = match(nanterre=False)
    app.matchs[1] = m
    app.resultats = [m]
    app.publier()
    h.t += 10 * 86400
    app.elaguer()
    app.publier()
    assert app.resultats == []
    assert bus.retenus['basket_live/resultats/etat'] == '0'
    archive = json.loads(bus.retenus['basket_live/resultats_saison/attributs'])
    assert archive['saison'] == '2026-2027' and [m['id'] for m in archive['matchs']] == [1]


def test_import_refuse_jour_de_match_meme_termine_ou_calendrier_non_verifie(tmp_path):
    app, _, api, h = faire(tmp_path)
    assert not app.import_archives_autorise()
    jour = datetime.fromtimestamp(h.t, TZ).date()
    app.dernier_calendrier[jour.isoformat()] = h.t
    assert app.import_archives_autorise()
    m = match(nanterre=False)
    app.matchs[1] = m
    assert not app.import_archives_autorise()
    m.code = 70
    assert app.import_archives_autorise()
    m.code = 100
    app.archives.ajouter(m, historique=True, maintenant=h.t)
    app.matchs = {}
    assert not app.import_archives_autorise()  # un résultat du jour dans l'archive suffit aussi
    app.archives.jobs = [{'type': 'equipe', 'id': NANTERRE, 'page': 0, 'termine': False}]
    traiter(app, api, h, app.import_archives_autorise())
    assert not api.archive_appels


def test_import_preserve_35_requetes_sur_100_et_attend_jour_libre(tmp_path):
    app, _, api, h = faire(tmp_path)
    assert app.archives.plafond_import(api) == 65
    api.compteur = 64
    assert not traiter(app, api, h, False)
    assert not api.archive_appels
    assert traiter(app, api, h, True)
    assert api.compteur == 65
    assert not traiter(app, api, h, True)
    assert len(api.archive_appels) == 1
    assert api.disponible('fond') and api.disponible('essentiel')


def test_import_pages_saison_filtre_clubs_francais_et_conserve_nanterre_toutes_competitions(tmp_path):
    app, bus, api, h = faire(tmp_path, T+86400)
    a = app.archives
    a.jobs = [{'type': 'equipe', 'id': NANTERRE, 'page': 0, 'termine': False},
              {'type': 'saisons', 'id': 156, 'termine': False}]
    api.reponses[('equipe', NANTERRE, 0)] = {'events': [ev()], 'hasNextPage': False}
    vieux = ev(id=4, debut=datetime(2026,6,30,20,tzinfo=TZ).timestamp(), nanterre=False)
    api.reponses[('tournoi',156,999,0)] = {'data': {'events':[ev(id=2,nanterre=False)], 'hasNextPage':True}}
    api.reponses[('tournoi',156,999,1)] = {'events':[vieux], 'hasNextPage':False}
    for _ in range(4):
        traiter(app, api, h, True)
    assert set(a.resultats) == {1,2}
    assert all(j['termine'] for j in a.jobs)
    assert app.resultats == [] and bus.evenements == []  # pas de notifications de résultats anciens
    assert set(a.details) == {1}
    # Deux clubs étrangers en coupe d'Europe ne sont pas archivés.
    e = evenement(50, EUROCUP, equipe(101,'A',pays='PL'), equipe(102,'B',pays='ES'), int(T),100)
    a.jobs=[{'type':'tournoi','id':141,'sid':44,'page':0,'termine':False}]
    api.reponses[('tournoi',141,44,0)]={'events':[e], 'hasNextPage':False}
    traiter(app,api,h,True)
    assert 50 not in a.resultats


def test_reprise_import_persistante_ne_refait_pas_les_stats_et_s_arrete_au_point_deja_connu(tmp_path):
    app, _, api, h = faire(tmp_path, T+86400)
    a=app.archives
    a.jobs=[{'type':'equipe','id':NANTERRE,'page':0,'termine':False}]
    api.reponses[('equipe',NANTERRE,0)]={'events':[ev()], 'hasNextPage':False}
    traiter(app,api,h,True)
    copie=Archives(tmp_path,TZ,app.criteres,h.t)
    assert copie.jobs[0]['reprise'] and copie.jobs[0]['page']==0
    h.t+=INTERVALLE_COLLECTE
    asyncio.run(copie.traiter(api,import_autorise=True,maintenant=h.t))
    assert copie.jobs[0]['termine']
    assert not [v for v in api.archive_appels if v[0] in ('statistics','lineups')]


def test_statistiques_historiques_uniquement_les_jours_sans_match(tmp_path):
    app, _, api, h = faire(tmp_path, T+86400)
    app.archives.jobs=[]
    app.archives.ajouter(match(),historique=True,maintenant=h.t)
    assert not traiter(app,api,h,False)
    assert not api.archive_appels
    assert traiter(app,api,h,True)
    assert api.archive_appels == [('statistics',1)]


def test_changement_de_saison_preserve_fichiers_anterieurs(tmp_path):
    app, _, _, h = faire(tmp_path)
    app.archives.ajouter(match(nanterre=False),historique=False,maintenant=h.t)
    ancien=tmp_path/'archives/2026-2027/index.json'
    contenu=ancien.read_text()
    h.t=datetime(2027,7,1,12,tzinfo=TZ).timestamp()
    app.archives.changer_saison(h.t)
    assert app.archives.saison=='2027-2028' and not app.archives.resultats
    assert ancien.read_text()==contenu


def test_detection_saison_et_protection_du_score_suivi(tmp_path):
    assert saison_compatible({'year':'26/27'},2026)
    assert saison_compatible({'name':'LNB Élite 2026-2027'},2026)
    assert saison_compatible({'year':'2026'},2026)
    assert not saison_compatible({'year':'25/26'},2026)
    app, _, _, h=faire(tmp_path)
    m=match(nanterre=False)
    app.archives.ajouter(m,historique=False,maintenant=h.t)
    ancien=deepcopy(m)
    ancien.score_dom=37
    assert not app.archives.ajouter(ancien,historique=True,maintenant=h.t,source='import')
    assert app.archives.resultats[1].score_dom==80


def test_commande_test_un_seul_match_trois_requetes_sans_jour_libre(tmp_path):
    from app.bus import COMMANDE
    app, bus, api, h = faire(tmp_path)
    api.reponses[('equipe', NANTERRE, 0)] = {'events': [ev(11, debut=T-86400), ev(12, debut=T-172800), ev(13, nanterre=False)]}
    app.sur_commande(COMMANDE, 'tester_archive_nanterre')
    assert traiter(app, api, h, False)
    assert set(app.archives.resultats) == {11}
    assert app.archives.test_match == 11
    assert traiter(app, api, h, False)
    assert traiter(app, api, h, False)
    assert traiter(app, api, h, False)
    assert app.archives.test_match is None
    assert api.archive_appels == [('equipe', NANTERRE, 0), ('statistics', 11), ('lineups', 11)]
    assert not bus.evenements
    app.sur_commande(COMMANDE, 'tester_archive_nanterre')
    traiter(app, api, h, False)
    traiter(app, api, h, False)
    assert len(api.archive_appels) == 3


def test_commande_test_refuse_si_marge_insuffisante_et_ne_pagine_pas(tmp_path):
    app, _, api, h = faire(tmp_path)
    api.compteur = 63
    app.archives.demande_test = True
    traiter(app, api, h, False)
    assert not api.archive_appels
    assert not app.archives.demande_test
    api.compteur = 0
    api.reponses[('equipe', NANTERRE, 0)] = {'events': [], 'hasNextPage': True}
    app.archives.demande_test = True
    traiter(app, api, h, False)
    assert api.archive_appels == [('equipe', NANTERRE, 0)]
    assert app.archives.test_match is None


def test_commande_test_reprise_cache_et_requetes_manquantes_seulement(tmp_path):
    app, _, api, h = faire(tmp_path)
    app.archives.ajouter(match(id=10), historique=True, maintenant=h.t)
    app.archives.demande_test = True
    traiter(app, api, h, False)
    traiter(app, api, h, False)
    assert api.archive_appels == [('statistics', 10)]
    api2 = ApiArchives()
    autre, _ = faire_app(tmp_path, api2, h)
    assert autre.archives.test_match == 10
    traiter(autre, api2, h, False)
    traiter(autre, api2, h, False)
    assert api2.archive_appels == [('lineups', 10)]
    assert autre.archives.test_match is None


def test_commande_test_filtre_matchs_non_eligibles_et_double_commande(tmp_path):
    app, _, api, h = faire(tmp_path)
    api.reponses[('equipe', NANTERRE, 0)] = {'events': [ev(1, nanterre=False), ev(2, code=15), ev(3, debut=T+86400), ev(4, debut=T-400*86400), ev(5, debut=T-86400)]}
    app.archives.demande_test = True
    traiter(app, api, h, False)
    assert set(app.archives.resultats) == {5}
    app.archives.demande_test = True
    traiter(app, api, h, False)
    assert api.archive_appels == [('equipe', NANTERRE, 0)]
    assert app.archives.test_match == 5
