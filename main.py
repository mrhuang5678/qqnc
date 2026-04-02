import Quartz
import Vision
from Foundation import NSDictionary, NSArray
import cv2
import numpy as np
import os
import sys
import time
import pyautogui
import logging
from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps

# --- 全局配置 ---
# 自定义延迟值 (300 毫秒)
FIXED_DELAY_MS = 0.3

# 故障恢复关键词（检测到后执行中心点击，具备最高优先级）
RECOVERY_KEYWORDS = ["重新登录", "重新连接"]

# 农场主要操作关键词（检测到后执行上方偏移点击）
FARM_ACTION_KEYWORDS = ["可摘", "一键收获", "一键浇水", "一键除草", "一键除虫"]

# 监控状态关键词（仅用于日志输出，不执行点击）
MONITOR_KEYWORDS = ["仓库", "商店", "好友"]

# 故障恢复后等待时间 (秒)
RECOVERY_WAIT = 3

# 巡查间隔时间 (秒)
LOOP_INTERVAL = 5

# 用于后续识别
TARGET_SIZE = (2000, 3720) 

# 配置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s,%(msecs)03d - INFO - 【巡查农场】 %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# ----------------

def focus_window(pid):
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    if app:
        app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        time.sleep(0.3)


def capture_wechat_mini_program(window_title="QQ经典农场", resize_to=None):
    window_list = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements,
        Quartz.kCGNullWindowID
    )
    
    target_id = None
    window_rect = None
    owner_pid = None
    for window in window_list:
        if window_title in window.get('kCGWindowName', ''):
            target_id = window.get('kCGWindowNumber')
            window_rect = window.get('kCGWindowBounds') 
            owner_pid = window.get('kCGWindowOwnerPID')
            break
            
    if not target_id or not window_rect:
        logging.error(f"❌ 未找到标题包含 '{window_title}' 的窗口")
        return None, None, None

    cg_image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull,
        Quartz.kCGWindowListOptionIncludingWindow,
        target_id,
        Quartz.kCGWindowImageBoundsIgnoreFraming
    )

    if not cg_image:
        logging.error(f"❌ 窗口 ID {target_id} 截图失败")
        return None, None

    width = Quartz.CGImageGetWidth(cg_image)
    height = Quartz.CGImageGetHeight(cg_image)
    bytes_per_row = Quartz.CGImageGetBytesPerRow(cg_image)
    pixel_data = Quartz.CGDataProviderCopyData(Quartz.CGImageGetDataProvider(cg_image))
    
    img_raw = np.frombuffer(pixel_data, dtype=np.uint8)
    img = img_raw.reshape((height, bytes_per_row))
    img = img[:, :width * 4].reshape((height, width, 4))
    
    frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    
    if resize_to:
        frame = cv2.resize(frame, resize_to, interpolation=cv2.INTER_LANCZOS4)
        
    return frame, window_rect, owner_pid

def recognize_text_vision(cv_frame):
    frame_bgra = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2BGRA)
    height, width = frame_bgra.shape[:2]
    
    bytes_per_row = width * 4
    color_space = Quartz.CGColorSpaceCreateDeviceRGB()
    context = Quartz.CGBitmapContextCreate(
        frame_bgra.data,
        width,
        height,
        8,
        bytes_per_row,
        color_space,
        Quartz.kCGImageAlphaNoneSkipFirst | Quartz.kCGBitmapByteOrder32Little
    )
    cg_image = Quartz.CGBitmapContextCreateImage(context)
    
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg_image, None)
    
    results = []
    
    def completion_handler(request, error):
        if error:
            logging.error(f"【 ❌ 】 Vision 识别错误: {error}")
            return
        
        observations = request.results()
        if observations:
            for obs in observations:
                top_candidate = obs.topCandidates_(1)[0]
                text = top_candidate.string()
                bbox = obs.boundingBox() 
                results.append((text, bbox))

    request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completion_handler)
    request.setRecognitionLevel_(0) # 精确识别模式
    request.setRecognitionLanguages_(["zh-Hans", "en-US"])
    
    handler.performRequests_error_([request], None)
    return results

def click_at(x, y):
    pyautogui.click(x, y, duration=0.1)

def fuzzy_match(keyword, vision_results):
    for text, bbox in vision_results:
        t_clean = text.replace(" ", "")
        if keyword in t_clean:
            return True, text, bbox
        if keyword.startswith("一键"):
            suffix = keyword[2:]
            if suffix in t_clean and any(wc in t_clean for wc in ["键", "=", "-", "i", "一", "~"]):
                return True, text, bbox
    return False, None, None

