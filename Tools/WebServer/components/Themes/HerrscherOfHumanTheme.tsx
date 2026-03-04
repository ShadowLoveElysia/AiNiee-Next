import React, { useEffect, useState, useRef } from 'react';

export const HerrscherOfHumanTheme: React.FC<{ active: boolean }> = ({ active }) => {
  const [petals, setPetals] = useState<{ id: number, x: number, y: number, size: number, rotation: number, speed: number, delay: number, sway: number }[]>([]);
  const [clicks, setClicks] = useState<{ id: number, x: number, y: number }[]>([]);
  const [trail, setTrail] = useState<{ id: number, x: number, y: number }[]>([]);
  const [parallax, setParallax] = useState({ x: 0, y: 0 });
  const clickIdRef = useRef(0);
  const trailIdRef = useRef(0);

  useEffect(() => {
    if (active) {
      document.documentElement.classList.add('herrscher-mode');
      document.body.classList.add('herrscher-transforming');
      setTimeout(() => document.body.classList.remove('herrscher-transforming'), 1000);

      // Reverting to Petal Logic: 80 Particles
      const newPetals = Array.from({ length: 80 }).map((_, i) => ({
        id: i,
        x: Math.random() * 100,
        y: Math.random() * 100,
        size: Math.random() * 15 + 10,
        rotation: Math.random() * 360,
        speed: Math.random() * 10 + 6,
        delay: Math.random() * -20,
        sway: Math.random() * 40 + 40
      }));
      setPetals(newPetals);

      const handleClick = (e: MouseEvent) => {
        clickIdRef.current += 1;
        const id = clickIdRef.current;
        setClicks(prev => [...prev, { id, x: e.clientX, y: e.clientY }]);
        setTimeout(() => setClicks(prev => prev.filter(c => c.id !== id)), 1000);
      };

      const handleMouseMove = (e: MouseEvent) => {
        trailIdRef.current += 1;
        const id = trailIdRef.current;
        setTrail(prev => [{ id, x: e.clientX, y: e.clientY }, ...prev.slice(0, 25)]);
        
        const moveX = (e.clientX / window.innerWidth - 0.5) * 20;
        const moveY = (e.clientY / window.innerHeight - 0.5) * 20;
        setParallax({ x: moveX, y: moveY });
      };

      const clearTrail = () => {
        setTrail([]);
      };

      const handleVisibilityChange = () => {
        if (document.hidden) {
          clearTrail();
        }
      };

      window.addEventListener('click', handleClick);
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('blur', clearTrail);
      window.addEventListener('mouseleave', clearTrail);
      document.addEventListener('visibilitychange', handleVisibilityChange);

      return () => {
        document.documentElement.classList.remove('herrscher-mode');
        document.body.classList.remove('herrscher-transforming');
        window.removeEventListener('click', handleClick);
        window.removeEventListener('mousemove', handleMouseMove);
        window.removeEventListener('blur', clearTrail);
        window.removeEventListener('mouseleave', clearTrail);
        document.removeEventListener('visibilitychange', handleVisibilityChange);
        setTrail([]);
      };
    } else {
      document.documentElement.classList.remove('herrscher-mode');
      document.body.classList.remove('herrscher-transforming');
      setPetals([]);
      setClicks([]);
      setTrail([]);
      setParallax({ x: 0, y: 0 });
    }
  }, [active]);

  useEffect(() => {
    if (active && trail.length > 0) {
      const timer = setTimeout(() => setTrail(prev => prev.slice(0, -1)), 40);
      return () => clearTimeout(timer);
    }
  }, [active, trail]);

  return (
    <>
      {active && (
        <div className="herrscher-overlay-container">
          <div 
            className="herrscher-sea-of-stars" 
            style={{ transform: `translate(${parallax.x * -0.5}px, ${parallax.y * -0.5}px) scale(1.1)` }}
          />
          <div 
            className="herrscher-rainbow-aurora" 
            style={{ transform: `translate(${parallax.x * 0.3}px, ${parallax.y * 0.3}px)` }}
          />
          
          {trail.map((t, i) => (
            <div 
              key={t.id}
              className="herrscher-mouse-trail"
              style={{ 
                left: t.x, 
                top: t.y, 
                opacity: (25 - i) / 50,
                transform: `translate(-50%, -50%) scale(${(25 - i) / 25})`
              }}
            />
          ))}

          {clicks.map(click => (
            <React.Fragment key={click.id}>
                <div className="herrscher-click-ripple" style={{ left: click.x, top: click.y }} />
                <div className="herrscher-click-sparkle" style={{ left: click.x, top: click.y }}>
                    {[...Array(6)].map((_, i) => (
                        <div key={i} className="herrscher-click-shard" style={{ '--i': i } as any} />
                    ))}
                </div>
            </React.Fragment>
          ))}

          {petals.map(p => (
            <div 
              key={p.id}
              className="herrscher-petal"
              style={{
                left: `${p.x}%`,
                top: `-10%`,
                width: `${p.size}px`,
                height: `${p.size}px`,
                transform: `rotate(${p.rotation}deg)`,
                animation: `herrscher-fall ${p.speed}s linear infinite, herrscher-sway ${p.speed/2}s ease-in-out infinite alternate`,
                animationDelay: `${p.delay}s`,
                '--sway-amount': `${p.sway}px`
              } as any}
            />
          ))}
        </div>
      )}
      <style>{`
        :root.herrscher-mode {
          --hoh-pink: #ff8fa3;
          --hoh-pink-bright: #ff4d6d;
          --hoh-pink-light: #ffccd5;
          --hoh-purple: #c8b6ff;
          --hoh-blue: #bde0fe;
          --hoh-gold: #ffea00;
          --hoh-pearl: rgba(255, 245, 247, 0.85);
          --hoh-spring: cubic-bezier(0.6, -0.28, 0.735, 1.45);
        }

        @keyframes herrscher-heartbeat {
          0%, 100% { filter: contrast(1.02) saturate(1.2) brightness(1.02); }
          50% { filter: contrast(1.1) saturate(1.4) brightness(1.08); }
        }
        .herrscher-mode body {
          background: linear-gradient(135deg, #fff5f8 0%, #ffdce5 50%, #ffb7c5 100%) !important;
          animation: herrscher-heartbeat 5s ease-in-out infinite;
          overflow-x: hidden;
        }

        @keyframes herrscher-squish {
          0% { transform: scale(1, 1); }
          30% { transform: scale(1.3, 0.7); }
          50% { transform: scale(0.8, 1.2); }
          100% { transform: scale(1, 1); }
        }
        .herrscher-mode .cursor-pointer:active, 
        .herrscher-mode button:active {
          animation: herrscher-squish 0.4s var(--hoh-spring) !important;
        }

        .herrscher-mode .bg-surface, 
        .herrscher-mode .bg-surface\/50 {
          background: rgba(255, 245, 247, 0.75) !important;
          backdrop-filter: blur(25px) saturate(200%) !important;
          border: 1px solid rgba(255, 255, 255, 0.8) !important;
          box-shadow: 0 15px 40px rgba(255, 143, 163, 0.15), 
                      inset 0 0 25px rgba(255, 255, 255, 0.6) !important;
          border-radius: 28px !important;
          position: relative;
          overflow: hidden;
        }

        .herrscher-mode .bg-surface::after,
        .herrscher-mode .bg-surface\/50::after {
          content: ""; position: absolute; top: -150%; left: -150%; width: 60%; height: 400%;
          background: linear-gradient(to right, transparent 0%, rgba(255, 255, 255, 0.5) 50%, transparent 100%);
          transform: rotate(45deg); animation: herrscher-jewelry-shine 12s infinite; pointer-events: none;
        }
        @keyframes herrscher-jewelry-shine {
          0% { left: -150%; top: -150%; } 15% { left: 150%; top: 150%; } 100% { left: 150%; top: 150%; }
        }

        .herrscher-mode .bg-surface::before {
          content: ""; position: absolute; inset: -2px; border-radius: 30px; padding: 2px;
          background: linear-gradient(45deg, #ff8fa3, #ffccd5, #bde0fe, #c8b6ff, #ffea00, #ff8fa3);
          background-size: 300% 300%; animation: herrscher-rainbow-border 6s linear infinite;
          -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
          -webkit-mask-composite: xor; mask-composite: exclude; pointer-events: none;
        }
        @keyframes herrscher-rainbow-border {
          0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; }
        }

        .herrscher-mode .grid > div {
          animation: herrscher-entrance 0.8s var(--hoh-spring) both;
        }
        .herrscher-mode .grid > div:nth-child(1) { animation-delay: 0.1s; }
        .herrscher-mode .grid > div:nth-child(2) { animation-delay: 0.2s; }
        .herrscher-mode .grid > div:nth-child(3) { animation-delay: 0.3s; }
        @keyframes herrscher-entrance {
          from { opacity: 0; transform: translateY(40px) scale(0.92); filter: blur(15px); }
          to { opacity: 1; transform: translateY(0) scale(1); filter: blur(0); }
        }

        .herrscher-mode .w-2.h-2.rounded-full {
          box-shadow: 0 0 12px var(--hoh-pink); position: relative;
        }
        .herrscher-mode .w-2.h-2.rounded-full::after {
          content: ""; position: absolute; inset: -5px; border-radius: 50%; border: 1.5px solid var(--hoh-pink);
          animation: herrscher-ring 2s ease-out infinite;
        }
        @keyframes herrscher-ring { 0% { transform: scale(1); opacity: 0.8; } 100% { transform: scale(3.5); opacity: 0; } }

        .herrscher-mode ::-webkit-scrollbar { width: 10px; }
        .herrscher-mode ::-webkit-scrollbar-track { background: rgba(255, 143, 163, 0.05); }
        .herrscher-mode ::-webkit-scrollbar-thumb {
          background: linear-gradient(to bottom, #ffccd5, #ff8fa3, #c8b6ff);
          border-radius: 12px; border: 3px solid #fff5f8;
        }

        .herrscher-mode .cursor-pointer.group:hover svg {
          animation: herrscher-jump 0.6s var(--hoh-spring) both;
          filter: drop-shadow(0 0 10px var(--hoh-pink-light));
        }
        @keyframes herrscher-jump {
          0%, 100% { transform: translateY(0) rotate(0); }
          30% { transform: translateY(-10px) rotate(15deg) scale(1.2); }
          60% { transform: translateY(2px) rotate(-5deg); }
        }

        .herrscher-mode input, .herrscher-mode select, .herrscher-mode textarea {
          background: rgba(255, 255, 255, 0.45) !important;
          border: 2px solid rgba(255, 143, 163, 0.25) !important;
          color: var(--hoh-pink-bright) !important;
          backdrop-filter: blur(15px) !important;
          border-radius: 14px !important;
        }
        .herrscher-mode input:focus {
          border-color: var(--hoh-pink) !important;
          box-shadow: 0 0 18px rgba(255, 143, 163, 0.4) !important;
          background: rgba(255, 255, 255, 0.7) !important;
        }

        .herrscher-overlay-container { position: fixed; inset: 0; pointer-events: none; z-index: 9998; overflow: hidden; }
        .herrscher-sea-of-stars {
          position: absolute; inset: -60px;
          background-image: radial-gradient(2px 2px at 20px 30px, #fff, rgba(0,0,0,0)),
                            radial-gradient(2.5px 2.5px at 140px 170px, #fff, rgba(0,0,0,0));
          background-repeat: repeat; background-size: 350px 350px; opacity: 0.55;
        }
        .herrscher-rainbow-aurora {
          position: absolute; inset: -60px;
          background: linear-gradient(45deg, rgba(255,143,163,0.2), rgba(189,224,254,0.15), rgba(200,182,255,0.15), rgba(255,234,0,0.12));
          background-size: 400% 400%; animation: herrscher-aurora 25s ease infinite;
        }

        .herrscher-petal {
          position: absolute; 
          background: linear-gradient(135deg, rgba(255,255,255,0.9), rgba(255, 204, 213, 0.5));
          border: 0.5px solid rgba(255, 255, 255, 0.8);
          /* Original Petal Shape: 100% 0% 100% 0% */
          border-radius: 100% 0% 100% 0% / 100% 0% 100% 0%;
          box-shadow: 0 0 15px rgba(255, 143, 163, 0.3);
          opacity: 0;
        }
        @keyframes herrscher-fall {
          0% { transform: translateY(-10vh) rotate(0deg); opacity: 0; } 15% { opacity: 0.8; }
          90% { opacity: 0.8; } 100% { transform: translateY(115vh) rotate(720deg); opacity: 0; }
        }
        @keyframes herrscher-sway { 0% { margin-left: calc(-1 * var(--sway-amount)); } 100% { margin-left: var(--sway-amount); } }

        .herrscher-click-ripple {
          position: fixed; width: 0; height: 0; border: 3px solid #fff; border-radius: 50%;
          pointer-events: none; z-index: 9999; transform: translate(-50%, -50%);
          animation: herrscher-ripple-expand 1.2s cubic-bezier(0.1, 0.9, 0.2, 1) forwards;
        }
        @keyframes herrscher-ripple-expand {
          0% { width: 0; height: 0; opacity: 1; border-width: 5px; }
          100% { width: 450px; height: 450px; opacity: 0; border-width: 1px; border-color: var(--hoh-purple); }
        }

        .herrscher-mouse-trail {
          position: fixed; width: 12px; height: 12px; background: radial-gradient(circle, #fff, var(--hoh-pink-light));
          border-radius: 50%; pointer-events: none; z-index: 9999; opacity: 0.4;
        }

        .herrscher-mode aside {
          background: rgba(255, 250, 252, 0.92) !important;
          border-right: 4px solid transparent !important;
          border-image: linear-gradient(to bottom, #ff8fa3, #c8b6ff, #bde0fe) 1 !important;
          backdrop-filter: blur(20px) !important;
        }

        /* Sidebar Internal Components Overrides */
        .herrscher-mode aside .bg-slate-900,
        .herrscher-mode aside [class*="bg-slate-"],
        .herrscher-mode aside .bg-black\/20 {
          background-color: rgba(255, 245, 247, 0.5) !important;
          border-color: rgba(255, 143, 163, 0.2) !important;
        }

        .herrscher-mode aside h1,
        .herrscher-mode aside span,
        .herrscher-mode aside .text-slate-400,
        .herrscher-mode aside .text-slate-500,
        .herrscher-mode aside .text-slate-600 {
          color: #ff4d6d !important;
        }

        .herrscher-mode aside .border-t {
          border-top-color: rgba(255, 143, 163, 0.2) !important;
        }

        .herrscher-mode h1 {
          background: linear-gradient(to right, #ff4d6d, #ff8fa3, #c8b6ff, #8093f1, #ff8fa3, #ff4d6d);
          background-size: 200% auto; -webkit-background-clip: text; -webkit-text-fill-color: transparent;
          animation: herrscher-text-flow 3s linear infinite; font-weight: 900 !important;
          text-shadow: 0 0 20px rgba(255, 143, 163, 0.4) !important;
        }

        /* Slogan Gradient Fix */
        .herrscher-mode .max-w-xl {
          background: linear-gradient(to right, #ff4d6d, #ff8fa3, #c8b6ff);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          font-weight: bold !important;
          opacity: 1 !important;
        }

        @keyframes herrscher-text-flow { to { background-position: 200% center; } }

        /* Theme Persistence Overrides */
        .herrscher-mode .text-primary { color: #ff4d6d !important; }
                .herrscher-mode .border-primary,
                .herrscher-mode .border-primary\/30,
                .herrscher-mode .border-primary\/20 {
                  border-color: rgba(255, 143, 163, 0.5) !important;
                }
        
                .herrscher-mode .bg-primary {
                  background: linear-gradient(45deg, #ff4d6d, #ff8fa3, #c8b6ff) !important;
                  background-size: 200% auto !important;
                  animation: herrscher-text-flow 4s linear infinite !important;
                  box-shadow: 0 10px 25px rgba(255, 77, 109, 0.4) !important;
                  border: none !important;
                  border-radius: 99px !important;
                  color: white !important;
                }
        
                /* Settings & Plugins Specific Fixes */
                .herrscher-mode .bg-primary\/20,
                .herrscher-mode .bg-primary\/10 {
                  background-color: rgba(255, 143, 163, 0.25) !important;
                }
        
                .herrscher-mode .absolute.top-0.left-0.w-1\.5.h-full.bg-primary {
                  background: linear-gradient(to bottom, #ff4d6d, #ff8fa3, #c8b6ff) !important;
                  box-shadow: 0 0 15px rgba(255, 143, 163, 0.6) !important;
                }
        
                .herrscher-mode .border-slate-800,
                .herrscher-mode .border-slate-700 {
                  border-color: rgba(255, 143, 163, 0.2) !important;
                }      `}</style>
    </>
  );
};
