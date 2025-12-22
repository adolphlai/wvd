
import React, { useState, useEffect, useRef } from 'react';
import { 
  Sword, Zap, BarChart3, Play, Square, Terminal, 
  Monitor, LayoutGrid, ShieldAlert,
  Moon, Heart, Crown, Sparkles, Save, CheckCircle2,
  Wand2, Cpu, Database
} from 'lucide-react';
import { TabType, AppSettings, LogEntry } from './types';

// 高密度開關 - 專為 800px 佈局優化
const MiniToggle = ({ label, enabled, onChange, disabled = false }: { label: string, enabled: boolean, onChange: (v: boolean) => void, disabled?: boolean }) => (
  <div 
    className={`flex items-center justify-between p-1.5 px-2 rounded-lg transition-all ${disabled ? 'opacity-20 cursor-not-allowed' : 'hover:bg-white/5 cursor-pointer'}`}
    onClick={() => !disabled && onChange(!enabled)}
  >
    <span className="text-[11px] font-medium text-slate-400 truncate mr-2 leading-none">{label}</span>
    <button
      disabled={disabled}
      className={`relative inline-flex h-3.5 w-6 shrink-0 items-center rounded-full transition-all ${
        enabled ? 'bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.3)]' : 'bg-slate-700'
      }`}
    >
      <span className={`inline-block h-2.5 w-2.5 transform rounded-full bg-white transition-transform ${enabled ? 'translate-x-3' : 'translate-x-0.5'}`} />
    </button>
  </div>
);

