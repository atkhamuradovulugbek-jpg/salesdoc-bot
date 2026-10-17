(function(){
  var slides=[].slice.call(document.querySelectorAll('.slide'));
  var N=slides.length, cur=-1, root=document.documentElement;
  var cnt=document.getElementById('cnt'), bar=document.getElementById('bar'), hint=document.getElementById('hint');
  var RM=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---- layout: scale 1600x900 stage, or mobile flow ---- */
  function layout(){
    var w=window.innerWidth,h=window.innerHeight;
    var mobile = w<700 || (w<1100 && h>w*1.15);
    document.body.classList.toggle('m',mobile);
    root.style.setProperty('--s', Math.min(w/1600,h/900));
  }
  window.addEventListener('resize',layout); layout();

  /* ---- count-up numbers (final text is always the original) ---- */
  var NUM=/\d{1,3}(?: \d{3})+(?!\d)|\d+(?:\.\d+)?/g;
  function fmt(v,tok){
    var dec=(tok.split('.')[1]||'').length, grouped=/ /.test(tok);
    var s=v.toFixed(dec);
    if(grouped){var p=s.split('.');p[0]=p[0].replace(/\B(?=(\d{3})+(?!\d))/g,' ');s=p.join('.');}
    return s;
  }
  function render(el,k){
    var o=el.__o;
    if(k>=1){el.textContent=o;return;}
    el.textContent=o.replace(NUM,function(tok){return fmt(parseFloat(tok.replace(/ /g,''))*k,tok);});
  }
  var counters=[].slice.call(document.querySelectorAll('[data-c]'));
  counters.forEach(function(el){el.__o=el.textContent;});
  function resetCounters(s){ s.querySelectorAll('[data-c]').forEach(function(el){ cancelAnimationFrame(el.__raf); clearTimeout(el.__t); render(el,0); }); }
  function runCounters(s){
    s.querySelectorAll('[data-c]').forEach(function(el){
      if(RM){render(el,1);return;}
      var host=el.closest('[style*="--d"]'), d=0;
      if(host){d=parseFloat(getComputedStyle(host).getPropertyValue('--d'))||0;}
      var hd=el.closest('[style*="--hd"]'); if(hd){d=parseFloat(getComputedStyle(hd).getPropertyValue('--hd'))||0;}
      var delay=d+(el.closest('table')?700:380), dur=el.closest('table')?1000:1500, t0;
      render(el,0);
      el.__t=setTimeout(function(){
        function step(t){ if(!t0)t0=t; var k=Math.min((t-t0)/dur,1); render(el,1-Math.pow(1-k,3)); if(k<1) el.__raf=requestAnimationFrame(step); }
        el.__raf=requestAnimationFrame(step);
      },delay);
    });
  }

  /* ---- logo: nur halqasi (4-variant) + yo'nalish strelkalari ---- */
  var logo=document.querySelector('.logo'), fx=document.createElement('div');
  fx.className='logo-fx'; fx.innerHTML='<i class="core"></i><i class="ring r1"></i><i class="ring r2"></i>';
  if(logo) logo.parentNode.insertBefore(fx, logo.nextSibling);
  function placeFx(){
    if(!logo) return;
    var w=logo.offsetWidth, h=logo.offsetHeight||w*.875;
    var cx=logo.offsetLeft+(document.body.classList.contains('m')?w/2:0);   /* desktop: translateX(-50%) */
    fx.style.left=cx+'px'; fx.style.top=(logo.offsetTop+h/2)+'px';
    fx.style.setProperty('--d', (Math.max(w,h)*2.3)+'px');                  /* logoning haqiqiy o'lchamiga mos */
  }
  function fxLogo(){
    if(!logo) return;
    logo.classList.remove('fx'); fx.classList.remove('go');
    void logo.offsetWidth; placeFx();
    logo.classList.add('fx'); fx.classList.add('go');
  }
  window.addEventListener('resize', placeFx);
  [].slice.call(document.querySelectorAll('table td span.v')).forEach(function(el){
    var t=el.textContent.trim();
    if(t==='▲'||t==='↑') el.classList.add('arr','up');
    else if(t==='▼'||t==='↓') el.classList.add('arr','down');
    else if(t==='='&&el.parentNode.classList.contains('c-m')) el.classList.add('arr','eq');
  });

  /* ---- navigation ---- */
  function go(i){
    i=Math.max(0,Math.min(N-1,i));
    if(i===cur) return;
    var dir=i>cur?1:-1, prev=slides[cur];
    if(prev){ prev.classList.remove('on'); prev.classList.toggle('left',dir>0); resetCounters(prev); }
    var s=slides[i];
    s.classList.toggle('left',dir<0);
    void s.offsetWidth;
    s.classList.remove('left');
    s.classList.add('on'); s.scrollTop=0; document.body.classList.remove('scrolled');
    cur=i;
    cnt.textContent=(i+1)+' / '+N;
    bar.style.width=((i+1)/N*100)+'%';
    if(history.replaceState) history.replaceState(null,'','#'+(i+1));
    runCounters(s);
    fxLogo(i);
  }
  function next(){go(cur+1)} function prev(){go(cur-1)}
  window.deckGo=function(n){go(n-1)};

  document.addEventListener('keydown',function(e){
    var k=e.key;
    if(k==='ArrowRight'||k===' '||k==='PageDown'||k==='Enter'||k==='ArrowDown'&&!document.body.classList.contains('m')){e.preventDefault();next();}
    else if(k==='ArrowLeft'||k==='PageUp'||k==='Backspace'||k==='ArrowUp'&&!document.body.classList.contains('m')){e.preventDefault();prev();}
    else if(k==='Home'){go(0)} else if(k==='End'){go(N-1)}
    else if(k==='f'||k==='F'){toggleFS()}
    hideHint();
  });
  document.getElementById('next').addEventListener('click',function(e){e.stopPropagation();next();});
  document.getElementById('prev').addEventListener('click',function(e){e.stopPropagation();prev();});
  document.getElementById('fs').addEventListener('click',function(e){e.stopPropagation();toggleFS();});
  document.getElementById('deck').addEventListener('click',function(e){
    if(document.body.classList.contains('m')) return;
    if(e.target.closest('button,a')) return;
    if(e.clientX < window.innerWidth*0.22) prev(); else next();
    hideHint();
  });
  function toggleFS(){
    var d=document, el=d.documentElement;
    if(!(d.fullscreenElement||d.webkitFullscreenElement)){ (el.requestFullscreen||el.webkitRequestFullscreen||function(){}).call(el); }
    else { (d.exitFullscreen||d.webkitExitFullscreen).call(d); }
  }

  /* ---- swipe ---- */
  var sx=0,sy=0,sw=null;
  document.addEventListener('touchstart',function(e){
    var t=e.touches[0]; sx=t.clientX; sy=t.clientY; sw=e.target.closest('.tscroll');
    if(sw){ sw.__l=sw.scrollLeft<=2; sw.__r=sw.scrollLeft+sw.clientWidth>=sw.scrollWidth-2; }
  },{passive:true});
  document.addEventListener('touchend',function(e){
    var t=e.changedTouches[0], dx=t.clientX-sx, dy=t.clientY-sy;
    if(Math.abs(dx)<55 || Math.abs(dx)<Math.abs(dy)*1.3) return;
    if(sw && sw.scrollWidth>sw.clientWidth+4){ if(dx<0 && !sw.__r) return; if(dx>0 && !sw.__l) return; }
    if(dx<0) next(); else prev();
    hideHint();
  },{passive:true});

  /* ---- wheel (debounced) ---- */
  var wl=0;
  window.addEventListener('wheel',function(e){
    if(document.body.classList.contains('m')) return;
    var now=Date.now(); if(now-wl<900||Math.abs(e.deltaY)<25) return; wl=now;
    if(e.deltaY>0) next(); else prev();
  },{passive:true});

  slides.forEach(function(s){ s.addEventListener('scroll',function(){ document.body.classList.toggle('scrolled', s.scrollTop>24); },{passive:true}); });
  var hintT;
  function hideHint(){ if(hint) hint.classList.add('hide'); }
  hintT=setTimeout(hideHint,5000);

  var start=parseInt((location.hash||'').slice(1),10);
  go(isNaN(start)?0:start-1);
})();
