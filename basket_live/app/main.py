"""Orchestrateur : calendrier, WebSocket, confirmation des fins de match, publication MQTT.

Budget de requêtes d'une journée type : 2 calendriers à 0 h 05, 1 à 12 h 05 et 17 h 05,
WebSocket hors quota REST ; 1 instantané live par fenêtre de match, 1 calendrier par vague de
fins de match. En cas de données manquantes, un instantané de secours toutes les 5 min
au plus, partagé entre les matchs et soumis au quota de fond.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from datetime import date, datetime, time as heure, timedelta
from zoneinfo import ZoneInfo

import aiohttp

from . import VERSION, config
from .api import ESSENTIEL, FOND, Api
from .secours import resultat_correspondant
from .archives import Archives, liste, saison_compatible
from .classements import normaliser_classement
from .notifications import Notifications
from .suivis import Suivis
from .pronos import Pronos, ouvert, saison
from .modele import (CODE_TERMINE, CODES_EN_COURS, Criteres, Match, actif, appliquer, categorie,
                     construire_match, date_locale, entier, finaliser, maj_statique, normaliser, vue)

log = logging.getLogger("basket_live")

# (heure locale, avec le lendemain)
CRENEAUX = [(heure(0, 5), True), (heure(12, 5), False), (heure(17, 5), False)]
SILENCE_WS = 75          # s sans aucun message (pong compris) avant de considérer la connexion morte
PING_WS = 30
INSTANTANE_MIN = 300     # s entre deux instantanés /api/live automatiques
SILENCE_MATCH = 300      # s sans changement du match avant de vérifier /api/live
SECOURS_MIN = 120        # s entre deux interrogations /api/live quand le WebSocket est indisponible
REESSAI_FIN = 180        # s entre deux tentatives de confirmation d'une fin de match
ESSAIS_FIN_MAX = 3       # au-delà, la fin est validée sur les seules données du WebSocket
DONNEES_RECENTES = 900   # s : en deçà, le calendrier ne contredit pas le live
PERIODE_PLANIF = 30
VERIF_SECOURS_MIN = 600  # s entre deux calendriers V1 pour confirmer les fins
SILENCE_SECOURS = 600    # s sans changement de score/statut avant de vérifier la fin en V1
AGE_VERIF_SECOURS = 90 * 60  # début des vérifications indépendantes après 90 min
ATTENTE_INACTIF = 20     # s entre deux vérifications du besoin de WebSocket


class App:
    def __init__(self, cfg: config.Config, api: Api, bus=None, horloge=time.time):
        self.cfg = cfg
        self.api = api
        self.horloge = horloge
        self.tz = ZoneInfo(cfg.fuseau)
        self.criteres = Criteres(cfg.equipe_nanterre, set(cfg.tournois_elite), set(cfg.tournois_europe),
                                 cfg.pays_europe)
        if bus is None:
            from .bus import Bus
            bus = Bus(cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_user, cfg.mqtt_password, self.sur_commande,
                      joueurs=cfg.joueurs)
        self.bus = bus
        self.matchs: dict[int, Match] = {}
        self.resultats: list[Match] = []
        self.dernier_calendrier: dict[str, float] = {}
        self.classements: dict = {}
        self.demande_classements = False
        self.dernier_instantane = 0.0
        self.verrou_instantane = asyncio.Lock()
        self.dernier_secours: dict[str, float] = {}
        self.ws_connecte = False
        self.prochain_calendrier_lointain = self.horloge() + 60
        self.demande_rafraichir = False
        self.dernier_rafraichir_manuel = 0.0
        self.creneaux_faits: set[str] = set()
        self.sale = True
        self.etat_modifie = False
        self.fichier_etat = cfg.dossier_donnees / "etat.json"
        self.pronos = Pronos(cfg.joueurs, set(cfg.tournois_elite))
        self.suivis = Suivis(cfg.joueurs)
        self.notifications = Notifications(cfg.joueurs)
        self.demarrage_ts = self.horloge()
        self.archives = Archives(cfg.dossier_donnees, self.tz, self.criteres, self.demarrage_ts)
        self.api.sur_compteur = self.sauver_etat

    # --- utilitaires ---------------------------------------------------------------------

    def aujourdhui(self) -> date:
        return datetime.fromtimestamp(self.horloge(), self.tz).date()

    def marquer(self) -> None:
        self.sale = True
        self.etat_modifie = True
        maintenant = self.horloge()
        for m in self.matchs.values():
            empreinte = [m.code, m.score_dom, m.score_ext]
            if m.progression_etat != empreinte:
                m.progression_ts = (maintenant if m.progression_etat is not None
                                    else min(maintenant, m.maj_ts or m.debut_ts))
                m.progression_etat = empreinte

    def ws_utile(self) -> bool:
        maintenant = self.horloge()
        return any(actif(m, maintenant) for m in self.matchs.values())

    def sur_commande(self, topic: str, texte: str) -> None:
        from .bus import COMMANDE, NOTIFICATION_ACK
        if topic == NOTIFICATION_ACK:
            try:
                ack = json.loads(texte)
            except (TypeError, ValueError):
                return
            if isinstance(ack, dict) and self.notifications.acquitter(ack.get("cle"), self.horloge()):
                log.info("Notification acquittée : %s", ack["cle"])
                self.marquer()
                self.sauver_etat()
            return
        if topic == COMMANDE:
            if texte.strip() == "rafraichir":
                self.demande_rafraichir = True
            elif texte.strip() == "rafraichir_classements":
                self.demande_classements = True
            elif texte.strip() == "tester_archive_nanterre":
                self.archives.demande_test = True
                log.info("Test archive Nanterre demandé par MQTT")
            return
        morceaux = topic.split("/")
        if len(morceaux) == 5 and morceaux[:2] == ["basket_live", "suivi"] and morceaux[4] == "set":
            m = self.matchs.get(entier(morceaux[3]))
            joueur, valeur = morceaux[2], texte.strip()
            if m is not None and self.suivis.choisir(m, joueur, valeur):
                self.marquer()
                self.sauver_etat()  # le choix est durable avant l'accusé de réception MQTT
                self.emettre_suivi("suivi_actif" if valeur == "ON" else "suivi_arrete", joueur, m)
            else:
                log.info("Suivi inchangé ou refusé (%s) : joueur, match ou valeur non admissible", topic)
                self.sale = True
            return
        # basket_live/prono/<joueur>/<id>/set
        if len(morceaux) == 5 and morceaux[1] == "prono" and morceaux[4] == "set":
            m = self.matchs.get(entier(morceaux[3]))
            if m is not None and self.pronos.choisir(m, morceaux[2], texte.strip(), self.horloge()):
                log.info("Pronostic de %s sur %s - %s : %s", morceaux[2], m.domicile, m.exterieur, texte.strip())
                self.marquer()
                self.actualiser_notifications()  # retirer immédiatement un rappel devenu inutile
                if self.etat_modifie:
                    self.sauver_etat()  # ne pas perdre un pronostic avant un redémarrage
            else:
                log.info("Pronostic refusé (%s, %s) : match inconnu ou déjà commencé", topic, texte)
                self.sale = True                            # republie l'état réel du menu

    # --- persistance ---------------------------------------------------------------------

    def charger_etat(self) -> None:
        try:
            etat = json.loads(self.fichier_etat.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            log.warning("État illisible, démarrage à vide : %s", e)
            return
        self.matchs = {m.id: m for m in (Match.depuis_dict(d) for d in etat.get("matchs", []))}
        self.resultats = [Match.depuis_dict(d) for d in etat.get("resultats", [])]
        self.dernier_calendrier = etat.get("dernier_calendrier", {})
        self.classements = etat.get("classements", {})
        self.prochain_calendrier_lointain = max(self.prochain_calendrier_lointain,
                                                etat.get("prochain_calendrier_lointain", 0))
        self.pronos.charger(etat.get("pronos", {}))
        self.suivis.charger(etat.get("suivis", {}))
        self.notifications.charger(etat.get("notifications", {}))
        for m in self.resultats:
            self.archives.ajouter(m, historique=True, maintenant=self.horloge())
        api = etat.get("api", {})
        self.api.restaurer(api.get("jour", ""), api.get("compteur", 0),
                           api.get("compteur_secours", 0), api.get("compteur_instantanes", 0))
        log.info("État restauré : %s matchs suivis, %s résultats", len(self.matchs), len(self.resultats))

    def sauver_etat(self) -> None:
        from dataclasses import asdict
        etat = {
            "version": 1,
            "matchs": [asdict(m) for m in self.matchs.values()],
            "resultats": [asdict(m) for m in self.resultats],
            "dernier_calendrier": self.dernier_calendrier,
            "classements": self.classements,
            "prochain_calendrier_lointain": self.prochain_calendrier_lointain,
            "pronos": self.pronos.vers_dict(),
            "suivis": self.suivis.vers_dict(),
            "notifications": self.notifications.vers_dict(),
            "api": {"jour": self.api.jour, "compteur": self.api.compteur,
                    "compteur_secours": self.api.compteur_secours,
                    "compteur_instantanes": self.api.compteur_instantanes},
        }
        tmp = self.fichier_etat.with_suffix(".tmp")
        tmp.write_text(json.dumps(etat, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.fichier_etat)
        self.etat_modifie = False

    def elaguer(self) -> None:
        maintenant = self.horloge()
        jour = self.aujourdhui()
        avant = len(self.matchs)
        self.matchs = {i: m for i, m in self.matchs.items()
                       if date_locale(m.debut_ts, self.tz) >= jour or actif(m, maintenant)}
        limite = maintenant - self.cfg.historique_jours * 86400
        self.resultats = [m for m in self.resultats if (m.termine_ts or 0) >= limite]
        self.pronos.nettoyer(set(self.matchs))
        self.suivis.nettoyer({i for i, m in self.matchs.items() if not m.termine})
        garder = {(jour + timedelta(days=i)).isoformat() for i in range(7)}
        self.dernier_calendrier = {j: t for j, t in self.dernier_calendrier.items() if j in garder}
        if len(self.matchs) != avant:
            log.info("Élagage : %s matchs retirés", avant - len(self.matchs))
        self.marquer()

    # --- émission ------------------------------------------------------------------------

    def emettre(self, type_: str, m: Match) -> None:
        maintenant = self.horloge()
        v = vue(m, self.tz, maintenant)
        charge = {"type": type_, "match": v, **self.suivis.destinataires(m.id), "ts": datetime.fromtimestamp(maintenant, self.tz).isoformat()}
        self.bus.emettre(json.dumps(charge, ensure_ascii=False))
        if type_ != "fin":
            m.dernier_push_ts = maintenant
            m.push_en_attente = False
        log.info("%s · %s · %s", type_, v["titre"], v["resume"])

    def emettre_suivi(self, type_: str, joueur: str, m: Match) -> None:
        maintenant = self.horloge()
        self.bus.emettre(json.dumps({"type": type_, "personne": joueur,
                                    "match": vue(m, self.tz, maintenant),
                                    **self.suivis.destinataires(m.id),
                                    "ts": datetime.fromtimestamp(maintenant, self.tz).isoformat()},
                                   ensure_ascii=False))
        # Un choix personnel ne doit pas effacer une mise à jour de score destinée aux autres.
        log.info("%s · %s · %s - %s", type_, joueur, m.domicile, m.exterieur)

    def cadencer(self) -> None:
        """Transforme les changements de score en événements « maj », au plus un par intervalle et par match."""
        maintenant = self.horloge()
        for m in self.matchs.values():
            if m.push_en_attente and not m.termine and maintenant - m.dernier_push_ts >= self.cfg.intervalle_push:
                self.emettre("maj", m)

    def finaliser(self, m: Match) -> None:
        finaliser(m, self.horloge())
        e = self.pronos.resultat(m, self.tz)
        if e:
            log.info("Pronostics de %s - %s : %s", m.domicile, m.exterieur, e["points"])
        self.resultats = [r for r in self.resultats if r.id != m.id]
        self.resultats.append(m)
        self.archives.ajouter(m, historique=False, maintenant=self.horloge())
        self.actualiser_notifications()  # échéance sauvegardée avant l'émission non retenue de fin
        self.emettre("fin", m)
        self.suivis.retirer(m.id)
        self.marquer()

    def actualiser_notifications(self) -> None:
        if self.notifications.actualiser(list(self.matchs.values()), self.resultats, self.pronos, self.horloge()):
            self.marquer()
            self.sauver_etat()

    def import_archives_autorise(self) -> bool:
        jour = self.aujourdhui()
        debut_jour = datetime.combine(jour, heure(0), self.tz).timestamp()
        if self.dernier_calendrier.get(jour.isoformat(), 0) < debut_jour:
            return False  # ne pas supposer une journée libre avant un calendrier du jour réussi
        return not any(date_locale(m.debut_ts, self.tz) == jour and m.code not in (60, 70)
                       for m in list(self.matchs.values()) + list(self.archives.resultats.values()))

    def publier(self) -> None:
        self.archives.changer_saison(self.horloge())
        for m in self.resultats:
            self.archives.ajouter(m, historique=(m.termine_ts or 0) < self.demarrage_ts,
                                  maintenant=self.horloge())
        self.actualiser_notifications()
        maintenant = self.horloge()
        jour = self.aujourdhui()
        jours = {jour + timedelta(days=i) for i in range(7)}
        a_venir = sorted((m for m in self.matchs.values()
                          if not m.termine and m.code not in CODES_EN_COURS and m.code != CODE_TERMINE
                          and date_locale(m.debut_ts, self.tz) in jours), key=lambda m: m.debut_ts)
        lives = sorted((m for m in self.matchs.values()
                        if not m.termine and (m.code in CODES_EN_COURS or m.code == CODE_TERMINE)),
                       key=lambda m: m.debut_ts)
        resultats = sorted(self.resultats, key=lambda m: m.termine_ts or 0, reverse=True)
        pronostics = self.pronos.resultats_par_match()

        from .bus import topic_attributs, topic_etat
        # Pour les capteurs, le chrono est celui de la dernière donnée reçue (pas d'extrapolation) :
        # sinon les attributs changeraient à chaque seconde et rempliraient le recorder.
        for objet, liste in (("matchs_a_venir", a_venir), ("lives_en_cours", lives), ("resultats", resultats)):
            self.bus.poser(topic_etat(objet), str(len(liste)))
            vues = [{**vue(m, self.tz, maintenant, extrapoler=False),
                     **({"pronostics": pronostics.get(m.id, {})} if m.termine else {})} for m in liste]
            self.bus.poser(topic_attributs(objet), json.dumps({"matchs": vues}, ensure_ascii=False))
        self.bus.poser(topic_etat("requetes_du_jour"), str(self.api.compteur))
        self.bus.poser(topic_etat("websocket"), "ON" if self.ws_connecte else "OFF")
        self.publier_pronos(maintenant)
        saison_courante = saison(maintenant, self.tz)
        tableaux = self.classements.get("tableaux", {}) if self.classements.get("saison") == saison_courante else {}
        self.bus.poser(topic_etat("classements_competitions"),
                       str(sum(bool(t.get("equipes")) for t in tableaux.values())))
        self.bus.poser(topic_attributs("classements_competitions"), json.dumps({
            "saison": saison_courante, "tableaux": tableaux,
        }, ensure_ascii=False))

        if self.suivis.nettoyer({i for i, m in self.matchs.items() if not m.termine}):
            self.etat_modifie = True
        for joueur, choix in self.suivis.vers_dict().items():
            objet = f"suivis_{joueur}"
            self.bus.poser(topic_etat(objet), str(sum(choix.values())))
            self.bus.poser(topic_attributs(objet), json.dumps({"joueur": joueur, "choix": choix},
                                                             ensure_ascii=False))
        echeances = self.notifications.attributs()
        self.bus.poser(topic_etat("notifications"), str(len(echeances["echeances"])))
        self.bus.poser(topic_attributs("notifications"), json.dumps(echeances, ensure_ascii=False))
        for topic, payload in self.archives.messages(maintenant, self.import_archives_autorise(), self.api, pronostics):
            self.bus.poser(topic, payload)
        if self.dernier_calendrier:
            dernier = max(self.dernier_calendrier.values())
            self.bus.poser(topic_etat("dernier_calendrier"), datetime.fromtimestamp(dernier, self.tz).isoformat())
        self.sale = False

    def publier_pronos(self, maintenant: float) -> None:
        from .bus import DISPO, topic_attributs, topic_etat
        for topic, payload in self.pronos.messages(sorted(self.matchs.values(), key=lambda m: m.debut_ts),
                                                   self.tz, maintenant, DISPO):
            self.bus.poser(topic, payload)
        courante = saison(maintenant, self.tz)
        # Matchs commencés et pas encore finis : les deux pronostics deviennent visibles
        en_cours = [self.pronos.entree(m, self.tz)
                    for m in sorted(self.matchs.values(), key=lambda m: m.debut_ts, reverse=True)
                    if m.id in self.pronos.choix and not m.termine and not ouvert(m, maintenant)]
        passes = [h for h in reversed(self.pronos.historique) if h["saison"] == courante]
        liste = (en_cours + passes)[:50]
        self.bus.poser(topic_etat("pronostics"), str(len(passes)))
        self.bus.poser(topic_attributs("pronostics"), json.dumps({"saison": courante, "matchs": liste}, ensure_ascii=False))
        classement = self.pronos.classement(courante)
        tete = classement[0] if classement else None
        egalite = len(classement) > 1 and classement[0]["points"] == classement[1]["points"]
        self.bus.poser(topic_etat("classement"), "Égalité" if egalite or not tete else tete["nom"])
        self.bus.poser(topic_attributs("classement"), json.dumps({"saison": courante, "joueurs": classement},
                                                                 ensure_ascii=False))

    # --- calendrier ----------------------------------------------------------------------

    async def rafraichir(self, jour: date, priorite: str = FOND) -> bool:
        evenements = await self.api.calendrier(jour.isoformat(), priorite)
        if evenements is None:
            return False
        self.dernier_calendrier[jour.isoformat()] = self.horloge()
        self.fusionner(evenements, jour)
        return True

    def fusionner(self, evenements: list[dict], jour: date) -> None:
        maintenant = self.horloge()
        retenus = set()
        for ev in evenements:
            if not isinstance(ev, dict) or "id" not in ev or not ev.get("startTimestamp"):
                continue
            cat = categorie(ev, self.criteres)
            if cat is None or date_locale(ev["startTimestamp"], self.tz) != jour:
                continue
            eid = int(ev["id"])
            retenus.add(eid)
            plat = normaliser(ev)
            code_cal = entier(plat.get("status.code"))
            m = self.matchs.get(eid)

            if m is None:
                m = construire_match(ev, cat)
                self.matchs[eid] = m
                appliquer(m, plat, maintenant)          # état initial, sans événement
                m.push_en_attente = False
                if code_cal == CODE_TERMINE:
                    finaliser(m, maintenant)
                    m.tardif = True                     # jamais suivi en direct : pas de notification attendue
                    self.resultats = [r for r in self.resultats if r.id != eid] + [m]
                    self.bus.emettre(json.dumps({"type": "fin", "match": vue(m, self.tz, maintenant),
                                                 "ts": datetime.fromtimestamp(maintenant, self.tz).isoformat()},
                                                ensure_ascii=False))
                continue

            if m.termine:
                continue
            maj_statique(m, ev, cat)
            recent = m.maj_ts is not None and maintenant - m.maj_ts < DONNEES_RECENTES
            if code_cal == CODE_TERMINE:
                pret = m.fin_provisoire_ts is not None and maintenant - m.fin_provisoire_ts >= self.cfg.delai_fin
                if pret or not recent:
                    appliquer(m, plat, maintenant, scores_seulement=True)
                    self.finaliser(m)
            elif not recent and m.code != CODE_TERMINE:
                # Le calendrier, souvent en retard sur le live, ne rouvre jamais une fin provisoire
                for e in appliquer(m, plat, maintenant):
                    self.emettre(e, m)

        # Match pas encore commencé et disparu du calendrier de ce jour : reporté à une autre date
        for eid in [i for i, m in self.matchs.items()
                    if i not in retenus and not m.termine and m.code == 0
                    and date_locale(m.debut_ts, self.tz) == jour]:
            if evenements:                              # réponse vide = incident côté API, on ne retire rien
                log.info("Match %s absent du calendrier du %s, retiré", eid, jour)
                del self.matchs[eid]
        log.info("Calendrier du %s : %s matchs suivis", jour, len(retenus))
        self.marquer()

    async def verifier_fins(self) -> None:
        maintenant = self.horloge()
        prets = [m for m in self.matchs.values()
                 if not m.termine and m.code == CODE_TERMINE and m.fin_provisoire_ts is not None
                 and maintenant - m.fin_provisoire_ts >= self.cfg.delai_fin and maintenant >= m.prochaine_verif_ts]
        if not prets:
            return
        # Un seul calendrier confirme toutes les fins d'une même soirée, statut compris
        for jour in sorted({date_locale(m.debut_ts, self.tz) for m in prets}):
            await self.rafraichir(jour, ESSENTIEL)
        for m in prets:
            if m.termine:
                continue
            m.essais_fin += 1
            m.prochaine_verif_ts = maintenant + REESSAI_FIN
            if m.essais_fin >= ESSAIS_FIN_MAX:
                log.warning("Fin de %s non confirmée par le calendrier, validée sur les données live", m.id)
                self.finaliser(m)

    async def verifier_secours(self) -> None:
        """Confirme les fins via V1 même si le WebSocket et les calendriers V2 restent figés.

        On ne termine jamais un match sur son âge ou sur son absence d'une liste.
        Deux résultats V1 identiques, séparés d'au moins delai_fin, sont requis.
        """
        maintenant = self.horloge()
        candidats = [m for m in self.matchs.values()
                     if not m.termine and maintenant >= m.debut_ts + AGE_VERIF_SECOURS
                     and (m.fin_secours_ts is not None
                          or maintenant - (m.progression_ts or m.maj_ts or m.debut_ts) >= SILENCE_SECOURS)]
        jours = {datetime.fromtimestamp(m.debut_ts, ZoneInfo("UTC")).date().isoformat()
                 for m in candidats}
        for jour in sorted(jours):
            if maintenant - self.dernier_secours.get(jour, 0) < VERIF_SECOURS_MIN:
                continue
            # Une première recherche reste en fond. Seule une preuve de fin V1 déjà
            # obtenue justifie de prendre dans la réserve pour sa confirmation.
            confirmation = any(m.fin_secours_ts is not None
                               and datetime.fromtimestamp(m.debut_ts, ZoneInfo("UTC")).date().isoformat() == jour
                               for m in candidats)
            priorite = ESSENTIEL if confirmation else FOND
            if not self.api.disponible(priorite):
                continue
            self.dernier_secours[jour] = maintenant
            evenements = await self.api.calendrier_secours(jour, priorite)
            if evenements is None:
                continue  # une panne ne constitue jamais une confirmation
            for m in candidats:
                if m.termine or datetime.fromtimestamp(m.debut_ts, ZoneInfo("UTC")).date().isoformat() != jour:
                    continue
                resultat = resultat_correspondant(m, evenements)
                if resultat is None:
                    # Match absent, ambigu, encore en cours ou sans score final exploitable.
                    if m.fin_secours_ts is not None:
                        m.fin_secours_ts = None
                        m.fin_secours_resultat = None
                        self.marquer()
                    continue
                if m.fin_secours_resultat != list(resultat) or m.fin_secours_ts is None:
                    m.fin_secours_resultat = list(resultat)
                    m.fin_secours_ts = maintenant
                    log.info("Fin V1 à confirmer pour %s : %s - %s", m.id, resultat[1], resultat[2])
                    self.marquer()
                    continue
                if maintenant - m.fin_secours_ts < self.cfg.delai_fin:
                    continue
                _, dom, ext = resultat
                # Les quarts V2 peuvent être incomplets ; ne pas présenter leurs totaux comme définitifs.
                if sum(v or 0 for v in m.periodes_dom) != dom:
                    m.periodes_dom = [None] * 4
                if sum(v or 0 for v in m.periodes_ext) != ext:
                    m.periodes_ext = [None] * 4
                appliquer(m, {"homeScore.current": dom, "awayScore.current": ext}, maintenant,
                          scores_seulement=True)
                log.warning("Fin confirmée par V1 pour %s : %s - %s (identifiant V2 conservé)", m.id, dom, ext)
                self.finaliser(m)

    # --- live ----------------------------------------------------------------------------

    def appliquer_live(self, evenements: list[dict]) -> None:
        maintenant = self.horloge()
        presents = set()
        for ev in evenements:
            if not isinstance(ev, dict):
                continue
            m = self.matchs.get(entier(ev.get("id")))
            if m is None or m.termine:
                continue
            presents.add(m.id)
            for e in appliquer(m, normaliser(ev), maintenant):
                self.emettre(e, m)
        # Sans WebSocket (mode secours), un match qu'on croyait en cours et absent du live est très
        # probablement terminé. WebSocket connecté, ses deltas de statut font foi : on ne devine rien.
        for m in self.matchs.values():
            if not self.ws_connecte and not m.termine and m.code in CODES_EN_COURS and m.id not in presents:
                for e in appliquer(m, {"status.code": CODE_TERMINE}, maintenant):
                    self.emettre(e, m)
        self.marquer()

    async def instantane(self, priorite: str = FOND, *, automatique: bool = False) -> None:
        # Une reconnexion et l'ordonnanceur peuvent demander le même rattrapage.
        if self.verrou_instantane.locked():
            return
        async with self.verrou_instantane:
            self.dernier_instantane = self.horloge()
            evenements = (await self.api.live(priorite, automatique=True) if automatique
                          else await self.api.live(priorite))
            if evenements is not None:
                log.info("Instantané live : %s matchs reçus", len(evenements))
                self.appliquer_live(evenements)

    async def verifier_live(self) -> None:
        maintenant = self.horloge()
        if maintenant - self.dernier_instantane < INSTANTANE_MIN:
            return
        muets = [m for m in self.matchs.values()
                 if actif(m, maintenant) and m.debut_ts <= maintenant
                 and m.code != CODE_TERMINE
                 and (m.code == 0 or maintenant - (m.maj_ts or 0) >= SILENCE_MATCH)]
        if muets and self.api.disponible(FOND):
            log.warning("Rattrapage live : matchs sans données récentes %s (WebSocket %s)",
                        [m.id for m in muets], "connecté" if self.ws_connecte else "déconnecté")
            await self.instantane(automatique=True)

    def traiter_ws(self, msg: dict) -> None:
        type_ = msg.get("type")
        if type_ in ("update", "snapshot"):
            data = msg.get("data")
            if isinstance(data, dict) and isinstance(data.get("events"), list):
                elements = data["events"]
            elif isinstance(data, list):
                elements = data
            else:
                elements = [data]
            maintenant = self.horloge()
            for d in elements:
                if not isinstance(d, dict):
                    continue
                m = self.matchs.get(entier(d.get("eventId") or d.get("id")))
                if m is None or m.termine:
                    continue
                for e in appliquer(m, normaliser(d), maintenant):
                    self.emettre(e, m)
                self.marquer()
        elif type_ == "subscribed":
            log.info("Abonné au canal %s (%s)", msg.get("channel"), msg.get("mode"))
        elif type_ == "error":
            log.warning("Erreur WebSocket : %s", msg)

    def ws_etat(self, connecte: bool) -> None:
        if connecte != self.ws_connecte:
            self.ws_connecte = connecte
            self.sale = True

    async def _pinger(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while True:
            await asyncio.sleep(PING_WS)
            await ws.send_json({"action": "ping", "channel": "live-scores"})

    async def boucle_ws(self) -> None:
        attente = 5
        session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None, sock_connect=20))
        try:
            while True:
                if not self.ws_utile():
                    await asyncio.sleep(ATTENTE_INACTIF)
                    attente = 5
                    continue
                connexion = self.horloge()
                try:
                    async with session.ws_connect(self.api.url_ws(), heartbeat=None) as ws:
                        await ws.send_json({"action": "subscribe", "channel": "live-scores"})
                        self.ws_etat(True)
                        log.info("WebSocket connecté")
                        if self.horloge() - self.dernier_instantane >= INSTANTANE_MIN:
                            asyncio.create_task(self.instantane(automatique=True))
                        pinger = asyncio.create_task(self._pinger(ws))
                        try:
                            while True:
                                msg = await ws.receive(timeout=SILENCE_WS)
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    try:
                                        self.traiter_ws(json.loads(msg.data))
                                    except ValueError:
                                        log.debug("Message non JSON ignoré")
                                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED,
                                                  aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.ERROR):
                                    log.warning("WebSocket fermé par le serveur (%s)", msg.type)
                                    break
                                if not self.ws_utile():
                                    log.info("Plus de match actif : déconnexion du WebSocket")
                                    break
                        finally:
                            pinger.cancel()
                except TimeoutError:
                    log.warning("WebSocket silencieux depuis %s s : reconnexion", SILENCE_WS)
                except aiohttp.ClientError as e:
                    log.warning("WebSocket indisponible : %s", e)
                finally:
                    self.ws_etat(False)
                if self.horloge() - connexion > 120:
                    attente = 5                     # connexion qui a tenu : reprise rapide
                if self.ws_utile() and self.horloge() - self.dernier_instantane >= SECOURS_MIN \
                        and self.api.disponible(FOND):
                    await self.instantane(automatique=True)
                await asyncio.sleep(attente)
                attente = min(attente * 2, 300)
        finally:
            await session.close()

    # --- ordonnancement ------------------------------------------------------------------

    async def demarrage(self) -> None:
        jour = self.aujourdhui()
        maintenant_local = datetime.fromtimestamp(self.horloge(), self.tz)
        for h, _ in CRENEAUX:
            if maintenant_local.time() >= h:
                self.creneaux_faits.add(f"{jour}-{h}")
        for j in (jour, jour + timedelta(days=1)):
            if self.horloge() - self.dernier_calendrier.get(j.isoformat(), 0) > 1800:
                await self.rafraichir(j)

    async def rafraichir_horizon(self) -> None:
        """J+2 à J+6 une fois par jour local, y compris après redémarrage."""
        maintenant = self.horloge()
        if maintenant < self.prochain_calendrier_lointain or not self.api.disponible(FOND):
            return
        jour = self.aujourdhui()
        for i in range(2, 7):
            cible = jour + timedelta(days=i)
            dernier = self.dernier_calendrier.get(cible.isoformat())
            if dernier is not None and date_locale(dernier, self.tz) == jour:
                continue
            succes = await self.rafraichir(cible)
            self.prochain_calendrier_lointain = maintenant + (60 if succes else 3600)
            self.sauver_etat()  # calendrier réussi et attente après échec survivent au redémarrage
            return  # un appel maximum, sans rafale au démarrage

    async def planifier(self) -> None:
        maintenant = self.horloge()
        local = datetime.fromtimestamp(maintenant, self.tz)
        jour = local.date()
        for h, lendemain in CRENEAUX:
            cle = f"{jour}-{h}"
            if local.time() >= h and cle not in self.creneaux_faits:
                self.creneaux_faits.add(cle)
                if h == CRENEAUX[0][0]:
                    self.elaguer()
                await self.rafraichir(jour)
                if lendemain:
                    await self.rafraichir(jour + timedelta(days=1))
        self.creneaux_faits = {c for c in self.creneaux_faits if c.startswith(jour.isoformat())}

        if self.demande_rafraichir:
            self.demande_rafraichir = False
            if maintenant - self.dernier_rafraichir_manuel >= 300:
                self.dernier_rafraichir_manuel = maintenant
                await self.rafraichir(jour)
                await self.rafraichir(jour + timedelta(days=1))
                if self.ws_utile():
                    log.info("Rafraîchissement manuel : récupération des scores live")
                    await self.instantane()
            else:
                log.info("Rafraîchissement manuel ignoré (moins de 5 min depuis le précédent)")

        # Matchs sans nouvelles : le calendrier tranche, au plus une fois par heure et par jour
        douteux = set()
        for m in self.matchs.values():
            if m.termine:
                continue
            jamais_vu = m.code == 0 and m.debut_ts + 3 * 3600 < maintenant < m.debut_ts + 8 * 3600
            muet = (m.code in CODES_EN_COURS and maintenant > m.debut_ts + 3 * 3600
                    and (m.maj_ts or 0) < maintenant - 2700)
            if jamais_vu or muet:
                douteux.add(date_locale(m.debut_ts, self.tz))
        for j in sorted(douteux):
            if maintenant - self.dernier_calendrier.get(j.isoformat(), 0) > 3600:
                await self.rafraichir(j)

        await self.verifier_live()
        await self.verifier_secours()
        await self.verifier_fins()
        await self.rafraichir_horizon()
        if await self.archives.traiter(self.api, import_autorise=self.import_archives_autorise(),
                                        maintenant=self.horloge()):
            self.marquer()

    async def rafraichir_classements(self) -> None:
        """Une consultation quotidienne par tournoi, avec une relance manuelle par jour."""
        demande = self.demande_classements
        self.demande_classements = False
        if not self.api.disponible(FOND) or self.api.compteur >= self.archives.plafond_import(self.api):
            if demande:
                log.warning("Relance des classements refusée : marge de quota préservée")
            return
        maintenant = self.horloge()
        courante = saison(maintenant, self.tz)
        if self.classements.get("saison") != courante:
            self.classements = {"saison": courante, "tableaux": {}}
        tableaux = self.classements["tableaux"]
        jour = self.aujourdhui().isoformat()
        if demande:
            if self.classements.get("jour_relance_manuelle") == jour:
                log.info("Relance des classements déjà demandée aujourd’hui")
            else:
                self.classements["jour_relance_manuelle"] = jour
                for tableau in tableaux.values():
                    tableau.pop("jour_tentative", None)
                self.sauver_etat()
                log.info("Relance manuelle des classements Élite et BCL")
        for cle, tournoi in (("elite", 156), ("bcl", 9357)):
            tableau = tableaux.setdefault(cle, {})
            if tableau.get("jour_tentative") == jour:
                continue
            tableau["jour_tentative"] = jour
            # Le compteur REST sauvegarde l'état avant l'appel réseau.
            sid = tableau.get("saison_id")
            if not sid:
                rep = await self.api.saisons_tournoi(tournoi)
                saisons = liste(rep, "seasons") or []
                sid = next((entier(s.get("id")) for s in saisons
                            if isinstance(s, dict) and entier(s.get("id"))
                            and saison_compatible(s, int(courante[:4]))), None)
                if sid:
                    tableau["saison_id"] = sid
                    tableau.pop("jour_tentative")
            else:
                rep = await self.api.classement_tournoi(tournoi, sid)
                resultat = normaliser_classement(rep, self.cfg.equipe_nanterre, bcl=cle == "bcl")
                if resultat:
                    tableau.update(resultat, mis_a_jour=datetime.fromtimestamp(maintenant, self.tz).isoformat())
                    log.info("Classement %s : %s équipes", cle, len(resultat["equipes"]))
                else:
                    log.warning("Classement %s indisponible, dernier tableau conservé", cle)
            self.marquer()
            self.sauver_etat()
            return

    async def boucle_planif(self) -> None:
        await self.demarrage()
        while True:
            try:
                await self.planifier()
                await self.rafraichir_classements()
            except Exception:                           # une erreur ne doit pas arrêter l'ordonnanceur
                log.exception("Erreur dans l'ordonnanceur")
            await asyncio.sleep(PERIODE_PLANIF)

    async def boucle_tic(self) -> None:
        dernier_publier = dernier_sauver = 0.0
        while True:
            await asyncio.sleep(1)
            try:
                self.cadencer()
                maintenant = self.horloge()
                if self.sale or maintenant - dernier_publier >= 10:
                    self.publier()
                    dernier_publier = maintenant
                if self.etat_modifie and maintenant - dernier_sauver >= 15:
                    self.sauver_etat()
                    dernier_sauver = maintenant
            except Exception:
                log.exception("Erreur dans la boucle de publication")

    async def run(self, arret: asyncio.Event) -> None:
        await self.api.ouvrir()
        self.charger_etat()
        self.elaguer()
        taches = [asyncio.create_task(c) for c in (self.bus.run(), self.boucle_planif(),
                                                     self.boucle_ws(), self.boucle_tic())]
        try:
            await arret.wait()
        finally:
            for t in taches:
                t.cancel()
            await asyncio.gather(*taches, return_exceptions=True)
            self.sauver_etat()
            await self.api.fermer()


async def principal() -> None:
    cfg = config.charger()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    log.info("Basket Live %s", VERSION)
    if not cfg.api_key:
        log.error("Clé API absente : la renseigner dans la configuration de l'add-on")
        raise SystemExit(1)
    api = Api(cfg.api_key, cfg.api_base, cfg.ws_url, cfg.quota_jour, cfg.api_v1_base)
    app = App(cfg, api)
    arret = asyncio.Event()
    boucle = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        boucle.add_signal_handler(sig, arret.set)
    await app.run(arret)


if __name__ == "__main__":
    asyncio.run(principal())
