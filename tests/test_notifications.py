"""Échéances persistantes et rappels personnels groupés, sans service externe."""
from copy import deepcopy
from datetime import datetime
import json
from zoneinfo import ZoneInfo

from app.notifications import AVANCE_RAPPEL, DELAI_FERMETURE, Notifications
from app.pronos import Pronos
from fixtures import ELITE, equipe, evenement
from test_app import FausseApi, Horloge, faire_app

TZ = ZoneInfo('Europe/Paris')
DEBUT = datetime(2026, 11, 7, 18, 0, tzinfo=TZ).timestamp()
JOUR = datetime.fromtimestamp(DEBUT, TZ).date()


def preparer(tmp_path, maintenant=DEBUT - AVANCE_RAPPEL):
    h = Horloge(maintenant)
    app, bus = faire_app(tmp_path, FausseApi(), h)
    matchs = [evenement(1, ELITE, equipe(11, 'Roanne'), equipe(12, 'Saint-Quentin'), int(DEBUT)),
              evenement(2, ELITE, equipe(21, 'Cholet'), equipe(22, 'Paris'), int(DEBUT)),
              evenement(3, ELITE, equipe(31, 'Nanterre'), equipe(32, 'Le Mans'), int(DEBUT + 1800))]
    app.fusionner(matchs, JOUR)
    return app, bus, h


def rappels(app, joueur):
    return [e for e in app.notifications.attributs()['echeances']
            if e['type'] == 'rappel_prono' and e['personne'] == joueur]


def test_a_16h_un_seul_rappel_pour_les_deux_matchs_de_18h(tmp_path):
    app, bus, h = preparer(tmp_path, DEBUT - AVANCE_RAPPEL - 1)
    app.publier()
    assert not rappels(app, 'francis')
    h.t += 1
    app.publier()
    assert datetime.fromtimestamp(h.t, TZ).strftime('%H:%M') == '16:00'
    for joueur in ['francis', 'ilona']:
        group = rappels(app, joueur)
        assert len(group) == 1
        assert [m['id'] for m in group[0]['matchs']] == [1, 2]
        assert group[0]['matchs'][0]['titre'] == 'Roanne - Saint-Quentin'
    assert app.api.compteur == 0
    assert 'notifications' in json.loads(app.fichier_etat.read_text())


def test_pronostics_manquants_personnels_et_horaires_separes(tmp_path):
    app, _, h = preparer(tmp_path)
    app.pronos.choix = {1: {'francis': 'dom'}, 2: {'ilona': 'ext'}}
    app.publier()
    assert [m['id'] for m in rappels(app, 'francis')[0]['matchs']] == [2]
    assert [m['id'] for m in rappels(app, 'ilona')[0]['matchs']] == [1]
    h.t += 1800
    app.publier()
    assert len(rappels(app, 'francis')) == 2  # le second groupe concerne 18 h 30
    assert len(rappels(app, 'ilona')) == 2


def test_aucun_rappel_si_tous_pronos_faits_et_annulation_immediate(tmp_path):
    app, _, _ = preparer(tmp_path)
    app.publier()
    app.sur_commande('basket_live/prono/francis/1/set', 'Roanne')
    assert [m['id'] for m in rappels(app, 'francis')[0]['matchs']] == [2]
    app.sur_commande('basket_live/prono/francis/2/set', 'Paris')
    assert not rappels(app, 'francis')
    assert len(rappels(app, 'ilona')) == 1
    etat = json.loads(app.fichier_etat.read_text())
    assert etat['pronos']['choix']['1']['francis'] == 'dom'
    assert etat['pronos']['choix']['2']['francis'] == 'ext'


def test_rappel_acquitte_pas_de_doublon_apres_redemarrage_ou_autre_match_meme_horaire(tmp_path):
    app, _, h = preparer(tmp_path)
    app.publier()
    cle = rappels(app, 'francis')[0]['cle']
    app.sur_commande('basket_live/notification/ack', json.dumps({'cle': cle}))
    assert not rappels(app, 'francis')
    # Une annulation de pronostic et un nouveau match à cet horaire ne renvoient pas un 2e rappel.
    nouveau = deepcopy(app.matchs[1])
    nouveau.id = 10
    app.matchs[10] = nouveau
    app.actualiser_notifications()
    assert not rappels(app, 'francis')
    autre, _ = faire_app(tmp_path, FausseApi(), h)
    autre.charger_etat()
    autre.publier()
    assert not rappels(autre, 'francis')
    assert len(rappels(autre, 'ilona')) == 1


def test_rappel_en_attente_survit_a_redemarrage_mais_ne_part_plus_apres_debut(tmp_path):
    app, _, h = preparer(tmp_path)
    app.publier()
    cles = [e['cle'] for e in rappels(app, 'francis')]
    autre, _ = faire_app(tmp_path, FausseApi(), h)
    autre.charger_etat()
    autre.publier()
    assert [e['cle'] for e in rappels(autre, 'francis')] == cles
    h.t = DEBUT
    autre.publier()
    assert all(e['debut'] > DEBUT for e in rappels(autre, 'francis'))


def test_rattrapage_apres_16h_uniquement_avant_le_match(tmp_path):
    app, _, h = preparer(tmp_path, DEBUT - 3600)
    app.publier()
    assert len(rappels(app, 'francis')) == 2
    h.t = DEBUT + 1800
    app.publier()
    assert not rappels(app, 'francis')


