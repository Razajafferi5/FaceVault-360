import React, { useState, useRef } from 'react';
import { Camera, CheckCircle2, AlertTriangle, Play, RefreshCw, UploadCloud, UserCheck } from 'lucide-react';
import { api } from '../services/api';

export const Testing: React.FC = () => {
  const [testImage, setTestImage] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      setTestImage(reader.result as string);
      setResult(null);
    };
    reader.readAsDataURL(file);
  };

  const runRecognitionTest = async () => {
    if (!testImage) return;
    setIsProcessing(true);
    try {
      const res = await fetch('/api/recognition', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ frame: testImage })
      });
      const data = await res.json();
      setResult(data);
    } catch (err: any) {
      alert(`Test failed: ${err.message || err}`);
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Facial Recognition Diagnostic Sandbox</h1>
        <p className="text-slate-400 text-sm">Upload or capture an arbitrary portrait to evaluate vector similarity, pose, and fail-closed gate metrics</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Input Panel */}
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 space-y-4 shadow-lg">
          <h2 className="text-lg font-semibold text-white">Test Image Input</h2>
          
          <div 
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-[#334155] hover:border-blue-500 rounded-xl aspect-video flex flex-col items-center justify-center cursor-pointer bg-[#0f172a] overflow-hidden relative transition-colors"
          >
            {testImage ? (
              <img src={testImage} alt="Test Subject" className="w-full h-full object-contain" />
            ) : (
              <div className="text-center p-6 space-y-2">
                <UploadCloud className="w-10 h-10 text-blue-400 mx-auto" />
                <p className="text-sm font-medium text-slate-300">Click to upload face photo (JPEG / PNG)</p>
                <p className="text-xs text-slate-500">Supports frontal or angled facial portraits</p>
              </div>
            )}
            <input 
              ref={fileInputRef} 
              type="file" 
              accept="image/*" 
              className="hidden" 
              onChange={handleFileUpload} 
            />
          </div>

          <div className="flex justify-between items-center pt-2">
            <button
              onClick={() => { setTestImage(null); setResult(null); }}
              className="text-xs text-slate-400 hover:text-white"
            >
              Clear Image
            </button>
            <button
              onClick={runRecognitionTest}
              disabled={!testImage || isProcessing}
              className="bg-blue-600 hover:bg-blue-500 text-white px-5 py-2 rounded-lg font-semibold flex items-center gap-2 shadow-lg shadow-blue-500/20 disabled:opacity-50 text-sm transition-all"
            >
              {isProcessing ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Run Recognition Engine
            </button>
          </div>
        </div>

        {/* Results Panel */}
        <div className="bg-[#1e293b] border border-[#334155] rounded-xl p-6 space-y-4 shadow-lg">
          <h2 className="text-lg font-semibold text-white">Pipeline Inference Result</h2>
          
          {!result ? (
            <div className="border border-[#334155] rounded-xl aspect-video flex items-center justify-center text-slate-500 bg-[#0f172a] text-sm text-center p-6">
              Awaiting image execution. Results and biometric vector comparison metrics will appear here.
            </div>
          ) : (
            <div className="space-y-4 animate-slide-in">
              <div className={`p-4 rounded-xl border flex items-center justify-between ${
                result.faces?.[0]?.authorized 
                  ? 'bg-green-500/10 border-green-500/40 text-green-400' 
                  : 'bg-red-500/10 border-red-500/40 text-red-400'
              }`}>
                <div>
                  <div className="text-xs uppercase font-bold tracking-wider">Access Authorization Decision</div>
                  <div className="text-xl font-bold text-white mt-0.5">
                    {result.faces?.[0]?.authorized ? 'ACCESS GRANTED' : 'ACCESS DENIED'}
                  </div>
                </div>
                {result.faces?.[0]?.authorized ? (
                  <CheckCircle2 className="w-8 h-8 text-green-400" />
                ) : (
                  <AlertTriangle className="w-8 h-8 text-red-400" />
                )}
              </div>

              {/* Metric Breakdown */}
              <div className="bg-[#0f172a] rounded-xl p-4 border border-[#334155] space-y-2.5 text-sm">
                <div className="flex justify-between pb-1.5 border-b border-slate-800">
                  <span className="text-slate-400">Identified Identity</span>
                  <span className="text-white font-semibold">{result.faces?.[0]?.name || 'Unknown / Unenrolled'}</span>
                </div>
                <div className="flex justify-between pb-1.5 border-b border-slate-800">
                  <span className="text-slate-400">Cosine Similarity</span>
                  <span className="text-white font-mono">{Math.round((result.faces?.[0]?.similarity || 0) * 100)}%</span>
                </div>
                <div className="flex justify-between pb-1.5 border-b border-slate-800">
                  <span className="text-slate-400">Head Pose Orientation</span>
                  <span className="text-white font-mono">{result.faces?.[0]?.pose_label || 'Frontal'} (Yaw: {Math.round(result.faces?.[0]?.pose_yaw || 0)}°)</span>
                </div>
                <div className="flex justify-between pb-1.5 border-b border-slate-800">
                  <span className="text-slate-400">Face Quality Metric</span>
                  <span className="text-white font-mono">{Math.round((result.faces?.[0]?.quality_score || 0) * 100)} / 100</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Verification Gate Reason</span>
                  <span className="text-white font-mono uppercase text-xs px-2 py-0.5 bg-slate-800 rounded">
                    {result.faces?.[0]?.status || 'no_face_detected'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