def main_qqnc():
    logging.info("=" * 22 + "开始新的一轮检查" + "=" * 22)
    
    logging.info("正在获取游戏画面")
    frame, window_rect, owner_pid = capture_wechat_mini_program("QQ经典农场", resize_to=TARGET_SIZE)
    if frame is None:
        logging.error("❌ 无法获取游戏画面")
        return

    logging.info("游戏画面获取成功,开始处理")
    
    vision_results = recognize_text_vision(frame)
    if not vision_results:
        logging.info("无可执行的任务，继续等待下一轮检查")
        logging.info("=" * 24 + "本轮巡查完毕" + "=" * 24)
        return

    recovery_tasks = []
    action_tasks = []
    
    for text, bbox in vision_results:
        for kw in RECOVERY_KEYWORDS:
            found, actual_text, _ = fuzzy_match(kw, [(text, bbox)])
            if found:
                center_x_ratio = bbox.origin.x + bbox.size.width / 2
                center_y_ratio = bbox.origin.y + bbox.size.height / 2
                screen_x = int(window_rect['X'] + center_x_ratio * window_rect['Width'])
                screen_y = int(window_rect['Y'] + (1 - center_y_ratio) * window_rect['Height'])
                
                recovery_tasks.append({
                    "keyword": kw, "actual_text": actual_text, "x": screen_x, "y": screen_y, "tag": "中心"
                })
                break
        
        else:
            for kw in FARM_ACTION_KEYWORDS:
                found, actual_text, _ = fuzzy_match(kw, [(text, bbox)])
                if found:
                    center_x_ratio = bbox.origin.x + bbox.size.width / 2
                    center_y_ratio = bbox.origin.y + bbox.size.height / 2
                    screen_x = int(window_rect['X'] + center_x_ratio * window_rect['Width'])
                    screen_y = int(window_rect['Y'] + (1 - center_y_ratio) * window_rect['Height'])
                    
                    offset_y = int(bbox.size.height * window_rect['Height'] * 1.5)
                    click_y = screen_y - offset_y
                    
                    action_tasks.append({
                        "keyword": kw, "actual_text": actual_text, "x": screen_x, "y": click_y, "tag": "上方"
                    })
                    break

    # for kw in MONITOR_KEYWORDS:
    #     found, actual_text, _ = fuzzy_match(kw, vision_results)
    #     if found:
    #         logging.info(f"监控中 [ {kw} ] (原文: {actual_text})")

    if recovery_tasks or action_tasks:
        if owner_pid:
            focus_window(owner_pid)

    if recovery_tasks:
        logging.info(f"检测到故障恢复任务: {[t['keyword'] for t in recovery_tasks]}")
        for task in recovery_tasks:
            logging.info(f"      🚨 优先执行恢复: [{task['keyword']}] -> ({task['x']}, {task['y']})")
            click_at(task['x'], task['y'])
            time.sleep(FIXED_DELAY_MS)
        
        logging.info(f"等待 {RECOVERY_WAIT} 秒以确保界面刷新...")
        time.sleep(RECOVERY_WAIT)
        
    if action_tasks:
        logging.info(f"检测到农场操作任务: {[t['keyword'] for t in action_tasks]}")
        for task in action_tasks:
            logging.info(f"      👉 执行点击: [{task['keyword']}] -> ({task['x']}, {task['y']})")
            click_at(task['x'], task['y'])
            time.sleep(FIXED_DELAY_MS)

    if not recovery_tasks and not action_tasks:
        logging.info("无可执行的任务，继续等待下一轮检查")
    
    logging.info("=" * 24 + "本轮巡查完毕" + "=" * 24)

if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info("【 📢 】 程序已启动")
    logging.info("【 💡 】 提示：按下 Ctrl+C 可在此处停止并退出程序")
    logging.info(f"【 ⚙️ 】 配置信息：")
    logging.info(f"      - 点击延时时间：{FIXED_DELAY_MS} 秒")
    logging.info(f"      - 故障恢复后等待时间：{RECOVERY_WAIT} 秒")
    logging.info(f"      - 巡查间隔时间：{LOOP_INTERVAL} 秒")
    logging.info("=" * 60)
    
    while True:
        try:
            main_qqnc()
            time.sleep(LOOP_INTERVAL)
        except KeyboardInterrupt:
            logging.info("【 ⛔ 】 用户停止程序")
            break
        except Exception as e:
            logging.error(f"程序运行异常: {e}")
            import traceback
            logging.error(traceback.format_exc())
            time.sleep(LOOP_INTERVAL)