import React from 'react';

interface ConfidenceMeterProps {
  value: number; // 0 to 1
  label?: string;
}

export const ConfidenceMeter: React.FC<ConfidenceMeterProps> = ({ value, label }) => {
  const percent = Math.round(value * 100);
  
  let colorClass = 'bg-red-500';
  if (percent >= 80) colorClass = 'bg-green-500';
  else if (percent >= 50) colorClass = 'bg-amber-500';

  return (
    <div className="w-full">
      {label && (
        <div className="flex justify-between text-xs mb-1">
          <span className="text-slate-400">{label}</span>
          <span className="text-white font-medium">{percent}%</span>
        </div>
      )}
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div 
          className={`h-full ${colorClass} transition-all duration-300 ease-out`}
          style={{ width: `${percent}%` }}
        />
      </div>
      {!label && (
        <div className="text-right text-xs mt-1 text-slate-400">{percent}%</div>
      )}
    </div>
  );
};
