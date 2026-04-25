import React from 'react';

export const MangaStatusBar: React.FC<React.PropsWithChildren<{ className?: string }>> = ({ className = '', children }) => {
  return <div className={className}>{children}</div>;
};
