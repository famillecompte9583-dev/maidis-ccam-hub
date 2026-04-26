document.addEventListener('DOMContentLoaded',()=>{
const app=window.CCAM_APP_DATA||{};
const articles=Array.isArray(app.articles)?app.articles:[];
const list=document.getElementById('articles');
const body=document.getElementById('articleBody');
function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]))}
if(list){
  if(!articles.length){
    list.innerHTML='<div class="note">Aucun dossier généré pour le moment. Les dossiers affichés ici proviennent uniquement de la synchronisation automatique réelle des sources suivies. Relancez la mise à jour puis revenez dans quelques minutes.</div>';
    return;
  }
  list.innerHTML=articles.map(a=>`<article class="card newsitem"><span class="pill p-med">${esc(a.category||a.tag||'Dossier')}</span><h3><a href="article.html?id=${encodeURIComponent(a.id)}">${esc(a.title)}</a></h3><p>${esc(a.summary||'')}</p><p class="small">${esc(a.source||'Source')} · ${new Date(a.date).toLocaleDateString('fr-FR')} · ${Number((a.codes||[]).length).toLocaleString('fr-FR')} code(s) détecté(s)</p></article>`).join('');
}
if(body){
  const id=new URLSearchParams(location.search).get('id');
  const a=articles.find(x=>x.id===id)||articles[0];
  if(!a){body.innerHTML='<div class="note">Dossier introuvable. Aucun article réel n’a encore été généré par la synchronisation.</div>';return}
  document.title=a.title+' — Annuaire CCAM Santé';
  document.getElementById('articleTag').textContent=a.category||a.tag||'Dossier';
  document.getElementById('articleTitle').textContent=a.title;
  document.getElementById('articleSummary').textContent=a.summary||'';
  body.innerHTML=a.content_html||'<p>Aucun contenu disponible.</p>';
  const codes=(a.codes||[]).slice(0,120);
  document.getElementById('articleCodes').innerHTML=codes.length?codes.map(c=>`<a class="pill p-out" style="margin:4px" href="acte.html?code=${encodeURIComponent(c)}">${esc(c)}</a>`).join(''):'Aucun code détecté automatiquement.';
}
});
