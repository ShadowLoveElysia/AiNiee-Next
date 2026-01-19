import{r as o,j as e}from"./index-CPL3COVj.js";const i=({active:n})=>(o.useEffect(()=>{if(n)return document.documentElement.classList.add("kevin-mode"),()=>document.documentElement.classList.remove("kevin-mode")},[n]),e.jsxs(e.Fragment,{children:[n&&e.jsxs("div",{className:"theme-overlay-container",children:[e.jsx("div",{className:"kevin-vignette"}),e.jsx("div",{className:"kevin-glow-orb kevin-glow-1"}),e.jsx("div",{className:"kevin-glow-orb kevin-glow-2"}),e.jsx("div",{className:"kevin-frost-vignette"})]}),e.jsx("style",{children:`
        :root.kevin-mode {
          --kevin-primary: #00f2ff;
          --kevin-secondary: #70a1ff;
          --kevin-bg: #000814;
          --kevin-surface: rgba(0, 20, 40, 0.7);
        }

        .kevin-mode body {
          background-color: var(--kevin-bg) !important;
          color: #e0faff !important;
        }

        .kevin-mode .bg-slate-900, 
        .kevin-mode aside {
          background: linear-gradient(to bottom, #001220, #000814) !important;
          border-right: 1px solid rgba(0, 242, 255, 0.3) !important;
        }

        .kevin-mode .text-primary { color: var(--kevin-primary) !important; }
        .kevin-mode .bg-primary { 
          background: linear-gradient(135deg, #00f2ff, #0060ff) !important;
          color: #000 !important;
          font-weight: 900 !important;
          clip-path: polygon(5% 0, 100% 0, 95% 100%, 0 100%);
        }

        .kevin-mode .bg-surface, .kevin-mode .bg-surface/50 {
          background: var(--kevin-surface) !important;
          backdrop-filter: blur(12px) !important;
          border: 1px solid rgba(0, 242, 255, 0.15) !important;
          box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4) !important;
        }

        /* 编辑栏适配 */
        .kevin-mode input, .kevin-mode select, .kevin-mode textarea, .kevin-mode .bg-slate-900 {
          background-color: rgba(0, 10, 20, 0.9) !important;
          border: 1px solid rgba(0, 242, 255, 0.2) !important;
          color: white !important;
        }
        .kevin-mode input:focus { border-color: var(--kevin-primary) !important; }

        .theme-overlay-container {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 9998;
          overflow: hidden;
        }

        .kevin-vignette {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle, transparent 40%, rgba(0, 242, 255, 0.05) 100%);
        }

        /* 氛围光晕 */
        .kevin-glow-orb {
          position: fixed;
          width: 60vw;
          height: 60vw;
          border-radius: 50%;
          filter: blur(120px);
          opacity: 0.12;
          z-index: -1;
          pointer-events: none;
          animation: kevin-float 20s ease-in-out infinite alternate;
        }
        .kevin-glow-1 { background: #00f2ff; left: -10%; top: -10%; }
        .kevin-glow-2 { background: #0060ff; right: -10%; bottom: -10%; animation-delay: -10s; }

        .kevin-frost-vignette {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: -1;
          background: radial-gradient(circle at center, transparent 60%, rgba(0, 242, 255, 0.03) 100%);
          box-shadow: inset 0 0 150px rgba(0, 242, 255, 0.05);
        }

        @keyframes kevin-float {
          from { transform: translate(0, 0) scale(1); }
          to { transform: translate(5%, 5%) scale(1.1); }
        }
      `})]}));export{i as KevinTheme};
