/*
 * Carte « Aujourd'hui et demain » de Basket Live, avec pronostic par bascule à trois positions.
 *
 * Emplacement : /config/www/basket-a-venir-card.js, ressource /local/basket-a-venir-card.js (module).
 * Données : attribut `matchs` de sensor.basket_live_matchs_a_venir, et menus select publiés par
 * l'add-on (attributs `joueur`, `match_id`, options [—, domicile, extérieur]).
 *
 * Configuration :
 *   type: custom:basket-a-venir-card
 *   joueurs:                       # user_id HA -> joueur de l'add-on
 *     c2af4c5a136e448ab37deaae63146536: francis
 *     7521abea3321478f8c461ee465767fcb: ilona
 */

const VERSION = "1.0.0";
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
    this._config = { capteur: "sensor.basket_live_matchs_a_venir", joueurs: {}, ...config };
    this._enAttente = {}; // match_id -> côté choisi, en attendant la confirmation de HA
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      this.shadowRoot.addEventListener("click", (e) => this._clic(e));
    }
    this._signature = null;
  }

  set hass(hass) {
    this._hass = hass;
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
    const etat = this._hass?.states[this._config.capteur];
    const liste = etat?.attributes?.matchs;
    return Array.isArray(liste) ? [...liste].sort((a, b) => String(a.debut).localeCompare(String(b.debut))) : [];
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
    const parts = [capteur?.last_updated ?? "absent", this._joueur() ?? "-"];
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
    if (!this._hass?.states[this._config.capteur]) {
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
      const statut = m.code === 60 || m.code === 70 ? ` · <span class="statut">${echapper(m.statut)}</span>` : "";
      const menu = menus[m.id];
      html += `<div class="match"><div class="meta">${heure(d)} · ${drapeau} ${echapper(m.tournoi)}${statut}</div>`;
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
  .meta { font-size: 0.85em; color: var(--secondary-text-color); margin-bottom: 6px; }
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

customElements.define("basket-a-venir-card", BasketAVenirCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "basket-a-venir-card",
  name: "Basket Live · Aujourd'hui et demain",
  description: "Matchs à venir groupés par jour, pronostic par bascule à trois positions.",
});
console.info(`%c basket-a-venir-card ${VERSION} `, "background:#F26B1D;color:#fff;border-radius:3px");
