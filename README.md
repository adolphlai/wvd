# 修改自德德版本的分支
提供修改範例代碼
### 1. 不打斷自動戰鬥(def IdentifyState():)
<pre>
	            Press([1, 1])
            Sleep(0.25)
            Press([1, 1])
            Sleep(0.25)
            Press([1, 1])
            Sleep(1)
            counter += 1
</pre>

<pre>
	            if counter>=4:
                logger.info("看起来遇到了一些不太寻常的情况...")
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
            FindCoordsOrElseExecuteFallbackAndWait('refilled', ['Inn', 'box', 'refill', 'OK', [1, 1]], 2)
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','Economy',[1,1]],2)
        else:
            FindCoordsOrElseExecuteFallbackAndWait('refilled', ['Inn', 'box', 'refill', 'OK', [1, 1]], 2)
            FindCoordsOrElseExecuteFallbackAndWait('OK',['Inn','Stay','royalsuite',[1,1]],2)
        FindCoordsOrElseExecuteFallbackAndWait('Stay',['OK',[299,1464]],2)
 </pre>
