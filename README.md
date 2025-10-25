要修改請下載德德的原始代碼後自己設定環境後自行編譯
# 請先自行安裝python環境以及IDE(VS code或者PyCharm之類)
# 修改自德德版本的分支(基於1.8.11，請勿全部下載後編譯，你只會得到一個老版本)
提供自行修改範例代碼
### 1. 不打斷自動戰鬥(def IdentifyState():)
<pre>
	        Press([1, 1])
            Sleep(0.25)
            Press([1, 1])
            Sleep(0.25)
            Press([1, 1])
            Sleep(1)
			# 移除原始代碼 counter += 1 上面的點擊行為
            counter += 1
</pre>

<pre>
	        if counter>=4:
			logger.info("看起来遇到了一些不太寻常的情况...")
			# 在 if counter>=4: 將上面移除的部分複製過來，需要對齊
            Press([1, 1])
            Sleep(0.25)
            Press([1, 1])
            Sleep(0.25)
            Press([1, 1])
            Sleep(1)
</pre>

### 2. 旅館自動補給(def StateInn():)
<pre> 
	        if not setting._ACTIVE_ROYALSUITE_REST:
			# 增加下面這一段，圖片需要額外手動添加Inn，box，refill至原始碼文件下的resoure/image資料夾下
            FindCoordsOrElseExecuteFallbackAndWait('refilled', ['Inn', 'box', 'refill', 'OK', [1, 1]], 2)
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','Economy',[1,1]],2)
        else:
			# 增加下面這一段，圖片需要額外手動添加Inn，box，refill至原始碼文件下的resoure/image資料夾下
            FindCoordsOrElseExecuteFallbackAndWait('refilled', ['Inn', 'box', 'refill', 'OK', [1, 1]], 2)
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','royalsuite',[1,1]],2)
        FindCoordsOrElseExecuteFallbackAndWait('Stay',['OK',[299,1464]],2)
		PressReturn()
 </pre>
# 圖片介紹
這是box圖連結  
![box](resources/images/box.png)  
這是refill圖連結  
![refill](resources/images/refill.png)  
這是Inn圖連結  
![Inn](resources/images/Inn.png)
# 打包bat
德德的是簡體會有編碼問題，會跑不了，可以抓取我修改過後的localpack.bat來替換原本的德德的打包bat

<pre>
	    def StateChest():
        """优化后的开箱流程 - 固定中下角色（盗贼）开箱"""

        # ========== 阶段1: 快速等待选人界面 ==========
        for _ in range(10):  # 最多等待3秒 (10 × 0.3)
            scn = ScreenShot()
            if CheckIf(scn, 'whowillopenit'):
                break
            # 点击推进对话
            Press(CheckIf(scn, 'chestFlag') or [450, 800])
            Sleep(0.3)
        else:
            logger.warning("未检测到选人界面，跳过开箱")
            return DungeonState.Dungeon

        # ========== 阶段2: 固定选择中下位置角色（盗贼）==========
        thief_pos = [516, 1345]  # 中下位置
        Press(thief_pos)
        Sleep(0.8)

        # ========== 阶段3: 连续点击3次解除陷阱 ==========
        disarm = [515, 934]
        for _ in range(3):
            Press(disarm)
            Sleep(0.3)
        for _ in range(15):
            Press(disarm)
            Sleep(0.2)
        # ========== 測試代碼 ==========
        # scn = ScreenShot()
        # 🔍 检查该角色是否恐惧状态
        #if CheckIf(scn, 'chestfear', [[800, 0, 800, 900]]):
            # logger.info("檢測到有人恐懼了")
        if CheckIf(scn := ScreenShot(), 'chestfear-1'):
            logger.info("檢測到有人恐懼了")
            shouldRecover = True
            if shouldRecover:
                Press([1, 1])
                counter_trychar = -1
                while 1:
                    counter_trychar += 1
                    if CheckIf(ScreenShot(), 'dungflag'):
                        Press([36 + (counter_trychar % 3) * 286, 1425])
                        Sleep(1)
                    else:
                        break
                    if CheckIf(scn := ScreenShot(), 'trait'):
                        if CheckIf(scn, 'story', [[676, 800, 220, 108]]):
                            Press([725, 850])
                        else:
                            Press([830, 850])
                        Sleep(1)
                        FindCoordsOrElseExecuteFallbackAndWait(
                            ['recover', 'combatActive', 'combatActive_2'],
                            [833, 843],
                            1
                        )
                        if CheckIf(ScreenShot(), 'recover'):
                            Sleep(1)
                            Press([600, 1200])
                            for _ in range(5):
                                t = time.time()
                                PressReturn()
                                if time.time() - t < 0.3:
                                    Sleep(0.3 - (time.time() - t))
                            shouldRecover = False
                            break

        # ========== 測試代碼 ==========

        # ========== 阶段4: 快速检测开箱完成 ==========
        for _ in range(20):  # 最多等待5秒 (20 × 0.25)
            scn = ScreenShot()

            # 检测完成标志
            if CheckIf(scn, 'dungFlag'):
                logger.info("开箱完成")
                return DungeonState.Dungeon

            # 检测战斗
            if CheckIf(scn, 'combatActive') or CheckIf(scn, 'combatActive_2'):
                logger.info("开箱触发战斗")
                return DungeonState.Combat

            # 检测死亡
            if CheckIf(scn, 'RiseAgain'):
                logger.warning("角色死亡")
                RiseAgainReset(reason='chest')
                return None

            # 检测重试按钮（网络问题）
            if Press(CheckIf(scn, 'retry')) or Press(CheckIf(scn, 'retry_blank')):
                logger.info("网络波动，点击重试")
                Sleep(1)
                continue

            Sleep(0.25)
</pre>
