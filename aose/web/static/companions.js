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
