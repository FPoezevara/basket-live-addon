"""Logique pure, sans réseau : sélection des matchs, application des mises à jour, chrono, mise en forme.

Les données SportsAPI Pro V2 suivent le format Sofascore. Trois formes arrivent ici, toutes
ramenées à un dictionnaire plat à clés pointées par `normaliser` :
- calendrier (/api/schedule/{date}) : objets imbriqués, `status` est un objet ;
- live (/api/live) : format allégé, `status` est une chaîne et `statusCode` un entier ;
- WebSocket (canal live-scores) : deltas déjà pointés (`homeScore.current`, `status.code`…).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, fields
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

CODE_A_VENIR = 0
CODES_QUARTS = {13, 14, 15, 16}
CODE_PROLONGATION = 17
CODES_HORLOGE = CODES_QUARTS | {CODE_PROLONGATION}
CODES_EN_COURS = CODES_HORLOGE | {30, 31}
CODE_TERMINE = 100

LIBELLES = {
    0: "À venir",
    13: "1er quart-temps",
    14: "2e quart-temps",
    15: "3e quart-temps",
    16: "4e quart-temps",
    17: "Prolongation",
    30: "Pause",
    31: "Mi-temps",
    60: "Reporté",
    70: "Annulé",
    100: "Terminé",
}
LIBELLES_COURTS = {13: "QT1", 14: "QT2", 15: "QT3", 16: "QT4", 17: "Prol.", 30: "Pause", 31: "Mi-temps"}

NOMS_TOURNOIS = {
    156: "Betclic Élite",
    1666: "Coupe de France",
    405: "Leaders Cup",
    138: "EuroLeague",
    141: "EuroCup",
    9357: "Basketball Champions League",
    2165: "FIBA Europe Cup",
}

# Un match terminé plus de 4 h après l'entre-deux est signalé « tardif » (fin rattrapée par le calendrier)
DELAI_TARDIF = 4 * 3600

SCORES = {
    "homeScore.current": "score_dom",
    "awayScore.current": "score_ext",
    "homeScore.overtime": "prolongation_dom",
    "awayScore.overtime": "prolongation_ext",
}


@dataclass
class Criteres:
    equipe: int
    elite: set[int]
    europe: set[int]
    pays: str


@dataclass
class Match:
    id: int
    categorie: str
    tournoi_id: int | None
    tournoi: str
    domicile: str
    domicile_id: int | None
    domicile_code: str | None
    exterieur: str
    exterieur_id: int | None
    exterieur_code: str | None
    debut_ts: int
    code: int = CODE_A_VENIR
    description: str = ""
    score_dom: int | None = None
    score_ext: int | None = None
    periodes_dom: list = field(default_factory=lambda: [None] * 4)
    periodes_ext: list = field(default_factory=lambda: [None] * 4)
    prolongation_dom: int | None = None
    prolongation_ext: int | None = None
    duree_quart: int = 600
    duree_prolongation: int = 300
    temps_joue: int | None = None
    temps_joue_ref: float | None = None
    horloge: bool = False
    fin_provisoire_ts: float | None = None
    essais_fin: int = 0
    prochaine_verif_ts: float = 0.0
    termine: bool = False
    termine_ts: float | None = None
    tardif: bool = False
    maj_ts: float | None = None
    dernier_push_ts: float = 0.0
    push_en_attente: bool = False

    @classmethod
    def depuis_dict(cls, d: dict) -> "Match":
        connus = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in connus})


# --- utilitaires -------------------------------------------------------------------------


def entier(v) -> int | None:
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def horodatage(v) -> float | None:
    """Convertit « 2026-11-03 22:37:08.696577 » (UTC) en epoch."""
    if not isinstance(v, str):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def aplatir(d: dict, prefixe: str = "") -> dict:
    """Aplatit les objets imbriqués en clés pointées ; les listes restent telles quelles."""
    plat = {}
    for k, v in d.items():
        cle = f"{prefixe}{k}"
        if isinstance(v, dict):
            plat.update(aplatir(v, cle + "."))
        else:
            plat[cle] = v
    return plat


def normaliser(ev: dict) -> dict:
    plat = aplatir(ev)
    # Format /api/live : statusCode entier, status chaîne
    if "statusCode" in plat and "status.code" not in plat:
        plat["status.code"] = plat.pop("statusCode")
    if isinstance(plat.get("status"), str):
        plat["status.description"] = plat.pop("status")
    return plat


def date_locale(ts: float, tz: ZoneInfo) -> date:
    return datetime.fromtimestamp(ts, tz).date()


def nom_equipe(eq: dict) -> str:
    return eq.get("shortName") or eq.get("name") or "?"


def code_equipe(eq: dict) -> str | None:
    code = eq.get("nameCode")
    if code:
        return code
    nom = eq.get("shortName") or eq.get("name")
    return nom[:3].upper() if nom else None


# --- sélection ---------------------------------------------------------------------------


def categorie(ev: dict, c: Criteres) -> str | None:
    """nanterre (toutes compétitions) > elite > europe (si un club du pays suivi joue)."""
    dom = ev.get("homeTeam") or {}
    ext = ev.get("awayTeam") or {}
    if not isinstance(dom, dict) or not isinstance(ext, dict):
        return None
    if c.equipe in (dom.get("id"), ext.get("id")):
        return "nanterre"
    tid = ((ev.get("tournament") or {}).get("uniqueTournament") or {}).get("id")
    if tid in c.elite:
        return "elite"
    if tid in c.europe:
        pays = {(dom.get("country") or {}).get("alpha2"), (ext.get("country") or {}).get("alpha2")}
        if c.pays in pays:
            return "europe"
    return None


def construire_match(ev: dict, cat: str) -> Match:
    dom = ev.get("homeTeam") or {}
    ext = ev.get("awayTeam") or {}
    tournoi = (ev.get("tournament") or {}).get("uniqueTournament") or {}
    tid = tournoi.get("id")
    return Match(
        id=int(ev["id"]),
        categorie=cat,
        tournoi_id=tid,
        tournoi=NOMS_TOURNOIS.get(tid, tournoi.get("name") or "?"),
        domicile=nom_equipe(dom),
        domicile_id=dom.get("id"),
        domicile_code=code_equipe(dom),
        exterieur=nom_equipe(ext),
        exterieur_id=ext.get("id"),
        exterieur_code=code_equipe(ext),
        debut_ts=int(ev["startTimestamp"]),
    )


def maj_statique(m: Match, ev: dict, cat: str) -> None:
    """Met à jour ce qui peut changer dans le calendrier sans relever du live (horaire, noms)."""
    neuf = construire_match(ev, cat)
    for attr in ("categorie", "tournoi_id", "tournoi", "domicile", "domicile_id", "domicile_code",
                 "exterieur", "exterieur_id", "exterieur_code", "debut_ts"):
        setattr(m, attr, getattr(neuf, attr))


# --- chrono ------------------------------------------------------------------------------


def fin_periode(m: Match, code: int | None = None) -> int | None:
    """Temps de jeu cumulé (s) à la fin de la période en cours, ou None hors période."""
    code = m.code if code is None else code
    q = m.duree_quart
    if code in CODES_QUARTS:
        return (code - 12) * q
    if code == CODE_PROLONGATION:
        joue = m.temps_joue or 0
        k = max(1, math.ceil((joue - 4 * q) / m.duree_prolongation)) if joue > 4 * q else 1
        return 4 * q + k * m.duree_prolongation
    return None


def temps_joue_actuel(m: Match, maintenant: float, extrapoler: bool = True) -> int | None:
    """Temps joué extrapolé si l'horloge tourne, borné à la fin de la période."""
    if m.temps_joue is None:
        return None
    t = float(m.temps_joue)
    if extrapoler and m.horloge and m.temps_joue_ref is not None and m.code in CODES_HORLOGE:
        t += max(0.0, maintenant - m.temps_joue_ref)
        fin = fin_periode(m)
        if fin is not None:
            t = min(t, fin)
    return int(t)


