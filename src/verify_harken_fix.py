from script import TargetInfo

def test_target_info_floor_image():
    # 測試 harken 目標
    harken_info = TargetInfo(target='harken', extra='harken_floor_7.png')
    print(f"Testing Harken: target={harken_info.target}, extra={harken_info.extra}, floorImage={harken_info.floorImage}")
    assert harken_info.floorImage == 'harken_floor_7.png'
    assert harken_info.extra == 'harken_floor_7.png'

    # 測試 minimap_stair 目標
    stair_info = TargetInfo(target='minimap_stair', extra='stair_marker.png')
    print(f"Testing MinimapStair: target={stair_info.target}, extra={stair_info.extra}, floorImage={stair_info.floorImage}")
    assert stair_info.floorImage == 'stair_marker.png'
    assert stair_info.extra == 'stair_marker.png'

    # 測試列表初始化方式
    list_info = TargetInfo(['harken', None, None, 'list_floor.png'])
    print(f"Testing List Init: target={list_info.target}, extra={list_info.extra}, floorImage={list_info.floorImage}")
    assert list_info.floorImage == 'list_floor.png'
    assert list_info.extra == 'list_floor.png'

    print("All tests passed!")

if __name__ == "__main__":
    try:
        test_target_info_floor_image()
    except Exception as e:
        print(f"Test failed: {e}")
        exit(1)
