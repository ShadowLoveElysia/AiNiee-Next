import{r as a,j as o}from"./index-DvvkBrRC.js";const e=({active:r})=>(a.useEffect(()=>{if(r)return document.documentElement.classList.add("pardo-mode"),()=>{document.documentElement.classList.remove("pardo-mode")}},[r]),o.jsxs(o.Fragment,{children:[r&&o.jsxs("div",{className:"pardo-overlay",children:[o.jsx("div",{className:"pardo-vignette"}),o.jsx("div",{className:"pardo-glow-orb pardo-glow-1"}),o.jsx("div",{className:"pardo-glow-orb pardo-glow-2"}),o.jsx("div",{className:"pardo-paw-container"})]}),o.jsx("style",{children:`
        :root.pardo-mode {
          --pardo-yellow: #f8e1a7;
          --pardo-orange: #e6b8a2;
          --pardo-brown: #7f5539;
          --pardo-bg: #fffcf2;
        }

        .pardo-mode body {
          background-color: var(--pardo-bg) !important;
          color: var(--pardo-brown) !important;
        }

        .pardo-mode .bg-slate-900, 
        .pardo-mode aside {
          background-color: #ede0d4 !important;
          border-right: 2px solid var(--pardo-orange) !important;
        }

        .pardo-mode aside * {
            color: var(--pardo-brown) !important;
        }

        .pardo-mode .text-primary { color: var(--pardo-brown) !important; }
        .pardo-mode .bg-primary { 
          background: var(--pardo-orange) !important; 
          color: white !important;
          border-radius: 12px !important;
          font-weight: bold !important;
          box-shadow: 0 4px 10px rgba(230, 184, 162, 0.3) !important;
        }

        .pardo-mode .bg-surface, .pardo-mode .bg-surface/50 {
          background: rgba(255, 255, 255, 0.9) !important;
          border: 2px solid var(--pardo-yellow) !important;
          border-radius: 20px !important;
        }

        /* Specialized Input Styles - Fixed visibility and recognition */
        .pardo-mode input, 
        .pardo-mode select, 
        .pardo-mode textarea {
          background-color: #fffef0 !important;
          color: var(--pardo-brown) !important;
          border: 2px solid var(--pardo-yellow) !important;
          padding: 8px 12px !important;
          transition: all 0.3s ease !important;
        }

        .pardo-mode input:focus, 
        .pardo-mode select:focus, 
        .pardo-mode textarea:focus {
          border-color: var(--pardo-orange) !important;
          background-color: #ffffff !important;
          box-shadow: 0 0 0 2px rgba(230, 184, 162, 0.2) !important;
          outline: none !important;
        }

        /* Container Styles - Keeping them distinct from inputs */
        .pardo-mode .bg-slate-900,
        .pardo-mode .bg-slate-950,
        .pardo-mode .bg-slate-800/50,
        .pardo-mode aside {
          background-color: #ede0d4 !important;
          color: var(--pardo-brown) !important;
          border-right: 2px solid var(--pardo-orange) !important;
        }

        .pardo-mode input::placeholder {
          color: rgba(127, 85, 57, 0.4) !important;
        }

        .pardo-mode .focus:border-primary:focus {
          border-color: var(--pardo-brown) !important;
        }

        .pardo-overlay {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 9998;
          overflow: hidden;
        }

        .pardo-vignette {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle, transparent 40%, rgba(127, 85, 57, 0.15) 100%);
        }

        .pardo-glow-orb {
          position: fixed;
          width: 50vw;
          height: 50vw;
          border-radius: 50%;
          filter: blur(120px);
          opacity: 0.15;
          z-index: -1;
          pointer-events: none;
          animation: pardo-float-glow 20s ease-in-out infinite alternate;
        }
        .pardo-glow-1 { background: var(--pardo-yellow); left: -10%; top: -10%; }
        .pardo-glow-2 { background: var(--pardo-orange); right: -10%; bottom: -10%; animation-delay: -7s; }

        @keyframes pardo-float-glow {
          from { transform: translate(0, 0) scale(1); }
          to { transform: translate(8%, 12%) scale(1.1); }
        }

        .pardo-mode button:hover {
          transform: scale(1.05) rotate(2deg);
          background-color: var(--pardo-orange) !important;
          color: white !important;
        }

        /* 猫爪光标效果 (Simulated) */
        .pardo-mode .cursor-pointer {
            cursor: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="%23f39c12"><path d="M12 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm-4.5 3c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm9 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zM4.5 10c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm15 0c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zM12 11c-2.5 0-4.5 2-4.5 4.5S9.5 20 12 20s4.5-2 4.5-4.5S14.5 11 12 11z"/></svg>'), auto !important;
        }
      `})]}));export{e as PardofelisTheme};
