import React, { useState, useEffect, useRef, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Settings, Save, Upload, Download, Plus, Trash2,
  Crosshair, Image as ImageIcon, Wifi, WifiOff,
  MousePointer, Map, Home, Play, Square, X, Monitor,
  Clock, Type, Move, Terminal, Crop, Scissors, ChevronDown, FileJson,
  Box, AlignJustify, MapPin, Search, GripVertical, Scan, FilePlus, Edit, Check
} from 'lucide-react';

// --- Types ---

type ScriptData = {
  _TYPE: string; // 'dungeon' | 'quest'
  questName?: string;
  _TARGETINFOLIST: any[];
  _EOT: any[];
  [key: string]: any;
};

type QuestsMap = Record<string, ScriptData>;

type ItemType = 'simple' | 'position' | 'press' | 'stair' | 'chest' | 'minimap_stair' | 'harken' | 'chest_auto' | 'unknown';

// Identify which field we are currently capturing for
type CaptureTarget = {
  index: number;
  field: 'coord' | 'target_pattern' | 'fallback_value' | 'roi';
  subIndex?: number; // For array based fields
} | null;

interface EditorState {
  wsUrl: string;
  isConnected: boolean;
  activeTab: 'dungeon' | 'village';
  selectedItemIndex: number | null;
  interactionMode: 'none' | 'pick' | 'rect' | 'swipe';
  captureTarget: CaptureTarget;
  quests: QuestsMap;
  currentQuestId: string | null;
  logs: string[];
}

interface QuestModalState {
  isOpen: boolean;
  mode: 'create' | 'edit' | 'delete';
  questId: string;
  originalQuestId?: string; // For tracking key changes during edit
  questName: string;
  questType: string;
}

const DEFAULT_QUESTS: QuestsMap = {
  "wolf_dungeon_1f": {
    "_TYPE": "dungeon",
    "questName": "[寶箱]狼洞1f寶箱",
    "_TARGETINFOLIST": [
      ["chest_auto"],
      ["position", "右下", [771, 921]]
    ],
    "_EOT": [
      ["press", "intoWorldMap", ["AWD/AWD", "input swipe 400 400 500 500"], 2],
      ["press", "AWD/AWD1F", [1, 1], 2]
    ]
  },
  "snow_church_boss": {
    "_TYPE": "dungeon",
    "questName": "[打王]深雪教會區",
    "_TARGETINFOLIST": [
      ["boss_mode"],
      ["position", "右下", [500, 500]]
    ],
    "_EOT": [
      ["press", "return", ["AWD/return", "tap 100 100"], 2]
    ]
  }
};

// --- Helper Functions ---

const identifyType = (item: any[]): ItemType => {
  if (!Array.isArray(item)) return 'unknown';
  const head = item[0];
  if (typeof head !== 'string') return 'unknown';

  if (head === 'press') return 'press';
  if (head === 'chest_auto') return 'chest_auto';
  if (head === 'harken') return 'harken';
  if (head === 'position') return 'position';
  if (head === 'minimap_stair') return 'minimap_stair';
  if (head.startsWith('stair')) return 'stair';
  if (head === 'chest') return 'chest';

  if (item.length === 1 && typeof item[0] === 'string') return 'simple';

  return 'unknown';
};

const getTypeColor = (type: string) => {
  switch (type) {
    case 'position': return 'bg-purple-500/20 text-purple-300';
    case 'stair': return 'bg-blue-500/20 text-blue-300';
    case 'minimap_stair': return 'bg-cyan-500/20 text-cyan-300';
    case 'chest': return 'bg-yellow-500/20 text-yellow-300';
    case 'chest_auto': return 'bg-green-500/20 text-green-300';
    case 'harken': return 'bg-pink-500/20 text-pink-300';
    case 'press': return 'bg-orange-500/20 text-orange-300';
    default: return 'bg-gray-500/20 text-gray-300';
  }
}

const formatCoord = (coord: number[]) => `[${coord.join(', ')}]`;

const isCoordinate = (val: any) => Array.isArray(val) && val.length === 2 && typeof val[0] === 'number';
const isRoi = (val: any) => Array.isArray(val) && val.length === 4 && typeof val[0] === 'number';

// --- Components ---

