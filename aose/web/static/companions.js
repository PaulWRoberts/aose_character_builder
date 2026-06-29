// Remember which Companions ledger rows are open across the full-page POST
// reloads the steppers/controls trigger. Open <details data-id> are stored in
// localStorage and re-opened on load.
(function () {
  var KEY = 'aose:companions:open';
  function load() { try { return new Set(JSON.parse(localStorage.getItem(KEY) || '[]')); } catch (e) { return new Set(); } }
  function save(set) { localStorage.setItem(KEY, JSON.stringify([...set])); }
  var open = load();
  document.querySelectorAll('details.crow[data-id]').forEach(function (d) {
    if (open.has(d.dataset.id)) d.open = true;
    d.addEventListener('toggle', function () {
      if (d.open) open.add(d.dataset.id); else open.delete(d.dataset.id);
      save(open);
    });
  });
})();

// Retainer hire form: filter the class dropdown and level cap by selected race.
// Only active when the race select is present (Advanced / separate-race-class mode).
(function () {
  var hireForm = document.querySelector('.retainer-add-expanded');
  if (!hireForm) return;
  var raceEl  = hireForm.querySelector('.ret-race-sel');
  var classEl = hireForm.querySelector('[name="class_id"]');
  var levelEl = hireForm.querySelector('[name="level"]');
  if (!raceEl || !classEl) return;

  // Snapshot full class list before any filtering
  var allOpts = Array.from(classEl.options).map(function (o) {
    return { value: o.value, text: o.text };
  });

  function parseCaps(str) {
    var caps = {};
    if (!str) return caps;
    str.split(',').forEach(function (pair) {
      var i = pair.indexOf(':');
      if (i > 0) caps[pair.slice(0, i)] = +pair.slice(i + 1);
    });
    return caps;
  }

  function selectedRaceData() {
    var opt = raceEl.options[raceEl.selectedIndex];
    if (!opt) return { allowed: null, caps: {} };
    var allowed = opt.dataset.allowed ? opt.dataset.allowed.split(',').filter(Boolean) : null;
    return { allowed: allowed, caps: parseCaps(opt.dataset.caps) };
  }

  function applyLevelCap(caps) {
    if (!levelEl) return;
    var cap = caps[classEl.value];
    if (cap) {
      levelEl.max = cap;
      if (+levelEl.value > cap) levelEl.value = cap;
    } else {
      levelEl.removeAttribute('max');
    }
  }

  function syncClass() {
    var d = selectedRaceData();
    var prev = classEl.value;
    classEl.innerHTML = '';
    allOpts.forEach(function (o) {
      if (!d.allowed || d.allowed.indexOf(o.value) !== -1) {
        classEl.appendChild(new Option(o.text, o.value));
      }
    });
    // Restore prior selection if it's still valid for this race
    var stillValid = Array.from(classEl.options).some(function (o) { return o.value === prev; });
    if (stillValid) classEl.value = prev;
    applyLevelCap(d.caps);
  }

  raceEl.addEventListener('change', syncClass);
  classEl.addEventListener('change', function () { applyLevelCap(selectedRaceData().caps); });
  syncClass(); // set initial state on page load
})();
