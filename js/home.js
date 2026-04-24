document.addEventListener('DOMContentLoaded',()=>{
    const m = window.CCAM_APP_DATA.meta;
    // Affiche les totaux avec séparation des milliers
    for (const [id, val] of Object.entries({ total: m.total, medical: m.medical, dental: m.bucco_dentaire, rac0: m.rac0 })) {
        document.getElementById(id).textContent = Number(val).toLocaleString('fr-FR');
    }
    // Convertit la date de génération en heure de Paris. Certains environnements
    // (GitHub Actions) génèrent en UTC, d’où l’importance de fixer le fuseau.
    const generatedDate = new Date(m.generated);
    document.getElementById('generated').textContent = generatedDate.toLocaleString('fr-FR', {
        timeZone: 'Europe/Paris',
        dateStyle: 'short',
        timeStyle: 'medium'
    });
});
