"""Page unique du tableau de bord (HTML + CSS + JS, sans dépendance externe)."""

from __future__ import annotations

PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>BAHO · veille des appels d'offres</title>
<style>
:root{
  --page:#f4f6f4; --card:#fff; --ink:#13211c; --muted:#5c6b63; --line:#e2e7e3;
  --brand:#14463a; --accent:#0c7a52; --soft:#eef5f1; --warn:#9a6b12; --urgent:#b4451f;
  --shadow:0 1px 3px #0f251c14, 0 8px 24px #0f251c0d;
}
@media (prefers-color-scheme:dark){:root{
  --page:#0e1613; --card:#16211d; --ink:#e8efea; --muted:#9bada3; --line:#26332d;
  --brand:#0f3a30; --accent:#3ec18a; --soft:#192621; --warn:#d6a53a; --urgent:#e58463;
  --shadow:0 1px 3px #0006, 0 8px 24px #0004;
}}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);
  font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:0 20px 64px}
header{background:var(--brand);color:#fff;padding:26px 0 22px;margin-bottom:26px}
header .wrap{padding-bottom:0}
h1{margin:0;font-size:22px;letter-spacing:-.2px}
.tag{font-size:11px;letter-spacing:1.6px;text-transform:uppercase;opacity:.72;font-weight:700}
.sub{opacity:.8;font-size:13px;margin-top:6px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin:-44px 0 24px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;box-shadow:var(--shadow)}
.card .n{font-size:28px;font-weight:800;line-height:1.1}
.card .k{font-size:12px;color:var(--muted);margin-top:4px}
nav{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:18px;border-bottom:1px solid var(--line)}
nav button{background:none;border:0;border-bottom:2px solid transparent;color:var(--muted);
  padding:10px 14px;font:inherit;font-weight:600;cursor:pointer}
nav button[aria-selected=true]{color:var(--ink);border-bottom-color:var(--accent)}
section[hidden]{display:none}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);
  padding:18px;margin-bottom:18px}
.panel h2{margin:0 0 4px;font-size:15px}
.panel p.hint{margin:0 0 16px;color:var(--muted);font-size:13px}
.toolbar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
input,select,textarea,button{font:inherit;color:inherit}
input[type=text],input[type=number],input[type=search],select,textarea{
  background:var(--page);border:1px solid var(--line);border-radius:8px;padding:9px 11px;width:100%}
