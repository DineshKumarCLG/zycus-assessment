"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ProjectWeeklyData, SlideData } from "@/lib/data";
import { GlowHoverCard } from "./smoothui/glow-hover-card";
import { AnimatedTabs } from "./smoothui/animated-tabs";
import { ScrambleHover } from "./smoothui/scramble-hover";
import { SiriOrb } from "./smoothui/siri-orb";

import { I18nextProvider } from 'react-i18next';
import i18n from 'i18next';
import { translationsEn } from 'pptx-react-viewer/i18n';
import { PowerPointViewer } from 'pptx-react-viewer';
import 'pptx-react-viewer/styles.css';

i18n.init({
  resources: { en: { translation: translationsEn } },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false }
});

export default function SmoothDashboard({ 
  projectHistories: initialProjects, 
  deckData: initialDeck 
}: { 
  projectHistories: ProjectWeeklyData[],
  deckData: SlideData[]
}) {
  const [projectHistories, setProjectHistories] = useState<ProjectWeeklyData[]>(initialProjects);
  const [deckData, setDeckData] = useState<SlideData[]>(initialDeck);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [stepLogs, setStepLogs] = useState<Record<number, string[]>>({});
  const [activeStep, setActiveStep] = useState<number>(-1);
  const [isRunning, setIsRunning] = useState(false);
  const [activeSlideIndex, setActiveSlideIndex] = useState(0);
  const [pptxBytes, setPptxBytes] = useState<Uint8Array | null>(null);
  const [downloadVersion, setDownloadVersion] = useState<number>(Date.now());
  const [viewerSlideIndex, setViewerSlideIndex] = useState(0);
  const [viewerSlideCount, setViewerSlideCount] = useState(0);
  const [isDownloading, setIsDownloading] = useState(false);
  const [scheduleType, setScheduleType] = useState<"daemon" | "cron">("daemon");
  const viewerRef = useRef<any>(null);
  const router = useRouter();

  const fetchPptx = async () => {
    try {
      const res = await fetch('/exec_deck.pptx');
      if (res.ok) {
        const buffer = await res.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        setPptxBytes(bytes);
        setDownloadVersion(Date.now()); // Update cache buster timestamp
      }
    } catch (e) {
      console.error("Failed to load pptx", e);
    }
  };

  useEffect(() => {
    fetchPptx();
  }, []);

  useEffect(() => {
    if (viewerRef.current && pptxBytes) {
      // Force it into pure view/preview mode and hide editor UI
      try {
        viewerRef.current.setMode('preview');
      } catch (e) {
        // ignore if not ready
      }
    }
  }, [pptxBytes, activeTab]);

  const runPipeline = async () => {
    if (isRunning) return;
    setIsRunning(true);
    setStepLogs({});
    setActiveStep(0);
    try {
      const response = await fetch("/api/pipeline");
      if (!response.body) throw new Error("No response body");
      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      let currentStep = 0;
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const newLines = chunk
          .split("\n")
          .filter(l => l.startsWith("data: "))
          .map(l => l.replace("data: ", "").trim())
          .filter(l => l !== "");
          
        if (newLines.length > 0) {
           setStepLogs(prev => {
             const nextLogs = { ...prev };
             for (const line of newLines) {
               // Determine which step this log belongs to
               const l = line.toLowerCase();
               if (l.includes("src.ingestion") || l.includes("loading project file") || l.includes("sheets found") || l.includes("parsed")) currentStep = 0;
               else if (l.includes("signals computed") || l.includes("disagreement=")) currentStep = 1;
               else if (l.includes("src.reasoning_agent") || l.includes("reasoning generated") || l.includes("openai") || l.includes("chat/completions") || l.includes("nim")) currentStep = 2;
               else if (l.includes("src.synthesis_agent") || l.includes("trend deltas") || l.includes("synthesis llm")) currentStep = 3;
               else if (l.includes("src.deck_builder") || l.includes("deck saved") || l.includes("pptx")) currentStep = 4;
               
               setActiveStep(currentStep);
               if (!nextLogs[currentStep]) nextLogs[currentStep] = [];
               nextLogs[currentStep].push(line);
             }
             return nextLogs;
           });
        }
      }
    } catch (err) {
      setStepLogs(prev => ({ ...prev, [activeStep]: [...(prev[activeStep] || []), `Stream error: ${err}`] }));
    } finally {
      setIsRunning(false);
      setActiveStep(-1);
      try {
        const res = await fetch("/api/data");
        if (res.ok) {
          const data = await res.json();
          if (data.projectHistories) setProjectHistories(data.projectHistories);
          if (data.deckData) setDeckData(data.deckData);
        }
        await fetchPptx();
      } catch (e) {
        console.error("Failed to fetch fresh data", e);
      }
      router.refresh();
    }
  };

  const tabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "pipeline", label: "Pipeline Progress" },
    { id: "deck", label: "Exec Deck Viewer" },
  ];

  const getWorstRAG = (rag: string) => {
    const l = rag.toLowerCase();
    if (l.includes("red")) return "red";
    if (l.includes("amber") || l.includes("yellow")) return "amber";
    return "green";
  };
  
  const pipelineSteps = [
    { name: "Ingestion Layer", desc: "Parsed XLSX, mapped schema, handled data gaps." },
    { name: "Signal Engine", desc: "Computed deterministic thresholds and rules." },
    { name: "Reasoning Agent", desc: "Generated plain-English synthesis via NIM LLaMA-3." },
    { name: "Synthesis Agent", desc: "Analyzed cross-project trends." },
    { name: "Deck Builder", desc: "Compiled findings into exec_deck.pptx." }
  ];

  return (
    <div className="min-h-screen bg-zinc-50 text-zinc-900 p-8 font-sans selection:bg-zinc-200">
      <div className="mx-auto max-w-6xl space-y-12">
        
        {/* Header */}
        <header className="flex flex-col items-start gap-6 border-b border-zinc-200 pb-8 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-4xl font-bold tracking-tight text-zinc-900">
              <ScrambleHover text="Project Health Intelligence" scrambleSpeed={40} />
            </h1>
            <p className="mt-2 text-zinc-500">Automated RAG inference and reasoning</p>
          </div>
          <AnimatedTabs tabs={tabs} activeTab={activeTab} setActiveTab={setActiveTab} />
        </header>

        {/* Dashboard Tab */}
        {activeTab === "dashboard" && (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            {projectHistories.map((project, idx) => (
              <GlowHoverCard key={idx} glowColor="rgba(0,0,0,0.03)">
                <div className="flex items-center justify-between border-b border-zinc-100 pb-4">
                  <h2 className="text-2xl font-semibold tracking-tight text-zinc-800">{project.project_name}</h2>
                  <SiriOrb color={getWorstRAG(project.overall_rag)} size={48} />
                </div>
                
                <div className="mt-6 space-y-5">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Overall RAG</span>
                      <p className="mt-1 text-base font-semibold text-zinc-800">{project.overall_rag}</p>
                    </div>
                    <div>
                      <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Source Reported</span>
                      <p className="mt-1 text-base font-semibold text-zinc-800">{project.source_reported_rag}</p>
                    </div>
                  </div>

                  {project.disagreement_flag && (
                    <div className="rounded-full bg-rose-50 px-5 py-2.5 border border-rose-100 text-rose-700 text-xs font-semibold shadow-sm flex items-center gap-2">
                      <span className="flex h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
                      AI assessment disagrees with human-reported status
                    </div>
                  )}

                  <div className="space-y-3">
                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">Sub-scores</span>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(project.sub_scores).map(([key, val]) => (
                        <div key={key} className="flex justify-between rounded-full bg-zinc-50 border border-zinc-200/60 px-4 py-2 shadow-sm">
                          <span className="capitalize font-medium text-zinc-500">{key.replace('_', ' ')}</span>
                          <span className={`font-bold ${val.includes('Red') ? 'text-rose-600' : val.includes('Amber') ? 'text-amber-600' : 'text-emerald-600'}`}>
                            {val}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="pt-4 border-t border-zinc-100 space-y-2">
                    <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">AI Synthesis Reasoning</span>
                    <div className="bg-zinc-50/50 border border-zinc-200/60 p-4 rounded-2xl shadow-inner">
                      <p className="text-sm leading-relaxed text-zinc-600 font-medium">
                        {project.reasoning}
                      </p>
                    </div>
                  </div>
                </div>
              </GlowHoverCard>
            ))}
            {projectHistories.length === 0 && (
              <div className="col-span-full py-12 text-center text-zinc-500">
                No pipeline data found. Run the ingestion pipeline first.
              </div>
            )}
          </div>
        )}

        {/* Pipeline Tab */}
        {activeTab === "pipeline" && (
          <div className="space-y-6">
            <GlowHoverCard className="w-full" glowColor="rgba(0,0,0,0.02)">
              <div className="mb-6 flex items-center justify-between border-b border-zinc-100 pb-6">
                <div>
                  <h2 className="text-2xl font-semibold tracking-tight text-zinc-800">Pipeline Progress</h2>
                  <p className="mt-1 text-sm text-zinc-500">Watch the agents reason and execute live.</p>
                </div>
                <button 
                  onClick={runPipeline}
                  disabled={isRunning}
                  className={`rounded-full px-6 py-2.5 text-sm font-semibold transition-all duration-150 border ${
                    isRunning 
                      ? "bg-zinc-100 text-zinc-400 border-zinc-200 cursor-not-allowed" 
                      : "bg-gradient-to-b from-indigo-500 to-indigo-650 hover:from-indigo-600 hover:to-indigo-750 text-white border-indigo-700 shadow-[inset_0_1.5px_0_rgba(255,255,255,0.3),_0_2px_4px_rgba(79,70,229,0.25)] hover:shadow-[inset_0_1.5px_0_rgba(255,255,255,0.35),_0_4px_10px_rgba(79,70,229,0.35)] active:translate-y-[1px] active:shadow-[inset_0_2px_4px_rgba(0,0,0,0.15)]"
                  }`}
                >
                  {isRunning ? "Running Pipeline..." : "Run Pipeline"}
                </button>
              </div>
              <div className="relative space-y-10">
                {/* Vertical Timeline Line */}
                <div className="absolute bottom-4 left-[11px] top-4 w-[2px] bg-gradient-to-b from-indigo-200 via-zinc-200 to-transparent" />
                
                {pipelineSteps.map((step, idx) => {
                  const logs = stepLogs[idx] || [];
                  const isCurrent = activeStep === idx;
                  const isDone = (!isRunning && logs.length > 0) || (isRunning && activeStep > idx);
                  
                  return (
                    <div key={idx} className="relative flex flex-col gap-4">
                      <div className="flex items-start gap-4">
                        <div className={`relative z-10 mt-1 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full transition-all duration-500 border ${
                          isCurrent ? "bg-indigo-50 text-indigo-600 border-indigo-200 shadow-[0_0_15px_rgba(79,70,229,0.3)]" :
                          isDone ? "bg-emerald-100 text-emerald-600 border-emerald-200 shadow-[0_0_10px_rgba(52,211,153,0.2)]" : "bg-white text-zinc-400 border-zinc-200"
                        }`}>
                          {isCurrent ? (
                            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                          ) : isDone ? (
                            <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor"><path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" /></svg>
                          ) : (
                            <div className="h-2 w-2 rounded-full bg-zinc-300" />
                          )}
                        </div>
                        <div>
                          <h3 className={`text-lg font-medium transition-colors duration-300 ${isCurrent ? "text-indigo-600 font-bold" : isDone ? "text-zinc-800" : "text-zinc-500"}`}>{step.name}</h3>
                          <p className="text-sm text-zinc-500">{step.desc}</p>
                        </div>
                      </div>
                      
                      {/* Mini Terminal for this step */}
                      {(logs.length > 0 || isCurrent) && (
                        <div className={`ml-10 overflow-hidden rounded-xl border transition-all duration-500 ${
                          isCurrent ? 'border-indigo-200 bg-white shadow-lg' : 'border-zinc-200 bg-zinc-50/50'
                        }`}>
                           <div className="flex items-center gap-2 border-b border-zinc-100 bg-zinc-50/80 px-4 py-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
                              {isCurrent ? (
                                <><span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75"></span><span className="relative inline-flex h-2 w-2 rounded-full bg-indigo-500"></span></span> <span className="text-indigo-600">Executing Process...</span></>
                              ) : (
                                <><span className="h-2 w-2 rounded-full bg-emerald-400"></span> Completed</>
                              )}
                           </div>
                           <div className="max-h-60 overflow-y-auto p-4 font-mono text-xs text-zinc-700">
                             {logs.length === 0 && <span className="text-zinc-400 animate-pulse">Initializing...</span>}
                             {logs.map((log, i) => (
                               <div key={i} className="mb-1 break-all whitespace-pre-wrap opacity-90 transition-opacity duration-300">
                                 <span className="mr-2 text-zinc-400">➜</span>{log}
                               </div>
                             ))}
                             {isCurrent && <div className="mt-2 flex items-center text-indigo-500"><span className="animate-pulse text-lg leading-none">_</span></div>}
                           </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </GlowHoverCard>

            <GlowHoverCard className="w-full mt-6" glowColor="rgba(99,102,241,0.02)">
              <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-6 pb-6 border-b border-zinc-100">
                <div className="flex gap-4 items-start">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-indigo-50 border border-indigo-100 text-indigo-600 shadow-[0_0_10px_rgba(79,70,229,0.1)] flex-shrink-0">
                    <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight text-zinc-800 flex items-center gap-2">
                      Automated Scheduler Setup <span className="inline-flex items-center rounded-full bg-emerald-50 px-2.5 py-0.5 text-[10px] font-bold text-emerald-700 border border-emerald-100 uppercase tracking-wider">Operational</span>
                    </h3>
                    <p className="mt-1 text-sm text-zinc-500">
                      Configure the Python pipeline to execute automatically every week.
                    </p>
                  </div>
                </div>

                {/* Segmented Pill Selector */}
                <div className="flex rounded-full bg-zinc-100 p-1 border border-zinc-200 self-start lg:self-center">
                  <button
                    onClick={() => setScheduleType("daemon")}
                    className={`rounded-full px-4 py-1.5 text-xs font-semibold tracking-wide transition-all duration-150 border ${
                      scheduleType === "daemon"
                        ? "bg-white text-indigo-600 border-zinc-200 shadow-sm"
                        : "text-zinc-500 hover:text-zinc-700 border-transparent"
                    }`}
                  >
                    APScheduler Daemon
                  </button>
                  <button
                    onClick={() => setScheduleType("cron")}
                    className={`rounded-full px-4 py-1.5 text-xs font-semibold tracking-wide transition-all duration-150 border ${
                      scheduleType === "cron"
                        ? "bg-white text-indigo-600 border-zinc-200 shadow-sm"
                        : "text-zinc-500 hover:text-zinc-700 border-transparent"
                    }`}
                  >
                    System Crontab
                  </button>
                </div>
              </div>

              {/* Conditional Panel Render */}
              <div className="mt-6">
                {scheduleType === "daemon" ? (
                  <div className="flex flex-col md:flex-row gap-6 items-start">
                    <div className="flex-1 space-y-3">
                      <h4 className="text-sm font-semibold text-zinc-700">In-Process Scheduling (APScheduler)</h4>
                      <p className="text-xs text-zinc-500 leading-relaxed">
                        This starts a resident Python process that runs in the background. It stays active on your host machine and programmatically triggers the weekly ingestion job precisely every **Monday at 9:00 AM**.
                      </p>
                      <div className="flex gap-4 text-xs font-medium text-zinc-500 pt-2">
                        <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-indigo-500"></span> APScheduler V3</span>
                        <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-indigo-500"></span> Resident Daemon</span>
                      </div>
                    </div>
                    
                    <div className="w-full md:w-[380px] overflow-hidden rounded-xl border border-zinc-200 bg-zinc-950 font-mono text-xs text-zinc-300 shadow-lg flex-shrink-0">
                      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                        <span>Terminal Command</span>
                        <span className="h-2 w-2 rounded-full bg-indigo-500"></span>
                      </div>
                      <div className="p-4 flex items-center justify-between gap-4">
                        <span className="text-emerald-400 break-all select-all">python run.py schedule</span>
                        <button 
                          onClick={() => navigator.clipboard.writeText("python run.py schedule")} 
                          className="text-zinc-500 hover:text-white transition-colors p-1.5 hover:bg-zinc-800 rounded-lg"
                          title="Copy command"
                        >
                          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-col md:flex-row gap-6 items-start">
                    <div className="flex-1 space-y-3">
                      <h4 className="text-sm font-semibold text-zinc-700">Unix System Crontab Deployment</h4>
                      <p className="text-xs text-zinc-500 leading-relaxed">
                        If you want a lightweight solution without running a persistent Python process, you can register a rule in the system's cron manager. It will wake up the virtual environment, execute the pipeline, and shut down cleanly.
                      </p>
                      <div className="flex gap-4 text-xs font-medium text-zinc-500 pt-2">
                        <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-indigo-500"></span> Zero Overhead</span>
                        <span className="flex items-center gap-1.5"><span className="h-1.5 w-1.5 rounded-full bg-indigo-500"></span> Cron Daemon</span>
                      </div>
                    </div>
                    
                    <div className="w-full md:w-[380px] overflow-hidden rounded-xl border border-zinc-200 bg-zinc-950 font-mono text-xs text-zinc-300 shadow-lg flex-shrink-0">
                      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                        <span>Crontab Entry (Monday 9AM)</span>
                        <span className="h-2 w-2 rounded-full bg-emerald-500"></span>
                      </div>
                      <div className="p-4 flex items-center justify-between gap-4">
                        <span className="text-amber-400 break-all select-all text-[11px] truncate">0 9 * * 1 python run.py weekly --all</span>
                        <button 
                          onClick={() => navigator.clipboard.writeText("0 9 * * 1 cd /path/to/project && source venv/bin/activate && python run.py weekly --all")} 
                          className="text-zinc-500 hover:text-white transition-colors p-1.5 hover:bg-zinc-800 rounded-lg flex-shrink-0"
                          title="Copy cron entry"
                        >
                          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </GlowHoverCard>
          </div>
        )}

        {/* Deck Viewer Tab */}
        {activeTab === "deck" && (
          <div className="space-y-6">
            <div className="flex items-center justify-between">
              <h2 className="text-2xl font-semibold tracking-tight text-zinc-800">Executive Presentation</h2>
              <a 
                href={`/exec_deck.pptx?v=${downloadVersion}`}
                download="exec_deck.pptx"
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full bg-gradient-to-b from-indigo-50 to-indigo-100 px-6 py-2.5 text-sm font-semibold text-indigo-700 border border-indigo-200 shadow-[inset_0_1.5px_0_rgba(255,255,255,0.7),_0_1px_2px_rgba(0,0,0,0.05)] hover:from-indigo-100 hover:to-indigo-150 hover:shadow-md active:translate-y-[1px] active:shadow-[inset_0_2px_4px_rgba(0,0,0,0.1)] transition-all flex items-center gap-2"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download Presentation
              </a>
            </div>
            
            {pptxBytes ? (
              <div className="flex flex-col gap-4">
                <div className="h-[70vh] min-h-[600px] w-full border border-zinc-200 rounded-2xl overflow-hidden shadow-xl bg-white relative">
                   <I18nextProvider i18n={i18n}>
                     <PowerPointViewer 
                       ref={viewerRef} 
                       content={pptxBytes} 
                       canEdit={false}
                       onActiveSlideChange={(idx) => setViewerSlideIndex(idx)}
                       onSlideCountChange={(count) => setViewerSlideCount(count)}
                     />
                   </I18nextProvider>
                </div>
                
                {/* Navigation Controls */}
                {viewerSlideCount > 0 && (
                  <div className="flex items-center justify-between bg-white border border-zinc-200 rounded-full px-6 py-3 shadow-sm w-full lg:w-1/2 mx-auto">
                    <button
                      onClick={() => viewerRef.current?.goPrev()}
                      disabled={viewerSlideIndex === 0}
                      className="rounded-full px-4 py-2 text-xs font-bold text-zinc-700 bg-gradient-to-b from-zinc-50 to-zinc-100 border border-zinc-200 shadow-[inset_0_1.5px_0_rgba(255,255,255,0.7),_0_1px_2px_rgba(0,0,0,0.05)] hover:from-zinc-100 hover:to-zinc-150 active:translate-y-[1px] active:shadow-[inset_0_2px_4px_rgba(0,0,0,0.08)] disabled:opacity-40 disabled:translate-y-0 disabled:shadow-none flex items-center gap-1.5 transition-all"
                    >
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 18l-6-6 6-6"/></svg>
                      Previous
                    </button>
                    <div className="text-sm font-mono text-zinc-400">
                      {viewerSlideIndex + 1} / {viewerSlideCount}
                    </div>
                    <button
                      onClick={() => viewerRef.current?.goNext()}
                      disabled={viewerSlideIndex === viewerSlideCount - 1}
                      className="rounded-full px-4 py-2 text-xs font-bold text-zinc-700 bg-gradient-to-b from-zinc-50 to-zinc-100 border border-zinc-200 shadow-[inset_0_1.5px_0_rgba(255,255,255,0.7),_0_1px_2px_rgba(0,0,0,0.05)] hover:from-zinc-100 hover:to-zinc-150 active:translate-y-[1px] active:shadow-[inset_0_2px_4px_rgba(0,0,0,0.08)] disabled:opacity-40 disabled:translate-y-0 disabled:shadow-none flex items-center gap-1.5 transition-all"
                    >
                      Next
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6"/></svg>
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-24 text-center text-zinc-500 border border-zinc-200 rounded-3xl border-dashed bg-white">
                <svg className="w-12 h-12 mx-auto text-zinc-300 mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>
                No presentation data available or loading... Run the pipeline first.
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
