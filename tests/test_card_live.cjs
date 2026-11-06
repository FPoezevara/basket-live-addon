// node --test tests/test_card_live.cjs
const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname, '../homeassistant/www/basket-a-venir-card.js'), 'utf8');
const copie = x => JSON.parse(JSON.stringify(x));

function fixture() {
  const registres = new Map(), timers = new Map(), appels = [];
  let numero = 0;
  class Element {
    attachShadow() { this.shadowRoot = {innerHTML: '', addEventListener() {}}; }
  }
  const contexte = vm.createContext({HTMLElement: Element, customElements: {define: (nom, classe) => registres.set(nom, classe)},
    window: {}, console: {info() {}, error() {}},
    setTimeout: fn => { timers.set(++numero, fn); return numero; }, clearTimeout: n => timers.delete(n)});
  vm.runInContext(code, contexte);
  const card = new (registres.get('basket-a-venir-card'))();
  card.setConfig({joueurs: {f: 'francis', i: 'ilona'}});
  const match = (id, categorie = 'elite') => ({id, categorie, titre: `A${id} - B${id}`, tournoi: 'Betclic Élite',
    tournoi_id: 156, domicile: `A${id}`, exterieur: `B${id}`, debut: '2026-11-07T20:00:00+01:00', code: 0});
  const m1 = match(1), m2 = match(2), m3 = {...match(3, 'nanterre'), code: 13, en_cours: true, statut: 'QT1'};
  const hass = {user: {id: 'f'}, states: {
    'sensor.basket_live_matchs_a_venir': {state: '2', last_updated: 'a', attributes: {matchs: [m1, m2]}},
    'sensor.basket_live_lives_en_cours': {state: '1', last_updated: 'b', attributes: {matchs: [m3]}},
    'sensor.basket_live_suivis_francis': {state: '0', attributes: {choix: {}}},
    'sensor.basket_live_suivis_ilona': {state: '0', attributes: {choix: {}}},
    'input_boolean.basket_francis_live_nanterre': {state: 'off'},
    'input_boolean.basket_ilona_live_nanterre': {state: 'off'},
    'select.prono_francis_1': {state: '—', attributes: {joueur: 'francis', match_id: 1, options: ['—', 'A1', 'B1']}},
  }, callService: async (...args) => { appels.push(copie(args)); }};
  card.hass = hass;
  function confirmer(joueur, id, actif) {
    hass.states[`sensor.basket_live_suivis_${joueur}`].attributes.choix[id] = actif;
    card.hass = hass;
  }
  return {card, hass, appels, timers, confirmer, m1, m2, m3};
}

