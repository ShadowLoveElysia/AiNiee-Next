import React from 'react';

export const MangaTopBar: React.FC<React.PropsWithChildren<{ className?: string }>> = ({ className = '', children }) => {
  return <div className={className}>{children}</div>;
};
