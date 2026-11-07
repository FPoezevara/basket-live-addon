/*
 * Carte « Les 7 prochains jours » : boutons Live personnels et pronostics à trois positions.
 *
 * Emplacement : /config/www/basket-a-venir-card.js, ressource /local/basket-a-venir-card.js (module).
 * Données : matchs à venir/en cours, choix de sensor.basket_live_suivis_<joueur>, et menus select publiés par
 * l'add-on (attributs `joueur`, `match_id`, options [—, domicile, extérieur]).
 *
 * Configuration :
 *   type: custom:basket-a-venir-card
 *   joueurs:                       # user_id HA -> joueur de l'add-on
 *     c2af4c5a136e448ab37deaae63146536: francis
 *     7521abea3321478f8c461ee465767fcb: ilona
 */

const VERSION = "1.3.0";
const EUROPE = new Set([138, 141, 9357, 2165]);
const AUCUN = "—";

const echapper = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const jourLong = (d) => {
  const j = d.toLocaleDateString("fr-FR", { weekday: "long" });
  const date = d.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
  return `${j.charAt(0).toUpperCase()}${j.slice(1)} ${date}`;
};

const heure = (d) => d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

class BasketAVenirCard extends HTMLElement {
  setConfig(config) {
    this._config = { capteur: "sensor.basket_live_matchs_a_venir", capteur_lives: "sensor.basket_live_lives_en_cours", joueurs: {}, ...config };
    for (const timer of Object.values(this._minuteursLive || {})) clearTimeout(timer);
    this._enAttenteLive = {};
    this._minuteursLive = {};
    this._erreursLive = {};
    this._enAttente = {}; // match_id -> côté choisi, en attendant la confirmation de HA
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (e) => this._clic(e));
    }
    this._signature = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._actualiserAttentesLive();
    const sig = this._calculerSignature();
    if (sig !== this._signature) {
      this._signature = sig;
      this._rendre();
    }
  }

  getCardSize() {
    return 3 + this._matchs().length;
  }

  // --- données -------------------------------------------------------------------------

  _joueur() {
    const id = this._hass?.user?.id;
    return (id && this._config.joueurs[id]) || null;
  }

  _matchs() {
    const futurs = this._hass?.states[this._config.capteur]?.attributes?.matchs;
    const lives = this._hass?.states[this._config.capteur_lives]?.attributes?.matchs;
    const matchs = new Map();
    for (const m of [...(Array.isArray(futurs) ? futurs : []), ...(Array.isArray(lives) ? lives : [])]) {
      const id = Number(m?.id);
      if (Number.isSafeInteger(id) && id > 0 && !m.termine) matchs.set(id, { ...m, id });
    }
    return [...matchs.values()].sort((a, b) => String(a.debut).localeCompare(String(b.debut)) || a.id - b.id);
  }

  _selection(joueur = this._joueur()) {
    const etat = this._hass?.states[`sensor.basket_live_suivis_${joueur}`];
    const choix = etat?.attributes?.choix;
    if (!joueur || !etat || ["unknown", "unavailable"].includes(etat.state)
        || !choix || typeof choix !== "object" || Array.isArray(choix)) return null;
    return choix;
  }

  _suiviConfirme(match, joueur = this._joueur()) {
    const explicite = this._selection(joueur)?.[match.id];
    if (typeof explicite === "boolean") return explicite;
    return match.categorie === "nanterre"
      && this._hass?.states[`input_boolean.basket_${joueur}_live_nanterre`]?.state === "on";
  }

  _suiviActif(match) {
    const attente = this._enAttenteLive[`${this._joueur()}:${match.id}`];
    return attente ? attente.actif : this._suiviConfirme(match);
  }

  _finirAttenteLive(cle) {
    clearTimeout(this._minuteursLive[cle]);
    delete this._minuteursLive[cle];
    delete this._enAttenteLive[cle];
  }

  _actualiserAttentesLive() {
    for (const [cle, attente] of Object.entries(this._enAttenteLive)) {
      if (this._selection(attente.joueur)?.[attente.matchId] === attente.actif) this._finirAttenteLive(cle);
    }
    for (const [joueur, erreur] of Object.entries(this._erreursLive)) {
      if (this._selection(joueur)?.[erreur.matchId] === erreur.actif
          || !this._matchs().some(m => m.id === erreur.matchId)) delete this._erreursLive[joueur];
    }
  }

  disconnectedCallback() {
    for (const cle of Object.keys(this._enAttenteLive)) this._finirAttenteLive(cle);
  }

  async _basculerLive(matchId) {
    const joueur = this._joueur();
    const match = this._matchs().find(m => m.id === matchId);
    const cle = `${joueur}:${matchId}`;
    if (!match || !this._selection() || this._enAttenteLive[cle]) return;
    const actif = !this._suiviConfirme(match);
    if (actif && [60, 70].includes(match.code)) return;
    const attente = { joueur, matchId, actif };
    this._enAttenteLive[cle] = attente;
    delete this._erreursLive[joueur];
    this._minuteursLive[cle] = setTimeout(() => {
      if (this._enAttenteLive[cle] !== attente) return;
      this._finirAttenteLive(cle);
      if (this._matchs().some(m => m.id === matchId)
          && this._selection(joueur)?.[matchId] !== actif) {
        this._erreursLive[joueur] = { matchId, actif, message: "Le suivi n’a pas été confirmé. Réessaie." };
      }
      this._signature = null;
      if (this._hass) this.hass = this._hass;
    }, 8000);
    this._signature = null;
    this._rendre();
    try {
      await this._hass.callService("script", "basket_live_selectionner", { personne: joueur, match_id: matchId, actif });
    } catch (err) {
      // Même si l'accusé MQTT est arrivé entre-temps, ne jamais annuler un choix confirmé.
      if (this._enAttenteLive[cle] === attente) {
        this._finirAttenteLive(cle);
        this._erreursLive[joueur] = { matchId, actif, message: "Le suivi n’a pas pu être modifié. Réessaie." };
        this._signature = null;
        if (this._hass) this.hass = this._hass;
      }
      console.error("basket-a-venir-card live", err);
    }
  }

  _menus() {
    const joueur = this._joueur();
    const menus = {};
    if (!joueur || !this._hass) return menus;
    for (const [entityId, etat] of Object.entries(this._hass.states)) {
      if (entityId.startsWith("select.") && etat.attributes?.joueur === joueur && etat.attributes?.match_id != null) {
        menus[etat.attributes.match_id] = { entityId, etat };
      }
    }
    return menus;
  }

  _calculerSignature() {
    const capteur = this._hass?.states[this._config.capteur];
    const menus = this._menus();
    const joueur = this._joueur();
    const parts = [capteur?.last_updated ?? "absent", joueur ?? "-",
      this._hass?.states[this._config.capteur_lives]?.last_updated ?? "absent",
      JSON.stringify(this._selection()),
      this._hass?.states[`input_boolean.basket_${joueur}_live_nanterre`]?.state ?? "off",
      JSON.stringify(this._enAttenteLive), JSON.stringify(this._erreursLive[joueur] ?? null)];
    for (const [id, m] of Object.entries(menus)) parts.push(`${id}=${m.etat.state}`);
    parts.push(JSON.stringify(this._enAttente));
    return parts.join("|");
  }

  _cote(menu, matchId) {
    if (matchId in this._enAttente) return this._enAttente[matchId];
    const opts = menu.etat.attributes.options || [];
    if (menu.etat.state === opts[1]) return "dom";
    if (menu.etat.state === opts[2]) return "ext";
    return "aucun";
  }

  // --- interaction ---------------------------------------------------------------------

  _clic(e) {
    const live = e.target.closest("[data-live]");
    if (live) {
      if (!live.disabled) void this._basculerLive(Number(live.dataset.live));
      return;
    }
    const cible = e.target.closest("[data-match][data-cote]");
    if (!cible) return;
    const matchId = Number(cible.dataset.match);
    const menu = this._menus()[matchId];
    if (!menu) return;
    let cote = cible.dataset.cote;
    // Un second appui sur l'équipe déjà choisie annule le pronostic
    if (cible.classList.contains("equipe") && this._cote(menu, matchId) === cote) cote = "aucun";
    const opts = menu.etat.attributes.options || [];
    const option = cote === "dom" ? opts[1] : cote === "ext" ? opts[2] : AUCUN;
    if (option === undefined) return;
    this._enAttente[matchId] = cote;
    this._signature = null;
    this._rendre();
    this._hass
      .callService("select", "select_option", { entity_id: menu.entityId, option })
      .catch((err) => console.error("basket-a-venir-card", err))
      .finally(() => {
        // L'add-on republie l'état du menu ; on lâche l'affichage provisoire après un court délai
        setTimeout(() => {
          delete this._enAttente[matchId];
          this._signature = null;
          if (this._hass) this.hass = this._hass;
        }, 4000);
      });
  }

  // --- rendu ---------------------------------------------------------------------------

  _rendre() {
    if (!this.shadowRoot || !this._config) return;
    const matchs = this._matchs();
    const menus = this._menus();
    let html = "";
    let jourCourant = "";
    if (!this._hass?.states[this._config.capteur] && matchs.length === 0) {
      html = `<div class="vide">Capteur ${echapper(this._config.capteur)} introuvable.</div>`;
    } else if (matchs.length === 0) {
      html = `<div class="vide">Aucun match prévu.</div>`;
    }
    for (const m of matchs) {
      const d = new Date(m.debut);
      const jour = jourLong(d);
      if (jour !== jourCourant) {
        jourCourant = jour;
        html += `<div class="jour">${echapper(jour)}</div>`;
      }
      const drapeau = EUROPE.has(m.tournoi_id) ? "🇪🇺" : "🇫🇷";
      const statut = m.en_cours || m.fin_provisoire || m.code === 60 || m.code === 70
        ? ` · <span class="statut">${echapper(m.statut)}</span>` : "";
      const menu = menus[m.id];
      const actif = this._suiviActif(m);
      const attente = Boolean(this._enAttenteLive[`${this._joueur()}:${m.id}`]);
      const indisponible = !this._selection() || (!actif && [60, 70].includes(m.code));
      const titreLive = indisponible ? "Suivi live indisponible"
        : `${actif ? "Arrêter" : "Suivre"} le live de ${m.titre || `${m.domicile} - ${m.exterieur}`}`;
      html += `<div class="match"><div class="meta"><span class="meta-texte">${heure(d)} · ${drapeau} ${echapper(m.tournoi)}${statut}</span>
        <button class="live-bouton${actif ? " actif" : ""}" data-live="${m.id}"
          aria-pressed="${actif}" aria-busy="${attente}" aria-label="${echapper(titreLive)}"
          title="${echapper(titreLive)}" ${attente || indisponible ? "disabled" : ""}>Live</button></div>`;
      if (menu) {
        const cote = this._cote(menu, m.id);
        html += `
          <div class="duel">
            <button class="equipe dom ${cote === "dom" ? "choisie" : ""}" data-match="${m.id}" data-cote="dom">${echapper(m.domicile)}</button>
            <div class="bascule ${cote}" role="radiogroup" aria-label="Pronostic">
              <button class="zone" data-match="${m.id}" data-cote="dom" aria-label="${echapper(m.domicile)}"></button>
              <button class="zone" data-match="${m.id}" data-cote="aucun" aria-label="Pas de pronostic"></button>
              <button class="zone" data-match="${m.id}" data-cote="ext" aria-label="${echapper(m.exterieur)}"></button>
              <span class="curseur"></span>
            </div>
            <button class="equipe ext ${cote === "ext" ? "choisie" : ""}" data-match="${m.id}" data-cote="ext">${echapper(m.exterieur)}</button>
          </div>`;
      } else {
        html += `<div class="duel sans"><span class="equipe dom">${echapper(m.domicile)}</span><span class="tiret">-</span><span class="equipe ext">${echapper(m.exterieur)}</span></div>`;
      }
      html += `</div>`;
    }
    const erreur = this._erreursLive[this._joueur()];
    if (erreur) html += `<div class="erreur-live" role="status">${echapper(erreur.message)}</div>`;
    const titre = this._config.titre ? `<h1 class="titre">${echapper(this._config.titre)}</h1>` : "";
    this.shadowRoot.innerHTML = `<style>${STYLE}</style><ha-card>${titre}<div class="contenu">${html}</div></ha-card>`;
  }
}

