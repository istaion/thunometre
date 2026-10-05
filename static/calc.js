// Calculateurs de score. Tout est calculé dans le navigateur : les réponses ne
// sont jamais envoyées ni stockées, seul le score final l'est si la personne
// clique sur « Enregistrer ».

const PRIVILEGE_QUESTIONS = [
  ["Âge", "Adulte", "Personne âgée", "Enfant, ado, jeune, jeune adulte"],
  ["Logement", "Propriétaire", "Locataire", "Sans logement, habitat léger, squat"],
  ["Richesse", "Riche", "Classe moyenne", "Pauvre"],
  ["Éducation", "Post-secondaire", "Secondaire", "Pas de diplôme"],
  ["Culture", "Française métropolitaine", "Occidentale hors France métropolitaine", "Non occidentale"],
  ["Langue", "Français métropolitain", "Français non métropolitain", "Langue étrangère, LSF"],
  ["Citoyenneté", "Citoyen·ne français·e",
    "Étranger·e avec statut permettant le travail, citoyen·ne de l'Union européenne", "Sans papiers"],
  ["Géographie", "Métropolitaine urbaine", "Métropolitaine rurale", "Outre-mer"],
  ["Numérique", "Accès internet facile, compétences numériques courantes ou plus",
    "Accès internet difficile, compétences numériques limitées",
    "Peu d'accès internet, pas de compétence numérique"],
  ["Situation familiale et matrimoniale", "Couple hétérosexuel, 1 à 3 enfants",
    "Couple hétérosexuel sans enfant, ou 4 enfants ou plus",
    "Célibataire, veuf·ve, divorcé·e, famille monoparentale, famille LGBTQIA+"],
  ["Neurodiversité", "Neurotypique", "Légère neurodivergence", "Neurodivergence importante ou multiple"],
  ["Santé mentale", "Robuste", "Généralement stable", "Vulnérable"],
  ["Genre", "Homme cisgenre", "Femme cisgenre", "Minorité de genre (hors femme cis)"],
  ["Orientation sexuelle", "Hétérosexuel·le", "Homme cisgenre homosexuel", "LGBTQIA+"],
  ["Capacités physiques", "Pas d'invalidité", "Invalidité partielle", "Invalidité importante"],
  ["Couleur de peau", "Blanche", "Teint mat", "Noire"],
  ["Ethnicité", "Blanche", "Perçu·e comme blanc·he la plupart du temps", "Racisé·e"],
  ["Apparence physique", "Proche des canons de beauté occidentaux", "Dans la moyenne",
    "Éloignée des canons de beauté occidentaux"],
];

// Chaque règle : montant saisi (en €) → points, avec l'explication affichée.
const FINANCE_AMOUNTS = [
  {
    id: "revenu", label: "Combien gagnes-tu environ par mois ?", unit: "€ / mois",
    rule: "−1 si moins de 800 € ; 0 de 800 à 1 499 € ; +1 à partir de 1 500 €, puis +1 par tranche de 500 € en plus.",
    points: v => (v < 800 ? -1 : v < 1500 ? 0 : 1 + Math.floor((v - 1500) / 500)),
  },
  {
    id: "epargne", label: "Combien as-tu d'épargne ?", unit: "€",
    rule: "+1 à partir de 5 000 €, puis +1 par tranche de 1 000 € en plus.",
    points: v => (v < 5000 ? 0 : 1 + Math.floor((v - 5000) / 1000)),
  },
  {
    id: "dettes", label: "Combien as-tu de dettes difficiles à rembourser ?", unit: "€",
    rule: "−1 à partir de 1 000 €.",
    points: v => (v >= 1000 ? -1 : 0),
  },
  {
    id: "heritage", label: "Quel héritage vas-tu recevoir ?", unit: "€",
    rule: "+1 à partir de 50 000 €, puis +1 par tranche de 50 000 € en plus.",
    points: v => (v < 50000 ? 0 : Math.floor(v / 50000)),
  },
];

