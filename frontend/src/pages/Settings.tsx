import React from 'react';

export const Settings: React.FC = () => {
  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-2xl font-bold text-white">System Settings</h1>
      
      <div className="bg-[#1e293b] border border-[#334155] rounded-xl overflow-hidden">
        <div className="p-6 border-b border-[#334155]">
          <h2 className="text-lg font-semibold text-white">Recognition Parameters</h2>
          <p className="text-sm text-slate-400">Adjust thresholds and confidence requirements</p>
        </div>
        <div className="p-6 space-y-6">
          <div>
            <label className="flex justify-between text-sm font-medium text-slate-300 mb-2">
              <span>Similarity Threshold</span>
              <span>0.65</span>
            </label>
            <input type="range" min="0" max="100" defaultValue="65" className="w-full accent-blue-500" />
            <p className="text-xs text-slate-500 mt-1">Minimum cosine similarity required for a match</p>
          </div>
          <div>
            <label className="flex justify-between text-sm font-medium text-slate-300 mb-2">
              <span>Liveness Threshold</span>
              <span>0.80</span>
            </label>
            <input type="range" min="0" max="100" defaultValue="80" className="w-full accent-blue-500" />
          </div>
        </div>
      </div>

      <div className="bg-[#1e293b] border border-[#334155] rounded-xl overflow-hidden">
        <div className="p-6 border-b border-[#334155]">
          <h2 className="text-lg font-semibold text-white">System Information</h2>
        </div>
        <div className="p-6 grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-slate-500 block mb-1">Database Provider</span>
            <span className="text-white font-medium">SQLite</span>
          </div>
          <div>
            <span className="text-slate-500 block mb-1">FAISS Index Type</span>
            <span className="text-white font-medium">IndexFlatIP</span>
          </div>
          <div>
            <span className="text-slate-500 block mb-1">Backend Version</span>
            <span className="text-white font-medium">v1.0.0</span>
          </div>
        </div>
      </div>
      
      <div className="flex justify-end">
        <button className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg font-medium transition-colors">
          Save Changes
        </button>
      </div>
    </div>
  );
};