test('bouton à droite de la ligne méta, blanc ou orange, attributs accessibles', () => {
  const {card, confirmer} = fixture();
  assert.match(card.shadowRoot.innerHTML, /meta-texte[\s\S]*data-live="1"/);
  assert.match(card.shadowRoot.innerHTML, /color: #fff/);
  assert.match(card.shadowRoot.innerHTML, /\.live-bouton\.actif \{ color: var\(--accent\)/);
  assert.match(card.shadowRoot.innerHTML, /aria-pressed="false"/);
  confirmer('francis', 1, true);
  assert.match(card.shadowRoot.innerHTML, /class="live-bouton actif" data-live="1"/);
});

test('plusieurs choix indépendants de la sélection d’Ilona, sans appel pronostic', async () => {
  const {card, hass, appels, confirmer, m1, m2} = fixture();
  await card._basculerLive(1);
  confirmer('francis', 1, true);
  await card._basculerLive(2);
  confirmer('francis', 2, true);
  assert.equal(card._suiviActif(m1), true);
  assert.equal(card._suiviActif(m2), true);
  hass.user = {id: 'i'};
  card.hass = hass;
  assert.equal(card._suiviActif(m1), false);
  assert.equal(card._suiviActif(m2), false);
  await card._basculerLive(1);
  confirmer('ilona', 1, true);
  assert.deepEqual(appels, [
    ['script', 'basket_live_selectionner', {personne: 'francis', match_id: 1, actif: true}],
    ['script', 'basket_live_selectionner', {personne: 'francis', match_id: 2, actif: true}],
    ['script', 'basket_live_selectionner', {personne: 'ilona', match_id: 1, actif: true}],
  ]);
  hass.user = {id: 'f'};
  card.hass = hass;
  await card._basculerLive(1);
  confirmer('francis', 1, false);
  assert.equal(card._suiviActif(m1), false);
  assert.equal(card._suiviActif(m2), true);
  assert.equal(hass.states['sensor.basket_live_suivis_ilona'].attributes.choix[1], true);
});

test('match commencé toujours visible, dédoublonné, et désactivable', async () => {
  const {card, hass, confirmer, m3} = fixture();
  hass.states['sensor.basket_live_matchs_a_venir'].attributes.matchs.push({...m3, code: 0});
  card.hass = hass;
  assert.equal(card._matchs().filter(m => m.id === 3).length, 1);
  assert.equal(card._matchs().find(m => m.id === 3).code, 13);
  confirmer('francis', 3, true);
  await card._basculerLive(3);
  confirmer('francis', 3, false);
  assert.equal(card._suiviActif(m3), false);
  assert.match(card.shadowRoot.innerHTML, /data-live="3"/);
});

test('désactivation Nanterre propre à un match, préférence automatique conservée', async () => {
  const {card, hass, confirmer, m3} = fixture();
  hass.states['input_boolean.basket_francis_live_nanterre'].state = 'on';
  card.hass = hass;
  assert.equal(card._suiviActif(m3), true);
  await card._basculerLive(3);
  confirmer('francis', 3, false);
  assert.equal(card._suiviActif(m3), false);
  assert.equal(card._suiviActif({...m3, id: 4}), true);
  assert.equal(hass.states['input_boolean.basket_francis_live_nanterre'].state, 'on');
});

test('attente MQTT, double clic ignoré et choix provisoire isolé par utilisateur', async () => {
  const {card, hass, appels, confirmer, m1} = fixture();
  await card._basculerLive(1);
  await card._basculerLive(1);
  assert.equal(appels.length, 1);
  assert.equal(card._suiviActif(m1), true);
  assert.match(card.shadowRoot.innerHTML, /aria-busy="true"/);
  hass.user = {id: 'i'};
  card.hass = hass;
  assert.equal(card._suiviActif(m1), false);
  confirmer('francis', 1, true);
  assert.equal(Object.keys(card._enAttenteLive).length, 0);
});

test('échec de service et absence d’accusé rendent le bouton réutilisable', async () => {
  const {card, hass, timers, m1} = fixture();
  hass.callService = async () => { throw Error('échec simulé'); };
  await card._basculerLive(1);
  assert.equal(card._suiviActif(m1), false);
  assert.equal(Object.keys(card._enAttenteLive).length, 0);
  assert.match(card.shadowRoot.innerHTML, /role="status"/);
  hass.callService = async () => {};
  await card._basculerLive(1);
  [...timers.values()][0]();
  assert.equal(card._suiviActif(m1), false);
  assert.equal(Object.keys(card._enAttenteLive).length, 0);
});

test('utilisateur non configuré et capteur indisponible : aucune commande', async () => {
  const {card, hass, appels} = fixture();
  hass.user = {id: 'inconnu'};
  card.hass = hass;
  await card._basculerLive(1);
  assert.equal(appels.length, 0);
  hass.user = {id: 'f'};
  hass.states['sensor.basket_live_suivis_francis'].state = 'unavailable';
  card.hass = hass;
  await card._basculerLive(1);
  assert.equal(appels.length, 0);
});

test('les boutons de pronostic continuent d’appeler uniquement le select', async () => {
  const {card, appels} = fixture();
  const cible = {dataset: {match: '1', cote: 'dom'}, classList: {contains: () => true}};
  card._clic({target: {closest: selecteur => selecteur === '[data-live]' ? null : cible}});
  await Promise.resolve();
  assert.deepEqual(appels, [['select', 'select_option', {entity_id: 'select.prono_francis_1', option: 'A1'}]]);
});


test('un accusé MQTT tardif efface le message d’échec sans changer le choix', async () => {
  const {card, timers, confirmer, m1} = fixture();
  await card._basculerLive(1);
  [...timers.values()][0]();
  assert.match(card.shadowRoot.innerHTML, /role="status"/);
  confirmer('francis', 1, true);
  assert.equal(card._suiviActif(m1), true);
  assert.doesNotMatch(card.shadowRoot.innerHTML, /role="status"/);
});
