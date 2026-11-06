"""Archives de saison et collecte unique des deux ressources statistiques Nanterre."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import logging
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from .api import FOND
from .modele import (Match, appliquer, categorie, construire_match, entier, finaliser,
                     normaliser, vue)
from .pronos import saison

log = logging.getLogger('archives')
DELAI_STATISTIQUES = 15 * 60
INTERVALLE_COLLECTE = 60


def lire(path: Path, defaut):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return defaut
    except (ValueError, OSError) as exc:
        log.error('Archive illisible %s : %s', path.name, exc)
        raise  # ne jamais écraser silencieusement un cache abîmé


def ecrire(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.replace(path)


def liste(rep, cle: str):
    for _ in range(4):
        if isinstance(rep, list):
            return rep
        if not isinstance(rep, dict):
            return None
        if isinstance(rep.get(cle), list):
            return rep[cle]
        rep = rep.get('data')
    return None


def suite(rep) -> bool | None:
    if not isinstance(rep, dict):
        return None
    if isinstance(rep.get('hasNextPage'), bool):
        return rep['hasNextPage']
    return suite(rep.get('data'))


def saison_compatible(ev: dict, an: int) -> bool:
    texte = str(ev.get('year') or ev.get('name') or '')
    nombres = [int(v) for v in re.findall(r'\d{2,4}', texte)]
    nombres = [v + 2000 if v < 100 else v for v in nombres]
    return ((an, an + 1) == tuple(nombres[-2:]) if len(nombres) >= 2
            else len(nombres) == 1 and nombres[0] in (an, an + 1))


def preparer_evenement(ev: dict) -> dict:
    ev = dict(ev)
    for cote in ('home', 'away'):
        cle = cote + 'Team'
        if isinstance(ev.get(cle), str):
            pays = ev.get(cote + 'TeamCountry')
            ev[cle] = {'id': ev.get(cle + 'Id'), 'name': ev[cle],
                       'country': pays if isinstance(pays, dict) else {'alpha2': pays}}
    if isinstance(ev.get('tournament'), str):
        ev['tournament'] = {'uniqueTournament': {'id': ev.get('tournamentId'),
                                                'name': ev['tournament']}}
    if isinstance(ev.get('status'), str):
        ev['status'] = {'code': ev.get('statusCode'), 'description': ev['status']}
    return ev


class Archives:
    def __init__(self, dossier: Path, tz: ZoneInfo, criteres, maintenant: float):
        self.racine, self.tz, self.criteres = dossier / 'archives', tz, criteres
        self.saison = ''
        self.prochain = maintenant + INTERVALLE_COLLECTE
        self.changer_saison(maintenant)

    def changer_saison(self, maintenant: float) -> None:
        courante = saison(maintenant, self.tz)
        if courante == self.saison:
            return
        self.saison = courante
        self.an = int(courante[:4])
        self.debut = datetime(self.an, 7, 1, tzinfo=self.tz).timestamp()
        self.fin = datetime(self.an + 1, 7, 1, tzinfo=self.tz).timestamp()
        self.dossier = self.racine / courante
        self.index = self.dossier / 'index.json'
        self.resultats: dict[int, Match] = {}
        self.origines: dict[int, str] = {}
        self.details: dict[int, dict] = {}
        self.jobs = [{'type': 'equipe', 'id': self.criteres.equipe, 'page': 0, 'termine': False}]
        self.jobs += [{'type': 'saisons', 'id': tid, 'termine': False}
                      for tid in sorted(self.criteres.elite | self.criteres.europe)]
        self.erreur = ''
        self.demande_test = False
        self.test_match = None
        ancien = lire(self.index, {})
        if ancien:
            self.test_match = ancien.get('test_match')
            self.resultats = {int(k): Match.depuis_dict(v) for k, v in ancien.get('resultats', {}).items()}
            self.origines = {int(k): v for k, v in ancien.get('origines', {}).items()}
            self.jobs = ancien.get('jobs', self.jobs)
            self.erreur = ancien.get('erreur', '')
            # Une reprise relit les pages récentes, jusqu'au dernier point déjà importé.
            for job in self.jobs:
                if job.get('termine') and job['type'] != 'saisons':
                    job.update(termine=False, page=0, reprise=True)
        for m in self.resultats.values():
            if self.est_nanterre(m):
                self._charger_detail(m, historique=True, maintenant=maintenant)

    def sauvegarder(self) -> None:
        ecrire(self.index, {'saison': self.saison,
                            'resultats': {str(i): asdict(m) for i, m in self.resultats.items()},
                            'origines': {str(i): v for i, v in self.origines.items()}, 'jobs': self.jobs, 'erreur': self.erreur, 'test_match': self.test_match})

    def est_nanterre(self, m: Match) -> bool:
        return self.criteres.equipe in (m.domicile_id, m.exterieur_id)

    def _chemin_detail(self, identifiant: int) -> Path:
        return self.dossier / 'statistiques' / f'{identifiant}.json'

    def _charger_detail(self, m: Match, historique: bool, maintenant: float) -> None:
        if m.id in self.details:
            return
        d = lire(self._chemin_detail(m.id), None)
        if d is None:
            d = {'match_id': m.id, 'historique': historique,
                 'collecter_apres': maintenant if historique else (m.termine_ts or maintenant) + DELAI_STATISTIQUES,
                 'statistics': {'etat': 'en_attente'}, 'lineups': {'etat': 'en_attente'}}
        for ressource in ('statistics', 'lineups'):
            if d[ressource]['etat'] == 'reserve':
                d[ressource]['etat'] = 'interrompu'  # pas de nouvel appel après un crash incertain
        self.details[m.id] = d
        ecrire(self._chemin_detail(m.id), d)

    def ajouter(self, m: Match, *, historique: bool, maintenant: float, source: str = "suivi") -> bool:
        self.changer_saison(maintenant)
        if not m.termine or not self.debut <= m.debut_ts < self.fin:
            return False
        if source == 'import' and self.origines.get(m.id) == 'suivi':
            return False  # ne pas écraser un score final suivi/confirmé avec une vieille page V2
        identique = (m.id in self.resultats and asdict(self.resultats[m.id]) == asdict(m)
                     and self.origines.get(m.id) == source)
        self.resultats[m.id] = Match.depuis_dict(asdict(m))
        self.origines[m.id] = source
        if self.est_nanterre(m):
            self._charger_detail(m, historique, maintenant)
        if not identique:
            self.sauvegarder()
        return not identique

    def plafond_import(self, api) -> int:
        # Avec 100 : 15 de réserve essentielle + 20 de marge = arrêt de l'import à 65.
        return max(0, api.quota - api.reserve - max(5, api.quota // 5))

    async def preparer_test(self, api, maintenant: float) -> bool:
        self.demande_test = False
        if self.test_match is not None:
            log.info('Test archive Nanterre déjà en attente : %s', self.test_match)
            return True
        candidats = [m for m in self.resultats.values() if self.est_nanterre(m)]
        recent = max(candidats, key=lambda m: m.debut_ts) if candidats else None
        besoin = (sum(self.details[recent.id][r]['etat'] == 'en_attente' for r in ('statistics', 'lineups'))
                  if recent is not None else 3)
        if not api.disponible(FOND) or api.compteur + besoin > self.plafond_import(api):
            log.warning('Test archive Nanterre refusé : marge de quota préservée (%s/%s)', api.compteur, api.quota)
            return True
        if not candidats:
            # Une seule page, un seul match : jamais de pagination ou d'import global forcé.
            rep = await api.historique_equipe(self.criteres.equipe, 0)
            for e in liste(rep, 'events') or []:
                if not isinstance(e, dict):
                    continue
                ts, mid = entier(e.get('startTimestamp')), entier(e.get('id'))
                if ts is None or mid is None or mid <= 0 or not self.debut <= ts < maintenant:
                    continue
                ev = preparer_evenement(e)
                if entier(normaliser(ev).get('status.code')) != 100 or categorie(ev, self.criteres) != 'nanterre':
                    continue
                m = construire_match(ev, 'nanterre')
                appliquer(m, normaliser(ev), maintenant)
                finaliser(m, maintenant)
                candidats.append(m)
        if not candidats:
            log.warning('Test archive Nanterre : aucun match terminé de la saison trouvé sur la première page')
            return True
        m = max(candidats, key=lambda m: m.debut_ts)
        self.ajouter(m, historique=True, maintenant=maintenant, source=self.origines.get(m.id, 'import'))
        self.test_match = m.id
        self.sauvegarder()
        log.info('Test archive Nanterre sélectionné : %s · %s · consultation du cache ou collecte unique', m.id, f"{m.domicile} - {m.exterieur}")
        return True

    async def traiter(self, api, *, import_autorise: bool, maintenant: float) -> bool:
        self.changer_saison(maintenant)
        if maintenant < self.prochain or not api.disponible(FOND):
            return False
        self.prochain = maintenant + INTERVALLE_COLLECTE
        if self.demande_test:
            return await self.preparer_test(api, maintenant)
        if self.test_match is not None:
            if api.compteur < self.plafond_import(api):
                if await self._collecter(api, self.test_match, maintenant):
                    return True
                log.info('Test archive Nanterre terminé : %s · données locales conservées', self.test_match)
                self.test_match = None
                self.sauvegarder()
                return True
        # Les deux ressources d'un match suivi sont prioritaires. L'import ancien attend un jour libre.
        for mid, d in sorted(self.details.items(), reverse=True):
            if d['historique'] or maintenant < d['collecter_apres']:
                continue
            if await self._collecter(api, mid, maintenant):
                return True
        if not import_autorise or api.compteur >= self.plafond_import(api):
            return False
        for job in self.jobs:
            if not job.get('termine') and maintenant >= job.get('reessai', 0):
                await self._importer(api, job, maintenant)
                return True
        for mid, d in sorted(self.details.items(), reverse=True):
            if d['historique'] and maintenant >= d['collecter_apres']:
                if await self._collecter(api, mid, maintenant):
                    return True
        return False

    async def _collecter(self, api, mid: int, maintenant: float) -> bool:
        d = self.details[mid]
        for ressource in ('statistics', 'lineups'):
            if d[ressource]['etat'] != 'en_attente':
                continue
            d[ressource] = {'etat': 'reserve', 'tente_le': maintenant}
            ecrire(self._chemin_detail(mid), d)  # réservation durable AVANT l'appel : une fois par ressource
            rep = await api.details_match(mid, ressource)
            disponible = isinstance(rep, (dict, list)) and not (isinstance(rep, dict) and rep.get('success') is False)
            d[ressource] = {'etat': 'enregistre' if disponible else 'indisponible',
                            'tente_le': maintenant, 'reponse': rep}
            ecrire(self._chemin_detail(mid), d)
            log.info('Archive Nanterre %s : %s %s', mid, ressource, d[ressource]['etat'])
            return True
        return False

    async def _importer(self, api, job: dict, maintenant: float) -> None:
        if job['type'] == 'saisons':
            rep = await api.saisons_tournoi(job['id'])
            saisons = liste(rep, 'seasons')
            eligibles = [s for s in saisons or [] if isinstance(s, dict) and entier(s.get('id'))
                         and saison_compatible(s, self.an)]
            if not eligibles:
                self._erreur(job, maintenant, 'Saison courante non trouvée')
                return
            for s in eligibles:
                cle = (job['id'], int(s['id']))
                if not any(j['type'] == 'tournoi' and (j['id'], j['sid']) == cle for j in self.jobs):
                    self.jobs.append({'type': 'tournoi', 'id': job['id'], 'sid': int(s['id']),
                                      'page': 0, 'termine': False})
            job['termine'] = True
        else:
            rep = (await api.historique_equipe(job['id'], job['page']) if job['type'] == 'equipe'
                   else await api.historique_tournoi(job['id'], job['sid'], job['page']))
            events = liste(rep, 'events')
            if events is None:
                self._erreur(job, maintenant, 'Page de résultats indisponible')
                return
            signature = [e.get('id') for e in events if isinstance(e, dict)]
            if events and job['page'] and signature == job.get('signature'):
                self._erreur(job, maintenant, 'Pagination sans progression')
                return
            limite_reprise = job.get('frontiere', 0) if job.get('reprise') else 0
            dates = []
            for e in events:
                if not isinstance(e, dict):
                    continue
                ts = entier(e.get('startTimestamp'))
                if ts is not None and ts <= maintenant:
                    dates.append(ts)
                if ts is None or not self.debut <= ts <= maintenant:
                    continue
                ev = preparer_evenement(e)
                if entier(ev.get('id')) is None or entier(ev['id']) <= 0:
                    continue
                if entier(normaliser(ev).get('status.code')) != 100:
                    continue
                cat = categorie(ev, self.criteres)
                if cat is None:
                    continue
                m = construire_match(ev, cat)
                appliquer(m, normaliser(ev), maintenant)
                finaliser(m, maintenant)
                self.ajouter(m, historique=True, maintenant=maintenant, source="import")
            fini = (not events or suite(rep) is False or (dates and min(dates) < self.debut)
                    or (limite_reprise and dates and min(dates) <= limite_reprise))
            job['maximum'] = max(job.get('maximum', 0), max(dates, default=0))
            job['signature'] = signature
            if fini:
                job.update(termine=True, frontiere=job['maximum'], reprise=False)
            else:
                job['page'] += 1
        self.erreur = ''
        job.pop('reessai', None)
        job.pop('erreur', None)
        self.sauvegarder()
        log.info('Import saison %s : %s %s, %s résultats archivés', self.saison, job['type'], job['id'], len(self.resultats))

    def _erreur(self, job: dict, maintenant: float, message: str) -> None:
        self.erreur = message
        job['reessai'] = maintenant + 86400
        job['erreur'] = message
        self.sauvegarder()
        log.warning('Import saison %s, %s %s : %s ; prochain essai dans 24 h au plus tôt',
                    self.saison, job['type'], job['id'], message)

    def attributs(self, maintenant: float, import_autorise: bool, api) -> dict:
        termine = all(j.get('termine') for j in self.jobs)
        etat = ('termine' if termine else 'attente_jour_sans_match' if not import_autorise
                else 'marge_quota_preservee' if api.compteur >= self.plafond_import(api) else 'en_cours')
        return {'saison': self.saison, 'equipe_nanterre': self.criteres.equipe,
                'matchs': [vue(m, self.tz, maintenant, extrapoler=False)
                           for m in sorted(self.resultats.values(), key=lambda m: m.debut_ts, reverse=True)],
                'import': {'etat': etat, 'sources_terminees': sum(bool(j.get('termine')) for j in self.jobs),
                           'sources_total': len(self.jobs),
                           'erreur': next((j['erreur'] for j in self.jobs if not j.get('termine') and j.get('erreur')), '')}}

    def messages(self, maintenant: float, import_autorise: bool, api) -> list[tuple[str, str]]:
        from . import VERSION
        from .bus import APPAREIL, DISPO, topic_attributs, topic_etat
        attributs = self.attributs(maintenant, import_autorise, api)
        messages = [(topic_etat("resultats_saison"), str(len(attributs["matchs"]))),
                    (topic_attributs("resultats_saison"), json.dumps(attributs, ensure_ascii=False))]
        for mid, d in self.details.items():
            objet = f"statistiques_{mid}"
            conf = {"unique_id": f"basket_live_{objet}", "name": f"Statistiques {mid}",
                    "icon": "mdi:chart-box", "entity_category": "diagnostic", "device": APPAREIL,
                    "availability_topic": DISPO, "state_topic": topic_etat(objet),
                    "json_attributes_topic": topic_attributs(objet),
                    "origin": {"name": "basket-live", "sw_version": VERSION}}
            messages += [(f"homeassistant/sensor/basket_live/{objet}/config", json.dumps(conf, ensure_ascii=False)),
                         (topic_etat(objet), str(sum(d[k]['etat'] == 'enregistre' for k in ('statistics', 'lineups')))),
                         (topic_attributs(objet), json.dumps({**d, "type": "basket_statistiques"}, ensure_ascii=False))]
        return messages
