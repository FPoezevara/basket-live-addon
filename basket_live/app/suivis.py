"""Choix de suivi live indépendants, persistants et sans limite par personne.

Absence de choix : Home Assistant applique la préférence automatique Nanterre.
True : suivi explicite ; False : désactivation explicite pour ce seul match.
"""
from __future__ import annotations

from .modele import Match, entier


class Suivis:
    def __init__(self, joueurs: list[str]):
        self.joueurs = list(dict.fromkeys(joueurs))
        self.choix: dict[str, dict[int, bool]] = {j: {} for j in self.joueurs}

    def choisir(self, m: Match, joueur: str, texte: str) -> bool:
        if joueur not in self.choix or m.termine or texte not in ("ON", "OFF"):
            return False
        actif = texte == "ON"
        if actif and m.code in (60, 70):
            return False
        if self.choix[joueur].get(m.id) is actif:
            return False
        self.choix[joueur][m.id] = actif
        return True

    def destinataires(self, match_id: int) -> dict[str, list[str]]:
        return {
            "suivis": [j for j in self.joueurs if self.choix[j].get(match_id) is True],
            "exclus": [j for j in self.joueurs if self.choix[j].get(match_id) is False],
        }

    def nettoyer(self, ids: set[int]) -> bool:
        avant = self.vers_dict()
        self.choix = {j: {i: v for i, v in choix.items() if i in ids}
                      for j, choix in self.choix.items()}
        return self.vers_dict() != avant

    def retirer(self, match_id: int) -> None:
        for choix in self.choix.values():
            choix.pop(match_id, None)

    def vers_dict(self) -> dict[str, dict[str, bool]]:
        return {j: {str(i): v for i, v in sorted(choix.items())}
                for j, choix in self.choix.items()}

    def charger(self, etat: dict) -> None:
        if not isinstance(etat, dict):
            return
        for j in self.joueurs:
            choix = etat.get(j, {})
            if isinstance(choix, dict):
                self.choix[j] = {i: v for identifiant, v in choix.items()
                                 if (i := entier(identifiant)) is not None and i > 0 and isinstance(v, bool)}
