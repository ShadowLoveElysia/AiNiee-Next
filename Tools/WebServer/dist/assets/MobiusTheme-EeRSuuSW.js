import{r as e,j as o}from"./index-_VzYsfab.js";const t=({active:r})=>(e.useEffect(()=>{if(r)return document.documentElement.classList.add("mobius-mode"),()=>{document.documentElement.classList.remove("mobius-mode")}},[r]),o.jsxs(o.Fragment,{children:[r&&o.jsxs("div",{className:"mobius-overlay",children:[o.jsx("div",{className:"mobius-vignette"}),o.jsx("div",{className:"mobius-grid"}),o.jsx("div",{className:"mobius-glow-orb mobius-glow-1"}),o.jsx("div",{className:"mobius-glow-orb mobius-glow-2"}),o.jsx("div",{className:"mobius-dna-container"})]}),o.jsx("style",{children:`
        :root.mobius-mode {
          --mobius-green: #00ff41;
          --mobius-green-dim: #003b00;
          --mobius-black: #050505;
        }

        .mobius-mode body {
          background-color: var(--mobius-black) !important;
          color: var(--mobius-green) !important;
          font-family: 'Courier New', Courier, monospace !important;
        }

        .mobius-mode .bg-slate-900, 
        .mobius-mode aside {
          background-color: #000 !important;
          border-right: 1px solid var(--mobius-green-dim) !important;
        }

        .mobius-mode .text-primary { color: var(--mobius-green) !important; }
        .mobius-mode .bg-primary { 
          background: var(--mobius-green-dim) !important; 
          color: var(--mobius-green) !important;
          border: 1px solid var(--mobius-green) !important;
          text-shadow: 0 0 5px var(--mobius-green);
        }

        .mobius-mode .border-primary { border-color: var(--mobius-green) !important; }

        .mobius-overlay {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 9998;
          overflow: hidden;
        }

        .mobius-vignette {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle, transparent 30%, rgba(0, 20, 0, 0.6) 100%);
        }

        .mobius-glow-orb {
          position: fixed;
          width: 50vw;
          height: 50vw;
          border-radius: 50%;
          filter: blur(130px);
          opacity: 0.2;
          z-index: -1;
          pointer-events: none;
          animation: mobius-float 25s ease-in-out infinite alternate;
        }
        .mobius-glow-1 { background: #00ff41; left: -15%; top: -10%; }
        .mobius-glow-2 { background: #003b00; right: -15%; bottom: -10%; animation-delay: -12s; }

        @keyframes mobius-float {
          from { transform: translate(0, 0) scale(1) rotate(0deg); }
          to { transform: translate(5%, 10%) scale(1.3) rotate(15deg); }
        }

        .mobius-grid {
          position: absolute;
          inset: 0;
          background-image: 
            linear-gradient(var(--mobius-green-dim) 1px, transparent 1px),
            linear-gradient(90deg, var(--mobius-green-dim) 1px, transparent 1px);
          background-size: 50px 50px;
        }

        /* Glitch effect for buttons */
        .mobius-mode button:hover {
          animation: mobius-glitch 0.2s infinite;
          background: var(--mobius-green) !important;
          color: black !important;
        }

        @keyframes mobius-glitch {
          0% { transform: translate(0); }
          20% { transform: translate(-2px, 2px); }
          40% { transform: translate(-2px, -2px); }
          60% { transform: translate(2px, 2px); }
          80% { transform: translate(2px, -2px); }
          100% { transform: translate(0); }
        }

        .mobius-mode .bg-surface, .mobius-mode .bg-surface/50 {
          background: rgba(0, 20, 0, 0.8) !important;
          border: 1px solid var(--mobius-green-dim) !important;
        }

        .mobius-mode input, .mobius-mode select, .mobius-mode textarea, .mobius-mode .bg-slate-900 {
          background-color: black !important;
          border: 1px solid var(--mobius-green-dim) !important;
          color: var(--mobius-green) !important;
        }
        
        .mobius-mode input:focus {
          border-color: var(--mobius-green) !important;
          box-shadow: 0 0 15px var(--mobius-green-dim) !important;
        }

        /* Snake eye or DNA helix decoration */
        .mobius-dna-container {
            position: absolute;
            right: 5%;
            top: 10%;
            bottom: 10%;
            width: 100px;
            background: repeating-linear-gradient(transparent, transparent 20px, var(--mobius-green-dim) 21px, var(--mobius-green-dim) 22px);
            opacity: 0.3;
        }
      `})]}));export{t as MobiusTheme};
