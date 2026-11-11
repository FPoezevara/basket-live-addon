/* Basket Live · Historique de saison 1.4.0 (badges du concours). Données MQTT locales uniquement : aucun appel API. */
const HIST_VERSION = '1.4.0';
const histEscape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const histNumber = value => value === null || value === undefined || value === '' ? '—'
  : typeof value === 'number' ? new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 2}).format(value) : String(value);
const histLabels = {
  points:'Points', rebounds:'Rebonds', totalRebounds:'Rebonds', assists:'Passes décisives', steals:'Interceptions', blocks:'Contres',
  turnovers:'Balles perdues', personalFouls:'Fautes personnelles', fouls:'Fautes', offensiveRebounds:'Rebonds offensifs', defensiveRebounds:'Rebonds défensifs',
  fieldGoalsMade:'Tirs réussis', fieldGoalAttempts:'Tirs tentés', fieldGoalPct:'Réussite aux tirs (valeur fournie)',
  twoPointsMade:'Tirs à 2 pts réussis', twoPointAttempts:'Tirs à 2 pts tentés', threePointsMade:'Tirs à 3 pts réussis', threePointAttempts:'Tirs à 3 pts tentés',
  freeThrowsMade:'Lancers francs réussis', freeThrowAttempts:'Lancers francs tentés', secondsPlayed:'Temps joué (secondes)', minutesPlayed:'Temps joué (minutes)',
  plusMinus:'Plus / moins', rating:'Note fournisseur', evaluation:'Évaluation fournie', efficiency:'Efficacité fournie', fieldGoals:'Tirs', twoPointers:'Tirs à 2 points', threePointers:'Tirs à 3 points', freeThrows:'Lancers francs',
  biggestLead:'Plus grand écart', biggestScoringRun:'Plus grande série', leadChanges:'Changements de leader', timeSpentInLead:'Temps en tête',
  fastBreakPoints:'Points en contre-attaque', pointsInPaint:'Points dans la raquette', benchPoints:'Points du banc', secondChancePoints:'Points sur seconde chance',
  pointsFromTurnovers:'Points après perte de balle', ALL:'Match', all:'Match', '1ST':'QT1', '2ND':'QT2', '3RD':'QT3', '4TH':'QT4',
  '1':'QT1','2':'QT2','3':'QT3','4':'QT4', OT:'Prolongation', 'Rebounds':'Rebonds', 'Scoring':'Tirs et points',
  'Other':'Autres indicateurs', 'Match overview':'Vue d’ensemble', 'Assists':'Passes décisives', 'Steals':'Interceptions', 'Blocks':'Contres', 'Turnovers':'Balles perdues'
};
Object.assign(histLabels, {
  'free throws':'Lancers francs', 'free throw percentage':'Réussite aux lancers francs', 'free throws percentage':'Réussite aux lancers francs',
  '2 pointers':'Tirs à 2 points', '3 pointers':'Tirs à 3 points', 'two pointers':'Tirs à 2 points', 'three pointers':'Tirs à 3 points',
  'field goals':'Tirs', 'field goal percentage':'Réussite aux tirs', '2 pointers percentage':'Réussite à 2 points', '3 pointers percentage':'Réussite à 3 points',
  'two point shots':'Tirs à 2 points', 'three point shots':'Tirs à 3 points', 'fouls':'Fautes', 'personal fouls':'Fautes personnelles',
  'free throws %':'Réussite aux lancers francs', '2 pointers %':'Réussite à 2 points', '3 pointers %':'Réussite à 3 points', 'field goals %':'Réussite aux tirs',
  'points in the paint':'Points dans la raquette', 'fast break points':'Points en contre-attaque', 'second chance points':'Points sur seconde chance',
  'points from turnovers':'Points après perte de balle', 'points off turnovers':'Points après perte de balle', 'bench points':'Points du banc',
  'biggest lead':'Plus grand écart', 'biggest scoring run':'Plus grande série', 'lead changes':'Changements de leader', 'time spent in lead':'Temps en tête',
  'scoring':'Tirs et points', 'shooting':'Tirs et points', 'points':'Points', 'rebounds':'Rebonds', 'assists':'Passes décisives',
  'steals':'Interceptions', 'blocks':'Contres', 'turnovers':'Balles perdues', 'offensive rebounds':'Rebonds offensifs', 'defensive rebounds':'Rebonds défensifs'
});
const histLabel = key => histLabels[key] || histLabels[String(key ?? '').trim().toLowerCase().replace(/\s+/g,' ')] || String(key ?? '').replace(/([a-zà-ÿ])([A-Z])/g, '$1 $2').replace(/_/g, ' ').replace(/^./, s => s.toUpperCase());
const histUnwrap = raw => {
  let data = raw;
  for (let i = 0; i < 4 && data && !Array.isArray(data) && typeof data === 'object' && data.data != null; i++) data = data.data;
  return data;
};
const histFlatten = (data, prefix = '') => {
  const result = [];
  if (!data || typeof data !== 'object') return result;
  for (const [key, value] of Object.entries(data)) {
    if (key === 'statisticsType' || value == null) continue;
    const label = prefix ? `${prefix} · ${histLabel(key)}` : histLabel(key);
    if (typeof value === 'object' && !Array.isArray(value)) result.push(...histFlatten(value, label));
    else result.push([label, Array.isArray(value) ? value.map(histNumber).join(' · ') : histNumber(value)]);
  }
  return result;
};
function histPeriods(raw) {
  const data = histUnwrap(raw);
  const stats = Array.isArray(data) ? data : data?.statistics;
  if (Array.isArray(stats)) {
    if (stats.some(p => Array.isArray(p.statisticsItems))) return [{period:'ALL',groups:stats}];
    if (stats.some(p => p.home !== undefined || p.away !== undefined)) return [{period:'ALL',groups:[{groupName:'Statistiques',statisticsItems:stats}]}];
    return stats.map((p, i) => ({period: String(p.period ?? (i ? i : 'ALL')), groups: Array.isArray(p.groups) ? p.groups : []}));
  }
  if (stats && typeof stats === 'object') return Object.entries(stats).map(([period,p]) => ({period,groups:Array.isArray(p) ? p : p.groups || []}));
  if (Array.isArray(data?.groups)) return [{period: 'ALL', groups: data.groups}];
  const home = data?.home, away = data?.away;
  if (home && away && typeof home === 'object' && typeof away === 'object') {
    const h = new Map(histFlatten(home)), a = new Map(histFlatten(away));
    return [{period: 'ALL', groups: [{groupName: 'Autres indicateurs', statisticsItems: [...new Set([...h.keys(), ...a.keys()])]
      .map(name => ({name, home: h.get(name), away: a.get(name)}))}]}];
  }
  return [];
}
function histLineups(raw) {
  const data = histUnwrap(raw);
  return data?.lineups && !data.home ? data.lineups : data || {};
}
const histMinutes = row => {
  const seconds = row.statistics?.secondsPlayed;
  if (typeof seconds === 'number' && Number.isFinite(seconds)) return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  return row.minutesPlayed ?? row.statistics?.minutesPlayed ?? '—';
};
const histShot = (stats, made, attempts) => stats[made] != null && stats[attempts] != null ? `${stats[made]}/${stats[attempts]}` : '—';