textarea{min-height:96px;resize:vertical;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.btn{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:10px 16px;font-weight:650;cursor:pointer}
.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
.btn:disabled{opacity:.5;cursor:progress}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
label.field{display:block}
label.field span{display:block;font-size:12px;color:var(--muted);margin-bottom:6px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:14px}
th{position:sticky;top:0;background:var(--card);text-align:left;font-size:12px;color:var(--muted);
  text-transform:uppercase;letter-spacing:.7px;padding:10px 12px;border-bottom:1px solid var(--line)}
td{padding:12px;border-bottom:1px solid var(--line);vertical-align:top}
tr.row{cursor:pointer}
tr.row:hover{background:var(--soft)}
.score{font-weight:800;font-size:16px;white-space:nowrap}
.bar{height:6px;border-radius:999px;background:var(--line);margin-top:6px;overflow:hidden;min-width:70px}
.bar i{display:block;height:100%;background:var(--accent)}
.pill{display:inline-block;font-size:11px;font-weight:700;padding:3px 9px;border-radius:999px;
  background:var(--soft);color:var(--muted);white-space:nowrap}
.pill.ok{background:#0c7a5222;color:var(--accent)}
.pill.warn{background:#9a6b1222;color:var(--warn)}
.pill.urgent{background:#b4451f22;color:var(--urgent)}
.detail{background:var(--soft)}
.detail dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px 20px;margin:0}
.detail dt{font-size:11px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);font-weight:700}
.detail dd{margin:2px 0 8px;word-break:break-word}
.break{display:grid;gap:7px;margin-top:12px}
.break .line{display:grid;grid-template-columns:180px 1fr 64px;gap:10px;align-items:center;font-size:13px}
.break .line b{font-weight:600}
.src{display:flex;justify-content:space-between;gap:14px;align-items:center;padding:12px 0;border-bottom:1px solid var(--line);flex-wrap:wrap}
.src:last-child{border-bottom:0}
.switch{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:var(--brand);color:#fff;
  padding:11px 20px;border-radius:999px;box-shadow:var(--shadow);font-size:14px;z-index:9}
.log{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.log .ERROR{color:var(--urgent)}
.muted{color:var(--muted)}
a{color:var(--accent)}
@media(max-width:720px){.break .line{grid-template-columns:1fr;gap:3px}.hide-s{display:none}}
</style></head>
<body>
<header><div class="wrap">
  <div class="tag">BAHO · veille commerciale</div>
  <h1>Appels d'offres — hébergement, séminaires et prestations hôtelières</h1>
  <p class="sub">Tout est historisé, y compris sous le seuil d'alerte. Les réglages ci-dessous s'appliquent au cycle suivant.</p>
</div></header>

<div class="wrap">
  <div class="cards" id="cards"></div>

  <nav id="tabs">
    <button data-tab="tenders" aria-selected="true">Opportunités</button>
    <button data-tab="sources" aria-selected="false">Sources</button>
    <button data-tab="settings" aria-selected="false">Réglages</button>
    <button data-tab="log" aria-selected="false">Journal</button>
  </nav>

  <section id="tab-tenders">
    <div class="panel">
      <div class="toolbar">
        <input type="search" id="q" placeholder="Filtrer par intitulé, acheteur, référence…" style="flex:1 1 260px">
        <label class="switch">Score ≥ <input type="number" id="minScore" value="0" min="0" max="100" style="width:80px"></label>
        <label class="switch"><input type="checkbox" id="onlyOpen"> Échéance à venir</label>
        <button class="btn" id="run">Lancer un cycle</button>
        <button class="btn ghost" id="mail">E-mail de test</button>
        <button class="btn ghost" id="resetAlerts">Purger l'historique d'envoi</button>
      </div>
      <div style="overflow:auto;max-height:70vh">
        <table><thead><tr>
          <th style="width:92px">Score</th><th>Appel d'offres</th><th class="hide-s">Acheteur</th>
          <th class="hide-s">Échéance</th><th class="hide-s">Lieu</th><th class="hide-s">Montant</th><th>Alerte</th>
        </tr></thead><tbody id="rows"></tbody></table>
      </div>
    </div>
  </section>

  <section id="tab-sources" hidden>
    <div class="panel">
      <h2>Plateformes surveillées</h2>
      <p class="hint">Activez une source dès que son flux ou son API est renseigné et ses conditions d'utilisation validées.
      Le changement prend effet au cycle suivant, sans redémarrage.</p>
      <div id="sources"></div>
    </div>
    <div class="panel">
      <h2>État du dernier cycle par source</h2>
      <div id="health" class="log"></div>
    </div>
  </section>

  <section id="tab-settings" hidden>
    <div class="panel">
      <h2>Seuil, cadence et pondérations</h2>
      <p class="hint">Le total des six pondérations constitue le score sur 100. Le seuil décide de l'envoi de l'alerte,
      jamais de la conservation de l'annonce.</p>
      <div class="grid" id="numbers"></div>
      <p class="hint" id="weightSum" style="margin:14px 0 0"></p>
    </div>
    <div class="panel">
      <h2>Ciblage commercial et destinataires</h2>
      <p class="hint">Une valeur par ligne. Les mots-clés alimentent la détection ; les termes interrogés
      servent aux requêtes envoyées aux plateformes.</p>
      <div class="grid" id="lists"></div>
    </div>
    <div class="panel">
      <h2>Implantations prises en compte</h2>
      <p class="hint">Ville et département de chaque établissement BAHO ; ils alimentent le score géographique.</p>
      <div id="hotels" class="log"></div>
    </div>
    <div class="toolbar">
      <button class="btn" id="save">Enregistrer les réglages</button>
      <button class="btn ghost" id="reset">Rétablir settings.toml</button>
      <span class="muted" id="overrideState"></span>
    </div>
  </section>

  <section id="tab-log" hidden>
    <div class="panel"><h2>Journal d'exécution</h2><div id="log" class="log"></div></div>
  </section>
</div>

<script>
const $ = (s, root = document) => root.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let STATE = null, OPEN = null;

const euro = v => v == null || v === '' ? 'Non renseigné'
  : new Intl.NumberFormat('fr-FR', {style:'currency', currency:'EUR', maximumFractionDigits:0}).format(v);
const date = v => v ? new Date(v).toLocaleDateString('fr-FR', {day:'2-digit', month:'2-digit', year:'numeric'}) : '—';
const days = v => v ? Math.round((new Date(v) - Date.now()) / 86400000) : null;

function toast(text) {
  const el = document.createElement('div');
  el.className = 'toast'; el.textContent = text;
  document.body.appendChild(el); setTimeout(() => el.remove(), 3200);
}

async function api(path, body) {
  const options = body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {};
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || ('Erreur ' + response.status));
  return payload;
}

async function load() { STATE = await api('/api/state'); render(); }

function render() {
  const stats = STATE.stats, threshold = stats.threshold;
  $('#cards').innerHTML = [
    [stats.total || 0, 'annonces historisées'],
    [stats.relevant || 0, `au-dessus du seuil (${threshold}/100)`],
    [stats.open_tenders || 0, 'échéances encore ouvertes'],
    [stats.alerts || 0, 'alertes e-mail envoyées'],
    [STATE.sources.filter(s => s.enabled).length + '/' + STATE.sources.length, 'sources actives'],
  ].map(([n, k]) => `<div class="card"><div class="n">${esc(n)}</div><div class="k">${esc(k)}</div></div>`).join('');
  renderRows(); renderSources(); renderSettings(); renderHealth();
  $('#overrideState').textContent = STATE.overrides ? 'Réglages personnalisés actifs.' : 'Réglages issus de settings.toml.';
  $('#run').disabled = STATE.running;
  $('#run').textContent = STATE.running ? 'Cycle en cours…' : 'Lancer un cycle';
}

function renderRows() {
  const needle = $('#q').value.trim().toLowerCase();
  const floor = Number($('#minScore').value || 0);
  const openOnly = $('#onlyOpen').checked;
  const rows = STATE.tenders.filter(t => {
    if (t.score < floor) return false;
    if (openOnly && !(t.deadline_at && new Date(t.deadline_at) > new Date())) return false;
    if (!needle) return true;
    return [t.title, t.buyer, t.reference, t.location, t.department].join(' ').toLowerCase().includes(needle);
  });
  $('#rows').innerHTML = rows.length
    ? rows.map(row).join('')
    : '<tr><td colspan="7" class="muted">Aucune annonce ne correspond à ce filtre.</td></tr>';
}

function urgency(t) {
  const d = days(t.deadline_at);
  if (d === null) return ['pill', 'Échéance inconnue'];
  if (d < 0) return ['pill', 'Clôturée'];
  if (d < 7) return ['pill urgent', 'J-' + d];
  if (d < 21) return ['pill warn', 'J-' + d];
  return ['pill ok', 'J-' + d];
}

function row(t) {
  const [cls, label] = urgency(t);
  const alerted = t.alert_status === 'sent'
    ? '<span class="pill ok">Envoyée</span>'
    : t.score >= STATE.stats.threshold ? '<span class="pill warn">En attente</span>' : '<span class="pill">Sous le seuil</span>';
  const url = (t.source_urls || '').split(',').find(u => u.startsWith('http')) || '';
  const title = url ? `<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(t.title)}</a>` : esc(t.title);
  return `<tr class="row" data-id="${t.id}">
    <td><div class="score">${t.score}</div><div class="bar"><i style="width:${Math.max(t.score,2)}%"></i></div></td>
    <td>${title}<div class="muted" style="font-size:12px;margin-top:4px">
      ${esc(t.reference || 'Référence non renseignée')} · ${esc(t.source_names || '')}</div></td>
    <td class="hide-s">${esc(t.buyer)}<div class="muted" style="font-size:12px">${esc(t.buyer_profile || '')}</div></td>
    <td class="hide-s">${date(t.deadline_at)}<div style="margin-top:4px"><span class="${cls}">${esc(label)}</span></div></td>
    <td class="hide-s">${esc(t.location || '—')}</td>
    <td class="hide-s">${t.estimate_eur == null ? '<span class="muted">—</span>' : euro(t.estimate_eur)}</td>
    <td>${alerted}</td>
  </tr>${OPEN === t.id ? detail(t) : ''}`;
}

function detail(t) {
  const fields = [
    ["Acheteur", t.buyer], ["Type d'acheteur", t.buyer_profile], ["Référence", t.reference],
    ["Lieu d'exécution", t.location], ["Département", t.department], ["Montant estimé", t.estimate_eur == null ? null : euro(t.estimate_eur)],
    ["Volume", t.rooms_or_nights], ["Codes CPV", (t.cpvs || []).join(', ')], ["Nature", t.contract_nature],
    ["Procédure", t.procedure], ["Type d'avis", t.notice_kind], ["Durée", t.duration],
    ["Publication", date(t.published_at)], ["Échéance", date(t.deadline_at)],
    ["Première détection", date(t.created_at)], ["Dernière mise à jour", date(t.updated_at)],
  ];
  const breakdown = (t.breakdown || []).map(l => `<div class="line">
      <b>${esc(l.label)}</b>
      <div class="bar"><i style="width:${l.maximum ? Math.max(100*l.points/l.maximum, 2) : 2}%"></i></div>
      <span>${l.points}/${l.maximum}</span>
      <div class="muted" style="grid-column:1/-1;font-size:12px">${esc(l.detail)}</div>
    </div>`).join('');
  const docs = (t.documents || []).map(u => `<li><a href="${esc(u)}" target="_blank" rel="noreferrer">${esc(u)}</a></li>`).join('');
  const lots = (t.lots || []).map(l => `<li>${esc(l)}</li>`).join('');
  return `<tr class="detail"><td colspan="7">
    <dl>${fields.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${v ? esc(v) : '<span class="muted">Non renseigné</span>'}</dd></div>`).join('')}</dl>
    ${breakdown ? `<h3 style="font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:16px 0 0">Détail du score</h3><div class="break">${breakdown}</div>` : ''}
    ${lots ? `<h3 style="font-size:13px;margin:16px 0 4px">Lots</h3><ul style="margin:0;padding-left:20px">${lots}</ul>` : ''}
    ${t.description ? `<h3 style="font-size:13px;margin:16px 0 4px">Objet</h3><p style="margin:0">${esc(t.description)}</p>` : ''}
    ${docs ? `<h3 style="font-size:13px;margin:16px 0 4px">Dossier de consultation</h3><ul style="margin:0;padding-left:20px;font-size:13px">${docs}</ul>` : ''}
  </td></tr>`;
}

function renderSources() {
  $('#sources').innerHTML = STATE.sources.map(s => `<div class="src">
    <div style="flex:1 1 220px">
      <b>${esc(s.name)}</b> <span class="pill">${esc(s.kind || 'inconnu')}</span>
      ${s.kind === 'feed' ? `<div style="margin-top:8px"><input type="text" data-url="${esc(s.name)}"
         value="${esc(s.url)}" placeholder="URL du flux RSS/Atom/JSON autorisé"></div>` : ''}
    </div>
    <label class="switch"><input type="checkbox" data-source="${esc(s.name)}" ${s.enabled ? 'checked' : ''}> active</label>
  </div>`).join('');
}

function renderHealth() {
  $('#health').innerHTML = STATE.health.length
    ? STATE.health.map(h => `<div class="${esc(h.level)}"><b>${esc(h.source)}</b> — ${esc(h.message)}
        <span class="muted">(${esc(h.created_at || '')})</span></div>`).join('')
    : '<span class="muted">En attente du premier cycle.</span>';
}

function renderSettings() {
  const schema = STATE.schema, values = STATE.settings;
  $('#numbers').innerHTML = Object.entries(schema.numeric).map(([key, meta]) =>
    `<label class="field"><span>${esc(meta.label)}</span>
      <input type="number" data-key="${esc(key)}" value="${esc(values[key] ?? '')}"
             min="${meta.min}" max="${meta.max}"></label>`).join('');
  $('#lists').innerHTML = Object.entries(schema.lists).map(([key, label]) =>
    `<label class="field"><span>${esc(label)} <span class="muted">(${(values[key] || []).length})</span></span>
      <textarea data-key="${esc(key)}">${esc((values[key] || []).join('\n'))}</textarea></label>`).join('');
  $('#hotels').innerHTML = STATE.hotels.length
    ? STATE.hotels.map(h => `<div>${esc(h.name)} — ${esc(h.city || '?')} (${esc(h.department || '?')})</div>`).join('')
    : '<span class="muted">Aucune implantation renseignée.</span>';
  updateSum();
}

function updateSum() {
  const total = ['keyword', 'geography', 'amount', 'deadline', 'information', 'service']
    .reduce((sum, name) => sum + Number($(`[data-key="scoring.${name}_weight"]`)?.value || 0), 0);
  $('#weightSum').textContent = `Total des pondérations : ${total} points` +
    (total === 100 ? ' — conforme au barème du brief.' : ` — le brief en prévoit 100 ; un score est plafonné à 100.`);
}

async function save() {
  const patch = {};
  document.querySelectorAll('#numbers [data-key]').forEach(el => patch[el.dataset.key] = Number(el.value));
  document.querySelectorAll('#lists [data-key]').forEach(el => patch[el.dataset.key] = el.value.split('\n'));
  const sources = {};
  document.querySelectorAll('[data-source]').forEach(el => sources[el.dataset.source] = {enabled: el.checked});
  document.querySelectorAll('[data-url]').forEach(el => {
    sources[el.dataset.url] = Object.assign(sources[el.dataset.url] || {}, {url: el.value.trim()});
  });
  patch.sources = sources;
  STATE = await api('/api/settings', patch);
  render();
  toast('Réglages enregistrés — appliqués au prochain cycle.');
}

$('#tabs').addEventListener('click', event => {
  const button = event.target.closest('button[data-tab]');
  if (!button) return;
  document.querySelectorAll('#tabs button').forEach(b => b.setAttribute('aria-selected', String(b === button)));
  ['tenders', 'sources', 'settings', 'log'].forEach(name => $('#tab-' + name).hidden = name !== button.dataset.tab);
  if (button.dataset.tab === 'log') refreshLog();
});

$('#rows').addEventListener('click', event => {
  const tr = event.target.closest('tr.row');
  if (!tr || event.target.tagName === 'A') return;
  OPEN = OPEN === Number(tr.dataset.id) ? null : Number(tr.dataset.id);
  renderRows();
});

['#q', '#minScore', '#onlyOpen'].forEach(sel => $(sel).addEventListener('input', renderRows));
$('#numbers').addEventListener('input', updateSum);
$('#save').addEventListener('click', () => save().catch(e => toast(e.message)));
$('#reset').addEventListener('click', async () => {
  if (!confirm('Supprimer les réglages personnalisés et revenir à settings.toml ?')) return;
  try { STATE = await api('/api/settings/reset', {}); render(); toast('Réglages d\'origine restaurés.'); }
  catch (e) { toast(e.message); }
});
$('#run').addEventListener('click', async () => {
  try {
    await api('/api/run', {});
    toast('Cycle lancé — les résultats arrivent au fil de la collecte.');
    $('#run').disabled = true;
    const timer = setInterval(async () => { await load(); if (!STATE.running) { clearInterval(timer); toast('Cycle terminé.'); } }, 3000);
  } catch (e) { toast(e.message); }
});
$('#mail').addEventListener('click', async () => {
  try {
    const result = await api('/api/test-email', {});
    const messages = {
      sent: 'E-mail de test envoyé à ' + (result.recipients || []).join(', '),
      skipped_no_smtp: 'SMTP non configuré : renseignez SMTP_HOST dans .env.',
      skipped_no_recipients: 'Aucun destinataire configuré.',
      failed: 'Échec SMTP : ' + (result.error || ''),
    };
    toast(messages[result.status] || result.status);
  } catch (e) { toast(e.message); }
});

$('#resetAlerts').addEventListener('click', async () => {
  const pending = STATE.tenders.filter(t => t.score >= STATE.stats.threshold).length;
  if (!confirm(`Oublier les alertes déjà envoyées ?\n\n${pending} opportunité(s) au-dessus du seuil seront `
    + `re-notifiées au fil des prochains cycles. Les annonces et leur classement sont conservés.`)) return;
  try {
    const result = await api('/api/alerts/reset', {});
    await load();
    toast(`Historique purgé (${result.removed} entrée(s)) — les alertes repartiront au prochain cycle.`);
  } catch (e) { toast(e.message); }
});

async function refreshLog() {
  const { events } = await api('/api/events');
  $('#log').innerHTML = events.length
    ? events.map(e => `<div class="${esc(e.level)}">${esc(e.created_at)} [${esc(e.level)}] ${esc(e.source || '-')} · ${esc(e.kind)} — ${esc(e.message)}</div>`).join('')
    : '<span class="muted">Journal vide.</span>';
}

load().catch(e => toast(e.message));
setInterval(() => { if (!document.hidden && !OPEN) load().catch(() => {}); }, 30000);
</script>
</body></html>
"""
