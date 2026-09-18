// Graphiques Chart.js (vendorisé, global window.Chart) : sans animation, sans dégradé,
// valeurs écrites directement sur le graphique pour être lisibles sans survol.

import { couleurCss } from "./ui.js";

const graphiques = new Set();

export function detruireGraphiques() {
  graphiques.forEach((graphique) => graphique.destroy());
  graphiques.clear();
}

function styleTexte() {
  return {
    couleur: couleurCss("--couleur-texte"),
    doux: couleurCss("--couleur-texte-doux"),
    grille: couleurCss("--couleur-bordure"),
    police: couleurCss("--police"),
  };
}

// Plugin maison : écrit la valeur formatée au bout de chaque barre.
function pluginValeurs(formater) {
  return {
    id: "valeursSurBarres",
    afterDatasetsDraw(graphique) {
      const { ctx } = graphique;
      const style = styleTexte();
      ctx.save();
      ctx.font = `12px ${style.police}`;
      ctx.fillStyle = style.couleur;
      ctx.textBaseline = "middle";
      graphique.getDatasetMeta(0).data.forEach((barre, index) => {
        const valeur = graphique.data.datasets[0].data[index];
        ctx.fillText(formater(valeur), barre.x + 6, barre.y);
      });
      ctx.restore();
    },
  };
}

export function histogrammeHorizontal(canvas, { libelles, valeurs, couleurs, formater }) {
  const style = styleTexte();
  const maximum = Math.max(...valeurs, 0);
  const graphique = new window.Chart(canvas, {
    type: "bar",
    data: {
      labels: libelles,
      datasets: [{ data: valeurs, backgroundColor: couleurs, borderWidth: 0, barThickness: 16 }],
    },
    options: {
      indexAxis: "y",
      animation: false,
      maintainAspectRatio: false,
      layout: { padding: { right: 8 } },
      plugins: { legend: { display: false }, tooltip: { enabled: true } },
      scales: {
        // Marge à droite pour que l'étiquette de la plus grande barre tienne.
        x: {
          beginAtZero: true,
          suggestedMax: maximum * 1.25,
          grid: { color: style.grille },
          ticks: { display: false },
        },
        y: { grid: { display: false }, ticks: { color: style.couleur } },
      },
    },
    plugins: [pluginValeurs(formater)],
  });
  graphiques.add(graphique);
  return graphique;
}

export function anneau(canvas, { libelles, valeurs, couleurs, formater }) {
  const style = styleTexte();
  const graphique = new window.Chart(canvas, {
    type: "doughnut",
    data: {
      labels: libelles,
      datasets: [{ data: valeurs, backgroundColor: couleurs, borderWidth: 1 }],
    },
    options: {
      animation: false,
      maintainAspectRatio: false,
      cutout: "60%",
      plugins: {
        legend: {
          position: "right",
          labels: {
            color: style.couleur,
            boxWidth: 12,
            // La valeur figure dans la légende : lisible sans survol.
            generateLabels: (g) =>
              window.Chart.overrides.doughnut.plugins.legend.labels
                .generateLabels(g)
                .map((etiquette, i) => ({
                  ...etiquette,
                  text: `${etiquette.text} — ${formater(valeurs[i])}`,
                })),
          },
        },
      },
    },
  });
  graphiques.add(graphique);
  return graphique;
}