// EFF classique : aucun lien avec la note rating. Les champs absents ne valent pas zéro.
function histEvaluation(s) {
  const nombre = value => value !== null && value !== undefined && value !== '' && typeof value !== 'boolean'
    && Number.isFinite(Number(value)) && Number.isInteger(Number(value)) ? Number(value) : null;
  const prendre = (...keys) => { for (const k of keys) { const n = nombre(s[k]); if (n !== null) return n; } return null; };
  const somme = (a,b) => a !== null && b !== null ? a+b : null;
  const reb = prendre('rebounds','totalRebounds') ?? somme(prendre('offensiveRebounds'),prendre('defensiveRebounds'));
  const marques = prendre('fieldGoalsMade') ?? somme(prendre('twoPointsMade'),prendre('threePointsMade'));
  const tentes = prendre('fieldGoalAttempts') ?? somme(prendre('twoPointAttempts'),prendre('threePointAttempts'));
  const valeurs = [prendre('points'),reb,prendre('assists'),prendre('steals'),prendre('blocks'),marques,tentes,
    prendre('freeThrowsMade'),prendre('freeThrowAttempts'),prendre('turnovers')];
  if (valeurs.some(n => n === null || n < 0) || marques > tentes || valeurs[7] > valeurs[8]) return null;
  return valeurs[0]+valeurs[1]+valeurs[2]+valeurs[3]+valeurs[4]-(tentes-marques)-(valeurs[8]-valeurs[7])-valeurs[9];
}
const histDrapeau = m => m.categorie === 'europe' || [138,141,9357,2165].includes(Number(m.tournoi_id)) ? '🇪🇺' : '🇫🇷';

function histScoreQuarts(m) {
  const dom = Array.isArray(m.quarts_dom) ? m.quarts_dom : [];
  const ext = Array.isArray(m.quarts_ext) ? m.quarts_ext : [];
  const prolongation = m.prolongation_dom != null || m.prolongation_ext != null;
  return `<div class="quarts"><table><caption>Score par quart-temps</caption><thead><tr><th scope="col">Équipe</th>${[1,2,3,4].map(i => `<th scope="col">QT${i}</th>`).join('')}${prolongation ? '<th scope="col">Prol.</th>' : ''}<th scope="col">Total</th></tr></thead><tbody>
    <tr><th scope="row">${histEscape(m.domicile)}</th>${[0,1,2,3].map(i => `<td>${histEscape(histNumber(dom[i]))}</td>`).join('')}${prolongation ? `<td>${histEscape(histNumber(m.prolongation_dom))}</td>` : ''}<td><b>${histEscape(histNumber(m.score_dom))}</b></td></tr>
    <tr><th scope="row">${histEscape(m.exterieur)}</th>${[0,1,2,3].map(i => `<td>${histEscape(histNumber(ext[i]))}</td>`).join('')}${prolongation ? `<td>${histEscape(histNumber(m.prolongation_ext))}</td>` : ''}<td><b>${histEscape(histNumber(m.score_ext))}</b></td></tr></tbody></table></div>`;
}

