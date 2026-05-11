import React, { useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Grid3X3, ImageOff, Loader2 } from 'lucide-react';

import { useI18n } from '../../contexts/I18nContext';
import { MangaScenePageSummary } from '../../types/manga';
import { translateMangaEnum } from './shared';

export interface MangaPageStripProps {
  pages: MangaScenePageSummary[];
  selectedPageId: string;
  selectedPageIds: string[];
  currentPageId: string;
  loadingPageId?: string;
  onSelectPage: (pageId: string) => void;
  onTogglePageSelection: (pageId: string) => void;
}

const PAGE_CARD_HEIGHT = 266;
const PAGE_GAP = 12;
const PAGE_ROW_SIZE = PAGE_CARD_HEIGHT + PAGE_GAP;
const OVERSCAN_ROWS = 16;
const THUMBNAIL_SPINNER_TIMEOUT_MS = 8000;
const THUMBNAIL_NEIGHBOR_PRELOAD_RADIUS = 2;
const THUMBNAIL_BACKGROUND_PRELOAD_DELAY_MS = 850;
const USER_SCROLL_AUTO_FOCUS_SUPPRESS_MS = 650;

interface LazyThumbnailProps {
  src: string;
  alt: string;
  eager: boolean;
}

const LazyThumbnail: React.FC<LazyThumbnailProps> = ({ src, alt, eager }) => {
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [showSpinner, setShowSpinner] = useState(true);

  useEffect(() => {
    setLoaded(false);
    setFailed(false);
    setShowSpinner(true);
  }, [src]);

  useEffect(() => {
    if (loaded || failed) {
      setShowSpinner(false);
      return;
    }
    setShowSpinner(true);
    const timeout = window.setTimeout(() => setShowSpinner(false), THUMBNAIL_SPINNER_TIMEOUT_MS);
    return () => window.clearTimeout(timeout);
  }, [failed, loaded, src]);

  return (
    <div className="relative flex h-full w-full items-center justify-center bg-slate-950">
      {showSpinner && !loaded && !failed && (
        <div className="absolute inset-0 flex items-center justify-center text-slate-600">
          <Loader2 size={20} className="animate-spin" />
        </div>
      )}
      {failed && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-950 text-slate-700">
          <ImageOff size={20} />
        </div>
      )}
      <img
        src={src}
        alt={alt}
        loading={eager ? 'eager' : 'lazy'}
        decoding={eager ? 'sync' : 'async'}
        onLoad={() => {
          setLoaded(true);
          setFailed(false);
          setShowSpinner(false);
        }}
        onError={() => {
          setLoaded(false);
          setFailed(true);
          setShowSpinner(false);
        }}
        className={`h-full w-full object-cover transition-opacity duration-150 ${failed ? 'opacity-0' : 'opacity-100'}`}
      />
    </div>
  );
};

