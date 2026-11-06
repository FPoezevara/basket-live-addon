const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');
const code = fs.readFileSync(path.join(__dirname,'../homeassistant/www/basket-historique-card.js'),'utf8');

function fixture() {
  const classes=new Map(), listeners={}, appels=[];
  class Element { attachShadow(){this.shadowRoot={innerHTML:'',addEventListener:(nom,fn)=>{listeners[nom]=fn;}};} }
  const contexte=vm.createContext({HTMLElement:Element,customElements:{define:(n,c)=>classes.set(n,c)},window:{},console:{info(){}}});
  vm.runInContext(code,contexte);
  const card=new (classes.get('basket-historique-card'))();
  card.setConfig({});
  const m=(id,nanterre)=>({id,categorie:nanterre?'nanterre':'elite',titre:'Nanterre - Paris',tournoi:'Betclic Élite',
    domicile:nanterre?'Nanterre':'Roanne',exterieur:'Paris',domicile_id:53125,exterieur_id:123,
    debut:'2026-11-07T20:00:00+01:00',score_dom:83,score_ext:69,quarts_dom:[20,20,20,23],quarts_ext:[18,18,18,15]});
  const stats={statistics:[{period:'ALL',groups:[{groupName:'Rebounds',statisticsItems:[
    {name:'Rebounds',key:'rebounds',home:'40',away:'30',homeValue:40,awayValue:30},
    {name:'Unknown metric',key:'unlistedMetric',home:'0',away:'2'}]}]},
    {period:'1ST',groups:[{groupName:'Scoring',statisticsItems:[{key:'points',home:20,away:18}]}]}]};
  const lineup={success:true,data:{home:{players:[{player:{name:'Joueur Nanterre'},jerseyNumber:'7',substitute:false,played:false,
    statistics:{secondsPlayed:650,points:0,rebounds:8,assists:7,fieldGoalsMade:0,fieldGoalAttempts:2,plusMinus:13,
      uncommonStat:5,statisticsType:{sportSlug:'basketball'}}}]},away:{players:[{player:{name:'Joueur Paris'},statistics:{points:20,secondsPlayed:900}}]}}};
  const hass={states:{
    'sensor.basket_live_resultats_saison':{state:'2',last_updated:'1',attributes:{saison:'2026-2027',equipe_nanterre:53125,matchs:[m(1,true),m(2,false)],import:{etat:'attente_jour_sans_match'}}},
    'sensor.basket_live_statistiques_1':{state:'2',last_updated:'1',attributes:{match_id:1,type:'basket_statistiques',historique:false,
      statistics:{etat:'enregistre',reponse:stats,tente_le:1794000000},lineups:{etat:'enregistre',reponse:lineup,tente_le:1794000060}}}
  },callService:(...args)=>appels.push(args)};
  card.hass=hass;
  return {card,hass,listeners,appels,contexte};
}

test('onglet de saison, tous les résultats et accordéon exclusivement Nanterre',()=>{
  const {card}=fixture();
  assert.match(card.shadowRoot.innerHTML,/Saison 2026-2027/);
  assert.match(card.shadowRoot.innerHTML,/details class="resultat nanterre" data-match="1"/);
  assert.match(card.shadowRoot.innerHTML,/div class="resultat simple"/);
  assert.doesNotMatch(card.shadowRoot.innerHTML,/details[^>]*data-match="2"/);
  assert.match(card.shadowRoot.innerHTML,/journée sans match/);
});

test('statistiques équipes et joueurs, valeurs zéro et champs supplémentaires sans perte',()=>{
  const {card}=fixture();
  const html=card.shadowRoot.innerHTML;
  assert.match(html,/Comparaison des équipes/);
  assert.match(html,/Rebonds/);
  assert.match(html,/Unknown metric/);
  assert.match(html,/Joueur Nanterre/);
  assert.match(html,/10:50/); // played:false n'efface pas les 650 secondes effectivement jouées
  assert.match(html,/Uncommon Stat/);
  assert.match(html,/<dd>5<\/dd>/);
  assert.match(html,/<dd>0<\/dd>/);
  assert.doesNotMatch(html,/Sport Slug/); // métadonnée de schéma, pas une statistique
});

test('ouverture fermeture et changements de période/équipe sans appel réseau',()=>{
  const {card,listeners,appels}=fixture();
  listeners.toggle({target:{matches:()=>true,dataset:{match:'1'},open:true}});
  card._rendre();
  assert.match(card.shadowRoot.innerHTML,/data-match="1" open/);
  listeners.click({target:{closest:()=>({dataset:{periode:'1ST',matchId:'1'}})}});
  assert.match(card.shadowRoot.innerHTML,/Points/);
  listeners.click({target:{closest:()=>({dataset:{equipe:'away',matchId:'1'}})}});
  assert.match(card.shadowRoot.innerHTML,/Joueur Paris/);
  listeners.toggle({target:{matches:()=>true,dataset:{match:'1'},open:false}});
  card._rendre();
  assert.doesNotMatch(card.shadowRoot.innerHTML,/data-match="1" open/);
  assert.equal(appels.length,0);
  assert.doesNotMatch(code,/\bfetch\s*\(|\.callService\s*\(|XMLHttpRequest/);
});

test('mise à jour MQTT conserve l’accordéon ouvert et filtre Nanterre',()=>{
  const {card,hass,listeners}=fixture();
  listeners.toggle({target:{matches:()=>true,dataset:{match:'1'},open:true}});
  hass.states['sensor.basket_live_statistiques_1'].last_updated='2';
  card.hass=hass;
  assert.match(card.shadowRoot.innerHTML,/data-match="1" open/);
  listeners.click({target:{closest:()=>({dataset:{filtre:'nanterre'}})}});
  assert.doesNotMatch(card.shadowRoot.innerHTML,/div class="resultat simple"/);
});

test('absence de données, collecte différée ou interrompue : messages explicites',()=>{
  const {card,hass}=fixture();
  const e=hass.states['sensor.basket_live_statistiques_1'];
  e.attributes={match_id:1,type:'basket_statistiques',historique:true,statistics:{etat:'en_attente'},lineups:{etat:'indisponible'}};
  e.last_updated='3';card.hass=hass;
  assert.match(card.shadowRoot.innerHTML,/journée sans match/);
  assert.match(card.shadowRoot.innerHTML,/collecte unique/);
  e.attributes.statistics.etat='interrompu';e.last_updated='4';card.hass=hass;
  assert.match(card.shadowRoot.innerHTML,/Aucun nouvel appel automatique/);
});

test('données échappées et sensor renommé retrouvé par attributs',()=>{
  const {card,hass}=fixture();
  const e=hass.states['sensor.basket_live_statistiques_1'];
  delete hass.states['sensor.basket_live_statistiques_1'];
  hass.states['sensor.mon_capteur_renomme']=e;
  hass.states['sensor.basket_live_resultats_saison'].attributes.matchs[0].domicile='<img src=x onerror=alert(1)>';
  hass.states['sensor.basket_live_resultats_saison'].last_updated='9';card.hass=hass;
  assert.match(card.shadowRoot.innerHTML,/&lt;img/);
  assert.doesNotMatch(card.shadowRoot.innerHTML,/<img src=x/);
  assert.match(card.shadowRoot.innerHTML,/Joueur Nanterre/);
});
