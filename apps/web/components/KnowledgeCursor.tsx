'use client';
import {useEffect, useRef} from 'react';

export default function KnowledgeCursor({enabled}: {enabled: boolean}) {
  const surface = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const layer = surface.current;
    if (!enabled || !layer) return;
    const fine = matchMedia('(hover: hover) and (pointer: fine) and (min-width: 761px) and (forced-colors: none)');
    const ring = layer.querySelector<HTMLElement>('.knowledge-cursor-ring')!;
    const point = layer.querySelector<HTMLElement>('.knowledge-cursor-point')!;
    const label = layer.querySelector<HTMLElement>('.knowledge-cursor-label')!;
    const ripple = layer.querySelector<HTMLElement>('.knowledge-cursor-ripple')!;
    const trails = [...layer.querySelectorAll<HTMLElement>('.knowledge-ink-trail')];
    const tail = trails.map(() => ({x:0,y:0}));
    let x=0,y=0,ringX=0,ringY=0,shown=false,frame=0,lastMove=0,layoutFrame=0;
    let mouseActive=false;
    let action: Element|null = null;
    let box: DOMRect|null = null;
    const moveTo=(element:HTMLElement,px:number,py:number)=>{element.style.transform=`translate3d(${px}px,${py}px,0)`;};
    function paint(time:number) {
      frame=0;
      const aimX=box ? x+(box.left+box.width/2-x)*.12 : x;
      const aimY=box ? y+(box.top+box.height/2-y)*.12 : y;
      ringX+=(aimX-ringX)*.26;ringY+=(aimY-ringY)*.26;
      moveTo(ring,ringX,ringY);
      let previous={x,y};
      let unsettled=Math.abs(aimX-ringX)+Math.abs(aimY-ringY)>.2;
      tail.forEach((position,index)=>{
        position.x+=(previous.x-position.x)*.36;position.y+=(previous.y-position.y)*.36;
        const dx=position.x-x,dy=position.y-y,distance=Math.hypot(dx,dy);
        if(distance>48){position.x=x+dx/distance*48;position.y=y+dy/distance*48;}
        moveTo(trails[index],position.x,position.y);
        trails[index].style.opacity=String(Math.max(0,1-(time-lastMove)/420)*(.22-index*.055));
        unsettled=unsettled||Math.abs(position.x-previous.x)+Math.abs(position.y-previous.y)>.3;
        previous=position;
      });
      if(shown&&(unsettled||time-lastMove<430))frame=requestAnimationFrame(paint);
    }
    function hide() {
      shown=false;action=null;box=null;
      layer!.classList.remove('knowledge-cursor-visible','knowledge-cursor-action','knowledge-cursor-down','knowledge-cursor-light');
      ripple.classList.remove('ink-click');
      document.body.classList.remove('knowledge-cursor-on');
      cancelAnimationFrame(frame);frame=0;
    }
    function reset() {
      mouseActive=false;
      cancelAnimationFrame(layoutFrame);layoutFrame=0;
      hide();
    }
    function updateTarget(target:Element|null) {
      if(!mouseActive||!fine.matches||document.hidden||!target?.closest('.landing')||target.closest('input,textarea,select,[contenteditable="true"],[data-native-cursor],button:disabled')){hide();return;}
      if(!shown){ringX=x;ringY=y;tail.forEach(p=>{p.x=x;p.y=y;});shown=true;}
      const next=target.closest('a,button,summary,[role="tab"],[data-cursor]');
      if(next!==action){
        action=next;
        const hint=action?.getAttribute('data-cursor') || (action?.tagName==='SUMMARY'?'READ':action?.getAttribute('href')?.startsWith('#')?'EXPLORE':action?'OPEN':'');
        label.textContent=hint;
        layer!.classList.toggle('knowledge-cursor-action',!!action);
      }
      // The same action can move underneath a stationary pointer while scrolling.
      box=action?.getBoundingClientRect()||null;
      layer!.classList.toggle('knowledge-cursor-light', !!target.closest('.orange,.final-cta'));
      layer!.classList.add('knowledge-cursor-visible');
      document.body.classList.add('knowledge-cursor-on');
      moveTo(point,x,y);
      if(!frame)frame=requestAnimationFrame(paint);
    }
    function move(event:PointerEvent) {
      if(event.pointerType!=='mouse'||!fine.matches||document.hidden){reset();return;}
      mouseActive=true;x=event.clientX;y=event.clientY;lastMove=performance.now();
      updateTarget(event.target instanceof Element?event.target:null);
    }
    function layoutChanged() {
      if(!mouseActive||layoutFrame)return;
      layoutFrame=requestAnimationFrame(()=>{
        layoutFrame=0;
        if(mouseActive)updateTarget(document.elementFromPoint(x,y));
      });
    }
    function down(event:PointerEvent) {
      if(!shown||event.button!==0)return;
      layer!.classList.add('knowledge-cursor-down');
      moveTo(ripple,event.clientX,event.clientY);
      ripple.classList.remove('ink-click');
      void ripple.offsetWidth;
      ripple.classList.add('ink-click');
    }
    function up(){layer!.classList.remove('knowledge-cursor-down');}
    function leave(event:MouseEvent){if(!event.relatedTarget)reset();}
    function key(event:globalThis.KeyboardEvent){if(['Tab','Escape','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','PageUp','PageDown','Home','End',' '].includes(event.key))reset();}
    function visibility(){if(document.hidden)reset();}
    document.addEventListener('pointermove',move,{passive:true});document.addEventListener('pointerdown',down,{passive:true});document.addEventListener('pointerup',up,{passive:true});
    document.addEventListener('mouseout',leave);document.addEventListener('keydown',key);document.addEventListener('visibilitychange',visibility);
    addEventListener('blur',reset);addEventListener('scroll',layoutChanged,{passive:true,capture:true});addEventListener('resize',layoutChanged);fine.addEventListener('change',reset);
    return()=>{reset();document.removeEventListener('pointermove',move);document.removeEventListener('pointerdown',down);document.removeEventListener('pointerup',up);document.removeEventListener('mouseout',leave);document.removeEventListener('keydown',key);document.removeEventListener('visibilitychange',visibility);removeEventListener('blur',reset);removeEventListener('scroll',layoutChanged,true);removeEventListener('resize',layoutChanged);fine.removeEventListener('change',reset);};
  },[enabled]);
  return <div className="knowledge-cursor-layer" ref={surface} aria-hidden="true"><div className="knowledge-cursor-ring"><span className="knowledge-cursor-lens"/><span className="knowledge-cursor-label"/></div><div className="knowledge-cursor-point"/>{[0,1,2].map(i=><span className="knowledge-ink-trail" key={i}/>)}<div className="knowledge-cursor-ripple"><span/><i/><b/></div></div>;
}
