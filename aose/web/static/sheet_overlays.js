(function(){
  const scrim = document.getElementById('scrim');
  let lastTrigger = null;
  function closeAll(){
    document.querySelectorAll('.overlay.on').forEach(o => o.classList.remove('on'));
    scrim.classList.remove('on');
    if (lastTrigger){ try{ lastTrigger.focus({preventScroll:true}); }catch(e){} lastTrigger = null; }
  }
  function fill(panel, t){
    panel.querySelectorAll('[data-role="title"]').forEach(el => { if (t.title) el.textContent = t.title; });
    panel.querySelectorAll('[data-role="text"]').forEach(el => { if (t.text) el.innerHTML = t.text; });
    panel.querySelectorAll('[data-role="ability"]').forEach(el => { if (t.ability) el.textContent = t.ability; });
    const spellEl = panel.querySelector('[data-role="spell"]');
    if (spellEl) {
      if (t.spell) {
        panel.querySelector('[data-role="spell-body"]').innerHTML = t.spell;
        spellEl.style.display = '';
        spellEl.open = false;
      } else {
        spellEl.style.display = 'none';
        panel.querySelector('[data-role="spell-body"]').innerHTML = '';
      }
    }
  }
  function place(panel, trigger){
    const r = trigger.getBoundingClientRect();
    panel.style.visibility='hidden'; panel.classList.add('on');
    const pw = panel.offsetWidth, ph = panel.offsetHeight;
    panel.classList.remove('on'); panel.style.visibility='';
    let left = r.left, top = r.bottom + 6;
    if (left + pw > innerWidth - 10) left = innerWidth - pw - 10;
    if (left < 10) left = 10;
    if (top + ph > innerHeight - 10) top = Math.max(10, r.top - ph - 6);
    panel.style.left = left + 'px'; panel.style.top = top + 'px';
  }
  function open(id, type, trigger){
    closeAll();
    const panel = document.getElementById(id); if (!panel) return;
    lastTrigger = trigger;
    if (trigger) fill(panel, trigger.dataset);
    if (type === 'pop') place(panel, trigger);
    scrim.classList.add('on');
    requestAnimationFrame(() => panel.classList.add('on'));
    if (type !== 'pop'){ const f = panel.querySelector('input,select,textarea,button:not(.x)'); if (f) setTimeout(()=>{ try{f.focus();}catch(e){} }, 60); }
  }
  document.addEventListener('click', (e) => {
    const trig = e.target.closest('[data-drawer],[data-modal],[data-pop]');
    if (trig){ e.preventDefault();
      if (trig.dataset.drawer) return open(trig.dataset.drawer,'drawer',trig);
      if (trig.dataset.modal)  return open(trig.dataset.modal,'modal',trig);
      if (trig.dataset.pop)    return open(trig.dataset.pop,'pop',trig);
    }
    if (e.target.closest('[data-close]')) closeAll();
  });
  scrim.addEventListener('click', closeAll);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAll(); });
  /* Re-open a modal after a roll redirect by reading the URL hash. */
  if (location.hash) {
    const id = location.hash.slice(1);
    const panel = document.getElementById(id);
    if (panel && panel.classList.contains('overlay')) {
      open(id, 'modal', null);
      history.replaceState(null, '', location.pathname + location.search);
    }
  }
  /* Equipment tab-switching lives in inventory.js (loaded by the shared
     equipment partial) so it works on the wizard page too, which has no
     overlay scrim / .ov-body. */
})();