const App = () => {
  const [state, setState] = useState<EditorState>({
    wsUrl: 'ws://localhost:8765',
    isConnected: false,
    activeTab: 'dungeon',
    selectedItemIndex: null,
    interactionMode: 'none',
    captureTarget: null,
    quests: DEFAULT_QUESTS,
    currentQuestId: Object.keys(DEFAULT_QUESTS)[0] || null,
    logs: ['Welcome. Connect WS to start.']
  });

  const [questModal, setQuestModal] = useState<QuestModalState>({
    isOpen: false,
    mode: 'create',
    questId: '',
    questName: '',
    questType: 'dungeon'
  });

  const [imageSrc, setImageSrc] = useState<string | null>(null);
  const [imageBlob, setImageBlob] = useState<Blob | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const reconnectTimerRef = useRef<any>(null);
  const shouldReconnectRef = useRef(false);

  // Drag and Drop State
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const [dragReadyIndex, setDragReadyIndex] = useState<number | null>(null);

  // Constants for Resolution
  const GAME_WIDTH = 900;
  const GAME_HEIGHT = 1600;

  // Derived state for current script
  const currentScript = state.currentQuestId ? state.quests[state.currentQuestId] : null;

  // --- WebSocket Handling ---

  const connectWS = () => {
    if (wsRef.current) {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current.close();
      wsRef.current = null;
      setState(s => ({ ...s, isConnected: false, logs: [...s.logs, 'Disconnected.'] }));
      return;
    }

    shouldReconnectRef.current = true;
    const startConnection = () => {
      if (!shouldReconnectRef.current) return;

      try {
        const ws = new WebSocket(state.wsUrl);

        ws.onopen = () => {
          setState(s => ({ ...s, isConnected: true, logs: [...s.logs, "Connected to WebSocket server"] }));
          // Request initial quest data from server
          ws.send(JSON.stringify({ cmd: "load_quest" }));
        };

        ws.onmessage = (event) => {
          if (event.data instanceof Blob) {
            setImageBlob(event.data);
            const url = URL.createObjectURL(event.data);
            setImageSrc(url);
          } else if (typeof event.data === 'string') {
            if (event.data.startsWith('{')) {
              try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'log') {
                  setState(s => ({ ...s, logs: [...s.logs, `SERVER: ${msg.message}`] }));
                } else if (msg.type === 'saved') {
                  setState(s => ({ ...s, logs: [...s.logs, "✅ Server saved quest.json successfully!"] }));
                } else if (msg.type === 'image_saved') {
                  setState(s => ({ ...s, logs: [...s.logs, `✅ Server saved image: ${msg.filename}`] }));
                } else if (msg.type === 'quest') {
                  setState(s => ({ ...s, quests: msg.data, currentQuestId: Object.keys(msg.data)[0] || null, logs: [...s.logs, "📥 Loaded quests from server."] }));
                } else if (msg.type === 'error') {
                  setState(s => ({ ...s, logs: [...s.logs, `❌ SERVER ERROR: ${msg.message}`] }));
                }
              } catch (e) {
                console.error("WS Parse error", e);
              }
            } else {
              setImageSrc(`data:image/jpeg;base64,${event.data}`);
            }
          }
        };

        ws.onclose = () => {
          setState(s => ({ ...s, isConnected: false, logs: [...s.logs, "Disconnected from WebSocket server"] }));
          wsRef.current = null;
          if (shouldReconnectRef.current) {
            setState(s => ({ ...s, logs: [...s.logs, "Reconnecting in 3s..."] }));
            reconnectTimerRef.current = setTimeout(startConnection, 3000);
          }
        };
        wsRef.current = ws;
      } catch (e) {
        console.error(e);
        setState(s => ({ ...s, logs: [...s.logs, 'Failed to connect.'] }));
      }
    };

    startConnection();
  };

  // Helper for reliable sending
  const sendWS = (cmd: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(cmd);
      const displayCmd = cmd.length > 100 ? cmd.substring(0, 100) + "..." : cmd;
      setState(s => ({ ...s, logs: [...s.logs, `▶ Sent: ${displayCmd}`] }));
      return true;
    } else {
      setState(s => ({ ...s, logs: [...s.logs, "⚠ WebSocket not connected"] }));
      return false;
    }
  };

  const handlePlayAction = (e: React.MouseEvent, item: any[]) => {
    e.stopPropagation();

    if (!wsRef.current || !state.isConnected) {
      setState(s => ({ ...s, logs: [...s.logs, "⚠ Connect WS to replay"] }));
      return;
    }

    const type = identifyType(item);

    if (type === 'press') {
      // 1. Test primary image
      const primaryImg = typeof item[1] === 'string' ? item[1] : '';
      if (primaryImg) {
        sendWS(JSON.stringify({ cmd: "click_image", filename: primaryImg }));
      }

      // 2. Do fallbacks
      const fallback = item[2];
      const actions = (Array.isArray(fallback) && !isCoordinate(fallback)) ? fallback : [fallback];

      actions.forEach((action: any) => {
        if (typeof action === 'string' && action.startsWith('input ')) {
          sendWS(action);
        } else if (isCoordinate(action)) {
          const cmd = `input tap ${action[0]} ${action[1]}`;
          sendWS(cmd);
        } else if (typeof action === 'string' && action !== "") {
          // Assume it's an image
          sendWS(JSON.stringify({ cmd: "click_image", filename: action }));
        }
      });
      return;
    }

    let cmd = "";

    if (['position', 'stair', 'minimap_stair'].includes(type)) {
      const coord = item[2];
      if (isCoordinate(coord)) {
        const [x, y] = coord;
        cmd = `input tap ${x} ${y}`;
      }
    } else if (type === 'simple') {
      cmd = item[0];
    } else if (type === 'chest') {
      setState(s => ({ ...s, logs: [...s.logs, `ℹ Chest uses ROI, cannot simple tap.`] }));
      return;
    }

    if (cmd) {
      sendWS(cmd);
    } else {
      setState(s => ({ ...s, logs: [...s.logs, `⚠ No executable command for: ${type}`] }));
    }
  };

  // --- Quest Management (Modal Logic) ---

  const openCreateModal = () => {
    setQuestModal({
      isOpen: true,
      mode: 'create',
      questId: `quest_${Date.now()}`,
      questName: 'New Quest',
      questType: 'dungeon'
    });
  };

  const openEditModal = () => {
    if (!currentScript || !state.currentQuestId) return;
    setQuestModal({
      isOpen: true,
      mode: 'edit',
      questId: state.currentQuestId,
      originalQuestId: state.currentQuestId,
      questName: currentScript.questName || '',
      questType: currentScript._TYPE || 'dungeon'
    });
  };

  const openDeleteModal = () => {
    if (!state.currentQuestId) return;
    setQuestModal({
      isOpen: true,
      mode: 'delete',
      questId: state.currentQuestId,
      questName: '',
      questType: ''
    });
  };

  const closeModal = () => {
    setQuestModal(s => ({ ...s, isOpen: false }));
  };

  const handleSaveModal = () => {
    if (questModal.mode === 'delete') {
      setState(s => {
        const newQuests = { ...s.quests };
        delete newQuests[questModal.questId];

        const remainingIds = Object.keys(newQuests);
        const nextId = remainingIds.length > 0 ? remainingIds[0] : null;

        return {
          ...s,
          quests: newQuests,
          currentQuestId: nextId,
          selectedItemIndex: null,
          logs: [...s.logs, `Deleted quest: ${questModal.questId}`]
        };
      });
      closeModal();
      return;
    }

    if (!questModal.questId.trim()) {
      alert("Quest ID cannot be empty");
      return;
    }

    // Check for duplicate IDs
    if (questModal.mode === 'create' && state.quests[questModal.questId]) {
      alert("Quest ID already exists!");
      return;
    }
    if (questModal.mode === 'edit' && questModal.questId !== questModal.originalQuestId && state.quests[questModal.questId]) {
      alert("Quest ID already exists! Choose another.");
      return;
    }

    setState(s => {
      let newQuests = { ...s.quests };
      let updatedQuest: ScriptData;

      if (questModal.mode === 'create') {
        updatedQuest = {
          _TYPE: questModal.questType,
          questName: questModal.questName,
          _TARGETINFOLIST: [],
          _EOT: []
        };
        newQuests[questModal.questId] = updatedQuest;
      } else {
        // Edit Mode
        // Preserve existing data but update metadata
        const originalData = s.quests[questModal.originalQuestId!];
        updatedQuest = {
          ...originalData,
          _TYPE: questModal.questType,
          questName: questModal.questName
        };

        if (questModal.questId !== questModal.originalQuestId) {
          // ID changed: Remove old key, add new key
          delete newQuests[questModal.originalQuestId!];
        }
        newQuests[questModal.questId] = updatedQuest;
      }

      return {
        ...s,
        quests: newQuests,
        currentQuestId: questModal.questId,
        logs: [...s.logs, `${questModal.mode === 'create' ? 'Created' : 'Updated'} quest: ${questModal.questId}`]
      };
    });

    closeModal();
  };

  // --- Script Manipulation ---

  const activeList = currentScript ? (state.activeTab === 'dungeon' ? currentScript._TARGETINFOLIST : currentScript._EOT) : [];

  const updateCurrentQuest = (updates: Partial<ScriptData>) => {
    if (!state.currentQuestId || !currentScript) return;
    const updatedQuest = { ...currentScript, ...updates };
    setState(s => ({
      ...s,
      quests: { ...s.quests, [state.currentQuestId!]: updatedQuest }
    }));
  };

  const updateScriptItem = (index: number, newValue: any) => {
    if (!currentScript) return;
    const listKey = state.activeTab === 'dungeon' ? '_TARGETINFOLIST' : '_EOT';
    const newList = [...currentScript[listKey]];
    newList[index] = newValue;
    updateCurrentQuest({ [listKey]: newList });
  };

  const addScriptItem = (type: ItemType) => {
    if (!currentScript) return;
    const listKey = state.activeTab === 'dungeon' ? '_TARGETINFOLIST' : '_EOT';
    let newItem;

    // Dungeon Types
    if (type === 'position') newItem = ["position", "右下", [0, 0]];
    if (type === 'chest_auto') newItem = ["chest_auto"];
    if (type === 'harken') newItem = ["harken", "右下", [null], null];
    if (type === 'stair') newItem = ["stair_name", "右下", [0, 0]];
    if (type === 'minimap_stair') newItem = ["minimap_stair", "右下", [0, 0], "floor_img"];
    if (type === 'chest') newItem = ["chest", "name", [0, 0, 0, 0]]; // Chest uses ROI [x1, y1, x2, y2]

    // Village Types
    if (type === 'press') {
      newItem = ["press", "target_image", ["input swipe 0 0 0 0"], 2];
    }

    if (newItem) {
      const newList = [...currentScript[listKey], newItem];
      const updatedQuest = { ...currentScript, [listKey]: newList };

      setState(s => ({
        ...s,
        quests: { ...s.quests, [state.currentQuestId!]: updatedQuest },
        selectedItemIndex: newList.length - 1
      }));
    }
  };

  const deleteScriptItem = (index: number) => {
    if (!currentScript) return;
    const listKey = state.activeTab === 'dungeon' ? '_TARGETINFOLIST' : '_EOT';
    const newList = currentScript[listKey].filter((_, i) => i !== index);
    updateCurrentQuest({ [listKey]: newList });
    setState(s => ({ ...s, selectedItemIndex: null }));
  };

  // --- Drag and Drop Handlers ---

  const handleDragStart = (e: React.DragEvent, index: number) => {
    setDraggingIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', index.toString());
  };

  const handleDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDrop = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    if (draggingIndex === null || draggingIndex === targetIndex) return;
    if (!currentScript) return;

    const listKey = state.activeTab === 'dungeon' ? '_TARGETINFOLIST' : '_EOT';
    const newList = [...currentScript[listKey]];
    const [movedItem] = newList.splice(draggingIndex, 1);
    newList.splice(targetIndex, 0, movedItem);

    let newSelectedIndex = state.selectedItemIndex;
    if (state.selectedItemIndex === draggingIndex) {
      newSelectedIndex = targetIndex;
    } else if (state.selectedItemIndex !== null) {
      if (draggingIndex < state.selectedItemIndex && targetIndex >= state.selectedItemIndex) {
        newSelectedIndex = state.selectedItemIndex - 1;
      } else if (draggingIndex > state.selectedItemIndex && targetIndex <= state.selectedItemIndex) {
        newSelectedIndex = state.selectedItemIndex + 1;
      }
    }

    const updatedQuest = { ...currentScript, [listKey]: newList };
    setState(s => ({
      ...s,
      quests: { ...s.quests, [state.currentQuestId!]: updatedQuest },
      selectedItemIndex: newSelectedIndex
    }));
    setDraggingIndex(null);
  };

  // --- Interaction Logic (Crop/Swipe/Pick) ---

  const [dragStart, setDragStart] = useState<{ x: number, y: number } | null>(null);

  const getGameCoordinates = (e: React.MouseEvent) => {
    if (!canvasRef.current) return { x: 0, y: 0 };
    const rect = canvasRef.current.getBoundingClientRect();
    const scaleX = GAME_WIDTH / rect.width;
    const scaleY = GAME_HEIGHT / rect.height;
    return {
      x: Math.round((e.clientX - rect.left) * scaleX),
      y: Math.round((e.clientY - rect.top) * scaleY)
    };
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    const coords = getGameCoordinates(e);

    if (state.interactionMode === 'pick' && state.captureTarget) {
      applyCaptureResult([coords.x, coords.y]);
      return;
    }

    if (state.interactionMode === 'rect' || state.interactionMode === 'swipe') {
      setDragStart(coords);
    }
  };

  const handleMouseUp = async (e: React.MouseEvent) => {
    if (!dragStart) return;
    const coords = getGameCoordinates(e);

    if (state.interactionMode === 'swipe') {
      const cmd = `input swipe ${dragStart.x} ${dragStart.y} ${coords.x} ${coords.y}`;
      setState(s => ({ ...s, logs: [...s.logs, `Captured: ${cmd}`] }));

      if (state.captureTarget?.field === 'fallback_value') {
        applyCaptureResult(cmd);
      }

    } else if (state.interactionMode === 'rect') {
      const width = Math.abs(coords.x - dragStart.x);
      const height = Math.abs(coords.y - dragStart.y);
      const x = Math.min(coords.x, dragStart.x);
      const y = Math.min(coords.y, dragStart.y);

      if (width > 0 && height > 0) {
        if (state.captureTarget?.field === 'roi') {
          // Save ROI [x1, y1, x2, y2]
          const roi = [x, y, x + width, y + height];
          applyCaptureResult(roi);
          setState(s => ({ ...s, logs: [...s.logs, `ROI Captured: ${roi.join(',')}`] }));
        } else {
          await handleImageCrop(x, y, width, height);
        }
      }
    }
    setDragStart(null);
  };

  const handleImageCrop = async (x: number, y: number, w: number, h: number) => {
    if (!imageSrc) return;

    const tempCanvas = document.createElement('canvas');
    tempCanvas.width = w;
    tempCanvas.height = h;
    const ctx = tempCanvas.getContext('2d');

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.src = imageSrc;

    await new Promise((resolve) => { img.onload = resolve; });

    if (ctx) {
      ctx.drawImage(img, x, y, w, h, 0, 0, w, h);

      // --- 智能決定預設檔名 ---
      let defaultName = "";

      // 嘗試獲取當前欄位的既有值作為預設檔名
      if (state.captureTarget && state.captureTarget.index !== null) {
        const list = currentScript ? (state.activeTab === 'village' ? currentScript._EOT : currentScript._TARGETINFOLIST) : [];
        if (list && list[state.captureTarget.index]) {
          const item = list[state.captureTarget.index];
          const field = state.captureTarget.field;

          // 根據不同類型獲取字串值
          if (field === 'target_pattern' && typeof item[1] === 'string') {
            defaultName = item[1];
          } else if (field === 'fallback_value' && item[2]) {
            const fb = item[2];
            const subIndex = state.captureTarget.subIndex;
            if (subIndex !== undefined && Array.isArray(fb)) {
              if (typeof fb[subIndex] === 'string' && !String(fb[subIndex]).startsWith("input ")) { // Ensure it's not a swipe command
                defaultName = fb[subIndex];
              }
            } else if (typeof fb === 'string') {
              defaultName = fb;
            }
          } else if ((field === 'target_pattern' || field === 'image') && typeof item[3] === 'string') {
            // harken / minimap_stair
            defaultName = item[3];
          }
        }
      }

      // 如果沒有既有值，使用短時間戳
      if (!defaultName) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '').slice(11, 17); // HHMMSS
        defaultName = `img_${timestamp}`;
      }

      // 1. 讓用戶確認檔名 (預設值就是格子裡的名字)
      let filename = prompt("Save Image As:", defaultName);
      if (!filename) return; // Cancelled

      // 2. 自動補 .png
      if (!filename.toLowerCase().endsWith('.png')) {
        filename += ".png";
      }

      // 3. 獲取圖片的 base64 資料
      const dataUrl = tempCanvas.toDataURL('image/png');
      const base64Data = dataUrl.split(',')[1];

      // 4. 自動填回前端欄位 (去掉 .png，因為通常習慣不寫副檔名)
      const displayVal = filename.replace(/\.png$/i, '');
      applyCaptureResult(displayVal);

      // 5. 發送到伺服器存檔
      if (wsRef.current && state.isConnected) {
        const saveMsg = JSON.stringify({
          cmd: "save_image",
          filename: filename,
          data: base64Data
        });
        sendWS(saveMsg);
      } else {
        // Fallback
        const link = document.createElement('a');
        link.download = filename;
        link.href = dataUrl;
        link.click();
        setState(s => ({ ...s, logs: [...s.logs, `⚠ Downloaded locally: ${filename}`] }));
      }
    }
  };

  const applyCaptureResult = (result: any) => {
    if (!currentScript) return;
    const { index, field, subIndex } = state.captureTarget!;
    const listKey = state.activeTab === 'dungeon' ? '_TARGETINFOLIST' : '_EOT';
    const items = [...currentScript[listKey]];
    const item = [...items[index]];

    if (field === 'coord') {
      if (['position', 'stair', 'minimap_stair'].includes(identifyType(item))) {
        item[2] = result;
      }
    } else if (field === 'coord_simple') {
      if (isCoordinate(result)) {
        item[0] = `input tap ${result[0]} ${result[1]}`;
      }
    } else if (field === 'roi') {
      if (item[0] === 'harken') {
        item[2] = [result];
      } else if (item[0] === 'chest') {
        const rawRoi = item[2];
        let roiList: number[][] = [];
        if (rawRoi && Array.isArray(rawRoi) && rawRoi.length > 0) {
          if (typeof rawRoi[0] === 'number') {
            roiList = [rawRoi];
          } else {
            roiList = [...rawRoi];
          }
        }
        roiList.push(result);
        item[2] = roiList;
      }
    } else if (field === 'target_pattern') {
      if (item[0] === 'press') item[1] = result;
      if (item[0] === 'minimap_stair' || item[0] === 'harken') item[3] = result;
    } else if (field === 'coord_fallback') {
      let fallback = item[2];
      if (subIndex !== undefined && isCoordinate(result)) {
        if (!Array.isArray(fallback) || isCoordinate(fallback)) {
          fallback = [fallback];
        }
        fallback = [...fallback];
        fallback[subIndex] = `input tap ${result[0]} ${result[1]}`;
        item[2] = fallback;
      }
    } else if (field === 'fallback_value' && item[0] === 'press') {
      let fallback = item[2];
      if (subIndex !== undefined) {
        if (!Array.isArray(fallback) || isCoordinate(fallback)) {
          fallback = [fallback];
        }
        fallback = [...fallback];
        fallback[subIndex] = result;
        item[2] = fallback;
      } else if (state.interactionMode === 'swipe') {
        // Direct swipe record for simple (handled by startRecordSwipe calling with fallback_value field)
        item[0] = result;
      }
    }

    items[index] = item;
    updateCurrentQuest({ [listKey]: items });

    setState(s => ({
      ...s,
      interactionMode: 'none',
      captureTarget: null
    }));
  };

  // --- Start Capture Modes ---

  const startPickCoord = (index: number, subIndex?: number, field: any = 'coord') => {
    setState(s => ({
      ...s,
      interactionMode: 'pick',
      captureTarget: { index, field, subIndex },
      logs: [...s.logs, "Pick a point on screen..."]
    }));
  };

  const startCropImage = (index: number, subIndex?: number, field: any = 'target_pattern') => {
    setState(s => ({
      ...s,
      interactionMode: 'rect',
      captureTarget: { index, field, subIndex },
      logs: [...s.logs, "Draw a box to crop image..."]
    }));
  };

  const startDrawRoi = (index: number) => {
    setState(s => ({
      ...s,
      interactionMode: 'rect',
      captureTarget: { index, field: 'roi' },
      logs: [...s.logs, "Draw ROI Area..."]
    }));
  };

  const startRecordSwipe = (index: number, subIndex?: number) => {
    setState(s => ({
      ...s,
      interactionMode: 'swipe',
      captureTarget: { index, field: 'fallback_value', subIndex },
      logs: [...s.logs, "Swipe on screen to record command..."]
    }));
  };

  // --- UI Render ---

  // Drawing the interaction overlay (box or line)
  useEffect(() => {
    const ctx = canvasRef.current?.getContext('2d');
    if (!ctx || !canvasRef.current) return;
    ctx.clearRect(0, 0, canvasRef.current.width, canvasRef.current.height);
  }, [dragStart, state.interactionMode]);

  const mousePos = useRef<{ x: number, y: number } | null>(null);

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!dragStart) return;
    const coords = getGameCoordinates(e);
    mousePos.current = coords;

    const ctx = canvasRef.current?.getContext('2d');
    if (ctx) {
      ctx.clearRect(0, 0, GAME_WIDTH, GAME_HEIGHT);
      ctx.strokeStyle = '#00ff00';
      ctx.lineWidth = 4;

      if (state.interactionMode === 'rect') {
        const w = coords.x - dragStart.x;
        const h = coords.y - dragStart.y;
        ctx.strokeRect(dragStart.x, dragStart.y, w, h);
        ctx.fillStyle = 'rgba(0, 255, 0, 0.2)';
        ctx.fillRect(dragStart.x, dragStart.y, w, h);
      } else if (state.interactionMode === 'swipe') {
        ctx.beginPath();
        ctx.moveTo(dragStart.x, dragStart.y);
        ctx.lineTo(coords.x, coords.y);
        ctx.stroke();
        ctx.fillStyle = '#00ff00';
        ctx.fillRect(coords.x - 5, coords.y - 5, 10, 10);
      }
    }
  };

  const renderSwipeSelect = (value: string, onChange: (val: string) => void) => (
    <div className="relative">
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 focus:border-blue-500 outline-none"
        placeholder="e.g. 右下"
      />
      <div className="flex gap-1 mt-1 flex-wrap">
        {['右上', '右下', '左上', '左下'].map(dir => (
          <button key={dir} onClick={() => onChange(dir)} className="px-2 py-0.5 bg-gray-800 text-[10px] rounded hover:bg-gray-700 border border-gray-600">
            {dir}
          </button>
        ))}
      </div>
    </div>
  );

  const renderEditorForm = (item: any[], index: number) => {
    const type = identifyType(item);
    const inputClass = "flex-1 bg-gray-950 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 focus:border-blue-500 outline-none";
    const labelClass = "text-[10px] uppercase text-gray-500 font-bold mb-1 block";
    const btnClass = "p-1.5 bg-gray-800 border border-gray-600 rounded hover:bg-blue-600 hover:text-white text-gray-400 transition-colors";

    // 1. Position: ["position", "swipe", [x,y]]
    if (type === 'position') {
      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div>
            <label className={labelClass}>Swipe Direction</label>
            {renderSwipeSelect(item[1], (val) => { const n = [...item]; n[1] = val; updateScriptItem(index, n); })}
          </div>
          <div>
            <label className={labelClass}>Target Coordinates [X, Y]</label>
            <div className="flex gap-2">
              <input type="number" onClick={(e) => e.stopPropagation()} value={item[2][0]} onChange={e => { const n = [...item]; n[2] = [parseInt(e.target.value) || 0, n[2][1]]; updateScriptItem(index, n); }} className={inputClass} />
              <input type="number" onClick={(e) => e.stopPropagation()} value={item[2][1]} onChange={e => { const n = [...item]; n[2] = [n[2][0], parseInt(e.target.value) || 0]; updateScriptItem(index, n); }} className={inputClass} />
              <button
                onClick={(e) => { e.stopPropagation(); startPickCoord(index); }}
                className={`${btnClass} ${state.captureTarget?.index === index ? 'bg-blue-600 text-white animate-pulse' : ''}`}
                title="Pick from Screen"
              >
                <Crosshair className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      );
    }

    // 1.1 Chest: ["chest", "swipe", [[x1,y1,x2,y2], [x1,y1,x2,y2], ...]] - Multi-ROI support
    if (type === 'chest') {
      // Normalize ROI data: ensure it's always an array of ROIs
      const rawRoi = item[2];
      let roiList: number[][] = [];
      if (rawRoi === null || rawRoi === undefined) {
        roiList = [];
      } else if (Array.isArray(rawRoi) && rawRoi.length > 0) {
        // Check if it's a single ROI [x1,y1,x2,y2] or multi-ROI [[...], [...]]
        if (typeof rawRoi[0] === 'number') {
          // Single ROI format: [x1, y1, x2, y2]
          roiList = [rawRoi];
        } else {
          // Multi-ROI format: [[x1,y1,x2,y2], ...]
          roiList = rawRoi;
        }
      }

      const updateRoiList = (newList: number[][]) => {
        const n = [...item];
        // If only one ROI, keep as single array for compatibility
        n[2] = newList.length === 0 ? null : (newList.length === 1 ? newList : newList);
        updateScriptItem(index, n);
      };

      const deleteRoi = (roiIndex: number) => {
        const newList = roiList.filter((_, i) => i !== roiIndex);
        updateRoiList(newList);
      };

      const addRoi = (roi: number[]) => {
        updateRoiList([...roiList, roi]);
      };

      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div>
            <label className={labelClass}>Swipe Direction</label>
            {renderSwipeSelect(item[1], (val) => { const n = [...item]; n[1] = val; updateScriptItem(index, n); })}
          </div>
          <div>
            <label className={labelClass}>Search ROI List ({roiList.length} regions)</label>
            <div className="space-y-1">
              {roiList.length === 0 && (
                <div className="text-xs text-gray-500 italic">No ROI defined (full screen)</div>
              )}
              {roiList.map((roi, roiIndex) => (
                <div key={roiIndex} className="flex gap-2 items-center p-1 bg-gray-900 rounded border border-gray-700">
                  <span className="text-[10px] text-gray-500 w-6">#{roiIndex + 1}</span>
                  <input
                    className={inputClass}
                    value={roi ? roi.join(', ') : ''}
                    placeholder="x1, y1, x2, y2"
                    disabled
                  />
                  <button
                    onClick={() => deleteRoi(roiIndex)}
                    className="text-red-400 hover:text-red-300 p-1"
                    title="Delete ROI"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); startDrawRoi(index); }}
              className="mt-2 w-full py-1 text-[10px] bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded text-gray-400 flex items-center justify-center gap-1"
            >
              <Scan className="w-3 h-3" /> Draw New ROI
            </button>
          </div>
        </div>
      );
    }

    // 2. Chest Auto: ["chest_auto"]
    if (type === 'chest_auto') {
      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div className="text-xs text-gray-500 italic">
            Auto-detect and click chests. No parameters needed.
          </div>
        </div>
      )
    }

    // 3. Stair: ["stair_ID", "swipe", [x,y]]
    if (type === 'stair') {
      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div>
            <label className={labelClass}>Stair ID (Command)</label>
            <input
              value={item[0]}
              onChange={e => { const n = [...item]; n[0] = e.target.value; updateScriptItem(index, n); }}
              className={inputClass}
            />
          </div>
          <div>
            <label className={labelClass}>Swipe Direction</label>
            {renderSwipeSelect(item[1], (val) => { const n = [...item]; n[1] = val; updateScriptItem(index, n); })}
          </div>
          <div>
            <label className={labelClass}>Target Coordinates [X, Y]</label>
            <div className="flex gap-2">
              <input type="number" onClick={(e) => e.stopPropagation()} value={item[2][0]} onChange={e => { const n = [...item]; n[2] = [parseInt(e.target.value) || 0, n[2][1]]; updateScriptItem(index, n); }} className={inputClass} />
              <input type="number" onClick={(e) => e.stopPropagation()} value={item[2][1]} onChange={e => { const n = [...item]; n[2] = [n[2][0], parseInt(e.target.value) || 0]; updateScriptItem(index, n); }} className={inputClass} />
              <button onClick={(e) => { e.stopPropagation(); startPickCoord(index); }} className={btnClass} title="Pick"><Crosshair className="w-4 h-4" /></button>
            </div>
          </div>
        </div>
      );
    }

    // 4. Minimap Stair: ["minimap_stair", "swipe", [x,y], "image"]
    if (type === 'minimap_stair') {
      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div>
            <label className={labelClass}>Swipe Direction</label>
            {renderSwipeSelect(item[1], (val) => { const n = [...item]; n[1] = val; updateScriptItem(index, n); })}
          </div>
          <div>
            <label className={labelClass}>Click Coordinates [X, Y]</label>
            <div className="flex gap-2">
              <input type="number" onClick={(e) => e.stopPropagation()} value={item[2][0]} onChange={e => { const n = [...item]; n[2] = [parseInt(e.target.value) || 0, n[2][1]]; updateScriptItem(index, n); }} className={inputClass} />
              <input type="number" onClick={(e) => e.stopPropagation()} value={item[2][1]} onChange={e => { const n = [...item]; n[2] = [n[2][0], parseInt(e.target.value) || 0]; updateScriptItem(index, n); }} className={inputClass} />
              <button onClick={(e) => { e.stopPropagation(); startPickCoord(index); }} className={btnClass} title="Pick"><Crosshair className="w-4 h-4" /></button>
            </div>
          </div>
          <div>
            <label className={labelClass}>Target Floor Image</label>
            <div className="flex gap-2">
              <input
                value={item[3] || ''}
                onChange={e => { const n = [...item]; n[3] = e.target.value; updateScriptItem(index, n); }}
                className={inputClass}
                placeholder="DH-R5-minimap"
                onDoubleClick={(e) => { e.stopPropagation(); startCropImage(index, undefined, 'target_pattern'); }}
                title="Double click to Crop"
              />
              <button onClick={(e) => { e.stopPropagation(); startCropImage(index, undefined, 'target_pattern'); }} className={btnClass} title="Crop Image"><Crop className="w-4 h-4" /></button>
              <button onClick={(e) => {
                e.stopPropagation();
                const filename = typeof item[3] === 'string' ? item[3] : '';
                if (filename) {
                  const msg = JSON.stringify({ cmd: "click_image", filename });
                  sendWS(msg);
                  setState(s => ({ ...s, logs: [...s.logs, `🔍 Testing image: ${filename}`] }));
                }
              }} className={btnClass} title="Test Match & Click">
                <Play className="w-4 h-4 text-green-400" />
              </button>
            </div>
          </div>
        </div>
      );
    }

    // 5. Harken: ["harken", "swipe", [[x1,y1,x2,y2]], "image"]
    if (type === 'harken') {
      const roi = (item[2] && item[2][0]) ? item[2][0] : null;
      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div>
            <label className={labelClass}>Swipe Direction</label>
            {renderSwipeSelect(item[1], (val) => { const n = [...item]; n[1] = val; updateScriptItem(index, n); })}
          </div>
          <div>
            <label className={labelClass}>Search ROI [x1, y1, x2, y2]</label>
            <div className="flex gap-2 items-center">
              <input
                className={inputClass}
                value={roi ? roi.join(', ') : ''}
                placeholder="Null (Full Screen / Default)"
                disabled
              />
              <button onClick={(e) => { e.stopPropagation(); startDrawRoi(index); }} className={btnClass} title="Draw ROI"><Scan className="w-4 h-4" /></button>
            </div>
          </div>
          <div>
            <label className={labelClass}>Target Floor Image</label>
            <div className="flex gap-2">
              <input
                value={item[3] || ''}
                onChange={e => { const n = [...item]; n[3] = e.target.value; updateScriptItem(index, n); }}
                className={inputClass}
                placeholder="e.g. DH-R5-harken"
                onDoubleClick={(e) => { e.stopPropagation(); startCropImage(index, undefined, 'target_pattern'); }}
                title="Double click to Crop"
              />
              <button onClick={(e) => { e.stopPropagation(); startCropImage(index, undefined, 'target_pattern'); }} className={btnClass} title="Crop Image"><Crop className="w-4 h-4" /></button>
              <button onClick={(e) => {
                e.stopPropagation();
                const filename = typeof item[3] === 'string' ? item[3] : '';
                if (filename) {
                  const msg = JSON.stringify({ cmd: "click_image", filename });
                  sendWS(msg);
                  setState(s => ({ ...s, logs: [...s.logs, `🔍 Testing image: ${filename}`] }));
                }
              }} className={btnClass} title="Test Match & Click">
                <Play className="w-4 h-4 text-green-400" />
              </button>
            </div>
          </div>
        </div>
      );
    }

    // 6. Press (Village)
    if (type === 'press') {
      const fallback = item[2];
      const fallbackList = (Array.isArray(fallback) && !isCoordinate(fallback)) ? fallback : [fallback];

      const updateFallbackList = (newList: any[]) => {
        let finalVal = newList;
        if (newList.length === 1 && !isCoordinate(newList[0])) {
          finalVal = newList[0];
        }
        const n = [...item];
        n[2] = finalVal;
        updateScriptItem(index, n);
      };

      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div>
            <label className={labelClass}>Target Pattern (Image)</label>
            <div className="flex gap-2">
              <input
                onClick={(e) => e.stopPropagation()}
                value={item[1]}
                onChange={e => { const n = [...item]; n[1] = e.target.value; updateScriptItem(index, n); }}
                className={inputClass}
                placeholder="e.g. DH or EdgeOfTown"
                onDoubleClick={(e) => { e.stopPropagation(); startCropImage(index, undefined, 'target_pattern'); }}
                title="Double click to Crop"
              />
              <button
                onClick={(e) => { e.stopPropagation(); startCropImage(index, undefined, 'target_pattern'); }}
                className={`${btnClass} ${state.captureTarget?.index === index && state.captureTarget?.field === 'target_pattern' ? 'bg-blue-600 text-white animate-pulse' : ''}`}
                title="Crop from Screen"
              >
                <Crop className="w-4 h-4" />
              </button>
              <button onClick={(e) => {
                e.stopPropagation();
                const filename = typeof item[1] === 'string' ? item[1] : '';
                if (filename) {
                  const msg = JSON.stringify({ cmd: "click_image", filename });
                  sendWS(msg);
                  setState(s => ({ ...s, logs: [...s.logs, `🔍 Testing image: ${filename}`] }));
                }
              }} className={btnClass} title="Test Match & Click">
                <Play className="w-4 h-4 text-green-400" />
              </button>
            </div>
          </div>

          <div>
            <label className={labelClass}>Fallback Actions</label>
            <div className="space-y-2">
              {fallbackList.map((fbItem: any, fbIndex: number) => {
                const isCoord = isCoordinate(fbItem);
                const isCommand = typeof fbItem === 'string' && fbItem.startsWith('input ');
                const isImage = typeof fbItem === 'string' && !isCommand;

                return (
                  <div key={fbIndex} className="flex items-center gap-2 p-1.5 bg-gray-900 rounded border border-gray-700">
                    <div className="text-[10px] font-bold text-gray-500 w-8 shrink-0 text-center">
                      {isCoord && "XY"}
                      {isCommand && "CMD"}
                      {isImage && "IMG"}
                    </div>

                    <div className="flex-1 min-w-0 flex items-center gap-2">
                      {isCoord ? (
                        <div className="flex gap-1">
                          <input type="number" className={inputClass} value={fbItem[0]}
                            onChange={e => {
                              const newList = [...fallbackList];
                              newList[fbIndex] = [parseInt(e.target.value) || 0, fbItem[1]];
                              updateFallbackList(newList);
                            }}
                            onDoubleClick={(e) => { e.stopPropagation(); startPickCoord(index, fbIndex, 'fallback_value'); }}
                            title="Double click to Pick Coords"
                          />
                          <input type="number" className={inputClass} value={fbItem[1]}
                            onChange={e => {
                              const newList = [...fallbackList];
                              newList[fbIndex] = [fbItem[0], parseInt(e.target.value) || 0];
                              updateFallbackList(newList);
                            }}
                            onDoubleClick={(e) => { e.stopPropagation(); startPickCoord(index, fbIndex, 'fallback_value'); }}
                            title="Double click to Pick Coords"
                          />
                        </div>
                      ) : (
                        <input
                          className={inputClass}
                          value={fbItem}
                          onChange={e => {
                            const newList = [...fallbackList];
                            newList[fbIndex] = e.target.value;
                            updateFallbackList(newList);
                          }}
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            if (isCommand) startRecordSwipe(index, fbIndex);
                            else if (isImage) startCropImage(index, fbIndex, 'fallback_value');
                          }}
                          title={isCommand ? "Double click to Record Swipe" : (isImage ? "Double click to Crop Image" : "")}
                        />
                      )}

                      {isCoord && (
                        <>
                          <button onClick={(e) => { e.stopPropagation(); startPickCoord(index, fbIndex, 'fallback_value'); }} className={btnClass} title="Pick Coord"><Crosshair className="w-3 h-3" /></button>
                          <button onClick={(e) => {
                            e.stopPropagation();
                            const cmd = `input tap ${fbItem[0]} ${fbItem[1]}`;
                            sendWS(cmd);
                          }} className={btnClass} title="Test Tap">
                            <Play className="w-3 h-3 text-green-400" />
                          </button>
                        </>
                      )}
                      {isImage && (
                        <>
                          <button onClick={(e) => { e.stopPropagation(); startCropImage(index, fbIndex, 'fallback_value'); }} className={btnClass} title="Crop Image"><Crop className="w-3 h-3" /></button>
                          <button onClick={(e) => {
                            e.stopPropagation();
                            const filename = typeof fbItem === 'string' ? fbItem : '';
                            if (filename) {
                              const msg = JSON.stringify({ cmd: "click_image", filename });
                              sendWS(msg);
                              setState(s => ({ ...s, logs: [...s.logs, `🔍 Testing image: ${filename}`] }));
                            }
                          }} className={btnClass} title="Test Match & Click">
                            <Play className="w-3 h-3 text-green-400" />
                          </button>
                        </>
                      )}
                      {isCommand && (
                        <>
                          <button
                            onClick={(e) => { e.stopPropagation(); startPickCoord(index, fbIndex, 'coord_fallback'); }}
                            className={`${btnClass} ${state.captureTarget?.index === index && state.captureTarget?.subIndex === fbIndex && state.captureTarget?.field === 'coord_fallback' ? 'bg-blue-600 text-white animate-pulse' : ''}`}
                            title="Pick Coordinate for Tap"
                          >
                            <Crosshair className="w-3 h-3" />
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); startRecordSwipe(index, fbIndex); }} className={btnClass} title="Record Swipe"><Move className="w-3 h-3" /></button>
                          <button onClick={(e) => {
                            e.stopPropagation();
                            if (typeof fbItem === 'string') sendWS(fbItem);
                          }} className={btnClass} title="Test Command">
                            <Play className="w-3 h-3 text-green-400" />
                          </button>
                        </>
                      )}

                      <button onClick={() => {
                        const newList = fallbackList.filter((_: any, i: number) => i !== fbIndex);
                        updateFallbackList(newList);
                      }} className="text-red-400 hover:text-red-300 p-1"><X className="w-3 h-3" /></button>
                    </div>
                  </div>
                );
              })}

              <div className="flex gap-2 mt-2">
                <button onClick={() => updateFallbackList([...fallbackList, "NewImage"])} className="flex-1 py-1 text-[10px] bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded text-gray-400">+ Image</button>
                <button onClick={() => updateFallbackList([...fallbackList, "input swipe 0 0 0 0"])} className="flex-1 py-1 text-[10px] bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded text-gray-400">+ Cmd</button>
                <button onClick={() => updateFallbackList([...fallbackList, [0, 0]])} className="flex-1 py-1 text-[10px] bg-gray-800 hover:bg-gray-700 border border-gray-600 rounded text-gray-400">+ Coord</button>
              </div>
            </div>
          </div>

          <div>
            <label className={labelClass}>Delay (Sec)</label>
            <input type="number" onClick={(e) => e.stopPropagation()} value={item[3]} onChange={e => { const n = [...item]; n[3] = parseFloat(e.target.value) || 0; updateScriptItem(index, n); }} className={inputClass} />
          </div>
        </div>
      );
    }

    if (type === 'simple') {
      const isSwipe = typeof item[0] === 'string' && item[0].startsWith('input swipe ');
      return (
        <div className="space-y-3 p-2 bg-black/20 rounded">
          <div>
            <label className={labelClass}>Raw Command</label>
            <div className="flex gap-2">
              <input
                onClick={(e) => e.stopPropagation()}
                value={item[0] || ''}
                onChange={e => { const n = [...item]; n[0] = e.target.value; updateScriptItem(index, n); }}
                className={inputClass}
                placeholder="e.g. input tap 500 500"
              />
              <button
                onClick={(e) => { e.stopPropagation(); startPickCoord(index, undefined, 'coord_simple'); }}
                className={`${btnClass} ${state.captureTarget?.index === index && state.captureTarget?.field === 'coord_simple' ? 'bg-blue-600 text-white animate-pulse' : ''}`}
                title="Pick Coordinate"
              >
                <Crosshair className="w-4 h-4" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); startRecordSwipe(index); }}
                className={`${btnClass} ${state.captureTarget?.index === index && state.interactionMode === 'swipe' ? 'bg-blue-600 text-white animate-pulse' : ''}`}
                title="Record Swipe"
              >
                <Move className="w-4 h-4" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); sendWS(item[0]); }}
                className={btnClass}
                title="Test Action"
              >
                <Play className="w-4 h-4 text-green-400" />
              </button>
            </div>
          </div>
        </div>
      );
    }

    return null;
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const json = JSON.parse(event.target?.result as string);
          if (Array.isArray(json)) {
            // Legacy support: Convert array to object
            const map: QuestsMap = {};
            json.forEach((q, i) => { map[`quest_${i}`] = { _TYPE: "dungeon", ...q }; });
            setState(s => ({ ...s, quests: map, currentQuestId: Object.keys(map)[0] || null, logs: [...s.logs, `Imported ${json.length} legacy quests.`] }));
          } else {
            // Valid dictionary import
            const keys = Object.keys(json);
            setState(s => ({ ...s, quests: json, currentQuestId: keys[0] || null, logs: [...s.logs, `Imported ${keys.length} quests.`] }));
          }
        } catch (err) {
          alert('Invalid JSON');
        }
      };
      reader.readAsText(file);
    }
  };

  const handleDownload = () => {
    if (wsRef.current && state.isConnected) {
      const msg = JSON.stringify({ cmd: "save_quest", data: state.quests });
      if (sendWS(msg)) {
        setState(s => ({ ...s, logs: [...s.logs, "💾 Sent quest data to server..."] }));
        return;
      }
    }

    // Fallback to browser download if not connected
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(state.quests, null, 4));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    downloadAnchorNode.setAttribute("download", "quest.json");
    document.body.appendChild(downloadAnchorNode);
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
    setState(s => ({ ...s, logs: [...s.logs, "💾 Downloaded quest.json locally"] }));
  };

  return (
    <div className="flex h-screen w-full bg-gray-900 text-gray-200 overflow-hidden font-sans">

      {/* --- Modal Overlay --- */}
      {questModal.isOpen && (
        <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-lg shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="bg-gray-900 border-b border-gray-700 px-4 py-3 flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-wider text-gray-200">
                {questModal.mode === 'create' && 'New Quest'}
                {questModal.mode === 'edit' && 'Edit Quest'}
                {questModal.mode === 'delete' && 'Delete Quest'}
              </h3>
              <button onClick={closeModal} className="text-gray-500 hover:text-white"><X className="w-5 h-5" /></button>
            </div>

            <div className="p-6 space-y-4">
              {questModal.mode === 'delete' ? (
                <div className="text-center space-y-2">
                  <div className="w-12 h-12 bg-red-900/30 rounded-full flex items-center justify-center mx-auto text-red-500 mb-2">
                    <Trash2 className="w-6 h-6" />
                  </div>
                  <h4 className="text-lg font-bold text-white">Confirm Deletion</h4>
                  <p className="text-sm text-gray-400">
                    Are you sure you want to delete <span className="text-white font-mono bg-gray-700 px-1 rounded">{questModal.questId}</span>?
                    This action cannot be undone.
                  </p>
                </div>
              ) : (
                <>
                  <div>
                    <label className="block text-xs uppercase font-bold text-gray-500 mb-1">Quest ID (Unique Key)</label>
                    <input
                      value={questModal.questId}
                      onChange={e => setQuestModal({ ...questModal, questId: e.target.value })}
                      className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none font-mono"
                      placeholder="unique_id_no_spaces"
                    />
                    <p className="text-[10px] text-gray-600 mt-1">Used as the JSON key. Must be unique.</p>
                  </div>
                  <div>
                    <label className="block text-xs uppercase font-bold text-gray-500 mb-1">Display Name</label>
                    <input
                      value={questModal.questName}
                      onChange={e => setQuestModal({ ...questModal, questName: e.target.value })}
                      className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                      placeholder="My Awesome Quest"
                    />
                  </div>
                  <div>
                    <label className="block text-xs uppercase font-bold text-gray-500 mb-1">Quest Type</label>
                    <input
                      value={questModal.questType}
                      onChange={e => setQuestModal({ ...questModal, questType: e.target.value })}
                      className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-white focus:border-blue-500 outline-none"
                      placeholder="dungeon"
                    />
                  </div>
                </>
              )}
            </div>

            <div className="bg-gray-900 border-t border-gray-700 px-4 py-3 flex justify-end gap-2">
              <button onClick={closeModal} className="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
              <button
                onClick={handleSaveModal}
                className={`px-4 py-2 text-sm font-bold text-white rounded shadow-lg transition-transform active:scale-95 flex items-center gap-2
                            ${questModal.mode === 'delete' ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'}
                        `}
              >
                {questModal.mode === 'delete' ? (
                  <>
                    <Trash2 className="w-4 h-4" /> Delete
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4" /> Save
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Left Panel: Emulator */}
      <div className="flex-1 flex flex-col border-r border-gray-800">
        <div className="h-14 bg-gray-800 border-b border-gray-700 flex items-center px-4 justify-between shrink-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-white tracking-wider flex items-center gap-2">
              <Monitor className="w-5 h-5 text-blue-400" />
              SIMULATOR
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={state.wsUrl}
              onChange={e => setState(s => ({ ...s, wsUrl: e.target.value }))}
              className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm w-48 focus:border-blue-500 outline-none"
            />
            <button
              onClick={connectWS}
              className={`p-2 rounded ${state.isConnected ? 'bg-green-600 hover:bg-green-700' : 'bg-red-600 hover:bg-red-700'}`}
              title={state.isConnected ? "Disconnect" : "Connect"}
            >
              {state.isConnected ? <Wifi className="w-4 h-4" /> : <WifiOff className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* Viewport Area */}
        <div
          ref={containerRef}
          className="flex-1 bg-black relative flex items-center justify-center overflow-hidden p-4"
        >
          <div className="relative shadow-2xl ring-1 ring-gray-800" style={{
            aspectRatio: `${GAME_WIDTH}/${GAME_HEIGHT}`,
            height: '100%',
            maxHeight: '100%',
            maxWidth: '100%'
          }}>
            {imageSrc ? (
              <img src={imageSrc} className="w-full h-full object-contain pointer-events-none select-none" alt="Stream" />
            ) : (
              <div className="w-full h-full bg-gray-900 flex flex-col items-center justify-center text-gray-600">
                <Monitor className="w-16 h-16 mb-4 opacity-20" />
                <p>No Signal</p>
                <p className="text-xs mt-2">Connect WebSocket</p>
              </div>
            )}

            {/* Interaction Layer */}
            <canvas
              ref={canvasRef}
              width={GAME_WIDTH}
              height={GAME_HEIGHT}
              className={`absolute inset-0 w-full h-full ${state.interactionMode !== 'none' ? 'cursor-crosshair' : ''}`}
              onMouseDown={handleMouseDown}
              onMouseUp={handleMouseUp}
              onMouseMove={handleMouseMove}
            />

            {/* Mode Indicator */}
            {state.interactionMode !== 'none' && (
              <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-blue-600/90 backdrop-blur text-white px-6 py-2 rounded-full shadow-lg text-sm font-bold animate-pulse pointer-events-none z-10 border border-blue-400">
                {state.interactionMode === 'rect' && (state.captureTarget?.field === 'roi' ? "DRAW ROI AREA" : "DRAG TO CROP IMAGE")}
                {state.interactionMode === 'swipe' && "SWIPE TO RECORD COMMAND"}
                {state.interactionMode === 'pick' && "CLICK TO PICK COORDINATE"}
              </div>
            )}
          </div>
        </div>

        {/* Toolbar */}
        <div className="h-12 bg-gray-800 border-t border-gray-700 flex items-center px-4 gap-2 shrink-0">
          <span className="text-xs text-gray-500 mr-2">ADB:</span>
          <input
            type="text"
            placeholder="input tap 450 800"
            className="bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm flex-1 max-w-xs focus:border-blue-500 outline-none"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const input = e.currentTarget;
                const cmd = input.value.trim();
                if (cmd) {
                  sendWS(cmd);
                  input.value = '';
                }
              }
            }}
          />
          <button
            className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded"
            onClick={() => {
              const input = document.querySelector('input[placeholder="input tap 450 800"]') as HTMLInputElement;
              const cmd = input?.value.trim();
              if (cmd) {
                sendWS(cmd);
                if (input) input.value = '';
              }
            }}
          >
            Send
          </button>
          <div className="flex-1" />
          <span className="text-xs text-gray-500">{GAME_WIDTH}x{GAME_HEIGHT}</span>
        </div>
      </div>

      {/* Right Panel: Script Editor */}
      <div className="w-[450px] flex flex-col bg-gray-900 border-l border-gray-800">

        {/* Header with Quest Selection and Controls */}
        <div className="bg-gray-800 border-b border-gray-700 p-3 space-y-3 shrink-0">

          {/* Quest Selector Row */}
          <div className="flex items-end gap-2">
            <div className="flex-1 flex flex-col gap-1 min-w-0">
              <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wide">Select Quest</span>
              <div className="relative">
                <select
                  value={state.currentQuestId || ''}
                  onChange={(e) => setState(s => ({ ...s, currentQuestId: e.target.value, selectedItemIndex: null, interactionMode: 'none', captureTarget: null }))}
                  className="w-full appearance-none bg-gray-900 border border-gray-700 text-gray-200 text-sm rounded py-2 pl-3 pr-8 focus:outline-none focus:border-blue-500 font-medium"
                >
                  {Object.entries(state.quests).map(([id, quest]) => (
                    <option key={id} value={id}>
                      {(quest as ScriptData).questName || id} ({id})
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
              </div>
            </div>

            {/* Quest Management Buttons */}
            <div className="flex gap-1 h-9">
              <button
                onClick={openCreateModal}
                className="bg-gray-700 hover:bg-gray-600 border border-gray-600 text-green-400 hover:text-green-300 rounded px-2 flex items-center justify-center transition-colors cursor-pointer"
                title="Add New Quest"
              >
                <FilePlus className="w-4 h-4" />
              </button>
              <button
                onClick={openEditModal}
                className="bg-gray-700 hover:bg-gray-600 border border-gray-600 text-blue-400 hover:text-blue-300 rounded px-2 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                title="Edit Quest Metadata"
                disabled={!state.currentQuestId}
              >
                <Edit className="w-4 h-4" />
              </button>
              <button
                onClick={openDeleteModal}
                className="bg-gray-700 hover:bg-gray-600 border border-gray-600 text-red-400 hover:text-red-300 rounded px-2 flex items-center justify-center transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                title="Delete Current Quest"
                disabled={!state.currentQuestId}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* File Actions Row */}
          <div className="flex items-center justify-between">
            <div className="flex gap-1">
              <button className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-medium text-gray-200 transition-colors relative overflow-hidden group">
                <FileJson className="w-3.5 h-3.5" />
                <span>Load</span>
                <input type="file" onChange={handleFileUpload} className="absolute inset-0 opacity-0 cursor-pointer" accept=".json" />
              </button>
              <button onClick={handleDownload} className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 rounded text-xs font-medium text-gray-200 transition-colors">
                <Save className="w-3.5 h-3.5" />
                <span>Save</span>
              </button>
            </div>

            {/* Tabs */}
            <div className="flex bg-gray-900 rounded p-1">
              <button
                onClick={() => setState(s => ({ ...s, activeTab: 'dungeon', selectedItemIndex: null, interactionMode: 'none', captureTarget: null }))}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${state.activeTab === 'dungeon' ? 'bg-blue-600 text-white shadow' : 'text-gray-400 hover:text-white'}`}
              >
                Dungeon
              </button>
              <button
                onClick={() => setState(s => ({ ...s, activeTab: 'village', selectedItemIndex: null, interactionMode: 'none', captureTarget: null }))}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${state.activeTab === 'village' ? 'bg-green-600 text-white shadow' : 'text-gray-400 hover:text-white'}`}
              >
                Village
              </button>
            </div>
          </div>
        </div>

        {/* Global Script Settings (Type Only) */}
        {currentScript && state.activeTab === 'village' && (
          <div className="bg-gray-800 p-3 border-b border-gray-700 shrink-0">
            <div>
              <label className="text-[10px] uppercase text-gray-500 font-bold mb-1 block">Quest Type</label>
              <input
                type="text"
                value={currentScript._TYPE}
                onChange={(e) => updateCurrentQuest({ _TYPE: e.target.value })}
                className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:border-blue-500 outline-none"
                placeholder="dungeon"
                readOnly
              />
            </div>
          </div>
        )}

        {/* Timeline / List */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {activeList.map((item, index) => {
            const type = identifyType(item);
            const isSelected = state.selectedItemIndex === index;
            const isDragging = draggingIndex === index;

            return (
              <div
                key={index}
                draggable={dragReadyIndex === index}
                onDragStart={(e) => handleDragStart(e, index)}
                onDragOver={(e) => handleDragOver(e, index)}
                onDrop={(e) => handleDrop(e, index)}
                onClick={() => setState(s => ({ ...s, selectedItemIndex: s.selectedItemIndex === index ? null : index }))}
                className={`
                  relative border rounded-lg overflow-hidden transition-all group cursor-pointer
                  ${isSelected ? 'border-blue-500 bg-gray-800/90 ring-1 ring-blue-500/50' : 'border-gray-700 bg-gray-800/40 hover:bg-gray-800/60'}
                  ${isDragging ? 'opacity-40 ring-2 ring-yellow-500 scale-95' : ''}
                `}
              >
                {/* Header of Item */}
                <div className={`flex items-center gap-2 p-3 ${isSelected ? 'bg-gray-800/50' : 'bg-transparent'}`}>

                  {/* Drag Handle */}
                  <div
                    className="drag-handle cursor-grab text-gray-600 hover:text-gray-300 p-1 rounded hover:bg-gray-700/50 transition-colors"
                    title="Drag to reorder"
                    onMouseEnter={() => setDragReadyIndex(index)}
                    onMouseLeave={() => setDragReadyIndex(null)}
                  >
                    <GripVertical className="w-4 h-4" />
                  </div>

                  {/* Main Content Info */}
                  <div className="flex-1 flex items-center justify-between overflow-hidden">
                    <div className="flex items-center gap-2 overflow-hidden">
                      <span className={`px-2 py-0.5 rounded-[4px] text-[10px] font-bold uppercase tracking-wider shrink-0 ${getTypeColor(type)}`}>
                        {type}
                      </span>
                      <span className="font-mono text-sm font-semibold text-gray-200 truncate">
                        {
                          type === 'press' ? item[1] :
                            type === 'position' || type === 'chest' ? `${item[1]} ${formatCoord(item[2] || [])}` :
                              type === 'stair' ? `${item[0]} -> ${item[1]}` :
                                type === 'minimap_stair' ? `${item[3] || 'No Img'}` :
                                  type === 'harken' ? `${item[3] || 'No Img'}` :
                                    type === 'simple' ? item[0] :
                                      type === 'chest_auto' ? 'Auto' : 'Unknown'
                        }
                      </span>
                    </div>
                    <div className="flex items-center gap-1 shrink-0 ml-2">
                      <button
                        onClick={(e) => handlePlayAction(e, item)}
                        className={`text-gray-500 hover:text-green-400 p-1 rounded hover:bg-gray-700/50 transition-colors ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                        title="Replay Action"
                      >
                        <Play className="w-4 h-4" />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteScriptItem(index); }}
                        className={`text-gray-600 hover:text-red-400 p-1 rounded hover:bg-gray-700/50 transition-colors ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Expanded Editor Form */}
                {isSelected && (
                  <div className="p-3 border-t border-gray-700/50 bg-gray-900/50" onClick={(e) => e.stopPropagation()}>
                    {renderEditorForm(item, index)}
                  </div>
                )}

                {/* Collapsed Details View (Only if not selected) */}
                {!isSelected && (
                  <div className="px-3 pb-3 pl-10 text-xs text-gray-500 space-y-1 font-mono">
                    {/* Summary details logic */}
                    {isCoordinate(item[2]) && (
                      <div className="flex items-center gap-2 opacity-50">
                        <Crosshair className="w-3 h-3" />
                        {formatCoord(item[2])}
                      </div>
                    )}
                    {isRoi(item[2]) && (
                      <div className="flex items-center gap-2 opacity-50">
                        <Scan className="w-3 h-3" />
                        {formatCoord(item[2])}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Empty State */}
          {!currentScript && (
            <div className="flex flex-col items-center justify-center h-48 text-gray-500">
              <FilePlus className="w-10 h-10 mb-2 opacity-20" />
              <p>No Quest Selected</p>
              <button onClick={openCreateModal} className="mt-2 text-blue-400 hover:underline">Create a Quest</button>
            </div>
          )}

          {/* Add Buttons - Context Aware */}
          {currentScript && (
            <div className="pt-4 border-t border-gray-800 mt-4">
              {state.activeTab === 'dungeon' ? (
                <div className="grid grid-cols-3 gap-2">
                  <button onClick={() => addScriptItem('harken')} className="flex flex-col items-center gap-1 bg-gray-800 hover:bg-gray-700 py-3 rounded text-xs text-gray-300 border border-gray-700 transition-all hover:border-pink-500/50">
                    <Home className="w-4 h-4 text-pink-400" />
                    <span>Harken</span>
                  </button>
                  <button onClick={() => addScriptItem('position')} className="flex flex-col items-center gap-1 bg-gray-800 hover:bg-gray-700 py-3 rounded text-xs text-gray-300 border border-gray-700 transition-all hover:border-purple-500/50">
                    <MapPin className="w-4 h-4 text-purple-400" />
                    <span>Position</span>
                  </button>
                  <button onClick={() => addScriptItem('chest_auto')} className="flex flex-col items-center gap-1 bg-gray-800 hover:bg-gray-700 py-3 rounded text-xs text-gray-300 border border-gray-700 transition-all hover:border-green-500/50">
                    <Box className="w-4 h-4 text-green-400" />
                    <span>Chest Auto</span>
                  </button>
                  <button onClick={() => addScriptItem('stair')} className="flex flex-col items-center gap-1 bg-gray-800 hover:bg-gray-700 py-3 rounded text-xs text-gray-300 border border-gray-700 transition-all hover:border-blue-500/50">
                    <AlignJustify className="w-4 h-4 text-blue-400" />
                    <span>Stair</span>
                  </button>
                  <button onClick={() => addScriptItem('chest')} className="flex flex-col items-center gap-1 bg-gray-800 hover:bg-gray-700 py-3 rounded text-xs text-gray-300 border border-gray-700 transition-all hover:border-yellow-500/50">
                    <Box className="w-4 h-4 text-yellow-400" />
                    <span>Chest</span>
                  </button>
                  <button onClick={() => addScriptItem('minimap_stair')} className="flex flex-col items-center gap-1 bg-gray-800 hover:bg-gray-700 py-3 rounded text-xs text-gray-300 border border-gray-700 transition-all hover:border-cyan-500/50">
                    <Map className="w-4 h-4 text-cyan-400" />
                    <span>MiniMap Stair</span>
                  </button>
                </div>
              ) : (
                /* Village Tab */
                <div className="grid grid-cols-1">
                  <button onClick={() => addScriptItem('press')} className="flex flex-col items-center gap-1 bg-gray-800 hover:bg-gray-700 py-3 rounded text-xs text-gray-300 border border-gray-700 transition-all hover:border-orange-500/50">
                    <MousePointer className="w-4 h-4 text-orange-400" />
                    <span>Press</span>
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Logs */}
        <div className="h-32 bg-black border-t border-gray-700 overflow-y-auto p-2 font-mono text-xs text-green-400 shrink-0">
          {state.logs.map((log, i) => <div key={i}>&gt; {log}</div>)}
        </div>
      </div>

    </div>
  );
};

const root = createRoot(document.getElementById('root')!);
root.render(<App />);