def test_reports_annulations_et_changement_horaire_annulent_le_rappel_obsolete(tmp_path):
    app, _, h = preparer(tmp_path)
    app.matchs[1].code = 60
    app.matchs[2].code = 70
    app.publier()
    assert not rappels(app, 'francis')
    app.matchs[1].code = 0
    app.matchs[1].debut_ts += 3600
    app.publier()
    assert not rappels(app, 'francis')
    h.t += 3600
    app.publier()
    assert any([m['id'] for m in e['matchs']] == [1] and e['debut'] == DEBUT + 3600
               for e in rappels(app, 'francis'))


def test_fermetures_persistantes_distinctes_et_acquittement_a_echeance(tmp_path):
    app, _, h = preparer(tmp_path, DEBUT + 7200)
    app.finaliser(app.matchs[1])
    premiere = deepcopy(app.notifications.vers_dict())
    cle = 'fermeture:francis:1'
    assert premiere['echeances'][cle]['echeance'] == h.t + DELAI_FERMETURE
    assert not app.notifications.acquitter(cle, h.t)  # ne pas acquitter prématurément
    h.t += 600
    app.finaliser(app.matchs[2])
    seconde = app.notifications.echeances['fermeture:francis:2']['echeance']
    autre, _ = faire_app(tmp_path, FausseApi(), h)
    autre.charger_etat()
    assert autre.notifications.echeances[cle]['echeance'] == premiere['echeances'][cle]['echeance']
    h.t = premiere['echeances'][cle]['echeance'] + 1
    autre.publier()
    dues = [e for e in autre.notifications.attributs()['echeances'] if e['echeance'] <= h.t]
    assert {e['cle'] for e in dues} == {'fermeture:francis:1', 'fermeture:ilona:1'}
    autre.sur_commande('basket_live/notification/ack', json.dumps({'cle': cle}))
    assert cle not in autre.notifications.echeances
    assert autre.notifications.echeances['fermeture:francis:2']['echeance'] == seconde
    autre.publier()
    assert cle not in autre.notifications.echeances  # ne pas reprogrammer un résultat déjà traité
    assert app.api.compteur == autre.api.compteur == 0


def test_migration_des_resultats_anciens_recupere_les_fermetures_perdues(tmp_path):
    app, _, h = preparer(tmp_path, DEBUT + 7200)
    app.finaliser(app.matchs[1])
    # État 0.3.0 dépourvu de file de notifications.
    etat = json.loads(app.fichier_etat.read_text())
    etat.pop('notifications')
    app.fichier_etat.write_text(json.dumps(etat))
    h.t += DELAI_FERMETURE + 100
    autre, _ = faire_app(tmp_path, FausseApi(), h)
    autre.charger_etat()
    autre.publier()
    assert autre.notifications.echeances['fermeture:francis:1']['echeance'] < h.t
    assert autre.notifications.echeances['fermeture:ilona:1']['echeance'] < h.t


def test_acquittement_persistant_empeche_repetition_fermeture_apres_redemarrage(tmp_path):
    app, _, h = preparer(tmp_path, DEBUT + 7200)
    app.finaliser(app.matchs[1])
    h.t += DELAI_FERMETURE
    cle = 'fermeture:francis:1'
    app.sur_commande('basket_live/notification/ack', json.dumps({'cle': cle}))
    autre, _ = faire_app(tmp_path, FausseApi(), h)
    autre.charger_etat()
    autre.publier()
    assert cle not in autre.notifications.echeances
    assert cle in autre.notifications.acquittes


def test_acquittements_invalides_et_chargement_corrompu_ignores():
    notifications = Notifications(['francis', 'ilona'])
    notifications.charger({'echeances': {'x': None, 'y': {'personne': 'inconnu', 'echeance': 1}},
                           'acquittes': {'cle': 'date invalide'}})
    assert not notifications.echeances and not notifications.acquittes
    assert not notifications.acquitter(None, DEBUT)
    assert not notifications.acquitter('inconnue', DEBUT)


def test_horaires_minute_regroupes_meme_si_secondes_differentes(tmp_path):
    app, _, h = preparer(tmp_path)
    app.matchs[2].debut_ts += 20
    app.publier()
    assert len(rappels(app, 'francis')) == 1
    assert len(rappels(app, 'francis')[0]['matchs']) == 2


def test_decouverte_et_reception_mqtt_des_acquittements():
    import asyncio
    from types import SimpleNamespace
    from app.bus import Bus, NOTIFICATION_ACK, decouverte
    configurations = {t: json.loads(p) for t, p in decouverte()}
    conf = configurations['homeassistant/sensor/basket_live/notifications/config']
    assert conf['json_attributes_topic'] == 'basket_live/notifications/attributs'
    assert conf['state_topic'] == 'basket_live/notifications/etat'
    recus = []
    bus = Bus('localhost', 1883, None, None, lambda topic, texte: recus.append((topic, texte)))
    class Topic:
        value = NOTIFICATION_ACK
        def matches(self, valeur):
            return valeur == self.value
    async def messages():
        yield SimpleNamespace(topic=Topic(), payload=b'{"cle":"rappel_prono:francis:123"}')
    asyncio.run(bus._recevoir(SimpleNamespace(messages=messages())))
    assert recus == [(NOTIFICATION_ACK, '{"cle":"rappel_prono:francis:123"}')]