def temps_restant(m: Match, maintenant: float, extrapoler: bool = True) -> int | None:
    if m.code not in CODES_HORLOGE:
        return None
    joue = temps_joue_actuel(m, maintenant, extrapoler)
    fin = fin_periode(m)
    if joue is None or fin is None:
        return None
    duree = m.duree_quart if m.code in CODES_QUARTS else m.duree_prolongation
    restant = fin - joue
    if restant < 0 or restant > duree:
        return None  # temps joué incohérent avec le statut : on n'affiche rien plutôt que faux
    return int(restant)


def format_chrono(s: int | None) -> str | None:
    return None if s is None else f"{s // 60}:{s % 60:02d}"


# --- application des mises à jour --------------------------------------------------------


def appliquer(m: Match, plat: dict, maintenant: float, scores_seulement: bool = False) -> list[str]:
    """Applique un dictionnaire plat au match et renvoie les transitions à signaler.

    Transitions : debut, periode, fin_provisoire, reprise, statut. Un changement de score
    ne renvoie rien mais lève `push_en_attente`, que l'ordonnanceur transforme en « maj » cadencée.
    """
    if m.termine:
        return []
    evts: list[str] = []
    change = False
    score_change = False

    for cle, attr in SCORES.items():
        if cle in plat:
            v = entier(plat[cle])
            if v is not None and getattr(m, attr) != v:
                setattr(m, attr, v)
                change = score_change = True
    for i in range(1, 5):
        for cote, liste in (("home", m.periodes_dom), ("away", m.periodes_ext)):
            cle = f"{cote}Score.period{i}"
            if cle in plat:
                v = entier(plat[cle])
                if v is not None and liste[i - 1] != v:
                    liste[i - 1] = v
                    change = True

    if scores_seulement:
        return []

    if entier(plat.get("time.periodLength")):
        m.duree_quart = entier(plat["time.periodLength"])
    if entier(plat.get("time.overtimeLength")):
        m.duree_prolongation = entier(plat["time.overtimeLength"])

    ref = (horodatage(plat.get("time.playedLastUpdated.date"))
           or entier(plat.get("changes.changeTimestamp"))
           or maintenant)
    ref = min(float(ref), maintenant)

    nouveau_code = entier(plat.get("status.code"))
    code_change = nouveau_code is not None and nouveau_code != m.code
    ancien_code = m.code

    if "time.played" in plat:
        v = entier(plat["time.played"])
        if v is not None:
            m.temps_joue, m.temps_joue_ref = v, ref
            change = True
    if "time.clockRunning" in plat:
        tourne = bool(plat["time.clockRunning"])
        if tourne != m.horloge:
            if "time.played" not in plat:
                # Fige l'extrapolation à l'arrêt, ou repart de la dernière valeur à la reprise
                m.temps_joue = temps_joue_actuel(m, maintenant)
                m.temps_joue_ref = maintenant
            m.horloge = tourne
            change = True

    if isinstance(plat.get("status.description"), str):
        m.description = plat["status.description"]

    if code_change:
        if ancien_code in CODES_HORLOGE and nouveau_code not in CODES_HORLOGE and m.horloge:
            m.temps_joue = temps_joue_actuel(m, maintenant)
            m.temps_joue_ref = maintenant
            m.horloge = False
        m.code = nouveau_code
        change = True
        if ancien_code == CODE_TERMINE and nouveau_code in CODES_EN_COURS:
            m.fin_provisoire_ts = None
            m.essais_fin = 0
            evts.append("reprise")
        elif nouveau_code in CODES_EN_COURS and ancien_code in CODES_EN_COURS:
            evts.append("periode")
        elif nouveau_code in CODES_EN_COURS:
            evts.append("debut")
        elif nouveau_code == CODE_TERMINE:
            m.fin_provisoire_ts = maintenant
            m.essais_fin = 0
            evts.append("fin_provisoire")
        else:
            evts.append("statut")

    if score_change and m.code in CODES_EN_COURS | {CODE_TERMINE}:
        m.push_en_attente = True
    if change:
        m.maj_ts = maintenant
    return evts


