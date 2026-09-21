import React from 'react';
import { EntryChart } from '../components/charts/EntryChart';

export const Analytics: React.FC = () => {
  const chartData = Array.from({ length: 30 }).map((_, i) => {
    const d = new Date();
    d.setDate(d.getDate() - (29 - i));
    return {
      date: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      total: Math.floor(100 + Math.random() * 100),
      authorized: Math.floor(80 + Math.random() * 80),
      denied: Math.floor(10 + Math.random() * 30)
    };
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Analytics</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Metric cards */}
        {['Total Entries (30d)', 'Success Rate', 'Avg Quality Score', 'Unknown Alerts'].map((title, i) => (
          <div key={i} className="bg-[#1e293b] border border-[#334155] rounded-xl p-6">
            <h3 className="text-sm text-slate-400 mb-2">{title}</h3>
            <p className="text-2xl font-bold text-white">
              {i === 1 ? '85%' : i === 2 ? '0.92' : Math.floor(Math.random() * 5000)}
            </p>
          </div>
        ))}
      </div>

      <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6">
        <h3 className="text-lg font-semibold text-white mb-6">30-Day Entry Trend</h3>
        <EntryChart data={chartData} />
      </div>
    </div>
  );
};
