"""Concours de pronostics : un menu par match à venir et par joueur, fermé à l'entre-deux,
points attribués à la fin confirmée (2 pour un match de Nanterre, 1 sinon), classement par saison.

Les pronostics de l'autre restent invisibles sur le tableau de bord jusqu'à l'entre-deux : chacun
n'y voit que ses menus, et l'historique ne contient que des matchs déjà commencés.
"""

from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from . import VERSION
from .modele import CODE_A_VENIR, Match, nom_court

AUCUN = "—"
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
HISTORIQUE_PUBLIE = 50


def saison(ts: float, tz: ZoneInfo) -> str:
    """Saison sportive, du 1er juillet au 30 juin."""
    d = datetime.fromtimestamp(ts, tz)
    an = d.year if d.month >= 7 else d.year - 1
    return f"{an}-{an + 1}"


def ouvert(m: Match, maintenant: float) -> bool:
    return not m.termine and m.code == CODE_A_VENIR and maintenant < m.debut_ts


def points_en_jeu(m: Match) -> int:
    return 2 if m.categorie == "nanterre" else 1


def gagnant(m: Match) -> str | None:
    if m.score_dom is None or m.score_ext is None or m.score_dom == m.score_ext:
        return None
    return "dom" if m.score_dom > m.score_ext else "ext"


def libelles(m: Match) -> dict[str, str]:
    dom, ext = nom_court(m.domicile), nom_court(m.exterieur)
    if dom == ext:
        dom, ext = f"{dom} (dom.)", f"{ext} (ext.)"
    return {"dom": dom, "ext": ext}


