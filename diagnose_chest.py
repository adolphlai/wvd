"""
诊断脚本：分析为什么截图中没找到宝箱
使用方法：在有 opencv-python 的环境中运行
"""
import cv2
import numpy as np
import os
import sys

# 添加src目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

try:
    from utils import LoadImage, ResourcePath, LoadTemplateImage
except ImportError as e:
    print(f"错误：无法导入 utils 模块: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)

def cut_roi(screenshot, roi):
    """复制CutRoI函数逻辑"""
    if roi is None:
        return screenshot.copy()
    
    img_height, img_width = screenshot.shape[:2]
    roi_copy = roi.copy()
    screenshot = screenshot.copy()
    
    # 第一个矩形：这是"保留区域"（搜索区域）
    roi1_rect = roi_copy.pop(0)
    x1, y1, w1, h1 = roi1_rect
    
    # 计算裁剪后的边界
    roi1_y_start = max(0, y1)
    roi1_y_end = min(img_height, y1 + h1)
    roi1_x_start = max(0, x1)
    roi1_x_end = min(img_width, x1 + w1)
    
    # 创建掩码：不在roi1中的像素设为0（黑色）
    pixels_not_in_roi1_mask = np.ones((img_height, img_width), dtype=bool)
    if roi1_x_start < roi1_x_end and roi1_y_start < roi1_y_end:
        pixels_not_in_roi1_mask[roi1_y_start:roi1_y_end, roi1_x_start:roi1_x_end] = False
    
    screenshot[pixels_not_in_roi1_mask] = 0
    
    # 后续矩形：这些都是"排除区域"（UI元素）
    for roi2_rect in roi_copy:
        x2, y2, w2, h2 = roi2_rect
        roi2_y_start = max(0, y2)
        roi2_y_end = min(img_height, y2 + h2)
        roi2_x_start = max(0, x2)
        roi2_x_end = min(img_width, x2 + w2)
        
        if roi2_x_start < roi2_x_end and roi2_y_end < roi2_y_end:
            screenshot[roi2_y_start:roi2_y_end, roi2_x_start:roi2_x_end] = 0
    
    return screenshot

def check_if(screen_image, template, roi=None, threshold=0.80):
    """模拟CheckIf函数"""
    search_area = cut_roi(screen_image, roi) if roi else screen_image
    
    try:
        result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        
        if max_val < threshold:
            return None, max_val, max_loc
        
        pos = [max_loc[0] + template.shape[1]//2, max_loc[1] + template.shape[0]//2]
        return pos, max_val, max_loc
    except Exception as e:
        print(f"  匹配过程出错: {e}")
        return None, 0.0, None

def main():
    print("=" * 70)
    print("宝箱识别诊断工具")
    print("=" * 70)
    
    # 截图路径
    screenshot_path = ResourcePath("resources/quest/MuMu-20251101-124850-862.png")
    
    if not os.path.exists(screenshot_path):
        print(f"错误：截图文件不存在: {screenshot_path}")
        print("请确认截图文件路径正确")
        sys.exit(1)
    
    # 加载截图
    print("\n[1] 加载截图...")
    screenshot = LoadImage(screenshot_path)
    if screenshot is None:
        print("  ✗ 无法加载截图！")
        sys.exit(1)
    
    img_height, img_width = screenshot.shape[:2]
    print(f"  ✓ 截图尺寸: {img_height} x {img_width} (高度 x 宽度)")
    print(f"  预期尺寸: 1600 x 900 (高度 x 宽度)")
    
    # 检查尺寸
    if img_width != 900 or img_height != 1600:
        print(f"  ⚠️  警告：截图尺寸与预期不符！")
        print(f"  实际: 宽度={img_width}, 高度={img_height}")
        print(f"  预期: 宽度=900, 高度=1600")
        print(f"  这可能导致ROI区域计算错误！")
    else:
        print(f"  ✓ 截图尺寸正确")
    
    # 测试不同的宝箱模板
    template_names = ['chest', 'chestStone', 'chestfear', 'chestFlag']
    templates = {}
    
    print("\n[2] 加载宝箱模板...")
    for name in template_names:
        template = LoadTemplateImage(name)
        if template is not None:
            templates[name] = template
            print(f"  ✓ {name}.png: {template.shape}")
        else:
            print(f"  ✗ {name}.png: 加载失败")
    
    if not templates:
        print("  ✗ 所有模板加载失败！")
        sys.exit(1)
    
    # 构建ROI（和代码中一样）
    roi = [
        [0, 0, 900, 1600],      # 搜索区域：全屏 [x, y, width, height]
        [0, 0, 900, 208],       # 排除：顶部UI
        [0, 1265, 900, 335],    # 排除：底部UI
        [0, 636, 137, 222],     # 排除：左侧UI
        [763, 636, 137, 222],   # 排除：右侧UI
        [336, 208, 228, 77],    # 排除：顶部中间UI
        [336, 1168, 228, 97]    # 排除：底部中间UI
    ]
    
    # 测试1：不使用ROI（全屏搜索）
    print("\n" + "=" * 70)
    print("[3] 测试1：不使用ROI（全屏搜索）")
    print("-" * 70)
    
    best_match_fullscreen = None
    best_val_fullscreen = 0.0
    
    for name, template in templates.items():
        pos, val, loc = check_if(screenshot, template, roi=None, threshold=0.0)  # 阈值设为0，查看所有结果
        print(f"  {name:15} 匹配度: {val*100:6.2f}%", end="")
        
        if val >= 0.80:
            print(f"  ✓ 找到！（位置: {loc}）")
            if val > best_val_fullscreen:
                best_match_fullscreen = (name, pos, val, loc)
                best_val_fullscreen = val
        elif val >= 0.70:
            print(f"  ⚠️  接近阈值（位置: {loc}）")
        else:
            print()
    
    if best_match_fullscreen:
        name, pos, val, loc = best_match_fullscreen
        print(f"\n  ✓ 最佳匹配: {name}，匹配度 {val*100:.2f}%")
        # 保存标记结果
        marked_img = screenshot.copy()
        template = templates[name]
        cv2.rectangle(marked_img, 
                     (loc[0], loc[1]),
                     (loc[0] + template.shape[1], loc[1] + template.shape[0]),
                     (0, 255, 0), 3)
        cv2.putText(marked_img, f"{name} {val*100:.1f}%", 
                   (loc[0], loc[1] - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.imwrite("diagnosis_result_fullscreen.png", marked_img)
        print(f"  已保存标记结果到: diagnosis_result_fullscreen.png")
    else:
        print(f"\n  ✗ 全屏搜索未找到任何匹配度≥80%的宝箱")
        max_val = max([check_if(screenshot, t, roi=None, threshold=0.0)[1] 
                      for t in templates.values()])
        print(f"  最大匹配度: {max_val*100:.2f}%")
    
    # 测试2：使用ROI（排除UI区域）
    print("\n" + "=" * 70)
    print("[4] 测试2：使用ROI（排除UI区域）")
    print("-" * 70)
    
    best_match_roi = None
    best_val_roi = 0.0
    
    for name, template in templates.items():
        pos, val, loc = check_if(screenshot, template, roi=roi, threshold=0.0)
        print(f"  {name:15} 匹配度: {val*100:6.2f}%", end="")
        
        if val >= 0.80:
            print(f"  ✓ 找到！（位置: {loc}）")
            if val > best_val_roi:
                best_match_roi = (name, pos, val, loc)
                best_val_roi = val
        elif val >= 0.70:
            print(f"  ⚠️  接近阈值（位置: {loc}）")
        else:
            print()
    
    if best_match_roi:
        name, pos, val, loc = best_match_roi
        print(f"\n  ✓ 最佳匹配: {name}，匹配度 {val*100:.2f}%")
        # 保存标记结果
        marked_img = screenshot.copy()
        template = templates[name]
        cv2.rectangle(marked_img, 
                     (loc[0], loc[1]),
                     (loc[0] + template.shape[1], loc[1] + template.shape[0]),
                     (0, 0, 255), 3)
        cv2.putText(marked_img, f"{name} {val*100:.1f}%", 
                   (loc[0], loc[1] - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.imwrite("diagnosis_result_with_roi.png", marked_img)
        print(f"  已保存标记结果到: diagnosis_result_with_roi.png")
    else:
        print(f"\n  ✗ 使用ROI未找到任何匹配度≥80%的宝箱")
        max_val = max([check_if(screenshot, t, roi=roi, threshold=0.0)[1] 
                      for t in templates.values()])
        print(f"  最大匹配度: {max_val*100:.2f}%")
        if max_val >= 0.70:
            print(f"  建议：可以考虑降低阈值到 {int((max_val + 0.05) * 100)}%")
    
    # 测试3：保存ROI处理后的图像
    print("\n" + "=" * 70)
    print("[5] 保存ROI处理后的图像")
    print("-" * 70)
    roi_processed = cut_roi(screenshot, roi)
    cv2.imwrite("diagnosis_roi_processed.png", roi_processed)
    print("  ✓ 已保存ROI处理后的图像到: diagnosis_roi_processed.png")
    print("  请查看这个图像，确认哪些区域被排除了")
    
    # 测试4：测试不同的阈值
    print("\n" + "=" * 70)
    print("[6] 测试不同阈值的影响（使用ROI，chest模板）")
    print("-" * 70)
    
    if 'chest' in templates:
        template = templates['chest']
        print("  阈值    最大匹配度    结果")
        print("  " + "-" * 40)
        
        for threshold in [0.70, 0.75, 0.80, 0.85, 0.90]:
            _, val, _ = check_if(screenshot, template, roi=roi, threshold=0.0)
            status = "✓ 找到" if val >= threshold else "✗ 未找到"
            print(f"  {threshold*100:4.0f}%    {val*100:6.2f}%      {status}")
    
    # 总结
    print("\n" + "=" * 70)
    print("诊断总结")
    print("=" * 70)
    
    if best_match_fullscreen:
        print(f"✓ 全屏搜索：找到 {best_match_fullscreen[0]}，匹配度 {best_match_fullscreen[2]*100:.2f}%")
    else:
        print("✗ 全屏搜索：未找到")
    
    if best_match_roi:
        print(f"✓ 使用ROI：找到 {best_match_roi[0]}，匹配度 {best_match_roi[2]*100:.2f}%")
        print("\n结论：")
        print("  宝箱可以识别，但在使用ROI时可能被排除了")
        print("  建议检查ROI配置，确认宝箱位置不在排除区域内")
    else:
        print("✗ 使用ROI：未找到")
        max_val_roi = max([check_if(screenshot, t, roi=roi, threshold=0.0)[1] 
                          for t in templates.values()])
        if max_val_roi >= 0.70:
            print("\n结论：")
            print(f"  最大匹配度 {max_val_roi*100:.2f}% 接近但未达到80%阈值")
            print(f"  建议：考虑降低阈值到 {int((max_val_roi + 0.05) * 100)}%")
        else:
            print("\n结论：")
            print("  匹配度太低，可能的原因：")
            print("  1. 截图中的宝箱类型不在模板列表中")
            print("  2. 宝箱图像与模板差异较大（角度、光照、缩放）")
            print("  3. 宝箱被UI元素遮挡")
            print("  4. 截图质量问题")
    
    print("\n生成的诊断文件：")
    print("  - diagnosis_result_fullscreen.png: 全屏搜索结果（如果找到）")
    print("  - diagnosis_result_with_roi.png: ROI搜索结果（如果找到）")
    print("  - diagnosis_roi_processed.png: ROI处理后的图像")
    print("\n诊断完成！")

if __name__ == "__main__":
    main()

