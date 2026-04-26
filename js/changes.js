document.addEventListener('DOMContentLoaded', () => {
  const changes = appData().changes || {};
  const box = document.getElementById('changesSummary');
  const table = document.getElementById('changesTable');

  if (box) {
    box.innerHTML = [
      ['Ajouts', changes.added_count],
      ['Retraits', changes.removed_count],
      ['Modifications', changes.modified_count],
    ].map(item => `<section class="card info"><h3>${escHTML(item[0])}</h3><p style="font-size:34px;font-weight:950;margin:0">${fmtInt(item[1])}</p></section>`).join('');
  }

  if (table) {
    const rows = [];
    (Array.isArray(changes.added) ? changes.added : []).forEach(record => rows.push(['Ajout', record.code, record.libelle]));
    (Array.isArray(changes.removed) ? changes.removed : []).forEach(record => rows.push(['Retrait', record.code, record.libelle]));
    (Array.isArray(changes.modified) ? changes.modified : []).forEach(record => rows.push(['Modification', record.code, `Champs modifiés : ${(record.fields || []).join(', ')}`]));

    table.innerHTML = rows.map(row => `<tr>
      <td><span class="pill p-med">${escHTML(row[0])}</span></td>
      <td class="code">${escHTML(row[1])}</td>
      <td>${escHTML(row[2])}</td>
    </tr>`).join('') || '<tr><td colspan="3" class="small">Aucun changement détecté depuis la génération précédente.</td></tr>';
  }
});