class BasketHistoriqueCard extends HTMLElement {
  setConfig(config) {
    this._config = {capteur: 'sensor.basket_live_resultats_saison', ...config};
    this._ouverts = this._ouverts || new Set();
    this._periodes = this._periodes || new Map();
    this._equipes = this._equipes || new Map();
    this._filtre = this._filtre || 'tous';
    if (!this.shadowRoot) {
      this.attachShadow({mode: 'open'});
      this.shadowRoot.addEventListener('toggle', e => {
        if (e.target.matches?.('details[data-match]')) {
          const id = Number(e.target.dataset.match);
          e.target.open ? this._ouverts.add(id) : this._ouverts.delete(id);
        }
      }, true);
      this.shadowRoot.addEventListener('click', e => {
        const cible = e.target.closest('[data-filtre], [data-periode], [data-equipe]');
        if (!cible) return;
        if (cible.dataset.filtre) this._filtre = cible.dataset.filtre;
        else if (cible.dataset.periode) this._periodes.set(Number(cible.dataset.matchId), cible.dataset.periode);
        else if (cible.dataset.equipe) this._equipes.set(Number(cible.dataset.matchId), cible.dataset.equipe);
        this._rendre();
      });
    }
    this._signature = null;
  }
  set hass(hass) {
    this._hass = hass;
    const source = hass.states[this._config.capteur];
    const details = this._matchs().filter(m => this._nanterre(m)).map(m => this._detailEtat(m.id)?.last_updated ?? 'absent');
    const signature = [source?.last_updated, source?.state, ...details].join('|');
    if (signature !== this._signature) { this._signature = signature; this._rendre(); }
  }
  getCardSize() { return 5 + this._matchs().length; }
  getGridOptions() { return {columns: 'full', min_columns: 6}; }
  _nanterre(m) { return m.categorie === 'nanterre'; }
  _matchs() {
    const liste = this._hass?.states[this._config.capteur]?.attributes?.matchs;
    return Array.isArray(liste) ? liste.filter(m => Number.isSafeInteger(Number(m?.id)) && Number(m.id) > 0).map(m => ({...m,id:Number(m.id)})).sort((a, b) => String(b.debut).localeCompare(String(a.debut)) || b.id - a.id) : [];
  }
  _detailEtat(id) {
    const direct = this._hass?.states[`sensor.basket_live_statistiques_${id}`];
    if (direct) return direct;
    return Object.values(this._hass?.states || {}).find(e => e.attributes?.type === 'basket_statistiques' && Number(e.attributes?.match_id) === id);
  }
  _details(m) {
    const etat = this._detailEtat(m.id);
    if (!etat || ['unavailable', 'unknown'].includes(etat.state)) return '<p class="notice">Les statistiques archivées ne sont pas encore disponibles.</p>';
    const d = etat.attributes;
    const periodes = histPeriods(d.statistics?.reponse);
    const composition = histLineups(d.lineups?.reponse);
    let html = histScoreQuarts(m);
    html += '<section class="stat-section"><h3>Comparaison des équipes</h3>';
    if (periodes.length && periodes.some(p => p.groups.some(g => g.statisticsItems?.length))) {
      const choisi = this._periodes.get(m.id) || periodes.find(p => ['ALL', 'all'].includes(p.period))?.period || periodes[0].period;
      const periode = periodes.find(p => p.period === choisi) || periodes[0];
      html += `<div class="pills" aria-label="Période des statistiques">${periodes.map(p => `<button data-periode="${histEscape(p.period)}" data-match-id="${m.id}" aria-pressed="${p === periode}">${histEscape(histLabel(p.period))}</button>`).join('')}</div>`;
      html += `<div class="equipes-stats"><span>${histEscape(m.domicile)}</span><span>${histEscape(m.exterieur)}</span></div>`;
      for (const groupe of periode.groups) {
        if (!Array.isArray(groupe.statisticsItems)) continue;
        html += `<h4>${histEscape(histLabel(groupe.groupName || 'Statistiques'))}</h4>`;
        for (const item of groupe.statisticsItems) {
          const dom = item.home ?? item.homeValue, ext = item.away ?? item.awayValue;
          const h = Math.max(0, parseFloat(String(item.homeValue ?? dom))) || 0;
          const a = Math.max(0, parseFloat(String(item.awayValue ?? ext))) || 0;
          const part = h + a ? h * 100 / (h + a) : 50;
          const label = histLabels[item.key] || histLabel(item.name || item.key || 'Indicateur');
          html += `<div class="stat"><div class="stat-valeurs"><b>${histEscape(histNumber(dom))}</b><span>${histEscape(label)}</span><b>${histEscape(histNumber(ext))}</b></div>
            <div class="barre" aria-hidden="true"><i class="dom" style="width:${part.toFixed(2)}%"></i><i class="ext" style="width:${(100-part).toFixed(2)}%"></i></div></div>`;
        }
      }
    } else html += this._notice(d.statistics, d.historique);
    html += '</section><section class="stat-section"><h3>Feuille de match · joueurs</h3>';
    const cotes = ['home', 'away'].filter(c => Array.isArray(composition[c]?.players) && composition[c].players.length);
    if (!cotes.length) html += this._notice(d.lineups, d.historique);
    else {
      const nanterreId = this._hass?.states[this._config.capteur]?.attributes?.equipe_nanterre;
      const defaut = Number(m.exterieur_id) === Number(nanterreId) || /nanterre/i.test(m.exterieur) ? 'away' : 'home';
      const cote = cotes.includes(this._equipes.get(m.id)) ? this._equipes.get(m.id) : cotes.includes(defaut) ? defaut : cotes[0];
      html += `<div class="pills" aria-label="Équipe des joueurs">${cotes.map(c => `<button data-equipe="${c}" data-match-id="${m.id}" aria-pressed="${c === cote}">${histEscape(c === 'home' ? m.domicile : m.exterieur)}</button>`).join('')}</div>`;
      html += this._joueurs(composition[cote].players);
    }
    html += '</section>';
    const collecte = Math.max(d.statistics?.tente_le || 0, d.lineups?.tente_le || 0);
    if (collecte) html += `<p class="cache">Données enregistrées le ${histEscape(new Date(collecte * 1000).toLocaleString('fr-FR'))} · consultation locale</p>`;
    return html;
  }
  _notice(ressource, historique) {
    const etat = ressource?.etat;
    const texte = etat === 'en_attente' || etat === 'reserve'
      ? historique ? 'Collecte prévue lors d’une journée sans match, selon le quota disponible.' : 'Collecte planifiée 15 minutes après la fin confirmée du match.'
      : etat === 'interrompu' ? 'La collecte a été interrompue. Aucun nouvel appel automatique n’est effectué.'
      : etat === 'indisponible' ? 'Ces données n’ont pas pu être récupérées lors de la collecte unique.'
      : 'Aucune donnée fournie pour cette rubrique.';
    return `<p class="notice">${histEscape(texte)}</p>`;
  }
  _joueurs(joueurs) {
    const lignes = [...joueurs].sort((a,b) => Boolean(a.substitute) - Boolean(b.substitute) || (b.statistics?.points ?? -1) - (a.statistics?.points ?? -1));
    const nom = r => r.player?.name || r.player?.shortName || r.name || 'Joueur';
    const colonnes = ['MIN','PTS','TIRS','2 PTS','3 PTS','LF','REB','PD','INT','CTR','BP','FP','+/−','ÉVAL'];
    let html = `<div class="table-scroll" tabindex="0" aria-label="Statistiques des joueurs, tableau défilant"><table class="boxscore"><caption>Statistiques des joueurs · R/T : réussis / tentés</caption><thead><tr><th scope="col">Joueur</th>${colonnes.map(c => `<th scope="col">${c}</th>`).join('')}</tr></thead><tbody>`;
    for (const r of lignes) {
      const s = r.statistics || {};
      const valeurs = [histMinutes(r), s.points, histShot(s,'fieldGoalsMade','fieldGoalAttempts'), histShot(s,'twoPointsMade','twoPointAttempts'),
        histShot(s,'threePointsMade','threePointAttempts'), histShot(s,'freeThrowsMade','freeThrowAttempts'), s.rebounds ?? s.totalRebounds,
        s.assists, s.steals, s.blocks, s.turnovers, s.personalFouls ?? s.fouls, s.plusMinus, histEvaluation(s)];
      html += `<tr><th scope="row"><span class="numero">${histEscape(r.jerseyNumber ?? r.shirtNumber ?? r.player?.jerseyNumber ?? '')}</span>${histEscape(nom(r))}${r.substitute === false ? '<small>5 de départ</small>' : ''}</th>${valeurs.map(v => `<td>${histEscape(histNumber(v))}</td>`).join('')}</tr>`;
    }
    html += '</tbody></table></div><p class="legende">MIN : temps joué · PD : passes décisives · INT : interceptions · CTR : contres · BP : balles perdues · FP : fautes personnelles · ÉVAL : EFF calculée (points + rebonds + passes + interceptions + contres − tirs ratés − LF ratés − balles perdues). La note fournisseur est distincte ; — si données insuffisantes.</p>';
    html += '<details class="complements"><summary>Tous les indicateurs disponibles par joueur</summary><div class="indicateurs">';
    for (const r of lignes) {
      const valeurs = histFlatten(r.statistics || {});
      html += `<section><h4>${histEscape(nom(r))}</h4>${valeurs.length ? `<dl>${valeurs.map(([k,v]) => `<div><dt>${histEscape(k)}</dt><dd>${histEscape(v)}</dd></div>`).join('')}</dl>` : '<p class="notice">Aucune statistique individuelle fournie.</p>'}</section>`;
    }
    return html + '</div></details>';
  }
  _pronos(m) {
    const p = m.pronostics || {};
    const cellule = (j, nom, avant) => {
      const choix = p.pronos?.[j], resultat = p.resultats?.[j];
      const connu = choix != null && typeof resultat === 'boolean';
      const points = connu ? histNumber(p.points?.[j] ?? 0) : '—';
      const couleur = connu ? resultat ? 'prono-gagne' : 'prono-perdu' : 'prono-absent';
      const titre = connu ? `${nom} : ${choix} · ${resultat ? 'gagné' : 'perdu'}` : `${nom} : aucun pronostic enregistré`;
      return `<span class="${couleur}" title="${histEscape(titre)}">${avant ? `${nom} ${points}` : `${points} ${nom}`}</span>`;
    };
    return `<span class="pronos-match" aria-label="Points des pronostics">${cellule('ilona','Ilona',true)}<span> - </span>${cellule('francis','Francis',false)}</span>`;
  }
  _ligne(m) {
    const date = new Date(m.debut);
    const nanterre = this._nanterre(m);
    const ligne = `<div class="result-meta"><span>${histEscape(date.toLocaleDateString('fr-FR', {weekday:'short',day:'numeric',month:'short'}))}</span><span>${histDrapeau(m)} ${histEscape(m.tournoi)}</span>${nanterre ? '<em>Nanterre</em>' : ''}${this._pronos(m)}</div>
      <div class="result-score"><span class="equipe-nom ${m.score_dom > m.score_ext ? 'gagnant' : ''}">${histEscape(m.domicile)}</span><strong>${histEscape(histNumber(m.score_dom))}<span>–</span>${histEscape(histNumber(m.score_ext))}</strong><span class="equipe-nom droite ${m.score_ext > m.score_dom ? 'gagnant' : ''}">${histEscape(m.exterieur)}</span>${nanterre ? '<span class="chevron" aria-hidden="true">⌄</span>' : ''}</div>`;
    if (!nanterre) return `<div class="resultat simple">${ligne}</div>`;
    return `<details class="resultat nanterre" data-match="${Number(m.id)}" ${this._ouverts.has(Number(m.id)) ? 'open' : ''}>
      <summary aria-label="Statistiques de ${histEscape(m.titre || `${m.domicile} - ${m.exterieur}`)}">${ligne}</summary>
      <div class="details-match">${this._details(m)}</div></details>`;
  }
  _rendre() {
    if (!this.shadowRoot || !this._hass) return;
    const source = this._hass.states[this._config.capteur];
    const attrs = source?.attributes || {};
    const tous = this._matchs();
    const nanterre = tous.filter(m => this._nanterre(m));
    const liste = this._filtre === 'nanterre' ? nanterre : tous;
    let corps = '';
    let mois = '';
    for (const m of liste) {
      const courant = new Date(m.debut).toLocaleDateString('fr-FR', {month:'long',year:'numeric'});
      if (courant !== mois) { mois = courant; corps += `<h2 class="mois">${histEscape(mois)}</h2>`; }
      corps += this._ligne(m);
    }
    if (!corps) corps = '<p class="notice">Aucun résultat archivé pour cette sélection.</p>';
    const importation = attrs.import || {};
    const messages = {attente_jour_sans_match:'',
      marge_quota_preservee:'Import en pause pour préserver la marge de quota.', en_cours:'Import progressif de la saison en cours.'};
    const importTexte = importation.erreur ? 'Import partiel : une source est momentanément indisponible.' : messages[importation.etat];
    this.shadowRoot.innerHTML = `<style>${HIST_STYLE}</style><ha-card><header class="hero"><span class="kicker">BASKET LIVE · ARCHIVES</span>
      <h1>Saison ${histEscape(attrs.saison || 'en cours')}</h1><p>Les résultats de la saison. Les rencontres de Nanterre se déplient pour retrouver la feuille de match.</p>
      <div class="compteurs"><span><b>${tous.length}</b> résultats</span><span><b>${nanterre.length}</b> matchs de Nanterre</span></div></header>
      <div class="contenu"><div class="pills filtres"><button data-filtre="tous" aria-pressed="${this._filtre === 'tous'}">Tous les matchs</button><button data-filtre="nanterre" aria-pressed="${this._filtre === 'nanterre'}">Nanterre</button></div>
      ${!source || ['unknown','unavailable'].includes(source.state) ? '<p class="notice">Les archives sont momentanément indisponibles.</p>' : ''}
      ${importTexte ? `<p class="import-info">${histEscape(importTexte)}</p>` : ''}${corps}</div></ha-card>`;
  }
}
const HIST_STYLE = `
  :host { --vert:#66c879; --orange:#f26b1d; display:block; color:var(--primary-text-color,#eef1f4); }
  * { box-sizing:border-box; } ha-card { display:block; overflow:hidden; border-radius:18px; }
  .hero { padding:24px; color:#fff; background:radial-gradient(circle at 105% 110%,transparent 0 72px,#ffffff0b 73px 75px,transparent 76px 125px,#ffffff0b 126px 128px,transparent 129px),linear-gradient(125deg,#102f23,#163f2d 60%,#121d22); }
  .kicker { color:#92cda4; font-size:10px; font-weight:700; letter-spacing:.16em; } h1 { margin:8px 0; font-size:clamp(24px,4vw,36px); font-weight:800; letter-spacing:-.04em; }
  .hero p { max-width:580px; margin:0; line-height:1.5; font-size:13px; color:#d3dfd8; }
  .compteurs { display:flex; flex-wrap:wrap; gap:20px; margin-top:20px; font-size:11px; color:#c1d2c7; }.compteurs b{font-size:22px;color:white;margin-right:4px;}
  .contenu { padding:16px 20px 24px; }.pills{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0 16px;}.pills button{font:inherit;font-size:12px;padding:7px 12px;border:1px solid var(--divider-color,#3b434b);border-radius:20px;color:var(--secondary-text-color,#b7c0c9);background:transparent;cursor:pointer;}
  .pills button[aria-pressed="true"]{color:var(--vert);border-color:var(--vert);background:#66c87910;}.pills button:focus-visible,summary:focus-visible{outline:2px solid var(--orange);outline-offset:3px;}
  .import-info,.notice,.cache,.legende{font-size:12px;line-height:1.5;color:var(--secondary-text-color,#aab5bf);}.import-info{border-left:2px solid var(--orange);padding-left:10px;}.mois{margin:26px 0 10px;font-size:13px;font-weight:700;text-transform:capitalize;color:var(--secondary-text-color,#aab5bf);}
  .resultat{margin:0 0 8px;border:1px solid var(--divider-color,#333c43);border-radius:12px;overflow:hidden;}.resultat.simple{padding:12px 14px;}.resultat.nanterre{border-left:3px solid var(--vert);}.resultat>summary{padding:12px 14px;list-style:none;cursor:pointer;}.resultat>summary::-webkit-details-marker{display:none;}.resultat[open]>summary{background:#66c8790a;}
  .result-meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:10px;color:var(--secondary-text-color,#aab5bf);}.result-meta>span:nth-child(2){flex:1;}.result-meta em{font-style:normal;font-size:9px;padding:2px 6px;border-radius:4px;color:var(--vert);background:#66c87912;}
  .pronos-match{margin-left:auto;white-space:nowrap;font-size:11px;font-weight:600;}.prono-gagne{color:var(--vert);}.prono-perdu{color:var(--orange);}.prono-absent{color:var(--secondary-text-color,#aab5bf);}
  .result-score{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr) 12px;align-items:center;gap:10px;margin-top:7px;}.simple .result-score{grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);}.result-score strong{font-variant-numeric:tabular-nums;font-size:23px;font-weight:800;white-space:nowrap;letter-spacing:-.04em;}.result-score strong span{font-size:15px;color:var(--secondary-text-color,#aab5bf);padding:0 7px;}
  .equipe-nom{font-size:13px;line-height:1.35;overflow-wrap:anywhere;}.equipe-nom.droite{text-align:right;}.gagnant{font-weight:700;}.chevron{color:var(--vert);font-size:19px;transition:transform .15s;}.resultat[open] .chevron{transform:rotate(180deg);}
  .details-match{padding:0 16px 16px;border-top:1px solid var(--divider-color,#333c43);}.stat-section{margin-top:24px;}h3{font-size:15px;margin:0 0 10px;}h4{font-size:11px;letter-spacing:.03em;color:var(--secondary-text-color,#aab5bf);margin:20px 0 12px;}.equipes-stats{display:flex;justify-content:space-between;gap:16px;font-size:11px;font-weight:700;}.equipes-stats span:last-child{text-align:right;}
  .stat{margin-bottom:14px;}.stat-valeurs{display:grid;grid-template-columns:65px minmax(0,1fr) 65px;align-items:center;gap:8px;font-size:12px;}.stat-valeurs>b:last-child{text-align:right;}.stat-valeurs>span{text-align:center;color:var(--secondary-text-color,#aab5bf);font-size:11px;}.barre{display:flex;height:4px;gap:3px;margin-top:6px;border-radius:4px;overflow:hidden;}.barre i{display:block;border-radius:3px;}.barre .dom{background:var(--vert);}.barre .ext{background:var(--orange);}
  .quarts,.table-scroll{overflow-x:auto;margin-top:16px;}table{width:100%;border-collapse:collapse;font-size:11px;font-variant-numeric:tabular-nums;}caption{text-align:left;color:var(--secondary-text-color,#aab5bf);font-size:10px;padding:0 0 8px;}th,td{padding:9px 8px;border-bottom:1px solid var(--divider-color,#333c43);text-align:right;white-space:nowrap;}th:first-child{text-align:left;}thead th{font-size:9px;font-weight:700;color:var(--secondary-text-color,#aab5bf);}.boxscore th:first-child{position:sticky;left:0;z-index:1;background:var(--card-background-color,#1c2228);min-width:160px;max-width:210px;white-space:normal;font-weight:500;}.boxscore td:nth-child(3){font-weight:800;color:var(--vert);}.boxscore small{display:block;font-size:8px;color:var(--secondary-text-color,#aab5bf);padding-left:20px;margin-top:2px;}.numero{display:inline-block;min-width:20px;color:var(--secondary-text-color,#aab5bf);font-size:9px;}.legende{font-size:10px;}
  .complements{margin-top:16px;}.complements>summary{font-size:12px;color:var(--vert);cursor:pointer;padding:10px 0;}.indicateurs{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:0 24px;}dl{margin:0;}dl>div{display:flex;justify-content:space-between;gap:12px;font-size:11px;padding:6px 0;border-bottom:1px solid var(--divider-color,#333c43);}dt{color:var(--secondary-text-color,#aab5bf);}dd{margin:0;text-align:right;font-weight:600;}.cache{font-size:10px;margin:20px 0 0;}
  @media(max-width:520px){.hero{padding:20px;}.contenu{padding:12px 12px 18px;}.result-score{gap:6px;}.equipe-nom{font-size:12px;}.result-score strong{font-size:20px;}.details-match{padding:0 10px 12px;}.stat-valeurs{grid-template-columns:50px minmax(0,1fr) 50px;}}
`;
customElements.define('basket-historique-card', BasketHistoriqueCard);
window.customCards = window.customCards || [];
window.customCards.push({type:'basket-historique-card',name:'Basket Live · Historique de saison',description:'Résultats de saison et feuilles de match Nanterre en accordéon.'});
console.info(`Basket Live · Historique ${HIST_VERSION}`);