class Pronos:
    def __init__(self, joueurs: list[str]):
        self.joueurs = joueurs
        self.choix: dict[int, dict[str, str]] = {}     # id du match -> joueur -> "dom" | "ext"
        self.historique: list[dict] = []               # matchs terminés ayant au moins un pronostic
        self.publies: set[str] = set()                 # menus publiés en découverte (« joueur_id »)

    # --- persistance ---------------------------------------------------------------------

    def vers_dict(self) -> dict:
        return {"choix": {str(k): v for k, v in self.choix.items()}, "historique": self.historique,
                "publies": sorted(self.publies)}

    def charger(self, d: dict) -> None:
        self.choix = {int(k): v for k, v in d.get("choix", {}).items()}
        self.historique = d.get("historique", [])
        self.publies = set(d.get("publies", []))

    # --- saisie --------------------------------------------------------------------------

    def choisir(self, m: Match, joueur: str, libelle: str, maintenant: float) -> bool:
        if joueur not in self.joueurs or not ouvert(m, maintenant):
            return False
        cotes = {v: k for k, v in libelles(m).items()}
        if libelle == AUCUN:
            self.choix.get(m.id, {}).pop(joueur, None)
        elif libelle in cotes:
            self.choix.setdefault(m.id, {})[joueur] = cotes[libelle]
        else:
            return False
        if not self.choix.get(m.id):
            self.choix.pop(m.id, None)
        return True

    def nettoyer(self, ids_connus: set[int]) -> None:
        """Oublie les pronostics de matchs disparus du calendrier (reports)."""
        self.choix = {i: c for i, c in self.choix.items() if i in ids_connus}

    # --- résultats -----------------------------------------------------------------------

    def entree(self, m: Match, tz: ZoneInfo) -> dict:
        noms = libelles(m)
        g = gagnant(m) if m.termine else None
        choix = self.choix.get(m.id, {})
        en_jeu = points_en_jeu(m)
        return {
            "id": m.id,
            "debut": datetime.fromtimestamp(m.debut_ts, tz).isoformat(),
            "saison": saison(m.debut_ts, tz),
            "tournoi": m.tournoi,
            "tournoi_id": m.tournoi_id,
            "categorie": m.categorie,
            "domicile": m.domicile,
            "exterieur": m.exterieur,
            "score": f"{m.score_dom} - {m.score_ext}" if m.score_dom is not None and m.score_ext is not None else None,
            "termine": m.termine,
            "points_en_jeu": en_jeu,
            "vainqueur": noms[g] if g else None,
            "pronos": {j: (noms[choix[j]] if j in choix else None) for j in self.joueurs},
            "resultats": {j: (None if g is None or j not in choix else choix[j] == g) for j in self.joueurs},
            "points": {j: (en_jeu if g is not None and choix.get(j) == g else 0) for j in self.joueurs},
        }

    def resultat(self, m: Match, tz: ZoneInfo) -> dict | None:
        """À la fin confirmée : fige l'entrée dans l'historique et libère les choix du match."""
        if m.id not in self.choix:
            return None
        e = self.entree(m, tz)
        self.historique = [h for h in self.historique if h["id"] != m.id] + [e]
        del self.choix[m.id]
        return e

    def classement(self, saison_courante: str) -> list[dict]:
        lignes = {j: {"nom": j.capitalize(), "points": 0, "bons": 0, "pronos": 0} for j in self.joueurs}
        for h in self.historique:
            if h["saison"] != saison_courante:
                continue
            for j in self.joueurs:
                if h["pronos"].get(j) is not None:
                    lignes[j]["pronos"] += 1
                    lignes[j]["bons"] += 1 if h["resultats"].get(j) else 0
                    lignes[j]["points"] += h["points"].get(j, 0)
        return sorted(lignes.values(), key=lambda x: (-x["points"], -x["bons"], x["nom"]))

    # --- découverte MQTT -----------------------------------------------------------------

    def messages(self, matchs: list[Match], tz: ZoneInfo, maintenant: float, dispo: str) -> list[tuple[str, str]]:
        """Messages retenus à poser : menus des matchs ouverts, effacement des menus fermés.

        Les menus n'ont pas d'appareil : leur nom (« jeu. 18:15 · Efes - Paris ») s'affiche tel quel
        dans les cartes. Les attributs `joueur` et `debut` servent au filtrage et au tri.
        """
        sortie: list[tuple[str, str]] = []
        ouverts = set()
        for m in matchs:
            if not ouvert(m, maintenant):
                continue
            d = datetime.fromtimestamp(m.debut_ts, tz)
            noms = libelles(m)
            for j in self.joueurs:
                cle = f"{j}_{m.id}"
                ouverts.add(cle)
                base = f"basket_live/prono/{j}/{m.id}"
                conf = {
                    "name": f"{JOURS[d.weekday()]} {d:%H:%M} · {noms['dom']} - {noms['ext']}",
                    "unique_id": f"basket_live_prono_{cle}",
                    "state_topic": f"{base}/etat",
                    "command_topic": f"{base}/set",
                    "json_attributes_topic": f"{base}/attributs",
                    "availability_topic": dispo,
                    "options": [AUCUN, noms["dom"], noms["ext"]],
                    "icon": "mdi:crystal-ball",
                    "origin": {"name": "basket-live", "sw_version": VERSION},
                }
                choix = self.choix.get(m.id, {}).get(j)
                sortie += [
                    (f"homeassistant/select/basket_live/prono_{cle}/config", json.dumps(conf, ensure_ascii=False)),
                    (f"{base}/attributs", json.dumps({"joueur": j, "debut": d.isoformat(), "match_id": m.id,
                                                      "tournoi": m.tournoi, "categorie": m.categorie,
                                                      "points_en_jeu": points_en_jeu(m)}, ensure_ascii=False)),
                    (f"{base}/etat", noms[choix] if choix else AUCUN),
                ]
        for cle in sorted(self.publies - ouverts):
            j, mid = cle.rsplit("_", 1)
            base = f"basket_live/prono/{j}/{mid}"
            sortie += [(f"homeassistant/select/basket_live/prono_{cle}/config", ""),
                       (f"{base}/attributs", ""), (f"{base}/etat", "")]
        self.publies = ouverts
        return sortie
