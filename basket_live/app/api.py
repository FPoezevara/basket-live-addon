"""Client REST SportsAPI Pro V2 avec comptage des requêtes.

L'API n'expose pas le quota consommé : on compte nous-mêmes, par jour UTC. Deux priorités :
« fond » (calendrier, instantané live) s'arrête avant la réserve,
« essentiel » (confirmation des fins de match) peut l'entamer.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote
from typing import Callable

import aiohttp

log = logging.getLogger("api")

FOND = "fond"
ESSENTIEL = "essentiel"


class Api:
    def __init__(self, cle: str, base: str, ws_url: str, quota: int,
                 base_v1: str = "https://api.sportsapipro.com/v1"):
        self.cle = cle
        self.base = base.rstrip("/")
        self.ws_base = ws_url
        self.base_v1 = base_v1.rstrip("/")
        self.quota = quota
        self.reserve = max(10, quota * 15 // 100)
        self.jour = self._jour()
        self.compteur = 0
        self.compteur_secours = 0
        self.compteur_instantanes = 0
        self.session: aiohttp.ClientSession | None = None
        self.sur_compteur: Callable[[], None] | None = None

    @staticmethod
    def _jour() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _remise_a_zero(self) -> None:
        jour = self._jour()
        if jour != self.jour:
            self.jour, self.compteur = jour, 0
            self.compteur_secours = self.compteur_instantanes = 0

    def disponible(self, priorite: str = FOND) -> bool:
        self._remise_a_zero()
        plafond = self.quota if priorite == ESSENTIEL else self.quota - self.reserve
        return self.compteur < plafond

    def compter(self) -> None:
        self._remise_a_zero()
        self.compteur += 1
        if self.sur_compteur:
            self.sur_compteur()  # réserve persistée avant l’envoi HTTP

    def restaurer(self, jour: str, compteur: int, compteur_secours: int = 0,
                  compteur_instantanes: int = 0) -> None:
        if jour == self._jour():
            self.jour, self.compteur = jour, int(compteur)
            self.compteur_secours = max(0, int(compteur_secours))
            self.compteur_instantanes = max(0, int(compteur_instantanes))

    def url_ws(self) -> str:
        return f"{self.ws_base}?x-api-key={quote(self.cle)}"

    async def ouvrir(self) -> None:
        self.session = aiohttp.ClientSession(
            headers={"x-api-key": self.cle, "User-Agent": "basket-live-addon"},
            timeout=aiohttp.ClientTimeout(total=30),
        )

    async def fermer(self) -> None:
        if self.session:
            await self.session.close()

    async def get(self, chemin: str, priorite: str = FOND, *, base: str | None = None,
                  vide_404: bool = False) -> dict | None:
        if not self.disponible(priorite):
            log.warning("Quota local atteint (%s/%s), requête %s non envoyée", self.compteur, self.quota, chemin)
            return None
        self.compter()
        try:
            async with self.session.get(f"{base or self.base}{chemin}") as rep:
                if rep.status == 429:
                    log.error("429 sur %s : quota de l'API épuisé, arrêt des requêtes jusqu'à minuit UTC", chemin)
                    self.compteur = self.quota
                    if self.sur_compteur:
                        self.sur_compteur()
                    return None
                if rep.status == 404 and vide_404:
                    return {"events": [], "hasNextPage": False}
                if rep.status != 200:
                    log.warning("HTTP %s sur %s", rep.status, chemin)
                    return None
                return await rep.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as e:
            log.warning("Échec de %s : %s", chemin, e)
            return None
        except ValueError as e:
            log.warning("Réponse illisible sur %s : %s", chemin, e)
            return None

    async def calendrier(self, jour: str, priorite: str = FOND) -> list[dict] | None:
        rep = await self.get(f"/api/schedule/{jour}", priorite)
        if rep is None or not isinstance(rep.get("events"), list):
            return None
        return rep["events"]

    async def live(self, priorite: str = FOND, *, automatique: bool = False) -> list[dict] | None:
        if not self.disponible(priorite):
            return None
        if automatique:
            self.compteur_instantanes += 1  # diagnostic uniquement, sans sous-plafond
        rep = await self.get("/api/live", priorite)
        if rep is None or not isinstance(rep.get("events"), list):
            return None
        return rep["events"]

    async def calendrier_secours(self, jour: str, priorite: str = FOND) -> list[dict] | None:
        # Requête par date UTC : inclut les matchs terminés, y compris après minuit.
        # Tous les appels V1 et V2 partagent le même compteur REST local.
        if not self.disponible(priorite):
            return None
        self.compteur_secours += 1  # diagnostic uniquement, sans sous-plafond
        rep = await self.get(f"/games?startDate={jour}&endDate={jour}&sportId=2", priorite,
                             base=self.base_v1)
        if not isinstance(rep, dict) or rep.get("success") is False:
            return None
        data = rep.get("data", rep)
        if not isinstance(data, dict) or not isinstance(data.get("games"), list):
            return None
        return data["games"]

    async def details_match(self, identifiant: int, ressource: str):
        if ressource not in ("statistics", "lineups"):
            raise ValueError("Ressource statistique non autorisée")
        return await self.get(f"/api/match/{identifiant}/{ressource}", FOND)

    async def saisons_tournoi(self, identifiant: int):
        return await self.get(f"/api/tournament/{identifiant}/seasons", FOND)

    async def historique_tournoi(self, identifiant: int, saison_id: int, page: int):
        return await self.get(f"/api/tournament/{identifiant}/season/{saison_id}/events/last/{page}",
                              FOND, vide_404=True)

    async def historique_equipe(self, identifiant: int, page: int):
        return await self.get(f"/api/teams/{identifiant}/events/last/{page}", FOND, vide_404=True)
