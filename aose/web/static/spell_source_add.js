// Add-spell-document form: pick spells (with quantities) into a staged list,
// emit one hidden `spell_ids` input per charge, and toggle list/language fields
// by kind/caster. The server re-validates everything.
(function () {
  var form = document.getElementById("spell-source-add-form");
  if (!form) return;
  var kind = document.getElementById("ss-kind");
  var caster = document.getElementById("ss-caster-type");
  var list = document.getElementById("ss-list");
  var listLabel = document.getElementById("ss-list-label");
  var langLabel = document.getElementById("ss-language-label");
  var pick = document.getElementById("ss-spell-pick");
  var qty = document.getElementById("ss-spell-qty");
  var addBtn = document.getElementById("ss-add-spell");
  var staged = document.getElementById("ss-staged");
  var hidden = document.getElementById("ss-hidden");
  var submit = document.getElementById("ss-submit");
  var cap = document.getElementById("ss-spell-cap");
  var MAX_SCROLL_SPELLS = 7;

  // staged: array of { id, label, n }
  var items = [];

  function isBook() { return kind.value === "spellbook"; }
  function wantCaster() { return isBook() ? "arcane" : caster.value; }
  function wantList() { return isBook() ? list.value : null; }

  function totalCharges() {
    return items.reduce(function (t, it) { return t + it.n; }, 0);
  }

  function refreshControls() {
    caster.disabled = isBook();
    if (isBook()) caster.value = "arcane";
    listLabel.style.display = isBook() ? "" : "none";
    list.disabled = !isBook();
    langLabel.style.display = (!isBook() && caster.value === "divine") ? "" : "none";
    cap.style.display = isBook() ? "none" : "";
    // Filter the pick list to matching spells.
    Array.prototype.forEach.call(pick.options, function (opt) {
      var ok = opt.getAttribute("data-caster") === wantCaster();
      if (ok && wantList() !== null) ok = opt.getAttribute("data-list") === wantList();
      opt.hidden = !ok;
    });
    var firstVisible = Array.prototype.filter.call(pick.options, function (o) { return !o.hidden; })[0];
    if (firstVisible) pick.value = firstVisible.value;
  }

  function renderStaged() {
    staged.innerHTML = "";
    hidden.innerHTML = "";
    items.forEach(function (it, idx) {
      var li = document.createElement("li");
      li.textContent = it.label + (it.n > 1 ? "  ×" + it.n : "") + "  ";
      var rm = document.createElement("button");
      rm.type = "button";
      rm.className = "btn link";
      rm.textContent = "remove";
      rm.addEventListener("click", function () { items.splice(idx, 1); renderStaged(); });
      li.appendChild(rm);
      staged.appendChild(li);
      for (var i = 0; i < it.n; i++) {
        var inp = document.createElement("input");
        inp.type = "hidden"; inp.name = "spell_ids"; inp.value = it.id;
        hidden.appendChild(inp);
      }
    });
    submit.disabled = items.length === 0;
  }

  addBtn.addEventListener("click", function () {
    var opt = pick.options[pick.selectedIndex];
    if (!opt || opt.hidden) return;
    var id = opt.value;
    var label = opt.getAttribute("data-label") || opt.textContent.trim();
    var n = Math.max(1, parseInt(qty.value, 10) || 1);
    // Spell books: one of each (no duplicates).
    if (isBook()) {
      if (items.some(function (it) { return it.id === id; })) return;
      n = 1;
    } else {
      var existing = items.filter(function (it) { return it.id === id; })[0];
      var room = MAX_SCROLL_SPELLS - totalCharges();
      if (room <= 0) return;
      n = Math.min(n, room);
      if (existing) { existing.n += n; renderStaged(); return; }
    }
    items.push({ id: id, label: label, n: n });
    renderStaged();
  });

  // Changing kind/caster/list invalidates the staged picks (different pool).
  function resetStaged() { items = []; renderStaged(); refreshControls(); }
  kind.addEventListener("change", resetStaged);
  caster.addEventListener("change", resetStaged);
  list.addEventListener("change", resetStaged);

  refreshControls();
  renderStaged();
})();
