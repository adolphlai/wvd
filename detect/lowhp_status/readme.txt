我需要將實際命令打印出來
要不然我知道到底有沒有動作
chest
1.找按鈕
  1.1 找到按鈕，點他
	1.1.1 點了之後顯示notresure
	->點了之後移動->跳到移動檢查
  ->沒找到
	->打開地圖
		->偵測到mapflag
			->點擊（嘗試一次）
			->都找不到 → 點擊盲點座標 [459, 1248]（嘗試一次）
		->沒偵測到mapflag(打不開)
			->跳到gohome


position
1.開地圖
  1.1 打的開 -> 開地圖選座標移動 ->移動邏輯
  1.2 打不開 -> gohome流程



移動檢查
[chest_auto=true]
1.循環檢查
	1.1 偵測 notresure → pop 目標，返回 Map
	1.2 狀態轉換（戰鬥、寶箱等）→ 正常處理	
	1.3 chest_resume: 每 5 秒點擊一次寶箱按鈕
2.靜止判定
	2.1 連續 3 次 diff < 0.05
		2.1.1 檢測 mapFlag（已在地圖狀態）
			PressReturn 離開地圖，pop 目標，持續執行gohome直到離開地城
		2.1.2 無 mapFlag（主畫面狀態）
			直接 pop 目標，返回 Map
[resume=true]
1.循環檢查
	1.1 偵測 routenotfound → pop 目標，返回 Map
	1.2 狀態轉換（戰鬥、寶箱等）→ 正常處理
 	    1.2.1 狀態變換完成後，偵測resume，有的話繼續resume，沒有的話開地圖重新點座標
	1.3 resume: 每 5 秒點擊一次寶箱按鈕
2.靜止判定
	2.1 連續 3 次 diff < 0.05
		2.1.1 檢測 mapFlag（已在地圖狀態）
			PressReturn 離開地圖，pop 目標，持續執行gohome直到離開地城
		2.1.2 無 mapFlag（主畫面狀態）
			直接 pop 目標，返回 Map


[gohome=true]
1.靜止判定 連續 3 次 diff < 0.05 執行gohome
	1.1 持續檢測diff
		1.1.1 還是 diff < 0.05 轉向解卡
			1.1.1.1 向左轉，轉一次檢測3次
				1.1.1.1.1 如果仍舊diff < 0.05就繼續轉
					1.1.1.1.1.1 轉完還是diff < 0.05
				1.1.1.1.2 如果diff > 0.05 就繼續gohome
		1.1.2 diff > 0.05 持續gohome

[DungeonState.Map]
1.還有目標要執行
繼續執行下一個目標
2.沒有目標執行
if (targetInfoList is None) or (targetInfoList == []):
如果還在地城內，且目標列變成空的時，執行gohome，但我最後一道防線是gohome
不可能跑到這，當每種異常之後都會跑到gohome來回家


----------
您的推論是正確的，流程設計上已經考慮到了這一點。

當目標列表為空時的流程 (Script.py:4680-4691 及 3376):



異常處理
1.轉向解卡-->>應該可以移除
2.靜止處理-->軟超時，觸發gohome 60S
3.重啟-->硬超時，重啟，120S


