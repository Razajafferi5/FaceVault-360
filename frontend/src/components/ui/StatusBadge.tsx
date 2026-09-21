import React from 'react';

interface StatusBadgeProps {
  status: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const normalized = status.toLowerCase();
  
  let colors = 'bg-slate-500/10 text-slate-400 border-slate-500/20';
  
  if (['authorized', 'granted', 'success', 'active'].includes(normalized)) {
    colors = 'bg-green-500/10 text-green-500 border-green-500/20';
  } else if (['denied', 'error', 'failed', 'disabled'].includes(normalized)) {
    colors = 'bg-red-500/10 text-red-500 border-red-500/20';
  } else if (['unknown', 'warning', 'pending'].includes(normalized)) {
    colors = 'bg-amber-500/10 text-amber-500 border-amber-500/20';
  }

  return (
    <span className={`px-2.5 py-1 text-xs font-semibold rounded-full border uppercase tracking-wider ${colors}`}>
      {status}
    </span>
  );
};
