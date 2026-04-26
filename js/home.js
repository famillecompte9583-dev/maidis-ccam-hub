document.addEventListener('DOMContentLoaded', () => {
    const data = window.CCAM_APP_DATA || {};
    const meta = data.meta || {};
    const records = Array.isArray(data.records) ? data.records : [];

    const values = {
        total: Number(meta.total ?? records.length ?? 0),
        medical: Number(meta.medical ?? records.filter(r => r.domaine === 'Médical CCAM').length ?? 0),
        dental: Number(meta.bucco_dentaire ?? records.filter(r => r.domaine !== 'Médical CCAM').length ?? 0),
        rac0: Number(meta.rac0 ?? records.filter(r => String(r.panier_100_sante || '').startsWith('RAC 0')).length ?? 0),
    };

    for (const [id, value] of Object.entries(values)) {
        const el = document.getElementById(id);
        if (el) el.textContent = value > 0 ? value.toLocaleString('fr-FR') : '0';
    }

    const generated = document.getElementById('generated');
    const status = document.getElementById('dataStatus');
    const generatedValue = meta.generated || meta.updated_at || null;

    if (generated) {
        if (generatedValue) {
            const date = new Date(generatedValue);
            generated.textContent = Number.isNaN(date.getTime())
                ? String(generatedValue)
                : date.toLocaleString('fr-FR', { timeZone: 'Europe/Paris', dateStyle: 'short', timeStyle: 'medium' });
        } else {
            generated.textContent = 'non renseignée';
        }
    }

    if (status) {
        if (records.length > 0) {
            status.textContent = 'État des données : à jour et chargées correctement';
            status.style.color = '#bbf7d0';
        } else {
            status.textContent = 'État des données : fichier vide ou mise à jour à relancer';
            status.style.color = '#fecaca';
        }
    }
});