const STYLE = `
  :host { --accent: #F26B1D; }
  ha-card { padding: 12px 16px 16px; }
  .titre { font-size: 1.1em; font-weight: 500; margin: 0 0 4px; }
  .vide { color: var(--secondary-text-color); font-style: italic; padding: 4px 0; }
  .jour { font-weight: 600; margin: 14px 0 4px; color: var(--primary-text-color); }
  .jour:first-child { margin-top: 2px; }
  .match { padding: 6px 0 8px 12px; border-left: 2px solid var(--divider-color); margin-bottom: 4px; }
  .meta { display: flex; align-items: center; gap: 10px; font-size: 0.85em;
          color: var(--secondary-text-color); margin-bottom: 6px; }
  .meta-texte { flex: 1; min-width: 0; }
  .live-bouton { appearance: none; flex: none; margin-left: auto; min-height: 30px; padding: 3px 10px;
                 border: 1px solid currentColor; border-radius: 16px; color: #fff;
                 background: rgba(0,0,0,.24); font: inherit; font-size: .9em; font-weight: 600;
                 line-height: 1.2; cursor: pointer; transition: color .15s, background .15s; }
  .live-bouton.actif { color: var(--accent); background: rgba(242,107,29,.1); }
  .live-bouton:focus-visible { outline: 2px solid currentColor; outline-offset: 3px; }
  .live-bouton:disabled { cursor: default; opacity: .5; }
  .live-bouton[aria-busy="true"] { cursor: wait; opacity: .7; }
  .erreur-live { color: var(--error-color, #c62828); font-size: .85em; margin-top: 8px; }
  .statut { color: var(--error-color, #c62828); }
  .duel { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 10px; }
  .equipe { all: unset; cursor: pointer; color: var(--primary-text-color); line-height: 1.25;
            overflow-wrap: anywhere; transition: color .15s; }
  .duel.sans .equipe { cursor: default; }
  .equipe.dom { text-align: right; }
  .equipe.ext { text-align: left; }
  .equipe.choisie { color: var(--accent); font-weight: 600; }
  .tiret { color: var(--secondary-text-color); }
  .bascule { position: relative; width: 66px; height: 26px; border-radius: 13px;
             background: var(--divider-color); display: flex; transition: background .2s; }
  .bascule.dom, .bascule.ext { background: color-mix(in srgb, var(--accent) 35%, var(--divider-color)); }
  .zone { all: unset; flex: 1; cursor: pointer; z-index: 1; border-radius: 13px; }
  .zone:focus-visible { outline: 2px solid var(--accent); }
  .curseur { position: absolute; top: 3px; left: calc(50% - 10px); width: 20px; height: 20px; border-radius: 50%;
             background: var(--card-background-color, #fff); box-shadow: 0 1px 3px rgba(0,0,0,.35);
             transition: left .2s, background .2s; pointer-events: none; }
  .bascule.dom .curseur { left: 3px; background: var(--accent); }
  .bascule.ext .curseur { left: calc(100% - 23px); background: var(--accent); }
`;

