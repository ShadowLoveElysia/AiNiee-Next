import { useLayoutEffect, useRef, useState } from 'react';
import { PAGE_ORDER, type Page } from './navigation';

export interface PageMotion { position: number; moving: boolean; target: number }

export function usePageMotion(page: Page, enabled = true): PageMotion {
  const initial = PAGE_ORDER.indexOf(page);
  const current = useRef(initial);
  const [motion, setMotion] = useState<PageMotion>({ position: initial, moving: false, target: initial });
  useLayoutEffect(() => {
    const target = PAGE_ORDER.indexOf(page);
    const start = current.current;
    const media = matchMedia('(prefers-reduced-motion: reduce)');
    let frame = 0;
    const finish = () => {
      cancelAnimationFrame(frame);
      current.current = target;
      setMotion({ position: target, moving: false, target });
    };
    if (!enabled || media.matches || Math.abs(target - start) < .001) { finish(); return; }
    const duration = Math.max(220, Math.abs(target - start) * 280);
    const started = performance.now();
    const animate = (now: number) => {
      const progress = Math.min(1, (now - started) / duration);
      // One normalized position drives the nav marker and page track together.
      const eased = 1 - (1 - progress) ** 3;
      current.current = start + (target - start) * eased;
      setMotion({ position: current.current, moving: progress < 1, target });
      if (progress < 1) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    const reduce = () => { if (media.matches) finish(); };
    media.addEventListener('change', reduce);
    return () => { cancelAnimationFrame(frame); media.removeEventListener('change', reduce); };
  }, [page, enabled]);
  return motion;
}
