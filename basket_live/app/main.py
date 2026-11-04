"""Orchestrateur : calendrier, WebSocket, confirmation des fins de match, publication MQTT.

Budget de requêtes d'une journée type : 2 calendriers à 0 h 05, 1 à 12 h 05 et 17 h 05,
1 connexion WebSocket + 1 instantané live par fenêtre de match, 1 calendrier par vague de
fins de match. Loin des 100 de l'offre gratuite, même un soir chargé.
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
from .modele import (CODE_TERMINE, CODES_EN_COURS, Criteres, Match, actif, appliquer, categorie,
                     construire_match, date_locale, entier, finaliser, maj_statique, normaliser, vue)

log = logging.getLogger("basket_live")

# (heure locale, avec le lendemain)
CRENEAUX = [(heure(0, 5), True), (heure(12, 5), False), (heure(17, 5), False)]
SILENCE_WS = 75          # s sans aucun message (pong compris) avant de considérer la connexion morte
PING_WS = 30
INSTANTANE_MIN = 300     # s entre deux instantanés /api/live après (re)connexion
SECOURS_MIN = 120        # s entre deux interrogations /api/live quand le WebSocket est indisponible
REESSAI_FIN = 180        # s entre deux tentatives de confirmation d'une fin de match
ESSAIS_FIN_MAX = 3       # au-delà, la fin est validée sur les seules données du WebSocket
DONNEES_RECENTES = 900   # s : en deçà, le calendrier ne contredit pas le live
PERIODE_PLANIF = 30
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
            bus = Bus(cfg.mqtt_host, cfg.mqtt_port, cfg.mqtt_user, cfg.mqtt_password, self.sur_commande)
        self.bus = bus
        self.matchs: dict[int, Match] = {}
        self.resultats: list[Match] = []
        self.dernier_calendrier: dict[str, float] = {}
        self.dernier_instantane = 0.0
        self.ws_connecte = False
        self.demande_rafraichir = False
        self.dernier_rafraichir_manuel = 0.0
        self.creneaux_faits: set[str] = set()
        self.sale = True
        self.etat_modifie = False
        self.fichier_etat = cfg.dossier_donnees / "etat.json"

    # --- utilitaires ---------------------------------------------------------------------

    def aujourdhui(self) -> date:
        return datetime.fromtimestamp(self.horloge(), self.tz).date()

    def marquer(self) -> None:
        self.sale = True
        self.etat_modifie = True

    def ws_utile(self) -> bool:
        maintenant = self.horloge()
        return any(actif(m, maintenant) for m in self.matchs.values())

    def sur_commande(self, texte: str) -> None:
        if texte.strip() == "rafraichir":
            self.demande_rafraichir = True

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
        api = etat.get("api", {})
        self.api.restaurer(api.get("jour", ""), api.get("compteur", 0))
        log.info("État restauré : %s matchs suivis, %s résultats", len(self.matchs), len(self.resultats))

    def sauver_etat(self) -> None:
        from dataclasses import asdict
        etat = {
            "version": 1,
            "matchs": [asdict(m) for m in self.matchs.values()],
            "resultats": [asdict(m) for m in self.resultats],
            "dernier_calendrier": self.dernier_calendrier,
            "api": {"jour": self.api.jour, "compteur": self.api.compteur},
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
        garder = {jour.isoformat(), (jour + timedelta(days=1)).isoformat()}
        self.dernier_calendrier = {j: t for j, t in self.dernier_calendrier.items() if j in garder}
        if len(self.matchs) != avant:
            log.info("Élagage : %s matchs retirés", avant - len(self.matchs))
        self.marquer()

    # --- émission ------------------------------------------------------------------------

    def emettre(self, type_: str, m: Match) -> None:
        maintenant = self.horloge()
        v = vue(m, self.tz, maintenant)
        charge = {"type": type_, "match": v, "ts": datetime.fromtimestamp(maintenant, self.tz).isoformat()}
        self.bus.emettre(json.dumps(charge, ensure_ascii=False))
        if type_ != "fin":
            m.dernier_push_ts = maintenant
            m.push_en_attente = False
        log.info("%s · %s · %s", type_, v["titre"], v["resume"])

    def cadencer(self) -> None:
        """Transforme les changements de score en événements « maj », au plus un par intervalle et par match."""
        maintenant = self.horloge()
        for m in self.matchs.values():
            if m.push_en_attente and not m.termine and maintenant - m.dernier_push_ts >= self.cfg.intervalle_push:
                self.emettre("maj", m)

    def finaliser(self, m: Match) -> None:
        finaliser(m, self.horloge())
        self.resultats = [r for r in self.resultats if r.id != m.id]
        self.resultats.append(m)
        self.emettre("fin", m)
        self.marquer()

    def publier(self) -> None:
        maintenant = self.horloge()
        jour = self.aujourdhui()
        jours = {jour, jour + timedelta(days=1)}
        a_venir = sorted((m for m in self.matchs.values()
                          if not m.termine and m.code not in CODES_EN_COURS and m.code != CODE_TERMINE
                          and date_locale(m.debut_ts, self.tz) in jours), key=lambda m: m.debut_ts)
        lives = sorted((m for m in self.matchs.values()
                        if not m.termine and (m.code in CODES_EN_COURS or m.code == CODE_TERMINE)),
                       key=lambda m: m.debut_ts)
        resultats = sorted(self.resultats, key=lambda m: m.termine_ts or 0, reverse=True)

        from .bus import topic_attributs, topic_etat
        # Pour les capteurs, le chrono est celui de la dernière donnée reçue (pas d'extrapolation) :
        # sinon les attributs changeraient à chaque seconde et rempliraient le recorder.
        for objet, liste in (("matchs_a_venir", a_venir), ("lives_en_cours", lives), ("resultats", resultats)):
            self.bus.poser(topic_etat(objet), str(len(liste)))
            vues = [vue(m, self.tz, maintenant, extrapoler=False) for m in liste]
            self.bus.poser(topic_attributs(objet), json.dumps({"matchs": vues}, ensure_ascii=False))
        self.bus.poser(topic_etat("requetes_du_jour"), str(self.api.compteur))
        self.bus.poser(topic_etat("websocket"), "ON" if self.ws_connecte else "OFF")
        if self.dernier_calendrier:
            dernier = max(self.dernier_calendrier.values())
            self.bus.poser(topic_etat("dernier_calendrier"), datetime.fromtimestamp(dernier, self.tz).isoformat())
        self.sale = False

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

    async def instantane(self, priorite: str = FOND) -> None:
        self.dernier_instantane = self.horloge()
        evenements = await self.api.live(priorite)
        if evenements is not None:
            self.appliquer_live(evenements)

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
                if self.api.disponible(FOND):
                    self.api.compter()                  # une connexion compte pour une requête
                    connexion = self.horloge()
                    try:
                        async with session.ws_connect(self.api.url_ws(), heartbeat=None) as ws:
                            await ws.send_json({"action": "subscribe", "channel": "live-scores"})
                            self.ws_etat(True)
                            log.info("WebSocket connecté")
                            if self.horloge() - self.dernier_instantane >= INSTANTANE_MIN:
                                asyncio.create_task(self.instantane())
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
                else:
                    log.warning("Quota de fond atteint : pas de connexion WebSocket")
                if self.ws_utile() and self.horloge() - self.dernier_instantane >= SECOURS_MIN \
                        and self.api.disponible(FOND):
                    await self.instantane()
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

        await self.verifier_fins()

    async def boucle_planif(self) -> None:
        await self.demarrage()
        while True:
            try:
                await self.planifier()
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
    api = Api(cfg.api_key, cfg.api_base, cfg.ws_url, cfg.quota_jour)
    app = App(cfg, api)
    arret = asyncio.Event()
    boucle = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        boucle.add_signal_handler(sig, arret.set)
    await app.run(arret)


if __name__ == "__main__":
    asyncio.run(principal())
