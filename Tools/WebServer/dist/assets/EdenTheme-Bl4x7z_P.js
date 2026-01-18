import{r as t,j as o}from"./index-BJxQTcBU.js";const l=({active:r})=>{const[n,a]=t.useState([]);return t.useEffect(()=>{if(r){document.documentElement.classList.add("eden-mode");const e=Array.from({length:15}).map((i,d)=>({id:d,x:Math.random()*100,y:Math.random()*100,size:Math.random()*10+5,duration:Math.random()*10+10}));return a(e),()=>{document.documentElement.classList.remove("eden-mode")}}},[r]),o.jsxs(o.Fragment,{children:[r&&o.jsxs("div",{className:"eden-overlay",children:[o.jsx("div",{className:"eden-vignette"}),o.jsx("div",{className:"eden-glow-orb eden-glow-1"}),o.jsx("div",{className:"eden-glow-orb eden-glow-2"}),n.map(e=>o.jsx("div",{className:"eden-particle",style:{left:`${e.x}%`,top:`${e.y}%`,width:`${e.size}px`,height:`${e.size}px`,animationDuration:`${e.duration}s`}},e.id))]}),o.jsx("style",{children:`
        :root.eden-mode {
          --eden-gold: #d4af37;
          --eden-gold-bright: #ffdf00;
          --eden-black: #0a0a0a;
          --eden-accent: #8b0000;
        }

        .eden-mode body {
          background-color: var(--eden-black) !important;
          color: #e0e0e0 !important;
        }

        .eden-mode .bg-slate-900, 
        .eden-mode aside {
          background-color: #050505 !important;
          border-right: 1px solid var(--eden-gold) !important;
        }

        .eden-mode .text-primary { color: var(--eden-gold) !important; }
        .eden-mode .bg-primary { 
          background: linear-gradient(135deg, var(--eden-gold), #b8860b) !important; 
          color: black !important;
          box-shadow: 0 0 15px rgba(212, 175, 55, 0.3) !important;
        }
        
        .eden-mode .border-primary { border-color: var(--eden-gold) !important; }

        .eden-overlay {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 9998;
          overflow: hidden;
        }

        .eden-vignette {
          position: absolute;
          inset: 0;
          background: radial-gradient(circle, transparent 40%, rgba(0,0,0,0.8) 100%);
        }

        .eden-particle {
          position: absolute;
          background: var(--eden-gold);
          border-radius: 50%;
          opacity: 0.2;
          filter: blur(2px);
          animation: eden-float linear infinite;
        }

        @keyframes eden-float {
          0% { transform: translateY(0) scale(1); opacity: 0; }
          20% { opacity: 0.3; }
          80% { opacity: 0.3; }
          100% { transform: translateY(-100vh) scale(1.5); opacity: 0; }
        }

        .eden-mode .cursor-pointer:hover {
          background-color: rgba(212, 175, 55, 0.1) !important;
          color: var(--eden-gold-bright) !important;
        }

        .eden-mode button {
          border-radius: 0 !important;
          border: 1px solid var(--eden-gold) !important;
          text-transform: uppercase;
          letter-spacing: 2px;
        }

        /* 留声机波纹效果 */
        .eden-mode .bg-surface, .eden-mode .bg-surface/50 {
          background: rgba(15, 15, 15, 0.9) !important;
          border: 1px solid rgba(212, 175, 55, 0.2) !important;
          position: relative;
        }

        .eden-mode .bg-surface::after {
          content: "";
          position: absolute;
          inset: 0;
          background: repeating-radial-gradient(circle at center, transparent 0, transparent 40px, rgba(212, 175, 55, 0.03) 41px, rgba(212, 175, 55, 0.03) 42px);
          pointer-events: none;
        }

        .eden-glow-orb {
          position: fixed;
          width: 50vw;
          height: 50vw;
          border-radius: 50%;
          filter: blur(120px);
          opacity: 0.15;
          z-index: -1;
          pointer-events: none;
          animation: eden-float-glow 15s ease-in-out infinite alternate;
        }
        .eden-glow-1 { background: var(--eden-gold); left: -10%; top: -10%; }
        .eden-glow-2 { background: var(--eden-accent); right: -10%; bottom: -10%; animation-delay: -5s; }

        @keyframes eden-float-glow {
          from { transform: translate(0, 0) scale(1); }
          to { transform: translate(10%, 5%) scale(1.2); }
        }

        .eden-mode input, .eden-mode select, .eden-mode textarea {
          background-color: #050505 !important;
          border: 1px solid var(--eden-gold) !important;
          color: var(--eden-gold) !important;
        }
      `})]})};export{l as EdenTheme};