class BasketPronosticsCard extends HTMLElement {
  setConfig(config) {
    this._recents = config.mode === 'recents';
    this._sources = this._recents
      ? ['sensor.basket_live_resultats']
      : ['sensor.basket_live_classement', 'sensor.basket_live_pronostics'];
    this._sourcesPrecedentes = [];
    if (!this.shadowRoot) this.attachShadow({mode: 'open'});
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._sources) return;
    const sources = this._sources.map(id => hass.states[id]);
    if (sources.length === this._sourcesPrecedentes.length &&
        sources.every((source, i) => source === this._sourcesPrecedentes[i])) return;
    this._sourcesPrecedentes = sources;
    const [premiere, seconde] = sources.map(source => source?.attributes || {});
    const baremeOuvert = this.shadowRoot.querySelector('details.bareme')?.open;
    const contenu = this._recents
      ? this._resultatsRecents(premiere.matchs || [])
      : this._concours(premiere, seconde, baremeOuvert);
    this._contenu = contenu;
    this._classement = premiere;
    this._rendre();
  }

  _rendre() {
    this.shadowRoot.innerHTML = `<style>${HIST_STYLE}${PRONOS_STYLE}${BADGES_STYLE}</style><ha-card>${this._contenu}${this._fiche()}</ha-card>`;
    if (!this._ecoute) {
      this._ecoute = true;
      this.shadowRoot.addEventListener('click', e => {
        const badge = e.target.closest?.('button.badge');
        if (badge) {
          this._ouvert = {joueur: badge.dataset.joueur, i: Number(badge.dataset.i)};
          this._rendre();
          return;
        }
        // Croix, ou appui sur le fond (la cible est alors la boîte de dialogue elle-même)
        const dialogue = e.target.closest?.('dialog.fiche-badge');
        if (dialogue && (e.target === dialogue || e.target.closest('.fermer'))) dialogue.close();
      });
    }
    const dialogue = this.shadowRoot.querySelector?.('dialog.fiche-badge');
    if (dialogue) {
      // Échap ou fermeture : la boîte se ferme d'elle-même, il suffit d'oublier la fiche ouverte.
      dialogue.addEventListener('close', () => { this._ouvert = null; });
      if (!dialogue.open) dialogue.showModal();
    }
  }

  _fiche() {
    if (!this._ouvert || this._recents) return '';
    const j = (this._classement?.joueurs || []).find(x => x.id === this._ouvert.joueur);
    const b = j?.badges?.[this._ouvert.i];
    if (!b) return '';
    const paliers = Array.isArray(b.paliers) ? b.paliers : [];
    const atteint = Number(b.niveau) || 0, suivant = paliers[atteint];
    const precedent = atteint ? paliers[atteint - 1] : 0;
    const part = suivant ? Math.max(0, Math.min(100, Math.round(100 * (b.valeur - precedent) / (suivant - precedent)))) : 100;
    // <dialog> modal : affiché au-dessus de tout le tableau de bord, quel que soit le conteneur de la carte.
    return `<dialog class="fiche-badge${b.negatif ? ' negatif' : ''}" aria-label="${histEscape(b.nom)}"><div class="fiche" tabindex="-1" autofocus>
      <button class="fermer" aria-label="Fermer"><ha-icon icon="mdi:close"></ha-icon></button>
      <div class="fiche-tete"><span class="pastille grande niveau-${atteint}"><ha-icon icon="${histEscape(b.icone)}"></ha-icon></span>
        <div><div class="fiche-joueur">${histEscape(j.nom)}</div><h3>${histEscape(b.nom)}</h3>
          <span class="etoiles grandes" aria-label="${atteint} étoile${atteint > 1 ? 's' : ''} sur 5">${badgeEtoiles(atteint)}</span></div></div>
      <p class="fiche-texte">${histEscape(b.description)}</p>
      <div class="progression"><div class="progression-libelle"><span>${suivant ? `Prochaine étoile à ${histEscape(histNumber(suivant))}` : 'Toutes les étoiles obtenues'}</span>
        <b>${histEscape(histNumber(b.valeur))}${suivant ? ' / ' + histEscape(histNumber(suivant)) : ''}</b></div>
        <div class="jauge"><i style="width:${part}%"></i></div></div>
      <ol class="paliers">${paliers.map((v, k) => `<li class="${k < atteint ? 'acquis' : ''}">${badgeEtoiles(1, k < atteint ? 1 : 0, true)}<span>${histEscape(histNumber(v))}</span></li>`).join('')}</ol>
    </div></dialog>`;
  }

  _badges(j) {
    const liste = Array.isArray(j.badges) ? j.badges : [];
    if (!liste.length) return '';
    return `<div class="badges">${liste.map((b, i) => `<button class="badge${b.negatif ? ' negatif' : ''}" data-joueur="${histEscape(j.id)}" data-i="${i}"
      aria-label="${histEscape(b.nom)}, ${Number(b.niveau) || 0} étoile${b.niveau > 1 ? 's' : ''} sur 5" title="${histEscape(b.nom)}">
      <span class="pastille niveau-${Number(b.niveau) || 0}"><ha-icon icon="${histEscape(b.icone)}"></ha-icon></span>
      <span class="etoiles">${badgeEtoiles(Number(b.niveau) || 0)}</span></button>`).join('')}</div>`;
  }

  getGridOptions() { return {columns: 'full', min_columns: 6}; }

  _choix(pronos, joueur) {
    const choix = pronos.pronos?.[joueur];
    const resultat = pronos.resultats?.[joueur];
    let valeur = '—';
    let classe = 'prono-absent';
    if (choix != null) {
      valeur = histEscape(choix);
      if (resultat === true) {
        classe = 'prono-gagne';
        valeur += ` ✓ (+${histEscape(histNumber(pronos.points?.[joueur] ?? 0))})`;
      } else if (resultat === false) {
        classe = 'prono-perdu';
        valeur += ' ✗ (0 pt)';
      }
    }
    return `<span class="${classe}"><b>${joueur === 'ilona' ? 'Ilona' : 'Francis'}</b> ${valeur}</span>`;
  }

  _resultatsRecents(matchs) {
    let jour = '';
    let lignes = '';
    for (const m of [...matchs].sort((a, b) => String(b.debut).localeCompare(String(a.debut)))) {
      const date = new Date(m.debut).toLocaleDateString('fr-FR', {
        weekday: 'long', day: '2-digit', month: '2-digit', timeZone: 'Europe/Paris'
      });
      if (date !== jour) {
        jour = date;
        lignes += `<h3 class="jour-recent">${histEscape(date)}</h3>`;
      }
      const prolongation = m.prolongation_dom != null || m.prolongation_ext != null;
      lignes += `<div class="match-recent">
        <div>${histEscape(m.domicile)} <strong>${histEscape(histNumber(m.score_dom))} – ${histEscape(histNumber(m.score_ext))}</strong>
          ${histEscape(m.exterieur)}${prolongation ? ' a.p.' : ''} <span class="competition">${histDrapeau(m)} ${histEscape(m.tournoi)}</span></div>
        <div class="choix-recents">${this._choix(m.pronostics || {}, 'ilona')}${this._choix(m.pronostics || {}, 'francis')}</div>
      </div>`;
    }
    return `<div class="contenu recents">${lignes || '<p class="notice">Aucun résultat.</p>'}</div>`;
  }

  _concours(classement, pronostics, baremeOuvert) {
    const joueurs = [...(classement.joueurs || [])]
      .sort((a, b) => b.points - a.points || b.bons - a.bons);
    const matchs = pronostics.matchs || [];
    const [premier, second] = joueurs;
    const egalite = joueurs.length === 2 &&
      premier.points === second.points && premier.bons === second.bons;
    const reussites = j => `${histEscape(histNumber(j.bons))} sur ${histEscape(histNumber(j.pronos))} réussis`;
    const tuile = (titre, points, bilan, badges = '') => `<article class="rang">
      <span class="rang-nom">${titre}</span>
      <div class="rang-score">${histEscape(histNumber(points))} <span>pts</span></div>
      <span class="competition">${bilan}</span>${badges}
    </article>`;
    const podium = egalite
      ? tuile("Égalité de l'amour - Ilona et Francis", premier.points,
          premier.pronos === second.pronos
            ? reussites(premier)
            : joueurs.map(j => `${histEscape(j.nom)} · ${reussites(j)}`).join('<br>'),
          joueurs.filter(j => (j.badges || []).length)
            .map(j => `<div class="badges-egalite"><span class="competition">${histEscape(j.nom)}</span>${this._badges(j)}</div>`).join(''))
      : joueurs.map((j, i) => tuile(
          `<span class="rang-numero">${i + 1}</span>${histEscape(j.nom)}`, j.points, reussites(j), this._badges(j)
        )).join('');
    const lignes = matchs.map(m => {
      const date = new Date(m.debut).toLocaleDateString('fr-FR', {
        day: '2-digit', month: 'short', timeZone: 'Europe/Paris'
      });
      return `<article class="resultat simple${m.categorie === 'nanterre' ? ' nanterre' : ''}">
        <div class="result-meta"><span>${histEscape(date)}</span><span>${histDrapeau(m)} ${histEscape(m.tournoi)}</span></div>
        <div class="result-score">
          <span class="equipe-nom">${histEscape(m.domicile)}</span>
          <strong${m.termine && m.score ? '' : ' class="etat-match"'}>${histEscape(m.termine ? m.score || '—' : 'En cours')}</strong>
          <span class="equipe-nom droite">${histEscape(m.exterieur)}</span>
        </div>
        <div class="choix-concours">${this._choix(m, 'ilona')}${this._choix(m, 'francis')}</div>
      </article>`;
    }).join('');
    return `<header class="hero">
      <span class="kicker">BASKET LIVE · CONCOURS</span>
      <h1>Pronostics</h1>
      <p>Saison ${histEscape(classement.saison || pronostics.saison || 'en cours')}</p>
    </header>
    <div class="contenu concours">
      <h2>Classement</h2>
      <div class="podium">${podium || '<p class="notice">Classement indisponible.</p>'}</div>
      <details class="bareme"${baremeOuvert ? ' open' : ''}>
        <summary>Barème des points</summary>
        <ul>
          <li>3 points pour Nanterre en Betclic Élite</li>
          <li>2 points pour Nanterre hors Betclic Élite ou un autre match de Betclic Élite</li>
          <li>1 point pour les autres matchs</li>
        </ul>
      </details>
      <h2>Matchs pronostiqués</h2>
      ${lignes || '<p class="notice">Les pronostics apparaissent ici à l’entre-deux.</p>'}
    </div>`;
  }
}