export const MangaPageStrip: React.FC<MangaPageStripProps> = ({
  pages,
  selectedPageId,
  selectedPageIds,
  currentPageId,
  loadingPageId = '',
  onSelectPage,
  onTogglePageSelection,
}) => {
  const { t } = useI18n();
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const scrollFrameRef = useRef<number | null>(null);
  const lastScrollTopRef = useRef(0);
  const lastViewportHeightRef = useRef(0);
  const userScrollingUntilRef = useRef(0);
  const lastAutoScrollPageIdRef = useRef('');
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node) return;

    const update = () => {
      const nextScrollTop = node.scrollTop;
      const nextViewportHeight = node.clientHeight;
      if (
        Math.abs(lastScrollTopRef.current - nextScrollTop) >= 1
        || lastViewportHeightRef.current !== nextViewportHeight
      ) {
        lastScrollTopRef.current = nextScrollTop;
        lastViewportHeightRef.current = nextViewportHeight;
        setScrollTop(nextScrollTop);
        setViewportHeight(nextViewportHeight);
      }
    };
    const scheduleUpdate = () => {
      if (scrollFrameRef.current !== null) return;
      scrollFrameRef.current = window.requestAnimationFrame(() => {
        scrollFrameRef.current = null;
        update();
      });
    };
    update();

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(scheduleUpdate);
      resizeObserver.observe(node);
    }
    const handleScroll = () => {
      userScrollingUntilRef.current = performance.now() + USER_SCROLL_AUTO_FOCUS_SUPPRESS_MS;
      scheduleUpdate();
    };
    node.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      node.removeEventListener('scroll', handleScroll);
      resizeObserver?.disconnect();
      if (scrollFrameRef.current !== null) {
        window.cancelAnimationFrame(scrollFrameRef.current);
        scrollFrameRef.current = null;
      }
    };
  }, []);

  const selectedIndex = useMemo(() => (
    pages.findIndex((page) => page.page_id === selectedPageId)
  ), [pages, selectedPageId]);

  const preloadedThumbnailsRef = useRef<Set<string>>(new Set());
  const thumbnailPreloadSeqRef = useRef(0);

  useEffect(() => {
    const preloadImage = (url: string) => {
      if (!url || preloadedThumbnailsRef.current.has(url)) return;
      preloadedThumbnailsRef.current.add(url);
      const image = new Image();
      image.decoding = 'async';
      image.src = url;
    };

    const runPreload = async (seq: number) => {
      if (selectedIndex < 0) return;
      const visited = new Set<number>([selectedIndex]);

      preloadImage(pages[selectedIndex]?.thumbnail_url || '');
      for (let distance = 1; distance <= THUMBNAIL_NEIGHBOR_PRELOAD_RADIUS; distance += 1) {
        for (const index of [selectedIndex + distance, selectedIndex - distance]) {
          if (thumbnailPreloadSeqRef.current !== seq) return;
          if (index < 0 || index >= pages.length || visited.has(index)) continue;
          visited.add(index);
          preloadImage(pages[index].thumbnail_url);
        }
      }

      for (let distance = THUMBNAIL_NEIGHBOR_PRELOAD_RADIUS + 1; distance < pages.length; distance += 1) {
        for (const index of [selectedIndex + distance, selectedIndex - distance]) {
          if (thumbnailPreloadSeqRef.current !== seq) return;
          if (index < 0 || index >= pages.length || visited.has(index)) continue;
          visited.add(index);
          preloadImage(pages[index].thumbnail_url);
          await new Promise((resolve) => window.setTimeout(resolve, THUMBNAIL_BACKGROUND_PRELOAD_DELAY_MS));
        }
      }
    };

    thumbnailPreloadSeqRef.current += 1;
    const seq = thumbnailPreloadSeqRef.current;
    void runPreload(seq);
    return () => {
      thumbnailPreloadSeqRef.current += 1;
    };
  }, [pages, selectedIndex]);

  useEffect(() => {
    const node = scrollerRef.current;
    if (!node || selectedIndex < 0) return;
    if (performance.now() < userScrollingUntilRef.current) return;
    if (lastAutoScrollPageIdRef.current === selectedPageId) return;
    lastAutoScrollPageIdRef.current = selectedPageId;
    const itemTop = selectedIndex * PAGE_ROW_SIZE;
    const itemBottom = itemTop + PAGE_CARD_HEIGHT;
    if (itemTop < node.scrollTop) {
      node.scrollTop = itemTop;
    } else if (itemBottom > node.scrollTop + node.clientHeight) {
      node.scrollTop = Math.max(0, itemBottom - node.clientHeight);
    }
  }, [selectedIndex, selectedPageId]);

  const visibleRange = useMemo(() => {
    if (!pages.length) return { start: 0, end: 0 };
    const start = Math.max(0, Math.floor(scrollTop / PAGE_ROW_SIZE) - OVERSCAN_ROWS);
    const visibleRows = Math.ceil(Math.max(1, viewportHeight) / PAGE_ROW_SIZE);
    const end = Math.min(pages.length, start + visibleRows + OVERSCAN_ROWS * 2 + 1);
    return { start, end };
  }, [pages.length, scrollTop, viewportHeight]);

  const visiblePages = pages.slice(visibleRange.start, visibleRange.end);

  return (
    <aside className="flex w-[220px] shrink-0 flex-col border-r border-slate-900 bg-slate-950/88">
      <div className="sticky top-0 z-10 border-b border-slate-900 bg-slate-950/95 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-xs uppercase tracking-[0.24em] text-slate-500">{t('manga_nav_title')}</div>
            <div className="mt-1 text-base font-semibold text-slate-100">{t('manga_nav_page_count', pages.length)}</div>
          </div>
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-800 bg-slate-900/70 text-slate-400">
            <Grid3X3 size={17} />
          </div>
        </div>
      </div>
      <div ref={scrollerRef} data-manga-page-strip-scroller className="min-h-0 flex-1 overflow-y-auto p-3">
        <div className="relative" style={{ height: Math.max(0, pages.length * PAGE_ROW_SIZE - PAGE_GAP) }}>
          <div
            className="absolute left-0 right-0"
            style={{ transform: `translateY(${visibleRange.start * PAGE_ROW_SIZE}px)` }}
          >
        {visiblePages.map((scenePage) => {
          const isFinalBlocked = Boolean(scenePage.quality_gate?.blocked_from_final);
          const isPageLoading = loadingPageId === scenePage.page_id && selectedPageId !== scenePage.page_id;
          return (
          <button
            key={scenePage.page_id}
            onClick={() => onSelectPage(scenePage.page_id)}
            className={`mb-3 w-full overflow-hidden rounded-lg border text-left transition-colors ${
              selectedPageId === scenePage.page_id
                ? 'border-primary bg-primary/10 shadow-[0_0_0_1px_rgba(34,211,238,0.18)]'
                : 'border-slate-800 bg-slate-900/55 hover:border-slate-700'
            }`}
            style={{ height: PAGE_CARD_HEIGHT }}
          >
            <div className="px-3 py-2 border-b border-slate-800/80 flex items-center justify-between">
              <label
                className="flex items-center gap-2 text-[11px] uppercase tracking-[0.18em] text-slate-500"
                onClick={(event) => event.stopPropagation()}
              >
                <input
                  type="checkbox"
                  checked={selectedPageIds.includes(scenePage.page_id)}
                  onChange={() => onTogglePageSelection(scenePage.page_id)}
                  className="w-4 h-4 rounded border-slate-700 text-primary bg-slate-950"
                />
                {t('manga_select')}
              </label>
              <span className="text-[10px] uppercase tracking-[0.18em] text-slate-500">{translateMangaEnum('manga_state', scenePage.status, t)}</span>
            </div>
            <div className="flex h-[180px] items-center justify-center overflow-hidden bg-slate-950">
              {isPageLoading ? (
                <Loader2 size={20} className="animate-spin text-slate-600" />
              ) : (
                <LazyThumbnail
                  src={scenePage.thumbnail_url}
                  alt={scenePage.page_id}
                  eager={selectedPageId === scenePage.page_id || currentPageId === scenePage.page_id}
                />
              )}
            </div>
            <div className="px-3 py-2 flex items-center justify-between gap-3">
              <span className="text-sm font-semibold text-slate-100">#{scenePage.index}</span>
              <span className="flex min-w-0 items-center gap-1.5">
                {isFinalBlocked && (
                  <span
                    className="inline-flex items-center gap-1 rounded-full border border-amber-300/25 bg-amber-300/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-amber-100"
                    title={t('manga_quality_gate_issue_count', scenePage.quality_gate?.issue_count || 0)}
                  >
                    <AlertTriangle size={11} />
                    {t('manga_page_badge_final_blocked')}
                  </span>
                )}
                {currentPageId === scenePage.page_id && (
                  <span className="text-[10px] uppercase tracking-[0.18em] text-primary">{t('manga_current')}</span>
                )}
              </span>
            </div>
          </button>
          );
        })}
          </div>
        </div>
      </div>
    </aside>
  );
};
