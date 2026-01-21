import{r as a,j as e}from"./index-Cd9o2-mK.js";const g=({active:i})=>{const t=a.useRef(null);return a.useEffect(()=>{if(i){document.documentElement.classList.add("griseo-mode");const r=t.current;if(!r)return;const o=r.getContext("2d");if(!o)return;r.width=window.innerWidth,r.height=window.innerHeight;const n=s=>{o.globalAlpha=.05,o.fillStyle=`hsl(${200+Math.random()*40}, 70%, 80%)`,o.beginPath(),o.arc(s.clientX,s.clientY,Math.random()*30+20,0,Math.PI*2),o.fill()};return window.addEventListener("mousemove",n),()=>{document.documentElement.classList.remove("griseo-mode"),window.removeEventListener("mousemove",n)}}},[i]),e.jsxs(e.Fragment,{children:[i&&e.jsxs("div",{className:"theme-overlay-container",children:[e.jsx("div",{className:"griseo-vignette"}),e.jsx("div",{className:"griseo-bg-gradient"}),e.jsx("div",{className:"griseo-glow griseo-glow-1"}),e.jsx("div",{className:"griseo-glow griseo-glow-2"}),e.jsx("canvas",{ref:t,style:{position:"fixed",inset:0,pointerEvents:"none",zIndex:9997,opacity:.3}})]}),e.jsx("style",{children:`
        :root.griseo-mode {
          --griseo-blue-light: #f0f9ff;
          --griseo-blue-primary: #a2c2e1;
          --griseo-ink: #334155;
        }

        .griseo-mode body {
          background: linear-gradient(135deg, #ffffff 0%, #f0f7ff 50%, #e0f2fe 100%) !important;
          color: var(--griseo-ink) !important;
        }

        .griseo-mode .bg-slate-900, 
        .griseo-mode aside {
          background-color: rgba(255, 255, 255, 0.8) !important;
          backdrop-filter: blur(10px);
          border-right: 1px solid rgba(162, 194, 225, 0.2) !important;
        }

        .griseo-mode .text-primary { color: #3b82f6 !important; }
        .griseo-mode .bg-primary { 
          background: linear-gradient(135deg, #a2c2e1, #60a5fa) !important; 
          color: white !important;
          border-radius: 8px !important;
        }

        .griseo-mode .bg-surface, .griseo-mode .bg-surface/50 {
          background: rgba(255, 255, 255, 0.6) !important;
          backdrop-filter: blur(16px) !important;
          border: 1px solid rgba(162, 194, 225, 0.1) !important;
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.03) !important;
        }

        /* 编辑栏适配 */
        .griseo-mode input, .griseo-mode select, .griseo-mode textarea, .griseo-mode .bg-slate-900, .griseo-mode .bg-slate-950 {
          background-color: #f8fafc !important;
          color: #1e293b !important;
          border: 1px solid #e2e8f0 !important;
        }
        .griseo-mode input:focus { border-color: var(--griseo-blue-primary) !important; }

        .theme-overlay-container {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 9998;
          overflow: hidden;
        }

        .griseo-vignette {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle, transparent 50%, rgba(162, 194, 225, 0.15) 100%);
        }

        .griseo-glow {
          position: fixed;
          width: 50vw;
          height: 50vw;
          border-radius: 50%;
          filter: blur(100px);
          opacity: 0.4;
          z-index: -1;
          pointer-events: none;
        }
        .griseo-glow-1 { background: #d0e7ff; left: -5%; top: -5%; }
        .griseo-glow-2 { background: #e0f2fe; right: -5%; bottom: -5%; }
      `})]})};export{g as GriseoTheme};