// Étoiles des badges : pleines jusqu'au niveau atteint ; or, ou rouge pour un badge négatif (classe CSS).
const BADGE_ETOILE = 'M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z';
const badgeEtoiles = (n, pleines = n, seule = false) => Array.from({length: seule ? 1 : 5}, (_, k) =>
  `<svg viewBox="0 0 24 24" class="${k < pleines ? 'pleine' : 'vide'}" aria-hidden="true"><path d="${BADGE_ETOILE}"/></svg>`).join('');
const BADGES_STYLE = `
  :host { --or:#f5b800; --rouge:#e5484d; }
  .badges { display:flex; flex-wrap:wrap; gap:10px 8px; margin-top:12px; }
  .badge { display:flex; flex-direction:column; align-items:center; gap:4px; padding:0; border:0; background:none; color:inherit; cursor:pointer; font:inherit; }
  .badge:focus-visible { outline:2px solid var(--orange); outline-offset:3px; border-radius:8px; }
  .pastille { display:grid; place-items:center; width:34px; height:34px; border-radius:50%; background:var(--secondary-background-color,#8881);
    border:2px solid #f5b80055; --mdc-icon-size:18px; color:var(--primary-text-color,#eef1f4); }
  .negatif .pastille { border-color:#e5484d55; }
  .pastille.niveau-5 { border-color:var(--or); box-shadow:0 0 10px #f5b80066; }
  .negatif .pastille.niveau-5 { border-color:var(--rouge); box-shadow:0 0 10px #e5484d66; }
  .etoiles { display:flex; }
  .etoiles svg { width:7px; height:7px; }
  .etoiles svg.pleine, .paliers .acquis svg { fill:var(--or); stroke:none; }
  .negatif .etoiles svg.pleine, .negatif .paliers .acquis svg { fill:var(--rouge); }
  .etoiles svg.vide, .paliers li:not(.acquis) svg { fill:none; stroke:var(--secondary-text-color,#7d8790); stroke-width:1.6; }
  .badges-egalite { margin-top:10px; } .badges-egalite .badges { margin-top:6px; }
  dialog.fiche-badge { width:min(calc(100vw - 32px),360px); padding:0; border:1px solid var(--divider-color,#333c43); border-radius:16px;
    background:var(--card-background-color,#1c2228); color:var(--primary-text-color,#eef1f4); box-shadow:0 12px 40px #0008; }
  dialog.fiche-badge::backdrop { background:#0009; }
  .fiche { position:relative; padding:20px; outline:none; }
  .fermer { position:absolute; top:10px; right:10px; border:0; background:none; color:var(--secondary-text-color,#aab5bf); cursor:pointer; --mdc-icon-size:20px; }
  .fiche-tete { display:flex; gap:14px; align-items:center; }
  .pastille.grande { width:64px; height:64px; --mdc-icon-size:34px; border-width:3px; }
  .fiche-joueur { font-size:11px; color:var(--secondary-text-color,#aab5bf); }
  .fiche h3 { margin:2px 0 6px; font-size:18px; }
  .etoiles.grandes svg { width:16px; height:16px; }
  .fiche-texte { margin:16px 0 12px; font-size:13px; line-height:1.5; }
  .progression-libelle { display:flex; justify-content:space-between; font-size:11px; color:var(--secondary-text-color,#aab5bf); }
  .jauge { height:6px; margin-top:6px; border-radius:4px; background:var(--secondary-background-color,#8882); overflow:hidden; }
  .jauge i { display:block; height:100%; background:var(--or); border-radius:4px; }
  .negatif .jauge i { background:var(--rouge); }
  .paliers { display:flex; justify-content:space-between; gap:4px; margin:16px 0 0; padding:0; list-style:none; }
  .paliers li { display:flex; flex-direction:column; align-items:center; gap:3px; flex:1; padding:6px 0; border-radius:8px; font-size:11px;
    font-variant-numeric:tabular-nums; color:var(--secondary-text-color,#aab5bf); background:var(--secondary-background-color,#8881); }
  .paliers li.acquis { color:var(--primary-text-color,#eef1f4); font-weight:700; }
  .paliers svg { width:11px; height:11px; }
`;
const PRONOS_STYLE = `
  .competition { color: var(--secondary-text-color, #aab5bf); font-size: 11px; }
  .recents { padding-block: 10px; }
  .jour-recent { margin: 10px 0 5px; text-transform: capitalize; }
  .jour-recent:first-child { margin-top: 0; }
  .match-recent { padding: 6px 0; line-height: 1.3; border-bottom: 1px solid var(--divider-color, #333c43); }
  .match-recent:last-child { border-bottom: 0; }
  .choix-recents { display: flex; flex-wrap: wrap; gap: 0 12px; margin-top: 2px; font-size: 11px; line-height: 1.25; }
  .concours h2 { font-size: 16px; margin: 4px 0 10px; }
  .podium { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 135px), 1fr)); gap: 8px; }
  .rang { border: 1px solid var(--divider-color, #333c43); border-radius: 12px; padding: 12px; }
  .rang-nom { display: flex; gap: 8px; align-items: center; font-weight: 700; }
  .rang-numero { border-radius: 6px; padding: 2px 7px; background: #66c87926; }
  .rang-score { margin: 8px 0 3px; font-size: 25px; font-weight: 800; font-variant-numeric: tabular-nums; }
  .rang-score span { font-size: 12px; }
  .bareme { margin: 12px 0 22px; font-size: 12px; color: var(--secondary-text-color, #aab5bf); }
  .bareme summary { cursor: pointer; }
  .bareme ul { padding-inline-start: 20px; }
  .choix-concours { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 8px; font-size: 12px; overflow-wrap: anywhere; }
  .choix-concours > span { padding: 6px 8px; border-radius: 8px; background: var(--secondary-background-color, #8881); }
  .result-score strong.etat-match { font-size: 12px; letter-spacing: normal; }
`;
customElements.define('basket-pronostics-card', BasketPronosticsCard);
window.customCards.push({
  type: 'basket-pronostics-card',
  name: 'Basket Live · Pronostics',
  description: 'Classement et matchs pronostiqués, ou résultats récents en mode recents.'
});

