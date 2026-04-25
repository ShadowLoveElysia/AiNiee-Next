import React from 'react';

export interface MangaStatusBarProps {
  leftText: string;
  centerText?: string;
  rightText: string;
}

export const MangaStatusBar: React.FC<MangaStatusBarProps> = ({ leftText, centerText, rightText }) => {
  return (
    <div className="h-8 border-t border-slate-900 bg-slate-950/90 px-4 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-4 text-[11px] uppercase tracking-[0.18em] text-slate-500">
      <div className="truncate">{leftText}</div>
      <div className="truncate text-center">{centerText || ''}</div>
      <div className="truncate text-right">{rightText}</div>
    </div>
  );
};
