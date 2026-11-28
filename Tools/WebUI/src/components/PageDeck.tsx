import { type CSSProperties, type ReactNode } from 'react';
import { PAGE_ORDER, type Page } from '../appearance/navigation';
import type { PageMotion } from '../appearance/usePageMotion';

export function PageDeck({ page, motion, children }: { page: Page; motion: PageMotion; children: Record<Page, ReactNode> }) {
  const style = { transform: `translate3d(0, ${-motion.position * 100}%, 0)` };
  return <div className={`page-viewport ${motion.moving ? 'is-moving' : ''}`}>
    <div className="page-track" style={style}>
      {PAGE_ORDER.map((id, index) => {
        const distance = Math.min(1, Math.abs(index - motion.position));
        const blur = motion.moving ? (id === page ? distance * 6 : 7) : 0;
        const opacity = motion.moving ? (id === page ? 1 - distance * .3 : .68) : 1;
        const pageStyle: CSSProperties = { filter: `blur(${blur}px)`, opacity };
        return <div key={id} className={`page-slot ${id === page ? 'is-current' : ''}`} style={pageStyle}
          data-page={id} inert={id !== page} aria-hidden={id !== page}>
          {children[id]}
        </div>;
      })}
    </div>
  </div>;
}
