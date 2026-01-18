import{r as o,j as e}from"./index-_VzYsfab.js";const u=({active:s})=>{const[f,p]=o.useState([]),[y,m]=o.useState([]),[l,d]=o.useState([]);return o.useRef([]),o.useEffect(()=>{if(s){document.documentElement.classList.add("elysia-mode"),document.body.classList.add("elysia-transforming"),setTimeout(()=>document.body.classList.remove("elysia-transforming"),1e3),console.log("%c嗨~ 发现我了？这是我们的小秘密哦~ ✨","color: #ff6699; font-size: 20px; font-weight: bold; text-shadow: 2px 2px 4px rgba(255,102,153,0.3);"),console.log("%c让我们一起把这些文字，变成像水晶一样闪耀的东西吧~","color: #d4a5ff; font-size: 14px;");const a=Array.from({length:20}).map((i,t)=>({id:t,x:Math.random()*100,y:Math.random()*100,size:Math.random()*18+6,duration:Math.random()*20+20,delay:Math.random()*-30,rotate:Math.random()*360,shape:Math.random()>.5?"polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)":"polygon(25% 0%, 100% 0%, 75% 100%, 0% 100%)"}));m(a);const r=i=>{const t=Date.now();p(n=>[...n,{id:t,x:i.clientX,y:i.clientY}]),setTimeout(()=>{p(n=>n.filter(b=>b.id!==t))},800)},c=i=>{const t=Date.now();d(n=>[{id:t,x:i.clientX,y:i.clientY},...n.slice(0,24)])};return window.addEventListener("click",r),window.addEventListener("mousemove",c),()=>{window.removeEventListener("click",r),window.removeEventListener("mousemove",c),document.body.classList.remove("elysia-transforming")}}else document.documentElement.classList.remove("elysia-mode"),document.body.classList.remove("elysia-transforming"),m([]),d([])},[s]),o.useEffect(()=>{if(s&&l.length>0){const a=setTimeout(()=>{d(r=>r.slice(0,-1))},60);return()=>clearTimeout(a)}},[s,l]),e.jsxs(e.Fragment,{children:[s&&e.jsxs("div",{className:"elysia-overlay-container",children:[e.jsx("div",{className:"elysia-glow-orb elysia-glow-1"}),e.jsx("div",{className:"elysia-glow-orb elysia-glow-2"}),y.map(a=>e.jsx("div",{className:"elysia-bg-shard",style:{left:`${a.x}%`,top:`${a.y}%`,width:`${a.size}px`,height:`${a.size}px`,clipPath:a.shape,transform:`rotate(${a.rotate}deg)`,animationDuration:`${a.duration}s`,animationDelay:`${a.delay}s`}},a.id)),l.map((a,r)=>e.jsx("div",{className:"elysia-mouse-trail",style:{left:a.x,top:a.y,opacity:(24-r)/60,transform:`translate(-50%, -50%) scale(${(24-r)/24})`}},a.id)),f.map(a=>e.jsx("div",{className:"elysia-click-sparkle",style:{left:a.x,top:a.y}},a.id))]}),e.jsx("style",{children:`
        :root {
          /* 全局基础弹性曲线，确保非爱莉模式下点击也有反馈 */
          --elysia-spring-standard: cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }

        /* 全局丝滑过渡：消除切换时的突兀感 */
        body, aside, main, section, div, button, h1, span, input, select, .bg-surface, .bg-slate-900 {
          transition: background-color 1.5s cubic-bezier(0.4, 0, 0.2, 1), 
                      color 1.2s ease, 
                      border-color 1.2s ease, 
                      box-shadow 1.2s ease,
                      transform 0.8s var(--elysia-spring-standard);
        }

        /* 状态点特化过渡：确保颜色切换更同步 */
        .rounded-full[class*="bg-"] {
          transition: background-color 0.8s ease-out, box-shadow 0.8s ease-out !important;
        }

        /* 效果层容器 */
        .elysia-overlay-container {
          position: fixed;
          inset: 0;
          pointer-events: none;
          z-index: 9998;
          overflow: hidden;
        }

        /* 核心动效：Logo 抖动 (全局可用) */
        @keyframes logo-shake {
          0% { transform: scale(1); }
          30% { transform: scale(1.3) rotate(10deg); }
          50% { transform: scale(0.8) rotate(-10deg); }
          70% { transform: scale(1.1) rotate(5deg); }
          100% { transform: scale(1) rotate(0); }
        }
        .logo-shake {
          animation: logo-shake 0.6s var(--elysia-spring-standard) both !important;
        }

        /* 暗示性微抖动 */
        @keyframes hint-shake {
          0%, 100% { transform: translate(0, 0); }
          25% { transform: translate(1.5px, 0.5px); }
          50% { transform: translate(-1px, 1.5px); }
          75% { transform: translate(0.5px, -1px); }
        }
        .hint-shake {
          animation: hint-shake 4s ease-in-out infinite;
        }

        /* 水滴涟漪扩散 (开启) - 带有能量爆发感 */
        @keyframes elysia-ripple-out {
          0% { clip-path: circle(0% at var(--ripple-x) var(--ripple-y)); opacity: 1; filter: brightness(1.5); }
          50% { clip-path: circle(120% at var(--ripple-x) var(--ripple-y)); opacity: 1; filter: brightness(1); }
          100% { clip-path: circle(180% at var(--ripple-x) var(--ripple-y)); opacity: 0; filter: blur(30px); }
        }
        .elysia-ripple-out {
          animation: elysia-ripple-out 2.5s cubic-bezier(0.4, 0, 0.2, 1) forwards;
          background: radial-gradient(circle at var(--ripple-x) var(--ripple-y), #ffb7c5, #d4a5ff, #81d4fa) !important;
        }

        /* 涟漪收束 (关闭) - 从全屏收束回按钮 */
        @keyframes elysia-ripple-in {
          0% { clip-path: circle(180% at var(--ripple-x) var(--ripple-y)); opacity: 1; filter: brightness(1); }
          50% { clip-path: circle(120% at var(--ripple-x) var(--ripple-y)); opacity: 1; }
          100% { clip-path: circle(0% at var(--ripple-x) var(--ripple-y)); opacity: 1; filter: brightness(0.8); }
        }
        .elysia-ripple-in {
          animation: elysia-ripple-in 2.5s cubic-bezier(0.6, 0, 0.4, 1) forwards;
          background: radial-gradient(circle at var(--ripple-x) var(--ripple-y), #ffb7c5, #d4a5ff, #81d4fa) !important;
          z-index: 10001 !important;
        }

        :root.elysia-mode {
          --elysia-pink: #ff6699;
          --elysia-pink-bright: #ff4d88;
          --elysia-pink-light: #ffb7c5;
          --elysia-purple: #d4a5ff;
          --elysia-blue: #81d4fa;
          /* 极致 Q 弹曲线：带超调的弹簧感 */
          --elysia-spring: cubic-bezier(0.6, -0.28, 0.735, 1.45);
        }
        
              /* 18. 极致加强：挤压与伸展动画 (Jelly Physics) */
              @keyframes elysia-squish {
                0% { transform: scale(1, 1); }
                30% { transform: scale(1.15, 0.85); }
                50% { transform: scale(0.9, 1.1); }
                100% { transform: scale(1, 1); }
              }
              .elysia-mode .cursor-pointer:active, .elysia-mode button:active {
                animation: elysia-squish 0.4s var(--elysia-spring) !important;
              }
                /* 1. 全量颜色覆盖 - 强制替换 Tailwind 的 primary 类 */
        .elysia-mode .text-primary { color: var(--elysia-pink) !important; }
        .elysia-mode .bg-primary { background-color: var(--elysia-pink) !important; color: white !important; }
        .elysia-mode .bg-primary/10 { background-color: rgba(255, 102, 153, 0.15) !important; }
        .elysia-mode .bg-primary/20 { background-color: rgba(255, 102, 153, 0.25) !important; }
        
        /* 氛围：轻盈透明感 */
        .elysia-glow-orb {
          position: absolute;
          width: 50vw;
          height: 50vw;
          border-radius: 50%;
          filter: blur(100px);
          opacity: 0.08;
          z-index: -1;
        }
        .elysia-glow-1 { background: var(--elysia-pink); left: -5%; top: -5%; }
        .elysia-glow-2 { background: var(--elysia-purple); right: -5%; bottom: -5%; }

        .elysia-bg-shard {
          position: absolute;
          background: rgba(255, 255, 255, 0.3);
          backdrop-filter: blur(1px);
          border: 1px solid rgba(255, 255, 255, 0.2);
          opacity: 0;
          animation: elysia-shard-float linear infinite;
        }

        @keyframes elysia-shard-float {
          0% { transform: translateY(0) rotate(0deg) scale(0.5); opacity: 0; }
          20% { opacity: 0.3; }
          80% { opacity: 0.3; }
          100% { transform: translateY(-100vh) rotate(720deg) scale(1.2); opacity: 0; }
        }

        .elysia-mouse-trail {
          position: fixed;
          width: 32px;
          height: 32px;
          background: radial-gradient(circle, var(--elysia-pink-light), var(--elysia-purple) 40%, transparent 80%);
          border-radius: 50%;
          pointer-events: none;
          z-index: 9999;
          filter: blur(8px) brightness(1.2);
          mix-blend-mode: screen;
        }

        /* 针对特定颜色的悬浮态覆盖 */
        .elysia-mode .hover:bg-cyan-400:hover, 
        .elysia-mode .hover:bg-primary:hover { 
          background-color: var(--elysia-pink-bright) !important; 
          transform: scale(1.05) translateY(-2px);
        }
        .elysia-mode .hover:text-cyan-300:hover { color: var(--elysia-pink-light) !important; }

        /* 2. 极致果冻按钮样式 */
        .elysia-mode button {
          transition: all 0.4s var(--elysia-spring) !important;
          position: relative;
          overflow: hidden;
        }

        .elysia-mode button:active {
          transform: scale(0.9) !important;
        }

        .elysia-mode button.bg-primary, 
        .elysia-mode .bg-primary {
          background: linear-gradient(45deg, var(--elysia-pink), #ff99bb) !important;
          border: none !important;
          border-radius: 99px !important;
          box-shadow: 0 6px 15px rgba(255, 102, 153, 0.3) !important;
          color: white !important;
        }

        /* 按钮流光横扫 */
        .elysia-mode button::after {
          content: "";
          position: absolute;
          top: -100%; left: -100%; width: 50%; height: 300%;
          background: linear-gradient(to right, transparent, rgba(255,255,255,0.5), transparent);
          transform: rotate(45deg);
          transition: 0.6s;
        }
        .elysia-mode button:hover::after {
          left: 150%;
        }

        /* 点击星星特效 */
        .elysia-click-sparkle {
          position: fixed;
          width: 10px;
          height: 10px;
          background: var(--elysia-pink);
          pointer-events: none;
          z-index: 9999;
          border-radius: 50%;
          transform: translate(-50%, -50%);
          animation: sparkle-burst 0.8s ease-out forwards;
        }

        @keyframes sparkle-burst {
          0% { transform: translate(-50%, -50%) scale(0); opacity: 1; box-shadow: 0 0 0 0px var(--elysia-pink); }
          100% { transform: translate(-50%, -50%) scale(4); opacity: 0; box-shadow: 0 0 20px 10px transparent; }
        }

        /* 水晶卡片 3.0：虹彩边缘 */
        .elysia-mode .bg-surface/50, .elysia-mode .bg-surface {
          background: rgba(255, 255, 255, 0.75) !important;
          backdrop-filter: blur(16px) saturate(200%) !important;
          border: 1px solid rgba(255, 255, 255, 0.5) !important;
          position: relative;
          overflow: hidden;
        }
        .elysia-mode .bg-surface/50::before {
          content: "";
          position: absolute;
          inset: 0;
          padding: 1px;
          border-radius: inherit;
          background: linear-gradient(45deg, transparent 40%, rgba(255, 102, 153, 0.3), transparent 60%);
          background-size: 200% 200%;
          animation: elysia-shimmer 4s linear infinite;
          -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          -webkit-mask-composite: xor;
          mask-composite: exclude;
          pointer-events: none;
        }

        @keyframes elysia-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }

        /* 字体：水晶珠光感 */
        .elysia-mode h1, .elysia-mode .text-2xl, .elysia-mode .text-3xl {
          text-shadow: 
            0 0 10px rgba(255, 102, 153, 0.2),
            0 0 20px rgba(212, 165, 255, 0.1) !important;
          letter-spacing: -0.02em;
        }

        /* 5. 侧边栏与标题 */
        .elysia-mode h1 {
          background: linear-gradient(45deg, #ff6699, #d4a5ff);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          font-weight: 900 !important;
          animation: elysia-float 4s ease-in-out infinite;
        }

        @keyframes elysia-float {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-8px); }
        }

        /* 滚动条 */
        .elysia-mode ::-webkit-scrollbar-thumb {
          background: var(--elysia-pink-light) !important;
          border-radius: 10px;
        }
        /* 6. 进阶加强：标题虹彩流光 */
        .elysia-mode h1 {
          background: linear-gradient(
            to right, 
            #ff6699, #ffb7c5, #d4a5ff, #81d4fa, #ffb7c5, #ff6699
          );
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          animation: elysia-float 4s ease-in-out infinite, iris-text-flow 10s linear infinite !important;
        }

        @keyframes iris-text-flow {
          to { background-position: 200% center; }
        }

        /* 7. 进阶加强：卡片入场动画 (错落感) */
        .elysia-mode .grid > div {
          animation: elysia-entrance 0.8s var(--elysia-spring) both;
        }
        .elysia-mode .grid > div:nth-child(1) { animation-delay: 0.1s; }
        .elysia-mode .grid > div:nth-child(2) { animation-delay: 0.2s; }
        .elysia-mode .grid > div:nth-child(3) { animation-delay: 0.3s; }

        @keyframes elysia-entrance {
          from { opacity: 0; transform: translateY(30px) scale(0.9); filter: blur(10px); }
          to { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
        }

        /* 8. 侧边栏图标魔法旋转 */
        .elysia-mode .cursor-pointer.group:hover svg {
          transform: rotate(15deg) scale(1.2);
          filter: drop-shadow(0 0 5px var(--elysia-pink-light));
          transition: all 0.4s var(--elysia-spring);
        }

        /* 9. 状态点呼吸光晕 */
        .elysia-mode .w-2.h-2.rounded-full {
          box-shadow: 0 0 10px var(--elysia-pink);
          position: relative;
        }
        .elysia-mode .w-2.h-2.rounded-full::after {
          content: "";
          position: absolute;
          inset: -4px;
          border-radius: 50%;
          border: 1px solid var(--elysia-pink);
          animation: elysia-ring 2s ease-out infinite;
        }

        @keyframes elysia-ring {
          0% { transform: scale(1); opacity: 0.8; }
          100% { transform: scale(3); opacity: 0; }
        }
        /* 10. 进阶加强：极致滚动条 */
        .elysia-mode ::-webkit-scrollbar {
          width: 8px;
        }
        .elysia-mode ::-webkit-scrollbar-track {
          background: transparent;
        }
        .elysia-mode ::-webkit-scrollbar-thumb {
          background: linear-gradient(to bottom, #ffb7c5, #d4a5ff, #81d4fa);
          border-radius: 10px;
          border: 2px solid #fff5f7;
          box-shadow: 0 0 10px rgba(255, 183, 197, 0.5);
        }

        /* 11. 容器边缘弥漫光晕 */
        .elysia-mode .bg-surface/50, .elysia-mode .bg-surface {
          box-shadow: 
            0 10px 30px rgba(255, 183, 197, 0.1),
            0 0 15px rgba(212, 165, 255, 0.1) !important;
        }

        /* 12. 魔法残影关键帧 */
        @keyframes sparkle-fade {
          0% { transform: scale(1); opacity: 0.8; }
          100% { transform: scale(0); opacity: 0; }
        }

        /* 13. 保持所有编辑区域深色背景，仅改变边框颜色 */
        .elysia-mode input, 
        .elysia-mode select, 
        .elysia-mode textarea,
        .elysia-mode .bg-slate-900,
        .elysia-mode .bg-slate-950,
        .elysia-mode .bg-slate-800/50,
        .elysia-mode [class*="bg-slate-900"],
        .elysia-mode [class*="bg-slate-950"] {
          background-color: #0f172a !important; /* 强制深色背景 */
          color: #f8fafc !important; /* 强制浅色文字 */
          border-color: rgba(255, 102, 153, 0.4) !important;
        }

        .elysia-mode input:focus, 
        .elysia-mode select:focus, 
        .elysia-mode textarea:focus,
        .elysia-mode .focus:border-primary:focus {
          border-color: var(--elysia-pink) !important;
          box-shadow: 0 0 10px rgba(255, 102, 153, 0.2) !important;
          outline: none !important;
        }
        /* 14. 进阶加强：全局水晶进度条 */
        .elysia-mode .bg-primary.h-full, 
        .elysia-mode .bg-cyan-500,
        .elysia-mode .bg-blue-500 {
          background: linear-gradient(90deg, #ffb7c5, #d4a5ff, #81d4fa) !important;
          background-size: 200% auto !important;
          animation: iris-text-flow 2s linear infinite !important;
          box-shadow: 0 0 10px rgba(212, 165, 255, 0.5) !important;
          border-radius: 99px !important;
        }

        /* 15. 进阶加强：魔法变换闪光 */
        @keyframes magic-transform {
          0% { filter: brightness(1) blur(0px); }
          50% { filter: brightness(1.5) blur(4px); }
          100% { filter: brightness(1) blur(0px); }
        }
        .elysia-transforming {
          animation: magic-transform 1s var(--elysia-spring);
        }

        /* 16. 全局文字虹彩闪烁 (针对重要数字) */
        .elysia-mode .text-2xl, .elysia-mode .text-3xl, .elysia-mode .text-4xl {
          background: linear-gradient(45deg, #ff6699, #d4a5ff, #ff6699);
          background-size: 200% auto;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          animation: iris-text-flow 5s linear infinite;
        }

        /* 17. 魔法控制台彩蛋 */
        /* (Logic in useEffect) */
        /* 19. 极致加强：图标跳跃 */
        .elysia-mode .cursor-pointer.group:hover svg {
          animation: elysia-jump 0.6s var(--elysia-spring) both;
          filter: drop-shadow(0 0 8px var(--elysia-pink-light));
        }
        @keyframes elysia-jump {
          0%, 100% { transform: translateY(0) rotate(0); }
          30% { transform: translateY(-8px) rotate(15deg) scale(1.15); }
          60% { transform: translateY(2px) rotate(-5deg); }
        }

        /* 20. 极致加强：卡片 3D 悬浮感 */
        .elysia-mode .bg-surface/50:hover {
          transform: perspective(1000px) rotateX(1deg) rotateY(-1deg) translateY(-8px) scale(1.01) !important;
          box-shadow: 
              -5px 15px 30px rgba(255, 102, 153, 0.1),
              5px 15px 30px rgba(212, 165, 255, 0.1) !important;
        }

        /* 21. Tips 气泡炸裂入场 */
        @keyframes elysia-pop {
          0% { transform: scale(0) translate(50px, 50px); opacity: 0; filter: blur(10px); }
          70% { transform: scale(1.1); opacity: 1; filter: blur(0); }
          100% { transform: scale(1); }
        }
        .elysia-tip {
          animation: elysia-pop 0.6s var(--elysia-spring) both !important;
        }
      `})]})};export{u as ElysiaTheme};
