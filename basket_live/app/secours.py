"""Confirmation V1 des fins : correspondance prudente avec les matchs conservés en V2."""
from __future__ import annotations

from datetime import datetime
import re
import unicodedata

from .modele import Match, entier, nom_court

# Correspondances observées sur les réponses des deux API, jamais entre les IDs de matchs.
COMPETITIONS = {156: 38, 138: 569}
ALIASES = {"bcmgravelinesdunkerque": "gravelines", "boulazacbasket": "boulazac"}


def nom(n: str) -> str:
    texte = unicodedata.normalize("NFKD", nom_court(n)).casefold()
    cle = re.sub(r"[^a-z0-9]", "", texte)
    return ALIASES.get(cle, cle)


def noms(equipe: dict) -> set[str]:
    return {nom(equipe[k]) for k in ("name", "shortName", "longName")
            if isinstance(equipe.get(k), str) and nom(equipe[k])}


def correspond(m: Match, ev: dict) -> bool:
    if not isinstance(ev, dict) or entier(ev.get("sportId")) != 2 or ev.get("isHomeAwayInverted"):
        return False
    try:
        debut = datetime.fromisoformat(ev["startTime"].replace("Z", "+00:00"))
        if debut.tzinfo is None or abs(debut.timestamp() - m.debut_ts) > 900:
            return False
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError):
        return False
    comp = COMPETITIONS.get(m.tournoi_id)
    if comp is not None and entier(ev.get("competitionId")) != comp:
        return False
    dom, ext = ev.get("homeCompetitor"), ev.get("awayCompetitor")
    return (isinstance(dom, dict) and isinstance(ext, dict)
            and nom(m.domicile) in noms(dom) and nom(m.exterieur) in noms(ext))


def resultat_correspondant(m: Match, evenements: list[dict]) -> tuple[int, int, int] | None:
    trouves = [ev for ev in evenements if correspond(m, ev)]
    if len(trouves) != 1:  # pas de choix arbitraire entre deux rencontres possibles
        return None
    ev = trouves[0]
    if entier(ev.get("statusGroup")) != 4:
        return None
    identifiant = entier(ev.get("id"))
    # Ne pas convertir un nombre fractionnaire en entier ni accepter un score négatif.
    scores = [ev[c].get("score") for c in ("homeCompetitor", "awayCompetitor")]
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not float(v).is_integer() or v < 0 for v in scores):
        return None
    dom, ext = map(int, scores)
    if identifiant is None or identifiant <= 0 or dom == ext:
        return None  # un match de basket ne se termine pas sur une égalité
    return identifiant, dom, ext
