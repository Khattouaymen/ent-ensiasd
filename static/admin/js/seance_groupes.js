// Formulaire « séance » de l'administration : n'affiche que les groupes de la classe choisie.
document.addEventListener("DOMContentLoaded", function () {
  var classe = document.getElementById("id_classe");
  var groupe = document.getElementById("id_groupe");
  if (!classe || !groupe) {
    return;
  }

  function filtrer() {
    Array.prototype.forEach.call(groupe.options, function (option) {
      if (!option.value) {
        return; // option vide « --------- » : toute la classe
      }
      var visible = option.dataset.classe === classe.value;
      option.hidden = !visible;
      option.disabled = !visible;
      if (!visible && option.selected) {
        groupe.value = "";
      }
    });
  }

  classe.addEventListener("change", filtrer);
  filtrer();
});
