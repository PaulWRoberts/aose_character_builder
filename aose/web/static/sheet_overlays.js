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
    if (type !== 'pop'){ const f = panel.querySelector('input,select,textarea,button:not(.x)'); if (f) setTimeout(()=>{ try{f.focus({preventScroll:true});}catch(e){} }, 60); }
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
  /* Preserve the equipment drawer across form submissions inside it.
   * On submit: save drawer id, .ov-body scrollTop, and active tab to sessionStorage.
   * On next load: re-open the drawer at the same tab and scroll position. */
  document.addEventListener('submit', function(e){
    const drawer = e.target.closest('.overlay.drawer');
    if (!drawer) return;
    const body = drawer.querySelector('.ov-body');
    const tab  = drawer.querySelector('.tabs .tab.on');
    sessionStorage.setItem('ss_drawer', drawer.id);
    sessionStorage.setItem('ss_scroll', body ? body.scrollTop : 0);
    sessionStorage.setItem('ss_tab',   tab ? tab.dataset.tab : '');
  });
  (function(){
    const did = sessionStorage.getItem('ss_drawer'); if (!did) return;
    const scroll = parseInt(sessionStorage.getItem('ss_scroll') || '0', 10);
    const tabId  = sessionStorage.getItem('ss_tab') || '';
    sessionStorage.removeItem('ss_drawer');
    sessionStorage.removeItem('ss_scroll');
    sessionStorage.removeItem('ss_tab');
    open(did, 'drawer', null);
    const panel = document.getElementById(did); if (!panel) return;
    if (tabId){
      const tab = panel.querySelector('.tabs .tab[data-tab="' + tabId + '"]');
      if (tab){
        const tabs = tab.closest('.tabs');
        const root = tabs.closest('.equip-ui') || tabs.parentElement;
        if (tabs && root){
          tabs.querySelectorAll('.tab').forEach(x => x.classList.toggle('on', x === tab));
          root.querySelectorAll('[data-pane]').forEach(p => { p.hidden = p.dataset.pane !== tabId; });
        }
      }
    }
    if (scroll > 0){
      const body = panel.querySelector('.ov-body');
      if (body) requestAnimationFrame(() => requestAnimationFrame(() => { body.scrollTop = scroll; }));
    }
  })();
  /* Equipment tab-switching lives in inventory.js (loaded by the shared
     equipment partial) so it works on the wizard page too, which has no
     overlay scrim / .ov-body. */
})();