class BasketScoreDirectCard extends HTMLElement {
  setConfig() {
    this._derniereSource = null;
    if (!this.shadowRoot) this.attachShadow({mode: 'open'});
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) return;
    const source = hass.states['sensor.basket_live_lives_en_cours'];
    if (source === this._derniereSource) return;
    this._derniereSource = source;
    const disponible = source && !['unknown', 'unavailable'].includes(source.state);
    const matchs = disponible ? source.attributes?.matchs || [] : [];
    const cartes = matchs.map(m => `<article class="resultat simple${m.categorie === 'nanterre' ? ' nanterre' : ''}">
      <div class="direct-meta">
        <span>${histDrapeau(m)} ${histEscape(m.tournoi)}</span>
        <span class="periode-direct">${histEscape(m.statut)}${m.chrono ? ` · ${histEscape(m.chrono)}` : ''}</span>
      </div>
      <div class="result-score">
        <span class="equipe-nom">${histEscape(m.domicile)}</span>
        <strong>${histEscape(histNumber(m.score_dom))}<span>–</span>${histEscape(histNumber(m.score_ext))}</strong>
        <span class="equipe-nom droite">${histEscape(m.exterieur)}</span>
      </div>
      <details class="quarts-direct"${this._quartsOuverts?.has(String(m.id)) ? ' open' : ''} data-match="${histEscape(m.id)}">
        <summary>Score par quart-temps</summary>
        ${histScoreQuarts(m)}
      </details>
    </article>`).join('');
    this.shadowRoot.innerHTML = `<style>${HIST_STYLE}${DIRECT_STYLE}</style><ha-card>
      <header class="hero direct-hero">
        <div><span class="kicker">BASKET LIVE</span><h2>En direct</h2></div>
        ${matchs.length ? `<span class="badge-direct">${matchs.length} match${matchs.length > 1 ? 's' : ''}</span>` : ''}
      </header>
      <div class="contenu direct-contenu">
        ${cartes || `<p class="notice">${disponible ? 'Aucun match en cours.' : 'Scores momentanément indisponibles.'}</p>`}
      </div>
    </ha-card>`;
    this.shadowRoot.querySelectorAll('details.quarts-direct').forEach(details => {
      details.addEventListener('toggle', () => {
        this._quartsOuverts ??= new Set();
        if (details.open) this._quartsOuverts.add(details.dataset.match);
        else this._quartsOuverts.delete(details.dataset.match);
      });
    });
  }

  getGridOptions() { return {columns: 'full', min_columns: 6}; }
}

