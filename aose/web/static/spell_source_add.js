// Progressive enhancement for the Add-spell-document form: show only the spell
// <option>s that match the chosen kind / caster type / list. The server
// re-validates, so this is purely a usability filter.
(function () {
  var form = document.getElementById("spell-source-add-form");
  if (!form) return;
  var kind = document.getElementById("ss-kind");
  var caster = document.getElementById("ss-caster-type");
  var list = document.getElementById("ss-list");
  var listLabel = document.getElementById("ss-list-label");
  var spells = document.getElementById("ss-spells");

  // AOSE Magic Scrolls table tops out at 7 spells per scroll; books are uncapped.
  var MAX_SCROLL_SPELLS = 7;
  var cap = document.getElementById("ss-spell-cap");

  function refresh() {
    var isBook = kind.value === "spellbook";
    // Spell books are always arcane and pick from a single list.
    caster.disabled = isBook;
    if (isBook) caster.value = "arcane";
    listLabel.style.display = isBook ? "" : "none";
    // A scroll spans a whole magic type, so the list select is irrelevant —
    // disable it so its value isn't submitted (the server ignores it too).
    list.disabled = !isBook;
    var wantCaster = isBook ? "arcane" : caster.value;
    var wantList = isBook ? list.value : null;
    Array.prototype.forEach.call(spells.options, function (opt) {
      var ok = opt.getAttribute("data-caster") === wantCaster;
      if (ok && wantList !== null) ok = opt.getAttribute("data-list") === wantList;
      opt.hidden = !ok;
      if (!ok) opt.selected = false;
    });
    if (cap) cap.style.display = isBook ? "none" : "";
    enforceCap();
  }

  // For scrolls, drop selections beyond the 7-spell cap (oldest kept).
  function enforceCap() {
    if (kind.value === "spellbook") return;
    var selected = Array.prototype.filter.call(spells.options, function (o) {
      return o.selected && !o.hidden;
    });
    for (var i = MAX_SCROLL_SPELLS; i < selected.length; i++) selected[i].selected = false;
  }

  kind.addEventListener("change", refresh);
  caster.addEventListener("change", refresh);
  list.addEventListener("change", refresh);
  spells.addEventListener("change", enforceCap);
  refresh();
})();
