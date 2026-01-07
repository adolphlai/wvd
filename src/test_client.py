import asyncio
import websockets
import json
import time

async def test():
    uri = "ws://localhost:8765"
    print(f"嘗試連接到 {uri} ...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print(">>> 連接成功！")
            
            # 測試指令 1: 點擊
            cmd1 = "input tap 200 200"
            print(f">>> 發送: {cmd1}")
            await websocket.send(cmd1)
            
            # 等待一下
            await asyncio.sleep(1)
            
            # 測試指令 2: 滑動
            cmd2 = "input swipe 200 200 500 500"
            print(f">>> 發送: {cmd2}")
            await websocket.send(cmd2)
            
            print(">>>發送完畢，等待 2 秒後斷開...")
            
            # 嘗試接收任何回傳訊息 (例如圖片串流或確認訊息)
            try:
                msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"<<< 收到回傳 (前50字): {str(msg)[:50]}")
            except asyncio.TimeoutError:
                print("<<< 沒有收到回傳 (正常，如果沒有開啟串流)")
                
    except ConnectionRefusedError:
        print("!!! 連接失敗：伺服器未啟動或端口錯誤")
    except Exception as e:
        print(f"!!! 發生錯誤: {e}")

if __name__ == "__main__":
    asyncio.run(test())