const DIRECT_STYLE = `
  .direct-hero { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding-block: 12px; }
  .direct-hero h2 { margin: 3px 0 0; font-size: 22px; line-height: 1.2; }
  .badge-direct { white-space: nowrap; color: #fff; background: #ffffff20; border-radius: 20px; padding: 5px 10px; font-size: 11px; font-weight: 600; }
  .direct-contenu { padding-block: 10px; }
  .direct-contenu .notice { margin: 4px 0; }
  .direct-contenu .resultat:last-child { margin-bottom: 0; }
  .direct-meta { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 6px 12px; font-size: 11px; }
  .periode-direct { background: #f26b1d18; border: 1px solid #f26b1d70; border-radius: 12px; padding: 2px 7px; font-variant-numeric: tabular-nums; }
  .direct-contenu .result-score strong { font-size: clamp(22px, 5vw, 34px); }
  .quarts-direct { margin-top: 9px; font-size: 11px; color: var(--secondary-text-color, #aab5bf); }
  .quarts-direct summary { cursor: pointer; }
  .quarts-direct .quarts { margin-top: 5px; }
  .quarts-direct caption { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
`;
customElements.define('basket-score-direct-card', BasketScoreDirectCard);
window.customCards.push({
  type: 'basket-score-direct-card',
  name: 'Basket Live · Scores en direct',
  description: 'Scores, chronomètre et détail par quart-temps.'
});