def finaliser(m: Match, maintenant: float) -> None:
    m.termine = True
    m.termine_ts = maintenant
    m.tardif = maintenant > m.debut_ts + DELAI_TARDIF
    m.horloge = False
    m.push_en_attente = False
    m.code = CODE_TERMINE


def actif(m: Match, maintenant: float) -> bool:
    """Match pour lequel le WebSocket est utile : de 15 min avant l'entre-deux à la fin confirmée."""
    if m.termine:
        return False
    if m.code in CODES_EN_COURS or m.code == CODE_TERMINE:
        return True
    return m.code == CODE_A_VENIR and m.debut_ts - 900 <= maintenant <= m.debut_ts + 4 * 3600


# --- mise en forme -----------------------------------------------------------------------


def statut_affiche(m: Match) -> str:
    if m.termine:
        return "Terminé a.p." if m.prolongation_dom is not None else "Terminé"
    if m.code == CODE_TERMINE:
        return "Fin du match"
    return LIBELLES.get(m.code, m.description or str(m.code))


def vue(m: Match, tz: ZoneInfo, maintenant: float, extrapoler: bool = True) -> dict:
    restant = temps_restant(m, maintenant, extrapoler)
    a_score = m.score_dom is not None and m.score_ext is not None
    score = f"{m.score_dom} - {m.score_ext}" if a_score else None
    etiquette = LIBELLES_COURTS.get(m.code)
    if m.code == CODE_TERMINE:
        etiquette = "Fin"
    resume = " · ".join(x for x in (score, etiquette, format_chrono(restant)) if x)
    court = None
    if a_score:
        court = f"{m.domicile_code or ''} {m.score_dom}-{m.score_ext} {m.exterieur_code or ''}".strip()
    return {
        "id": m.id,
        "categorie": m.categorie,
        "tournoi": m.tournoi,
        "tournoi_id": m.tournoi_id,
        "domicile": m.domicile,
        "exterieur": m.exterieur,
        "domicile_id": m.domicile_id,
        "exterieur_id": m.exterieur_id,
        "domicile_code": m.domicile_code,
        "exterieur_code": m.exterieur_code,
        "titre": f"{m.domicile} - {m.exterieur}",
        "debut": datetime.fromtimestamp(m.debut_ts, tz).isoformat(),
        "code": m.code,
        "statut": statut_affiche(m),
        "en_cours": m.code in CODES_EN_COURS and not m.termine,
        "fin_provisoire": m.code == CODE_TERMINE and not m.termine,
        "termine": m.termine,
        "tardif": m.tardif,
        "score_dom": m.score_dom,
        "score_ext": m.score_ext,
        "quarts_dom": list(m.periodes_dom),
        "quarts_ext": list(m.periodes_ext),
        "prolongation_dom": m.prolongation_dom,
        "prolongation_ext": m.prolongation_ext,
        "score": score,
        "resume": resume or statut_affiche(m),
        "court": court,
        "horloge": m.horloge,
        "temps_restant": restant,
        "chrono": format_chrono(restant),
        "termine_le": datetime.fromtimestamp(m.termine_ts, tz).isoformat() if m.termine_ts else None,
    }
