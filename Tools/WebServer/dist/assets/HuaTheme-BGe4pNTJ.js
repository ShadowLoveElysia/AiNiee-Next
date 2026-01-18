import{r as o,j as a}from"./index-DjTeLmkM.js";const r=({active:e})=>(o.useEffect(()=>{if(e)return document.documentElement.classList.add("hua-mode"),()=>document.documentElement.classList.remove("hua-mode")},[e]),a.jsxs(a.Fragment,{children:[e&&a.jsxs("div",{className:"hua-overlay",children:[a.jsx("div",{className:"hua-vignette"}),a.jsx("div",{className:"hua-glow-orb hua-glow-1"}),a.jsx("div",{className:"hua-glow-orb hua-glow-2"})]}),a.jsx("style",{children:`
        :root.hua-mode {
          --hua-red: #8b0000;
          --hua-orange: #d4a017;
          --hua-bg: #0f0a0a;
        }
        .hua-mode body { background-color: var(--hua-bg) !important; color: #dcdcdc !important; }
        .hua-overlay { position: fixed; inset: 0; pointer-events: none; z-index: 9998; overflow: hidden; }
        .hua-vignette { position: absolute; inset: 0; background: radial-gradient(circle, transparent 40%, rgba(139, 0, 0, 0.15) 100%); }
        .hua-glow-orb { position: fixed; width: 60vw; height: 60vw; border-radius: 50%; filter: blur(120px); opacity: 0.15; z-index: -1; animation: hua-float 20s ease-in-out infinite alternate; }
        .hua-glow-1 { background: var(--hua-red); left: -10%; top: -10%; }
        .hua-glow-2 { background: var(--hua-orange); right: -10%; bottom: -10%; }
        @keyframes hua-float { from { transform: translate(0,0); } to { transform: translate(5%, 5%); } }
      `})]}));export{r as HuaTheme};
