import json

from app.bus import decouverte
from app.suivis import Suivis
from test_app import FausseApi, Horloge, T, TZ, ev_wroclaw, faire_app
from datetime import datetime
from fixtures import ELITE, NANTERRE, equipe, evenement

JOUR = datetime.fromtimestamp(T, TZ).date()


def preparer(tmp_path):
    h = Horloge(T - 60)
    app, bus = faire_app(tmp_path, FausseApi(), h)
    ev = evenement(1, ELITE, equipe(NANTERRE, "Nanterre 92"), equipe(3, "Paris"), int(T))
    app.fusionner([ev, ev_wroclaw()], JOUR)
    return app, bus, h


def test_plusieurs_matchs_par_personne_sans_croiser_les_choix(tmp_path):
    app, bus, _ = preparer(tmp_path)
    app.sur_commande('basket_live/suivi/francis/1/set', 'ON')
    app.sur_commande('basket_live/suivi/francis/16561673/set', 'ON')
    app.sur_commande('basket_live/suivi/ilona/16561673/set', 'ON')
    app.sur_commande('basket_live/suivi/francis/1/set', 'OFF')
    app.publier()
    francis = json.loads(bus.retenus['basket_live/suivis_francis/attributs'])
    ilona = json.loads(bus.retenus['basket_live/suivis_ilona/attributs'])
    assert francis['choix'] == {'1': False, '16561673': True}
    assert ilona['choix'] == {'16561673': True}
    assert bus.retenus['basket_live/suivis_francis/etat'] == '1'
    assert bus.evenements[-1]['personne'] == 'francis'
    assert bus.evenements[-1]['exclus'] == ['francis']
    assert app.api.compteur == 0


def test_selection_persistante_avant_accuse_et_restoration(tmp_path):
    app, _, h = preparer(tmp_path)
    app.sur_commande('basket_live/suivi/francis/1/set', 'OFF')
    app.sur_commande('basket_live/suivi/ilona/1/set', 'ON')
    etat = json.loads(app.fichier_etat.read_text())
    assert etat['suivis'] == {'francis': {'1': False}, 'ilona': {'1': True}}
    autre, _ = faire_app(tmp_path, FausseApi(), h)
    autre.charger_etat()
    assert autre.suivis.vers_dict() == app.suivis.vers_dict()


def test_fin_capture_les_destinataires_avant_nettoyage_et_ne_touche_pas_aux_autres(tmp_path):
    app, bus, _ = preparer(tmp_path)
    for joueur in ['francis', 'ilona']:
        app.sur_commande(f'basket_live/suivi/{joueur}/1/set', 'ON')
    app.sur_commande('basket_live/suivi/francis/16561673/set', 'ON')
    app.finaliser(app.matchs[1])
    fin = bus.evenements[-1]
    assert fin['type'] == 'fin' and fin['suivis'] == ['francis', 'ilona']
    assert app.suivis.vers_dict() == {'francis': {'16561673': True}, 'ilona': {}}
    app.publier()
    assert json.loads(bus.retenus['basket_live/suivis_francis/attributs'])['choix'] == {'16561673': True}


def test_choisir_en_cours_emet_un_evenement_personnel_sans_effacer_les_scores_en_attente(tmp_path):
    app, bus, h = preparer(tmp_path)
    h.t = T + 60
    app.traiter_ws({'type': 'update', 'data': {'eventId': 1, 'status.code': 13}})
    m = app.matchs[1]
    m.push_en_attente = True
    dernier = m.dernier_push_ts
    app.sur_commande('basket_live/suivi/ilona/1/set', 'ON')
    evt = bus.evenements[-1]
    assert evt['type'] == 'suivi_actif' and evt['personne'] == 'ilona'
    assert evt['match']['en_cours'] and evt['suivis'] == ['ilona']
    assert m.push_en_attente and m.dernier_push_ts == dernier
    app.sur_commande('basket_live/suivi/ilona/1/set', 'OFF')
    assert bus.evenements[-1]['type'] == 'suivi_arrete'
    assert bus.evenements[-1]['exclus'] == ['ilona']


def test_commandes_invalides_idempotence_et_pronos_independants(tmp_path):
    app, bus, h = preparer(tmp_path)
    for topic, valeur in [('basket_live/suivi/inconnu/1/set', 'ON'),
                           ('basket_live/suivi/francis/999/set', 'ON'),
                           ('basket_live/suivi/francis/1/set', 'oui')]:
        app.sur_commande(topic, valeur)
    assert not bus.evenements
    app.sur_commande('basket_live/suivi/francis/1/set', 'ON')
    app.sur_commande('basket_live/suivi/francis/1/set', 'ON')
    assert len(bus.evenements) == 1  # retransmission QoS 1 sans doublon
    assert app.pronos.choix == {}
    app.sur_commande('basket_live/prono/ilona/1/set', 'Paris')
    assert app.pronos.choix[1] == {'ilona': 'ext'}
    assert app.suivis.choix['francis'][1] is True
    app.matchs[1].termine = True
    app.sur_commande('basket_live/suivi/ilona/1/set', 'ON')
    assert not app.suivis.choix['ilona']


def test_plus_de_28_choix_sans_limite_de_champ_texte_et_nettoyage(tmp_path):
    app, _, _ = preparer(tmp_path)
    choix = Suivis(['francis', 'ilona'])
    for i in range(1, 61):
        m = app.matchs[1]
        m.id = 10_000_000 + i
        assert choix.choisir(m, 'francis', 'ON')
    assert len(choix.vers_dict()['francis']) == 60
    assert len(json.dumps(choix.vers_dict()['francis'])) > 255
    copie = Suivis(['francis', 'ilona'])
    copie.charger(json.loads(json.dumps(choix.vers_dict())))
    assert copie.vers_dict() == choix.vers_dict()
    copie.nettoyer({10_000_001})
    assert copie.vers_dict()['francis'] == {'10000001': True}


def test_decouverte_des_capteurs_personnels():
    configs = {topic: json.loads(payload) for topic, payload in decouverte(['francis', 'ilona'])}
    for joueur in ['francis', 'ilona']:
        conf = configs[f'homeassistant/sensor/basket_live/suivis_{joueur}/config']
        assert conf['json_attributes_topic'] == f'basket_live/suivis_{joueur}/attributs'
        assert conf['state_topic'] == f'basket_live/suivis_{joueur}/etat'