/*
 * En-tête de l'onglet : titre encadré de deux ballons, sur un fond de terrain dessiné en SVG.
 *   type: custom:basket-entete-card
 *   titre: Basket Live          # facultatif
 */
const TERRAIN = `
  <svg class="terrain" viewBox="0 0 940 200" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <g fill="none" stroke="#fff" stroke-width="3">
      <rect x="10" y="10" width="920" height="180" rx="4"/>
      <line x1="470" y1="10" x2="470" y2="190"/>
      <circle cx="470" cy="100" r="42"/>
      <circle cx="470" cy="100" r="12"/>
      <rect x="10" y="62" width="130" height="76"/>
      <rect x="800" y="62" width="130" height="76"/>
      <path d="M140 62 A38 38 0 0 1 140 138"/>
      <path d="M800 62 A38 38 0 0 0 800 138"/>
      <path d="M10 22 L60 22 A150 150 0 0 1 60 178 L10 178"/>
      <path d="M930 22 L880 22 A150 150 0 0 0 880 178 L930 178"/>
    </g>
  </svg>`;

class BasketEnteteCard extends HTMLElement {
  setConfig(config) {
    this._config = { titre: "Basket Live", ...config };
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._rendre();
  }

  set hass(_hass) {}

  getCardSize() {
    return 2;
  }