class BasketClassementsCard extends HTMLElement {
  setConfig() {
    this._source = null;
    if (!this.shadowRoot) this.attachShadow({mode: 'open'});
    if (this._hass) this.hass = this._hass;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this.shadowRoot) return;
    const source = hass.states['sensor.basket_live_classements_competitions'];
    if (source === this._source) return;
    this._source = source;
    const attrs = source?.attributes || {};
    const tableaux = attrs.tableaux || {};
    this.shadowRoot.innerHTML = `<style>${HIST_STYLE}${CLASSEMENTS_STYLE}</style><ha-card>
      <header class="hero">
        <span class="kicker">BASKET LIVE · COMPÉTITIONS</span>
        <h1>Classements</h1>
        <p>Saison ${histEscape(attrs.saison || 'en cours')}</p>
      </header>
      <div class="contenu">
        ${this._tableau('🇫🇷 Betclic Élite', tableaux.elite)}
        ${this._tableau('🇪🇺 Basketball Champions League', tableaux.bcl, true)}
        <p class="legende">J = matchs joués · G = gagnés · P = perdus · Pts = points au classement · PM = points marqués · PE = points encaissés · Diff. = PM − PE</p>
      </div>
    </ha-card>`;
  }

  getGridOptions() { return {columns: 'full', min_columns: 6}; }

  _tableau(titre, tableau, bcl = false) {
    const nombre = valeur => histEscape(histNumber(valeur));
    const equipes = tableau?.equipes || [];
    const date = tableau?.mis_a_jour && new Date(tableau.mis_a_jour).toLocaleString('fr-FR', {
      timeZone: 'Europe/Paris', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
    });
    return `<section class="classement-competition">
      <h2>${titre}</h2>
      ${bcl ? `<p class="notice">${histEscape(tableau?.groupe || 'Poule de Nanterre')}</p>` : ''}
      ${equipes.length ? `<div class="classement-scroll" tabindex="0" role="region" aria-label="${histEscape(titre)}">
        <table class="classement-equipes" aria-label="${histEscape(titre)}">
          <thead><tr>
            <th scope="col">Équipe</th><th scope="col">J</th><th scope="col">G</th><th scope="col">P</th>
            <th scope="col">Pts</th><th scope="col">PM</th><th scope="col">PE</th><th scope="col">Diff.</th><th scope="col">% G</th>
          </tr></thead>
          <tbody>${equipes.map(e => `<tr${e.nanterre ? ' class="classement-nanterre"' : ''}>
            <th scope="row"><span class="place-equipe">${nombre(e.rang)}</span> ${histEscape(e.equipe)}</th>
            <td>${nombre(e.joues)}</td><td>${nombre(e.victoires)}</td><td>${nombre(e.defaites)}</td>
            <td><b>${nombre(e.points)}</b></td><td>${nombre(e.marques)}</td><td>${nombre(e.encaisses)}</td>
            <td>${e.difference > 0 ? '+' : ''}${nombre(e.difference)}</td>
            <td>${nombre(e.pourcentage)}${e.pourcentage == null ? '' : ' %'}</td>
          </tr>`).join('')}</tbody>
        </table>
      </div>` : '<p class="notice">Classement momentanément indisponible.</p>'}
      ${date ? `<p class="cache">Dernière mise à jour le ${histEscape(date)}</p>` : ''}
    </section>`;
  }
}

const CLASSEMENTS_STYLE = `
  .classement-competition + .classement-competition { margin-top: 28px; }
  .classement-competition h2 { font-size: 17px; margin: 4px 0 8px; }
  .classement-competition .cache { margin-top: 8px; }
  .classement-scroll { overflow-x: auto; border: 1px solid var(--divider-color, #8885); border-radius: 12px; }
  .classement-scroll:focus-visible { outline: 2px solid var(--vert); outline-offset: 2px; }
  .classement-equipes { min-width: 460px; }
  .classement-equipes th:first-child { position: sticky; left: 0; z-index: 1; text-align: left; background: var(--ha-card-background, var(--card-background-color, #fff)); }
  .classement-equipes thead th { font-size: 11px; }
  .classement-equipes th, .classement-equipes td { padding: 9px 7px; }
  .classement-equipes tbody tr:last-child > * { border-bottom: 0; }
  .place-equipe { display: inline-block; min-width: 22px; margin-right: 3px; font-variant-numeric: tabular-nums; }
  .classement-nanterre > * { background: #66c87930; font-weight: 700; }
  .classement-equipes .classement-nanterre th:first-child {
    border-left: 3px solid #51a865;
    background: linear-gradient(#66c87938, #66c87938), var(--ha-card-background, var(--card-background-color, #fff));
  }
`;
customElements.define('basket-classements-card', BasketClassementsCard);
window.customCards.push({
  type: 'basket-classements-card',
  name: 'Basket Live · Classements',
  description: 'Betclic Élite et poule de Nanterre en Basketball Champions League.'
});