// 設定分組 - 減少間距
const CompactGroup = ({ title, icon: Icon, children }: { title: string, icon: any, children?: React.ReactNode }) => (
  <div className="mb-3">
    <div className="flex items-center space-x-1.5 mb-1.5 px-1">
      <Icon size={11} className="text-blue-500" />
      <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">{title}</span>
    </div>
    <div className="bg-slate-900/30 border border-white/5 rounded-lg p-1.5">
      {children}
    </div>
  </div>
);

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>(TabType.General);
  const [isRunning, setIsRunning] = useState(false);
  const [settings, setSettings] = useState<AppSettings>({
    port: '5555',
    dungeon: '*新!*[宝箱+刷怪]深雪R6',
    chestOpener: '左上',
    skipPostBattleRestore: true,
    skipPostChestRestore: false,
    resumeOptimization: true,
    strongSkillAfterRestart: true,
    strongSkillAfterReturn: true,
    hotelRest: true,
    restInterval: 3,
    luxuryRoom: true,
    karma: '维持现状',
    adjustKarma: true,
    jumpToTriumph: true,
    autoBattle: true,
    oneAoePerBattle: false,
    autoBattleAfterAoe: false,
    enableAllSkills: false,
    enableRowAoe: false,
    enableAllAoe: false,
    enableSecretAoe: false,
    enableSingleTarget: false,
    enableCrowdControl: false,
  });

  const [logs, setLogs] = useState<LogEntry[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isRunning) {
      const interval = setInterval(() => {
        setLogs(prev => [...prev.slice(-100), { 
          id: Date.now().toString(), 
          timestamp: new Date().toLocaleTimeString('zh-CN', { hour12: false }), 
          message: "引擎循環偵測中...", 
          type: 'info' 
        }]);
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [isRunning]);

  useEffect(() => { logEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [logs]);

  return (
    <div className="flex h-full w-full bg-[#020617] text-slate-200 overflow-hidden select-none">
      
      {/* 1. 側邊導航 (64px) */}
      <aside className="w-16 border-r border-white/5 bg-slate-950 flex flex-col items-center py-6 shrink-0">
        <div className="mb-10 bg-blue-600 p-2 rounded-xl shadow-lg shadow-blue-500/20">
          <Sparkles size={18} className="text-white" />
        </div>

        <nav className="flex-1 space-y-5">
          {[
            { id: TabType.General, icon: LayoutGrid },
            { id: TabType.Battle, icon: Sword },
            { id: TabType.Skills, icon: Wand2 },
            { id: TabType.Advanced, icon: Moon },
            { id: TabType.Stats, icon: BarChart3 }
          ].map(item => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={`p-2.5 rounded-lg transition-all relative group ${
                activeTab === item.id 
                  ? 'bg-blue-600/20 text-blue-400' 
                  : 'text-slate-600 hover:text-slate-300'
              }`}
            >
              <item.icon size={20} />
              <div className="absolute left-14 bg-slate-800 text-white text-[9px] px-2 py-1 rounded opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50">
                {item.id}
              </div>
            </button>
          ))}
        </nav>

        <button
          onClick={() => setIsRunning(!isRunning)}
          className={`mt-auto p-3 rounded-full transition-all ${
            isRunning 
              ? 'text-red-500 bg-red-500/10' 
              : 'text-emerald-500 bg-emerald-500/10 hover:scale-110'
          }`}
        >
          {isRunning ? <Square size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" />}
        </button>
      </aside>

      {/* 2. 主設定區 (450px) */}
      <main className="w-[450px] flex flex-col border-r border-white/5 bg-[#020617]">
        <header className="h-12 border-b border-white/5 flex items-center justify-between px-5 bg-slate-950/40 shrink-0">
          <div className="flex items-center space-x-2">
            <span className="text-[12px] font-bold text-white tracking-tight">{activeTab}</span>
            <div className={`w-1.5 h-1.5 rounded-full ${isRunning ? 'bg-emerald-500 animate-pulse' : 'bg-slate-700'}`} />
          </div>
          <div className="flex items-center space-x-3 text-[10px] font-mono text-slate-500">
            <div className="flex items-center space-x-1">
              <Cpu size={12} />
              <span>12%</span>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-4 custom-scroll">
          
          {activeTab === TabType.General && (
            <div className="space-y-1">
              <CompactGroup title="環境聯接" icon={Monitor}>
                <div className="flex items-center justify-between p-1.5 px-2">
                  <div className="flex items-center space-x-2">
                    <CheckCircle2 size={12} className="text-emerald-500" />
                    <span className="text-[11px] text-slate-300">Port: {settings.port}</span>
                  </div>
                  <button className="text-[10px] bg-blue-600/20 hover:bg-blue-600/40 px-2 py-0.5 rounded text-blue-400 flex items-center space-x-1 transition-colors">
                    <Save size={10} />
                    <span>SAVE</span>
                  </button>
                </div>
              </CompactGroup>

              <CompactGroup title="當前任務" icon={Crown}>
                <div className="px-1 py-0.5">
                  <select 
                    value={settings.dungeon} 
                    onChange={e => setSettings({...settings, dungeon: e.target.value})}
                    className="w-full bg-slate-950 border border-white/10 rounded px-2 py-2 text-[11px] outline-none text-blue-400 font-bold"
                  >
                    <option>{settings.dungeon}</option>
                    <option>火焰之歌 R1 (速刷模式)</option>
                    <option>深寒冰境 R4 (資源優先)</option>
                  </select>
                </div>
              </CompactGroup>

              <CompactGroup title="自動化策略" icon={Zap}>
                {/* 使用雙列佈局縮短長度 */}
                <div className="grid grid-cols-2 gap-1">
                  <MiniToggle label="戰後不恢復" enabled={settings.skipPostBattleRestore} onChange={v => setSettings({...settings, skipPostBattleRestore: v})} />
                  <MiniToggle label="箱後不恢復" enabled={settings.skipPostChestRestore} onChange={v => setSettings({...settings, skipPostChestRestore: v})} />
                  <div className="col-span-2 mt-1 pt-1 border-t border-white/5">
                    <MiniToggle label="極速 Resume 優化" enabled={settings.resumeOptimization} onChange={v => setSettings({...settings, resumeOptimization: v})} />
                  </div>
                </div>
              </CompactGroup>
            </div>
          )}

          {activeTab === TabType.Battle && (
            <div className="space-y-1">
              <CompactGroup title="自動戰鬥" icon={Sword}>
                <div className="bg-blue-500/5 rounded p-1 mb-1 border border-blue-500/10">
                  <MiniToggle label="全自動模式核心" enabled={settings.autoBattle} onChange={v => setSettings({...settings, autoBattle: v})} />
                </div>
                <div className="grid grid-cols-2 gap-1">
                  <MiniToggle label="單次 AOE" enabled={settings.oneAoePerBattle} onChange={v => setSettings({...settings, oneAoePerBattle: v})} />
                  <MiniToggle label="AOE 後自動" enabled={settings.autoBattleAfterAoe} onChange={v => setSettings({...settings, autoBattleAfterAoe: v})} />
                </div>
              </CompactGroup>
              <CompactGroup title="例外防禦" icon={ShieldAlert}>
                <div className="grid grid-cols-2 gap-1">
                  <MiniToggle label="重啟強力技" enabled={settings.strongSkillAfterRestart} onChange={v => setSettings({...settings, strongSkillAfterRestart: v})} />
                  <MiniToggle label="返回強力技" enabled={settings.strongSkillAfterReturn} onChange={v => setSettings({...settings, strongSkillAfterReturn: v})} />
                </div>
              </CompactGroup>
            </div>
          )}

          {activeTab === TabType.Skills && (
            <CompactGroup title="技能授權矩陣" icon={Wand2}>
              <div className="grid grid-cols-2 gap-1">
                <div className="col-span-2 border-b border-white/5 pb-1 mb-1">
                  <MiniToggle label="啟用所有技能" enabled={settings.enableAllSkills} onChange={v => setSettings({...settings, enableAllSkills: v})} />
                </div>
                <MiniToggle label="優先全體 AOE" enabled={settings.enableAllAoe} onChange={v => setSettings({...settings, enableAllAoe: v})} />
                <MiniToggle label="優先橫排 AOE" enabled={settings.enableRowAoe} onChange={v => setSettings({...settings, enableRowAoe: v})} />
                <MiniToggle label="秘術解鎖" enabled={settings.enableSecretAoe} onChange={v => setSettings({...settings, enableSecretAoe: v})} />
                <MiniToggle label="單體爆發" enabled={settings.enableSingleTarget} onChange={v => setSettings({...settings, enableSingleTarget: v})} />
                <MiniToggle label="控制系技能" enabled={settings.enableCrowdControl} onChange={v => setSettings({...settings, enableCrowdControl: v})} />
              </div>
            </CompactGroup>
          )}

          {activeTab === TabType.Advanced && (
            <div className="space-y-1">
              <CompactGroup title="補給物流" icon={Moon}>
                <div className="flex items-center justify-between p-1.5 px-2 bg-slate-950/40 rounded mb-1">
                  <span className="text-[11px] text-slate-400">旅店休息間隔 (場)</span>
                  <div className="flex items-center space-x-2">
                    <input 
                      type="number" 
                      value={settings.restInterval} 
                      onChange={e => setSettings({...settings, restInterval: parseInt(e.target.value)})}
                      className="w-8 bg-slate-900 border border-white/10 rounded text-center text-[11px] py-0.5 outline-none focus:border-blue-500" 
                    />
                    <MiniToggle label="" enabled={settings.hotelRest} onChange={v => setSettings({...settings, hotelRest: v})} />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-1">
                  <MiniToggle label="豪華房優先" enabled={settings.luxuryRoom} onChange={v => setSettings({...settings, luxuryRoom: v})} />
                  <MiniToggle label="跳過凱旋" enabled={settings.jumpToTriumph} onChange={v => setSettings({...settings, jumpToTriumph: v})} />
                </div>
              </CompactGroup>
              <CompactGroup title="因果控制" icon={Heart}>
                <div className="space-y-2 p-1">
                  <select 
                    value={settings.karma} 
                    onChange={e => setSettings({...settings, karma: e.target.value})}
                    className="w-full bg-slate-950 border border-white/10 rounded px-2 py-1.5 text-[11px] outline-none"
                  >
                    <option>維持現狀</option><option>偏向善意</option><option>偏向惡意</option>
                  </select>
                  <MiniToggle label="主動因果調整" enabled={settings.adjustKarma} onChange={v => setSettings({...settings, adjustKarma: v})} />
                </div>
              </CompactGroup>
            </div>
          )}

        </div>
      </main>

      {/* 3. 日誌反饋區 (286px) */}
      <section className="flex-1 bg-slate-950/20 flex flex-col shrink-0">
        <div className="h-12 border-b border-white/5 flex items-center px-4 space-x-2 shrink-0">
          <Terminal size={12} className="text-slate-500" />
          <span className="text-[9px] font-black text-slate-500 uppercase tracking-widest">系統終端日誌</span>
        </div>
        
        <div className="flex-1 overflow-y-auto p-3 space-y-2 font-mono text-[10px]">
          {logs.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-slate-700 opacity-30">
              <Database size={20} />
              <span className="mt-2 text-[9px]">AWAITING DATA...</span>
            </div>
          )}
          {logs.map(log => (
            <div key={log.id} className="border-l border-blue-500/30 pl-2 py-0.5">
              <span className="text-slate-600 mr-1.5">[{log.timestamp}]</span>
              <span className="text-slate-400">{log.message}</span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>

        <div className="p-3 border-t border-white/5 bg-slate-950/60 shrink-0">
          <div className="flex items-center justify-between text-[8px] text-slate-600 font-mono">
            <div className="flex items-center space-x-2">
              <span className="flex items-center"><div className="w-1 h-1 rounded-full bg-emerald-500 mr-1" />ADB: OK</span>
              <span className="flex items-center"><div className="w-1 h-1 rounded-full bg-emerald-500 mr-1" />SCRIPT: V2.1</span>
            </div>
            <span>MEM: 128MB</span>
          </div>
        </div>
      </section>

    </div>
  );
};

export default App;
