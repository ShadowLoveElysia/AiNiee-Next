import{r,j as a}from"./index-DlTvAMcz.js";const t=({active:o})=>(r.useEffect(()=>{if(o)return document.documentElement.classList.add("kalpas-mode"),()=>{document.documentElement.classList.remove("kalpas-mode")}},[o]),a.jsxs(a.Fragment,{children:[o&&a.jsxs("div",{className:"kalpas-overlay",children:[a.jsx("div",{className:"kalpas-vignette"}),a.jsx("div",{className:"kalpas-glow-orb kalpas-glow-1"}),a.jsx("div",{className:"kalpas-glow-orb kalpas-glow-2"}),a.jsx("div",{className:"kalpas-embers"})]}),a.jsx("style",{children:`
        :root.kalpas-mode {
          --kalpas-red: #ff4d4d;
          --kalpas-orange: #ff8c00;
          --kalpas-black: #1a1a1a;
        }

        .kalpas-mode body {
          background-color: var(--kalpas-black) !important;
          color: #ddd !important;
        }

        .kalpas-mode .bg-slate-900, 
        .kalpas-mode aside {
          background-color: #000 !important;
          border-right: 2px solid var(--kalpas-red) !important;
        }

        .kalpas-mode .text-primary { color: var(--kalpas-red) !important; }
        .kalpas-mode .bg-primary { 
          background: var(--kalpas-red) !important; 
          color: white !important;
          border-radius: 0 !important;
          transform: skewX(-10deg);
        }

        .kalpas-mode .bg-surface, .kalpas-mode .bg-surface/50 {
          background: rgba(40, 40, 40, 0.9) !important;
          border: 1px solid #444 !important;
          border-bottom: 2px solid var(--kalpas-red) !important;
        }

        .kalpas-mode input, .kalpas-mode select, .kalpas-mode textarea, .kalpas-mode .bg-slate-900 {
          background-color: black !important;
          color: white !important;
          border: 1px solid #555 !important;
        }

        .kalpas-mode input:focus {
          border-color: var(--kalpas-red) !important;
        }

        .kalpas-mode button:hover {
            background-color: var(--kalpas-orange) !important;
            box-shadow: 0 0 20px rgba(255, 77, 77, 0.5) !important;
            transform: skewX(-10deg) scale(1.05);
        }

        .kalpas-overlay {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 9998;
          overflow: hidden;
        }

        .kalpas-vignette {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle at center, transparent 30%, rgba(255, 0, 0, 0.2) 100%);
        }

        .kalpas-glow-orb {
          position: fixed;
          width: 70vw;
          height: 70vw;
          border-radius: 50%;
          filter: blur(140px);
          opacity: 0.15;
          z-index: -1;
          pointer-events: none;
          animation: kalpas-float-glow 12s ease-in-out infinite alternate;
        }
        .kalpas-glow-1 { background: var(--kalpas-red); left: -20%; top: -10%; }
        .kalpas-glow-2 { background: var(--kalpas-orange); right: -20%; bottom: -10%; animation-delay: -3s; }

        @keyframes kalpas-float-glow {
          from { transform: translate(0, 0) scale(1); }
          to { transform: translate(10%, 5%) scale(1.3); }
        }
        
        /* Broken effect */
        .kalpas-mode .bg-surface::before {
            content: "";
            position: absolute;
            top: 0; right: 0;
            width: 30px; height: 30px;
            background: linear-gradient(225deg, var(--kalpas-red) 50%, transparent 50%);
            opacity: 0.5;
        }
      `})]}));export{t as KalpasTheme};
