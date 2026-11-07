"""Sélection et normalisation des classements du fournisseur."""

from .archives import liste
from .modele import entier


def normaliser_classement(reponse, equipe_id: int, *, bcl: bool) -> dict | None:
    if isinstance(reponse, dict) and reponse.get("success") is False:
        return None
    candidats = []
    for groupe in liste(reponse, "standings") or []:
        if not isinstance(groupe, dict) or groupe.get("type", "total") != "total":
            continue
        lignes = groupe.get("rows")
        if not isinstance(lignes, list) or not lignes or (bcl and len(lignes) != 4):
            continue
        equipes = []
        for ligne in lignes:
            if not isinstance(ligne, dict):
                break
            equipe = ligne.get("team")
            rang = entier(ligne.get("position"))
            if not isinstance(equipe, dict) or not equipe.get("name") or not rang or rang < 1:
                break
            marques = entier(ligne.get("scoresFor"))
            encaisses = entier(ligne.get("scoresAgainst"))
            joues = entier(ligne.get("matches"))
            victoires = entier(ligne.get("wins"))
            equipes.append({
                "rang": rang,
                "equipe": equipe.get("shortName") or equipe["name"],
                "nanterre": entier(equipe.get("id")) == equipe_id,
                "joues": joues,
                "victoires": victoires,
                "defaites": entier(ligne.get("losses")),
                "points": entier(ligne.get("points")),
                "marques": marques,
                "encaisses": encaisses,
                "difference": marques - encaisses if marques is not None and encaisses is not None else None,
                "pourcentage": round(100 * victoires / joues, 1) if joues and victoires is not None else None,
            })
        if len(equipes) != len(lignes) or not any(e["nanterre"] for e in equipes):
            continue
        nom = groupe.get("name") or ""
        candidats.append({"groupe": nom, "equipes": sorted(equipes, key=lambda e: e["rang"])})

    if not candidats:
        return None
    if bcl:
        # Le Top 16 remplace la poule initiale une fois que Nanterre y figure.
        top16 = [c for c in candidats if any(phase in c["groupe"].lower()
                 for phase in ("round of 16", "top 16", "huitièmes"))]
        candidats = top16 or candidats
        return candidats[0] if len(candidats) == 1 else None
    return max(candidats, key=lambda c: len(c["equipes"]))
