import React from 'react';

export const MangaPageStrip: React.FC<React.PropsWithChildren<{ className?: string }>> = ({ className = '', children }) => {
  return <div className={className}>{children}</div>;
};
