document.addEventListener('DOMContentLoaded', () => {
  const code = qs('code');
  const activity = qs('a');
  const phase = qs('p');
  const records = appRecords();
  const record = records.find(item => item.code === code && (!activity || item.activite === activity) && (!phase || item.phase === phase))
    || records.find(item => item.code === code);
  const root = document.getElementById('detail');

  if (!record) {
    if (root) root.innerHTML = '<div class="note">Acte introuvable ou base indisponible.</div>';
    return;
  }

  const title = document.getElementById('title');
  const subtitle = document.getElementById('subtitle');
  const pill = document.getElementById('pill');
  const brss = document.getElementById('brss');
  const taux = document.getElementById('taux');
  const amo = document.getElementById('amo');

  if (title) title.textContent = record.code || 'Acte';
  if (subtitle) subtitle.textContent = record.libelle || '';
  if (pill) {
    pill.textContent = record.panier_100_sante || 'Non classé';
    pill.className = `pill ${clsPanier(record.panier_100_sante)}`;
  }
  if (brss) brss.textContent = fmtEuro(record.brss);
  if (taux) taux.textContent = fmtPercent(record.taux_amo_standard);
  if (amo) amo.textContent = fmtEuro(record.montant_amo_standard);

  const rows = [
    ['Code CCAM', record.code],
    ['Activité / phase', `Activité ${record.activite || '—'} · phase ${record.phase || '—'}`],
    ['Libellé', record.libelle],
    ['Domaine', record.domaine],
    ['Tarif de base (BRSS)', fmtEuro(record.brss)],
    ['Taux de remboursement standard', fmtPercent(record.taux_amo_standard)],
    ['Montant remboursé AMO estimé', fmtEuro(record.montant_amo_standard)],
    ['Panier de soins', record.panier_100_sante],
    ['Certitude panier', record.certitude_panier],
    ['Justification panier', record.justification_panier],
    ['Accord préalable', record.accord_prealable || 'Non renseigné'],
    ['Code suggéré Maidis', record.code_maidis_suggere],
    ['Notes paramétrage', record.notes_parametrage],
  ];

  if (root) {
    root.innerHTML = `<table class="params">${rows.map(row => `<tr><th>${escHTML(row[0])}</th><td>${escHTML(row[1])}</td></tr>`).join('')}</table>`;
  }

  const exportOne = document.getElementById('exportOne');
  if (exportOne) {
    exportOne.onclick = () => {
      const csv = 'parametre;valeur\n' + rows.map(row => `${csvCell(row[0])};${csvCell(row[1])}`).join('\n');
      downloadText(`acte_${record.code}_maidis.csv`, csv);
    };
  }
});
