document.addEventListener('DOMContentLoaded', () => {
    const TZ = 'Europe/Paris';
    let currentData = window.CCAM_APP_DATA || {};

    function formatParisDateTime(value) {
        if (!value) return 'non renseignée';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString('fr-FR', {
            timeZone: TZ,
            dateStyle: 'short',
            timeStyle: 'medium'
        });
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function render(data) {
        const meta = data.meta || {};
        const records = Array.isArray(data.records) ? data.records : [];
        const values = {
            total: Number(meta.total ?? records.length ?? 0),
            medical: Number(meta.medical ?? records.filter(r => r.domaine === 'Médical CCAM').length ?? 0),
            dental: Number(meta.bucco_dentaire ?? records.filter(r => r.domaine !== 'Médical CCAM').length ?? 0),
            rac0: Number(meta.rac0 ?? records.filter(r => String(r.panier_100_sante || '').startsWith('RAC 0')).length ?? 0),
        };

        for (const [id, value] of Object.entries(values)) {
            setText(id, value.toLocaleString('fr-FR'));
        }

        const generatedValue = meta.generated || meta.updated_at || null;
        setText('generated', formatParisDateTime(generatedValue));

        const status = document.getElementById('dataStatus');
        if (status) {
            if (records.length > 0) {
                status.textContent = `Données à jour · ${records.length.toLocaleString('fr-FR')} actes chargés`;
                status.style.color = '#bbf7d0';
            } else {
                status.textContent = 'Données indisponibles : synchronisation à relancer';
                status.style.color = '#fecaca';
            }
        }
    }

    function updateParisClock() {
        setText('parisNow', new Date().toLocaleString('fr-FR', {
            timeZone: TZ,
            dateStyle: 'short',
            timeStyle: 'medium'
        }));
    }

    async function refreshDataFromJson() {
        try {
            const response = await fetch(`data/app-data.json?ts=${Date.now()}`, { cache: 'no-store' });
            if (!response.ok) return;
            const fresh = await response.json();
            if (fresh && Array.isArray(fresh.records) && fresh.records.length > 0) {
                currentData = fresh;
                render(currentData);
            }
        } catch (error) {
            // Le site continue avec les données déjà chargées par app-data.js.
        }
    }

    render(currentData);
    updateParisClock();
    setInterval(updateParisClock, 1000);
    refreshDataFromJson();
    setInterval(refreshDataFromJson, 60000);
});
