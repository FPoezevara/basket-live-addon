"""Badges du concours de pronostics : catalogue, calcul par saison et nouvelles étoiles.

Calcul pur à partir de l'historique figé des pronostics (aucun appel réseau). Chaque badge a
cinq paliers ; le niveau est le nombre de paliers atteints. Les badges négatifs sont affichés
en rouge par la carte. L'icône est propre au badge : identique pour tous les joueurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .pronos import libelles_noms
from .modele import nom_court


def pl(n: int, singulier: str, pluriel: str | None = None) -> str:
    return f"{n} {singulier if n <= 1 else (pluriel or singulier + 's')}"


@dataclass(frozen=True)
class Badge:
    id: str
    masculin: str
    feminin: str
    icone: str
    paliers: tuple[int, int, int, int, int]
    phrase: Callable[[int, str], str]          # (valeur, prénom de l'autre joueur) -> description
    negatif: bool = False

    def niveau(self, valeur: int) -> int:
        return sum(valeur >= p for p in self.paliers)


CATALOGUE: tuple[Badge, ...] = (
    Badge("lucky_streak", "Lucky Streak", "Lucky Streak", "mdi:target", (5, 10, 25, 50, 100),
          lambda v, a: f"Meilleure série de la saison : {pl(v, 'pronostic')} {'réussi' if v <= 1 else 'réussis'} d'affilée."),
    Badge("ultra", "Ultra Nanterrien", "Ultra Nanterrienne", "mdi:bullhorn", (1, 5, 10, 20, 30),
          lambda v, a: f"{pl(v, 'victoire')} de Nanterre correctement {'pronostiquée' if v <= 1 else 'pronostiquées'}."),
    Badge("judas", "Judas", "Judas", "mdi:drama-masks", (1, 5, 10, 20, 30),
          lambda v, a: f"{pl(v, 'pronostic')} contre Nanterre cette saison.", negatif=True),
    Badge("europeen", "Européen", "Européenne", "mdi:earth", (5, 10, 25, 50, 100),
          lambda v, a: f"{pl(v, 'pronostic')} {'réussi' if v <= 1 else 'réussis'} en coupe d'Europe."),
    Badge("chanceux", "Chanceux", "Chanceuse", "mdi:clover", (1, 2, 5, 10, 20),
          lambda v, a: f"{pl(v, 'pronostic')} {'réussi' if v <= 1 else 'réussis'} sur un match gagné d'un point."),
    Badge("malchanceux", "Malchanceux", "Malchanceuse", "mdi:weather-pouring", (1, 2, 5, 10, 20),
          lambda v, a: f"{pl(v, 'pronostic')} {'perdu' if v <= 1 else 'perdus'} sur un match gagné d'un point.", negatif=True),
    Badge("assidu", "Assidu", "Assidue", "mdi:calendar-check", (10, 50, 100, 200, 300),
          lambda v, a: f"{pl(v, 'pronostic')} {'joué' if v <= 1 else 'joués'} cette saison."),
    Badge("sans_faute", "Sans-faute", "Sans-faute", "mdi:check-all", (1, 5, 10, 20, 30),
          lambda v, a: f"{pl(v, 'journée')} d'au moins 3 pronostics, tous réussis."),
    Badge("duelliste", "Duelliste", "Duelliste", "mdi:sword-cross", (1, 5, 10, 20, 30),
          lambda v, a: f"{v} fois raison contre {a} sur un pronostic opposé."),
    Badge("ames_soeurs", "Âmes sœurs", "Âmes sœurs", "mdi:heart-multiple", (5, 15, 30, 50, 80),
          lambda v, a: f"{pl(v, 'pronostic')} {'identique' if v <= 1 else 'identiques'} et {'réussi' if v <= 1 else 'réussis'} avec {a}."),
    Badge("globe_trotter", "Globe-trotter", "Globe-trotter", "mdi:airplane", (5, 10, 25, 50, 100),
          lambda v, a: f"{pl(v, 'victoire')} à l'extérieur correctement {'pronostiquée' if v <= 1 else 'pronostiquées'}."),
    Badge("rouleau", "Rouleau compresseur", "Rouleau compresseur", "mdi:bulldozer", (1, 2, 5, 10, 20),
          lambda v, a: f"{pl(v, 'pronostic')} {'réussi' if v <= 1 else 'réussis'} sur une victoire d'au moins 20 points."),
    Badge("visionnaire", "Visionnaire", "Visionnaire", "mdi:eye-circle", (1, 2, 5, 10, 20),
          lambda v, a: f"{pl(v, 'victoire')} d'une équipe classée au moins 4 places plus bas, correctement "
                       f"{'pronostiquée' if v <= 1 else 'pronostiquées'}."),
    Badge("chat_noir", "Chat noir", "Chat noir", "mdi:cat", (1, 2, 5, 10, 20),
          lambda v, a: f"Pire série de la saison : {pl(v, 'pronostic')} {'perdu' if v <= 1 else 'perdus'} d'affilée.",
          negatif=True),
)
PAR_ID = {b.id: b for b in CATALOGUE}
ECART_SERRE = 1
ECART_LARGE = 20
ECART_RANGS = 4
JOURNEE_MIN = 3


def score(h: dict) -> tuple[int, int] | None:
    try:
        dom, ext = (int(x) for x in str(h.get("score") or "").split(" - "))
    except ValueError:
        return None
    return dom, ext


def cote_nanterre(h: dict) -> str | None:
    """Côté de Nanterre : champ figé à la fin depuis 0.8.0, sinon déduit du nom court."""
    if h.get("nanterre") in ("dom", "ext"):
        return h["nanterre"]
    if nom_court(h.get("domicile", "")) == "Nanterre":
        return "dom"
    if nom_court(h.get("exterieur", "")) == "Nanterre":
        return "ext"
    return None


class Badges:
    def __init__(self, joueurs: list[str], joueuses: list[str], elite: set[int], europe: set[int]):
        self.joueurs = list(dict.fromkeys(joueurs))
        self.joueuses = set(joueuses)
        self.elite = elite
        self.europe = europe
        self.notifiees: dict[str, dict[str, dict[str, int]]] = {}   # saison -> joueur -> badge -> niveau

    # --- calcul --------------------------------------------------------------------------

    def valeurs(self, historique: list[dict], saison: str, joueur: str) -> dict[str, int]:
        entrees = sorted((h for h in historique if h.get("saison") == saison and h.get("termine")),
                         key=lambda h: (str(h.get("debut", "")), int(h.get("id", 0))))
        autres = [j for j in self.joueurs if j != joueur]
        v = {b.id: 0 for b in CATALOGUE}
        serie = echecs = 0
        journees: dict[str, list[bool]] = {}
        for h in entrees:
            noms = libelles_noms(h.get("domicile", ""), h.get("exterieur", ""))
            cotes = {nom: c for c, nom in noms.items()}
            choix = cotes.get((h.get("pronos") or {}).get(joueur))
            if choix is None:
                continue
            reussi = (h.get("resultats") or {}).get(joueur)
            v["assidu"] += 1
            nanterre = cote_nanterre(h)
            if nanterre and choix != nanterre:
                v["judas"] += 1
            if reussi is None:                      # match nul ou vainqueur inconnu : ne compte pas
                continue
            serie, echecs = (serie + 1, 0) if reussi else (0, echecs + 1)
            v["lucky_streak"] = max(v["lucky_streak"], serie)
            v["chat_noir"] = max(v["chat_noir"], echecs)
            journees.setdefault(str(h.get("debut", ""))[:10], []).append(reussi)
            s = score(h)
            ecart = abs(s[0] - s[1]) if s else None
            if ecart == ECART_SERRE:
                v["chanceux" if reussi else "malchanceux"] += 1
            if not reussi:
                continue
            if nanterre and choix == nanterre:
                v["ultra"] += 1
            if h.get("tournoi_id") in self.europe:
                v["europeen"] += 1
            if choix == "ext":
                v["globe_trotter"] += 1
            if ecart is not None and ecart >= ECART_LARGE:
                v["rouleau"] += 1
            rangs = h.get("rangs") or {}
            if (h.get("tournoi_id") in self.elite and isinstance(rangs.get("dom"), int)
                    and isinstance(rangs.get("ext"), int)):
                autre_cote = "ext" if choix == "dom" else "dom"
                if rangs[choix] - rangs[autre_cote] >= ECART_RANGS:
                    v["visionnaire"] += 1
            for a in autres:
                choix_autre = cotes.get((h.get("pronos") or {}).get(a))
                if choix_autre is None:
                    continue
                if choix_autre != choix:
                    v["duelliste"] += 1
                elif (h.get("resultats") or {}).get(a) is True:
                    v["ames_soeurs"] += 1
        v["sans_faute"] = sum(len(r) >= JOURNEE_MIN and all(r) for r in journees.values())
        return v

    def calculer(self, historique: list[dict], saison: str) -> dict[str, list[dict]]:
        """Badges obtenus (au moins une étoile) par joueur : ordre du catalogue, badges négatifs à la fin."""
        sortie = {}
        for j in self.joueurs:
            valeurs = self.valeurs(historique, saison, j)
            autres = [a.capitalize() for a in self.joueurs if a != j]
            autre = autres[0] if len(autres) == 1 else "l'autre"
            obtenus = []
            for b in CATALOGUE:
                n = b.niveau(valeurs[b.id])
                if n:
                    obtenus.append({
                        "id": b.id, "nom": b.feminin if j in self.joueuses else b.masculin,
                        "icone": b.icone, "niveau": n, "valeur": valeurs[b.id], "paliers": list(b.paliers),
                        "negatif": b.negatif, "description": b.phrase(valeurs[b.id], autre),
                    })
            sortie[j] = sorted(obtenus, key=lambda b: b["negatif"])     # tri stable : ordre du catalogue conservé
        return sortie

    def nouvelles_etoiles(self, obtenus: dict[str, list[dict]], saison: str) -> dict[str, list[dict]]:
        """Badges dont le niveau dépasse le dernier niveau annoncé. Le premier calcul d'une saison
        (installation de 0.8.0, ou état perdu) est enregistré sans annonce."""
        courants = {j: {b["id"]: b["niveau"] for b in obtenus.get(j, [])} for j in self.joueurs}
        if saison not in self.notifiees:
            self.notifiees[saison] = courants
            self.notifiees = {s: n for s, n in self.notifiees.items() if s >= saison}
            return {}
        connus = self.notifiees[saison]
        nouveaux: dict[str, list[dict]] = {}
        for j in self.joueurs:
            deja = connus.setdefault(j, {})
            for b in obtenus.get(j, []):
                if b["niveau"] > deja.get(b["id"], 0):
                    deja[b["id"]] = b["niveau"]
                    nouveaux.setdefault(j, []).append(b)
        return nouveaux

    # --- persistance ---------------------------------------------------------------------

    def vers_dict(self) -> dict:
        return {"notifiees": self.notifiees}

    def charger(self, d: dict) -> None:
        notifiees = d.get("notifiees", {}) if isinstance(d, dict) else {}
        if isinstance(notifiees, dict):
            self.notifiees = {
                s: {j: {b: int(n) for b, n in niveaux.items() if b in PAR_ID and isinstance(n, int)}
                    for j, niveaux in par_joueur.items() if isinstance(niveaux, dict)}
                for s, par_joueur in notifiees.items() if isinstance(s, str) and isinstance(par_joueur, dict)
            }
