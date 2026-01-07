(function () {
    // --- Constants & Fallback Data ---
    const V_WIDTH = 900;
    const V_HEIGHT = 1600;

    // 內嵌數據備援，解決本地直接開啟 file:// 的 CORS 限制
    const FALLBACK_DATA = {
        "GoblinCave": { "_TYPE": "dungeon", "questName": "[寶箱]狼洞1f寶箱", "_TARGETINFOLIST": [["chest_auto"], ["position", "右上", [771, 921]]], "_EOT": [["press", "intoWorldMap", ["AWD/AWD", "input swipe 400 400 500 500"], 2], ["press", "AWD/AWD1F", [1, 1], 2]] },
        "AWD": { "_TYPE": "dungeon", "questName": "[寶箱]狼洞2f寶箱", "_TARGETINFOLIST": [["chest_auto"], ["position", "右下", [766, 974]]], "_EOT": [["press", "intoWorldMap", ["AWD/AWD", "input swipe 400 400 500 500"], 2], ["press", "AWD/AWD2F", [1, 1], 2]] },
        "DH-Church": { "_TYPE": "dungeon", "questName": "[刷怪]深雪教會區", "_TARGETINFOLIST": [["position", "左下", [240, 810]], ["position", "左下", [130, 400]], ["position", "右上", [500, 930]], ["position", "右上", [820, 712]]], "_EOT": [["press", "DH", ["EdgeOfTown", [1, 1]], 2], ["press", "stair_DH_Church", "input swipe 650 900 650 250", 2]] }
    };

    let fullQuestData = {};
    let currentDungeon = '';
    let currentMode = 'dungeon';
    let activeStepIdx = -1;
    let currentTool = 'move';
    let lastClickedPos = { x: 0, y: 0 };

    // --- DOM Elements ---
    const canvas = document.getElementById('game-canvas');
    const overlay = document.getElementById('overlay');
    const dungeonSelect = document.getElementById('dungeon-select');
    const stepsContainer = document.getElementById('steps-container');
    const mouseCoords = document.getElementById('mouse-coords');
    const toolbarDungeon = document.getElementById('toolbar-dungeon');
    const toolbarEOT = document.getElementById('toolbar-eot');
    const navTabs = document.querySelectorAll('.nav-tab');
    const pointer = document.getElementById('target-pointer');
    const roiBox = document.getElementById('target-roi');
    const dungPropEditor = document.getElementById('dung-prop-editor');
    const eotPropEditor = document.getElementById('eot-prop-editor');
    const btnAddDungeon = document.getElementById('btn-add-dungeon');
    const btnRenameDungeon = document.getElementById('btn-rename-dungeon');
    const btnDeleteDungeon = document.getElementById('btn-delete-dungeon');
    const modalAdd = document.getElementById('dialog-add-dungeon');
    const btnConfirmAdd = document.getElementById('btn-confirm-add');
    const btnCancelAdd = document.getElementById('btn-cancel-add');

    // --- Initialization ---
    async function init() {
        try {
            console.log("Attempting to load quest.json...");
            const resp = await fetch('quest.json');
            if (resp.ok) {
                fullQuestData = await resp.json();
                console.log("Successfully loaded quest.json via fetch");
            } else {
                throw new Error("HTTP error");
            }
        } catch (err) {
            console.warn("Fetch failed (likely CORS). Using embedded fallback data.");
            fullQuestData = FALLBACK_DATA;
            showToast("本地模式：使用內嵌資料", "warning");
        }

        populateDungeonSelect();
        setupEventListeners();
        resizeCanvas();

        const keys = Object.keys(fullQuestData);
        if (keys.length > 0) window.selectDungeon(keys[0]);
    }

    function populateDungeonSelect() {
        dungeonSelect.innerHTML = Object.entries(fullQuestData)
            .map(([id, data]) => `<option value="${id}">${data.questName || id}</option>`)
            .join('');
    }

    function setupEventListeners() {
        window.addEventListener('resize', resizeCanvas);

        navTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                navTabs.forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                currentMode = tab.dataset.tab;

                toolbarDungeon.style.display = currentMode === 'dungeon' ? 'flex' : 'none';
                toolbarEOT.style.display = currentMode === 'eot' ? 'flex' : 'none';
                dungPropEditor.style.display = currentMode === 'dungeon' ? 'block' : 'none';
                eotPropEditor.style.display = currentMode === 'eot' ? 'block' : 'none';

                renderStepsList();
                const steps = getStepsArray();
                if (steps.length > 0) selectStep(0);
                else { activeStepIdx = -1; renderActiveStepOverlay(); }
            });
        });

        document.querySelectorAll('.tool-icon-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.tool-icon-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentTool = btn.dataset.tool;
            });
        });

        dungeonSelect.onchange = (e) => window.selectDungeon(e.target.value);

        btnAddDungeon.onclick = () => modalAdd.style.display = 'flex';
        btnCancelAdd.onclick = () => modalAdd.style.display = 'none';
        btnConfirmAdd.onclick = handleAddDungeon;

        btnDeleteDungeon.onclick = () => {
            if (confirm(`確定要刪除地城 [${currentDungeon}] 嗎？`)) {
                delete fullQuestData[currentDungeon];
                populateDungeonSelect();
                const keys = Object.keys(fullQuestData);
                if (keys.length > 0) selectDungeon(keys[0]);
                showToast("刪除成功");
            }
        };

        btnRenameDungeon.onclick = () => {
            const newName = prompt("輸入新的顯示名稱:", fullQuestData[currentDungeon].questName);
            if (newName) {
                fullQuestData[currentDungeon].questName = newName;
                populateDungeonSelect();
                dungeonSelect.value = currentDungeon;
            }
        };

        overlay.onmousemove = (e) => {
            const v = toVirtual(e.clientX, e.clientY);
            mouseCoords.textContent = `解析度: 900 x 1600 | 座標: [${v.x}, ${v.y}]`;
        };

        overlay.onclick = (e) => {
            if (currentTool === 'eot-swipe') return;
            const v = toVirtual(e.clientX, e.clientY);
            lastClickedPos = v;

            if (currentTool === 'move') {
                showTapEffect(e.clientX, e.clientY);
            } else if (currentTool === 'chest' || currentTool === 'stair') {
                addStep(currentTool, v);
            }
        };

        document.getElementById('save-step').onclick = saveActiveStepProps;
        document.getElementById('write-json').onclick = () => {
            console.log("Full JSON Output:", JSON.stringify(fullQuestData, null, 4));
            showToast("數據已匯出 (請見 Console)", "success");
        };
    }

    // --- Core Logic ---
    window.selectDungeon = (id) => {
        console.log(`[App] Selecting Dungeon: ${id}`);
        if (!fullQuestData[id]) {
            console.error(`[App] Dungeon ID [${id}] not found in data.`);
            return;
        }
        currentDungeon = id;

        // Ensure dropdown reflects selection
        if (dungeonSelect.value !== id) {
            dungeonSelect.value = id;
        }

        renderStepsList();

        const steps = getStepsArray();
        console.log(`[App] Loaded ${steps.length} steps for ${id}`);

        if (steps.length > 0) {
            window.selectStep(0);
        } else {
            activeStepIdx = -1;
            renderActiveStepOverlay();
            // Clear props editor
            document.querySelectorAll('#dung-prop-editor input, #eot-prop-editor input').forEach(i => i.value = '');
        }

        showToast(`已切換至: ${fullQuestData[id].questName || id}`);
    };

    function getStepsArray() {
        if (!fullQuestData[currentDungeon]) return [];
        return currentMode === 'dungeon'
            ? fullQuestData[currentDungeon]._TARGETINFOLIST || []
            : fullQuestData[currentDungeon]._EOT || [];
    }

    function renderStepsList() {
        const steps = getStepsArray();
        stepsContainer.innerHTML = steps.map((s, i) => `
            <div class="step-item ${i === activeStepIdx ? 'active' : ''}" onclick="window.selectStep(${i})">
                <div class="step-idx">${i + 1}</div>
                <div class="step-content">
                    <div class="step-type">${getStepLabel(s)}</div>
                    <div class="step-desc">${getStepDesc(s)}</div>
                </div>
                <div class="step-actions">
                    <button class="btn-icon" onclick="event.stopPropagation(); window.deleteStep(${i})" title="Delete">🗑️</button>
                </div>
            </div>
        `).join('');
    }

    function getStepLabel(s) {
        if (currentMode === 'dungeon') return s[0];
        return s[1];
    }

    function getStepDesc(s) {
        if (currentMode === 'dungeon') {
            return s[2] ? JSON.stringify(s[2]) : "無數據";
        }
        return JSON.stringify(s[2]);
    }

    window.selectStep = (idx) => {
        activeStepIdx = idx;
        renderStepsList();
        renderActiveStepOverlay();
        loadActiveStepProps();
    };

    window.deleteStep = (idx) => {
        const steps = getStepsArray();
        steps.splice(idx, 1);
        if (activeStepIdx >= steps.length) activeStepIdx = steps.length - 1;
        renderStepsList();
        renderActiveStepOverlay();
        if (activeStepIdx >= 0) loadActiveStepProps();
    };

    function addStep(type, data) {
        const steps = getStepsArray();
        const newStep = [type, "無", [data.x, data.y]];
        steps.push(newStep);
        renderStepsList();
        window.selectStep(steps.length - 1);
        stepsContainer.scrollTop = stepsContainer.scrollHeight;
    }

    function handleAddDungeon() {
        const id = document.getElementById('new-dung-id').value.trim();
        const name = document.getElementById('new-dung-name').value.trim();
        if (!id || !name) return showToast("資料不全", "error");

        fullQuestData[id] = { "_TYPE": "dungeon", "questName": name, "_TARGETINFOLIST": [], "_EOT": [] };
        populateDungeonSelect();
        selectDungeon(id);
        modalAdd.style.display = 'none';
        showToast("建立成功");
    }

    function loadActiveStepProps() {
        const steps = getStepsArray();
        const s = steps[activeStepIdx];
        if (!s) return;

        if (currentMode === 'dungeon') {
            document.getElementById('step-type').value = s[0];
            document.getElementById('step-swipe').value = s[1] || "無";
            if (Array.isArray(s[2])) {
                document.getElementById('step-x').value = s[2][0] || 0;
                document.getElementById('step-y').value = s[2][1] || 0;
            }
        } else {
            document.getElementById('eot-img').value = s[1] || "";
            document.getElementById('eot-parent').value = (s[2] && s[2][0]) || "";
        }
    }

    function saveActiveStepProps() {
        const steps = getStepsArray();
        const s = steps[activeStepIdx];
        if (!s) return showToast("未選步", "error");

        if (currentMode === 'dungeon') {
            s[0] = document.getElementById('step-type').value;
            s[1] = document.getElementById('step-swipe').value;
            s[2] = [parseInt(document.getElementById('step-x').value), parseInt(document.getElementById('step-y').value)];
        }
        renderStepsList();
        renderActiveStepOverlay();
        showToast("已更新");
    }

    function resizeCanvas() {
        const container = document.getElementById('canvas-container');
        if (!container) return;
        const ratio = V_WIDTH / V_HEIGHT;
        let h = container.clientHeight;
        let w = h * ratio;
        if (w > container.clientWidth) { w = container.clientWidth; h = w / ratio; }
        canvas.width = V_WIDTH; canvas.height = V_HEIGHT;
        canvas.style.width = `${w}px`; canvas.style.height = `${h}px`;
        overlay.style.width = `${w}px`; overlay.style.height = `${h}px`;
        drawGrid();
        renderActiveStepOverlay();
    }

    function drawGrid() {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, V_WIDTH, V_HEIGHT);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
        for (let x = 0; x < V_WIDTH; x += 100) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, V_HEIGHT); ctx.stroke(); }
        for (let y = 0; y < V_HEIGHT; y += 100) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(V_WIDTH, y); ctx.stroke(); }
    }

    function renderActiveStepOverlay() {
        const steps = getStepsArray();
        const s = steps[activeStepIdx];
        pointer.style.display = 'none';
        roiBox.style.display = 'none';
        if (s && currentMode === 'dungeon' && Array.isArray(s[2]) && typeof s[2][0] === 'number') {
            const css = fromVirtual(s[2][0], s[2][1]);
            pointer.style.display = 'block';
            pointer.style.left = `${css.x}px`;
            pointer.style.top = `${css.y}px`;
        }
    }

    function toVirtual(cx, cy) {
        const r = overlay.getBoundingClientRect();
        return { x: Math.round((cx - r.left) * (V_WIDTH / r.width)), y: Math.round((cy - r.top) * (V_HEIGHT / r.height)) };
    }

    function fromVirtual(vx, vy) {
        const r = overlay.getBoundingClientRect();
        return { x: vx * (r.width / V_WIDTH), y: vy * (r.height / V_HEIGHT) };
    }

    function showTapEffect(cx, cy) {
        const el = document.createElement('div');
        el.className = 'tap-ripple';
        el.style.left = `${cx - 20}px`; el.style.top = `${cy - 20}px`;
        el.style.width = '40px'; el.style.height = '40px';
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 600);
    }

    function showToast(msg, type = 'success') {
        const root = document.getElementById('toast-root');
        const t = document.createElement('div');
        t.className = `toast toast-${type}`;
        t.innerText = msg;
        root.appendChild(t);
        setTimeout(() => t.remove(), 3000);
    }

    init();
})();
