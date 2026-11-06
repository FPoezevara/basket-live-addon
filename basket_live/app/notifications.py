"""Échéances persistantes : fermeture des lives et rappels de pronostics groupés.

Home Assistant lit les tâches MQTT retenues et acquitte celles qu'il a traitées.
Aucun appel réseau ni requête SportsAPI dans ce module.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .modele import Match, entier, nom_court
from .pronos import Pronos, ouvert

DELAI_FERMETURE = 30 * 60
AVANCE_RAPPEL = 2 * 3600
RETENTION = 8 * 86400


def timestamp(valeur) -> bool:
    return (isinstance(valeur, (int, float)) and not isinstance(valeur, bool)
            and math.isfinite(valeur) and valeur >= 0)


class Notifications:
    def __init__(self, joueurs: list[str]):
        self.joueurs = list(dict.fromkeys(joueurs))
        self.echeances: dict[str, dict] = {}
        self.acquittes: dict[str, float] = {}

    def actualiser(self, matchs: list[Match], resultats: list[Match], pronos: Pronos,
                   maintenant: float) -> bool:
        avant = self.vers_dict()
        # Conserver les acquittements tant que le résultat existe, même avec un historique long.
        cles_resultats = {f"fermeture:{j}:{m.id}" for m in resultats for j in self.joueurs}
        self.acquittes = {c: t for c, t in self.acquittes.items()
                         if t >= maintenant - RETENTION or c in cles_resultats}
        for m in resultats:
            if not m.termine or not timestamp(m.termine_ts):
                continue
            for j in self.joueurs:
                cle = f"fermeture:{j}:{m.id}"
                if cle not in self.acquittes:
                    self.echeances[cle] = {
                        "cle": cle, "type": "fermeture", "personne": j, "match_id": m.id,
                        "echeance": m.termine_ts + DELAI_FERMETURE,
                    }

        # Un groupe par personne et horaire affiché, pas par match ni par compétition.
        groupes: dict[str, dict] = {}
        for m in sorted(matchs, key=lambda match: (match.debut_ts, match.id)):
            if not ouvert(m, maintenant):
                continue
            debut = int(m.debut_ts) // 60 * 60
            if not debut - AVANCE_RAPPEL <= maintenant < debut:
                continue
            for j in self.joueurs:
                if pronos.choix.get(m.id, {}).get(j) in ("dom", "ext"):
                    continue
                cle = f"rappel_prono:{j}:{debut}"
                if cle in self.acquittes:
                    continue
                groupe = groupes.setdefault(cle, {
                    "cle": cle, "type": "rappel_prono", "personne": j,
                    "echeance": debut - AVANCE_RAPPEL, "debut": debut, "matchs": [],
                })
                groupe["matchs"].append({"id": m.id,
                                          "titre": f"{nom_court(m.domicile)} - {nom_court(m.exterieur)}",
                                          "tournoi": m.tournoi})
        # Annule un rappel si tous les pronostics sont faits, le match a été reporté ou a débuté.
        self.echeances = {c: e for c, e in self.echeances.items()
                          if e["type"] != "rappel_prono" or c in groupes}
        self.echeances.update(groupes)
        return self.vers_dict() != avant

    def acquitter(self, cle: str, maintenant: float) -> bool:
        if not isinstance(cle, str):
            return False
        echeance = self.echeances.get(cle)
        if echeance is None or maintenant < echeance["echeance"]:
            return False
        self.acquittes[cle] = maintenant
        del self.echeances[cle]
        return True

    def attributs(self) -> dict:
        return {"echeances": sorted(deepcopy(list(self.echeances.values())),
                                     key=lambda e: (e["type"] != "rappel_prono", e["echeance"], e["cle"]))}

    def vers_dict(self) -> dict:
        return {"echeances": deepcopy(self.echeances), "acquittes": dict(self.acquittes)}

    def charger(self, donnees: dict) -> None:
        if not isinstance(donnees, dict):
            return
        echeances = donnees.get("echeances", {})
        acquittes = donnees.get("acquittes", {})
        if isinstance(echeances, dict):
            for cle, e in echeances.items():
                if not isinstance(cle, str) or not isinstance(e, dict):
                    continue
                j = e.get("personne")
                if j not in self.joueurs or not timestamp(e.get("echeance")):
                    continue
                if e.get("type") == "fermeture":
                    mid = entier(e.get("match_id"))
                    if mid is None or mid <= 0 or cle != f"fermeture:{j}:{mid}":
                        continue
                elif e.get("type") == "rappel_prono":
                    debut = e.get("debut")
                    if not timestamp(debut) or cle != f"rappel_prono:{j}:{int(debut)}":
                        continue
                    if not isinstance(e.get("matchs"), list):
                        continue
                else:
                    continue
                self.echeances[cle] = deepcopy({**e, "cle": cle})
        if isinstance(acquittes, dict):
            self.acquittes = {c: t for c, t in acquittes.items()
                             if isinstance(c, str) and timestamp(t)}
        for cle in self.acquittes:
            self.echeances.pop(cle, None)