const FINANCE_CHECKS = [
  ["soutien", "Je peux compter sur un soutien familial", 1],
  ["charge", "J'ai des personnes à charge (enfant, animal, proche…)", -1],
  ["proprio", "Je suis propriétaire d'un logement", 1],
  ["depenses", "J'ai des dépenses spécifiques (santé, addiction…)", -1],
];

const fmt = n => (n > 0 ? "+" + n : n < 0 ? "−" + -n : "0");

function h(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const k in attrs) k === "class" ? (e.className = attrs[k]) : e.setAttribute(k, attrs[k]);
  e.append(...children);
  return e;
}

// onUse(score) est appelé quand la personne clique sur « Utiliser ce score ».
function buildPrivilegeCalc(container, onUse) {
  const total = h("strong", {}, "0");
  const status = h("span", { class: "muted" });
  const use = h("button", { type: "button" }, "Utiliser ce score");
  const form = h("form", { class: "calc" });

  PRIVILEGE_QUESTIONS.forEach(([title, ...opts], i) => {
    const fs = h("fieldset", {}, h("legend", {}, title));
    opts.forEach((text, j) => {
      const value = 1 - j;
      fs.append(h("label", { class: "opt" },
        h("input", { type: "radio", name: "q" + i, value }),
        h("span", { class: "pts" }, fmt(value)),
        h("span", {}, text)));
    });
    form.append(fs);
  });

  const update = () => {
    const answers = [...new FormData(form).values()].map(Number);
    const score = answers.reduce((a, b) => a + b, 0);
    total.textContent = fmt(score);
    const missing = PRIVILEGE_QUESTIONS.length - answers.length;
    status.textContent = missing ? ` — ${missing} question${missing > 1 ? "s" : ""} sans réponse` : "";
    use.disabled = missing > 0;
    use.onclick = () => onUse(score);
  };
  form.addEventListener("change", update);
  update();

  container.append(
    h("p", { class: "muted" }, "Pour chaque ligne, choisis ce qui te correspond : +1, 0 ou −1. Le score est la somme."),
    form,
    h("div", { class: "calc-total" }, h("span", {}, "Score « privilèges » : ", total, status), use));
}

function buildFinanceCalc(container, onUse) {
  const total = h("strong", {}, "0");
  const use = h("button", { type: "button" }, "Utiliser ce score");
  const form = h("form", { class: "calc" });
  const outputs = {};

  for (const q of FINANCE_AMOUNTS) {
    outputs[q.id] = h("span", { class: "pts" }, "0");
    form.append(h("fieldset", {},
      h("legend", {}, q.label),
      h("div", { class: "amount" },
        h("input", { type: "number", name: q.id, min: 0, step: 1, inputmode: "numeric", placeholder: "0" }),
        h("span", { class: "muted" }, q.unit),
        outputs[q.id]),
      h("p", { class: "rule" }, q.rule)));
  }
  const checks = h("fieldset", {}, h("legend", {}, "Ta situation"));
  for (const [id, text, value] of FINANCE_CHECKS) {
    checks.append(h("label", { class: "opt" },
      h("input", { type: "checkbox", name: id }),
      h("span", { class: "pts" }, fmt(value)),
      h("span", {}, text)));
  }
  form.append(checks);

  const update = () => {
    let score = 0;
    for (const q of FINANCE_AMOUNTS) {
      const raw = form.elements[q.id].value;
      const p = raw === "" ? 0 : q.points(Math.max(0, Number(raw) || 0)); // vide = pas de point
      outputs[q.id].textContent = fmt(p);
      score += p;
    }
    for (const [id, , value] of FINANCE_CHECKS) if (form.elements[id].checked) score += value;
    total.textContent = fmt(score);
    use.disabled = form.elements.revenu.value === "";
    use.onclick = () => onUse(score);
  };
  form.addEventListener("input", update);
  update();

  container.append(
    form,
    h("div", { class: "calc-total" }, h("span", {}, "Score « thune » : ", total), use));
}
