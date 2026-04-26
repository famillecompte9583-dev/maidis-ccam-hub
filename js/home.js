document.addEventListener('DOMContentLoaded', () => {
    const TZ = 'Europe/Paris';
    let currentData = window.CCAM_APP_DATA || {};

    function parseGenerationDate(value) {
        if (!value) return null;
        if (value instanceof Date) return value;
        const raw = String(value).trim();
        // Les anciennes générations GitHub Actions écrivaient une date ISO sans fuseau
        // alors qu'elle correspondait à l'heure UTC. On ajoute donc Z pour obtenir
        // une conversion correcte vers Europe/Paris.
        const looksIsoWithoutTimezone = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(raw);
        const normalized = looksIsoWithoutTimezone ? `${raw}Z` : raw;
        const date = new Date(normalized);
        return Number.isNaN(date.getTime()) ? null : date;
    }

    function formatParisDateTime(value) {
        const date = parseGenerationDate(value);
        if (!date) return value ? String(value) : 'non renseignée';
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
    refreshDataFromJson();
    setInterval(refreshDataFromJson, 60000);
});