  getGridOptions() {
    return { columns: "full", rows: 2, min_rows: 2 };
  }

  _rendre() {
    this.shadowRoot.innerHTML = `
      <style>${STYLE_ENTETE}</style>
      <ha-card>
        ${TERRAIN}
        <div class="bandeau">
          <span class="ballon gauche">🏀</span>
          <h1>${echapper(this._config.titre)}</h1>
          <span class="ballon droite">🏀</span>
        </div>
      </ha-card>`;
  }
}

const STYLE_ENTETE = `
  ha-card { display: block; container-type: inline-size; position: relative; overflow: hidden; height: 100%; min-height: 104px; border: none;
            background:
              radial-gradient(ellipse at 50% 120%, rgba(255,255,255,.18), transparent 60%),
              linear-gradient(135deg, #F26B1D 0%, #C2410C 48%, #7C2D12 78%, #1C1917 100%); }
  .terrain { position: absolute; inset: 0; width: 100%; height: 100%; opacity: .16; }
  .bandeau { position: relative; height: 100%; min-height: 104px; display: flex; align-items: center;
             justify-content: center; gap: clamp(8px, 3cqw, 18px); padding: 0 12px; box-sizing: border-box; }
  h1 { margin: 0; color: #fff; font-size: clamp(1.2rem, 7.5cqw, 2.4rem); font-weight: 800; letter-spacing: .05em;
       text-transform: uppercase; text-shadow: 0 2px 10px rgba(0,0,0,.35); white-space: nowrap; }
  .ballon { font-size: clamp(1.2rem, 7cqw, 2.3rem); filter: drop-shadow(0 3px 4px rgba(0,0,0,.4));
            animation: rebond 2.8s ease-in-out infinite; }
  .ballon.droite { animation-delay: 1.4s; }
  @keyframes rebond { 0%, 100% { transform: translateY(0) rotate(0); } 50% { transform: translateY(-5px) rotate(20deg); } }
  @media (prefers-reduced-motion: reduce) { .ballon { animation: none; } }
`;

customElements.define("basket-a-venir-card", BasketAVenirCard);
customElements.define("basket-entete-card", BasketEnteteCard);
window.customCards = window.customCards || [];
window.customCards.push(
  {
    type: "basket-a-venir-card",
    name: "Basket Live · Les 7 prochains jours",
    description: "Matchs à venir et en cours, boutons Live personnels et pronostics.",
  },
  { type: "basket-entete-card", name: "Basket Live · En-tête", description: "Titre sur fond de terrain de basket." },
);
console.info(`%c basket-a-venir-card ${VERSION} `, "background:#F26B1D;color:#fff;border-radius:3px");
