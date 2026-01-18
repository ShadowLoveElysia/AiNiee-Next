import{r as o,j as e}from"./index-DjTeLmkM.js";const r=({active:s})=>(o.useEffect(()=>{if(s)return document.documentElement.classList.add("su-mode"),()=>document.documentElement.classList.remove("su-mode")},[s]),e.jsxs(e.Fragment,{children:[s&&e.jsxs("div",{className:"su-overlay",children:[e.jsx("div",{className:"su-vignette"}),e.jsx("div",{className:"su-glow-orb su-glow-1"}),e.jsx("div",{className:"su-glow-orb su-glow-2"})]}),e.jsx("style",{children:`
        :root.su-mode {
          --su-green: #88a070;
          --su-teal: #4a6b6b;
          --su-bg: #0e1110;
        }
        .su-mode body { background-color: var(--su-bg) !important; color: #d0d5cc !important; }
        .su-overlay { position: fixed; inset: 0; pointer-events: none; z-index: 9998; overflow: hidden; }
        .su-vignette { position: absolute; inset: 0; background: radial-gradient(circle, transparent 50%, rgba(136, 160, 112, 0.15) 100%); }
        .su-glow-orb { position: fixed; width: 60vw; height: 60vw; border-radius: 50%; filter: blur(140px); opacity: 0.12; z-index: -1; animation: su-float 30s ease-in-out infinite alternate; }
        .su-glow-1 { background: var(--su-green); left: -10%; top: -15%; }
        .su-glow-2 { background: var(--su-teal); right: -10%; bottom: -15%; }
        @keyframes su-float { from { transform: scale(1); } to { transform: scale(1.1) translate(2%, 2%); } }
      `})]}));export{r as SuTheme};
