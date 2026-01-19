import{r as e,j as o}from"./index-SaevF0Eg.js";const r=({active:a})=>(e.useEffect(()=>{if(a)return document.documentElement.classList.add("kosma-mode"),()=>document.documentElement.classList.remove("kosma-mode")},[a]),o.jsxs(o.Fragment,{children:[a&&o.jsxs("div",{className:"kosma-overlay",children:[o.jsx("div",{className:"kosma-vignette"}),o.jsx("div",{className:"kosma-glow-orb kosma-glow-1"}),o.jsx("div",{className:"kosma-glow-orb kosma-glow-2"})]}),o.jsx("style",{children:`
        :root.kosma-mode {
          --kosma-dark: #02040a;
          --kosma-blue: #1a2a4a;
          --kosma-purple: #2a1a3a;
        }
        .kosma-mode body { background-color: var(--kosma-dark) !important; color: #8e9aaf !important; }
        .kosma-overlay { position: fixed; inset: 0; pointer-events: none; z-index: 9998; overflow: hidden; }
        .kosma-vignette { 
          position: absolute; 
          inset: 0; 
          background: radial-gradient(circle at 60% 50%, transparent 20%, rgba(0, 0, 0, 0.8) 120%); 
        }
        .kosma-mode aside {
          background-color: #05070a !important;
          border-right: 1px solid rgba(26, 42, 74, 0.5) !important;
          z-index: 10000; /* Ensure sidebar is above vignette */
        }
        .kosma-glow-orb { position: fixed; width: 65vw; height: 65vw; border-radius: 50%; filter: blur(150px); opacity: 0.15; z-index: -1; animation: kosma-float 25s ease-in-out infinite alternate; }
        .kosma-glow-1 { background: var(--kosma-blue); left: -15%; top: -15%; }
        .kosma-glow-2 { background: var(--kosma-purple); right: -15%; bottom: -15%; }
        @keyframes kosma-float { from { transform: scale(1); } to { transform: scale(1.2); } }
      `})]}));export{r as KosmaTheme};
