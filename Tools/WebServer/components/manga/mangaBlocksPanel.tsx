import React from 'react';

export const MangaBlocksPanel: React.FC<React.PropsWithChildren<{ className?: string }>> = ({ className = '', children }) => {
  return <div className={className}>{children}</div>;
};
