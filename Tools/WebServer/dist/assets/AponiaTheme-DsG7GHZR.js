import{r as n,j as a}from"./index-BJxQTcBU.js";const i=({active:o})=>(n.useEffect(()=>{if(o)return document.documentElement.classList.add("aponia-mode"),()=>document.documentElement.classList.remove("aponia-mode")},[o]),a.jsxs(a.Fragment,{children:[o&&a.jsxs("div",{className:"aponia-overlay",children:[a.jsx("div",{className:"aponia-vignette"}),a.jsx("div",{className:"aponia-glow-orb aponia-glow-1"}),a.jsx("div",{className:"aponia-glow-orb aponia-glow-2"})]}),a.jsx("style",{children:`
        :root.aponia-mode {
          --aponia-purple: #9d81ba;
          --aponia-blue: #5b7da1;
          --aponia-bg: #0b0c10;
        }
        .aponia-mode body { background-color: var(--aponia-bg) !important; color: #d1d1d1 !important; }
        .aponia-overlay { position: fixed; inset: 0; pointer-events: none; z-index: 9998; overflow: hidden; }
        .aponia-vignette { position: absolute; inset: 0; background: radial-gradient(circle, transparent 40%, rgba(157, 129, 186, 0.2) 100%); }
        .aponia-glow-orb { position: fixed; width: 60vw; height: 60vw; border-radius: 50%; filter: blur(120px); opacity: 0.15; z-index: -1; pointer-events: none; animation: aponia-float 25s ease-in-out infinite alternate; }
        .aponia-glow-1 { background: var(--aponia-purple); left: -10%; top: -10%; }
        .aponia-glow-2 { background: var(--aponia-blue); right: -10%; bottom: -10%; animation-delay: -5s; }
        @keyframes aponia-float { from { transform: translate(0, 0) scale(1); } to { transform: translate(5%, 10%) scale(1.2); } }
      `})]}));export{i as AponiaTheme};
