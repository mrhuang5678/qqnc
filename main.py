import Quartz
import Vision
from Foundation import NSDictionary, NSArray
import cv2
import numpy as np
import os
import sys
import time
import random
import pyautogui
import logging
import friend
import trading
from AppKit import NSRunningApplication, NSApplicationActivateIgnoringOtherApps
from oc import get_land_pos, identify_empty_lands, find_seed_pos

# --- 全局配置 ---
DEFAULT_SEED_NAME = "迎春花"  # 默认种植种子名称
TOTAL_PATROL_COUNT = 0 # 巡查总计数
FRIEND_PATROL_INTERVAL = 20 # 好友巡查间隔次数
FRIEND_MAX_PATROL = 5      # 单次巡查的最大好友数
# 点击后等待时间随机范围（秒）
CLICK_DELAY_MIN = 0.3
CLICK_DELAY_MAX = 0.5

# 故障恢复关键词
RECOVERY_KEYWORDS = ["点击空白处关闭", "重新登录", "重新连接", "账号已在其他地方登入", "下次再来"]

# 仓库种子未找到计数器
seed_not_found_streak = 0

# 农场主要操作关键词
FARM_ACTION_KEYWORDS = ["可摘", "一键收获", "一键浇水", "一键除草", "一键除虫", "一键摘取"]

# 监控状态关键词
MONITOR_KEYWORDS = ["仓库", "商店", "好友", "好友求助"]

# 故障恢复后等待时间随机范围（秒）
RECOVERY_WAIT_MIN = 3
RECOVERY_WAIT_MAX = 5

# 巡查间隔随机范围（秒）
LOOP_INTERVAL_MIN = 5
LOOP_INTERVAL_MAX = 10

# 用于后续识别
TARGET_SIZE = (2000, 3720) 

# 配置日志格式 (默认主场)
def update_log_prefix(prefix="【巡查农场】"):
    log_format = f'%(asctime)s,%(msecs)03d - 信息 - {prefix} %(message)s'
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

update_log_prefix("【巡查农场】")
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

def get_window_center(window_rect, dx=0, dy=0):
    cx = int(window_rect['X'] + window_rect['Width'] / 2) + dx
    cy = int(window_rect['Y'] + window_rect['Height'] / 2) + dy
    return cx, cy

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
    request.setUsesLanguageCorrection_(True) # 启用语言校正
    
    handler.performRequests_error_([request], None)
    return results

def click_at(x, y):
    pyautogui.click(x, y, duration=0.1)

def fuzzy_match(keyword, vision_results):
    for text, bbox in vision_results:
        t_clean = text.replace(" ", "")
        if keyword in t_clean:
            if any(rk in keyword for rk in ["连接", "登录"]) and ("？" in t_clean or "?" in t_clean):
                continue
            return True, text, bbox
        if keyword.startswith("一键"):
            suffix = keyword[2:]
            if suffix in t_clean and any(wc in t_clean for wc in ["键", "=", "-", "i", "一", "~"]):
                return True, text, bbox
    return False, None, None

def main_qqnc():
    global TOTAL_PATROL_COUNT, seed_not_found_streak
    
    frame, window_rect, owner_pid = capture_wechat_mini_program("QQ经典农场", resize_to=TARGET_SIZE)
    if frame is None:
        logging.error("❌ 无法获取游戏画面，请确保“QQ经典农场”窗口已打开")
        return

    vision_results = recognize_text_vision(frame)
    is_in_friend_farm = any("回家" in text for text, _ in vision_results)
    
    if is_in_friend_farm:
        update_log_prefix("【好友农场】")
    else:
        update_log_prefix("【巡查农场】")
    
    if is_in_friend_farm:
        logging.info("=" * 10 + " 发现当前处于【好友农场】，执行专项巡查 " + "=" * 10)

        friend.patrol_friend_farm(window_rect, capture_wechat_mini_program, recognize_text_vision, click_at, get_window_center, RECOVERY_KEYWORDS, max_patrol=FRIEND_MAX_PATROL)
        
        mx, my = get_window_center(window_rect, dx=8, dy=350)
        pyautogui.moveTo(mx, my, duration=0.2)
        logging.info("好友场专项巡查完毕，即将开启批量出售及主场循环...")
        
        trading.batch_sell_fruits(window_rect, capture_wechat_mini_program, recognize_text_vision, click_at, get_window_center)
        
        logging.info("=" * 60)
        return

    TOTAL_PATROL_COUNT += 1
    logging.info("-" * 20 + f" 🔄 第 {TOTAL_PATROL_COUNT} 次常规巡查 " + "-" * 20)
    
    if vision_results:
        logging.info(f"【 📜 】 识别到 {len(vision_results)} 条内容：")
    else:
        logging.info("【 📜 】 未识别到有效内容")
        return

    recovery_tasks = []
    action_tasks = []
    has_harvest_action = False
    
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

    if recovery_tasks or action_tasks:
        if owner_pid:
            focus_window(owner_pid)

    if recovery_tasks:
        logging.info(f"检测到故障恢复任务: {[t['keyword'] for t in recovery_tasks]}")
        for task in recovery_tasks:
            logging.info(f"      🚨 优先执行恢复: [{task['keyword']}] -> ({task['x']}, {task['y']})")
            click_at(task['x'], task['y'])
            time.sleep(random.uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))
        
        recovery_wait = random.uniform(RECOVERY_WAIT_MIN, RECOVERY_WAIT_MAX)
        logging.info(f"等待 {recovery_wait:.2f} 秒以确保界面刷新...")
        time.sleep(recovery_wait)

    if action_tasks:
        logging.info(f"检测到农场操作任务: {[t['keyword'] for t in action_tasks]}")
        for task in action_tasks:
            if task['keyword'] in ["一键收获", "可摘"]:
                has_harvest_action = True
                
            logging.info(f"      👉 执行点击: [{task['keyword']}] -> ({task['x']}, {task['y']})")
            click_at(task['x'], task['y'])
            time.sleep(random.uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))

            for _ in range(2):
                f_c, r_c, _ = capture_wechat_mini_program("QQ经典农场", resize_to=TARGET_SIZE)
                if f_c is None: break
                vision_check = recognize_text_vision(f_c)
                match = next(((t, b, k) for t, b in vision_check for k in RECOVERY_KEYWORDS if fuzzy_match(k, [(t, b)])[0]), None)
                if not match: break
                t, b, k = match
                rx = int(r_c['X'] + (b.origin.x + b.size.width/2) * r_c['Width'])
                ry = int(r_c['Y'] + (1 - (b.origin.y + b.size.height/2)) * r_c['Height'])
                logging.info(f"      🚨 [自动恢复] 检测到 {k}，执行点击 -> ({rx}, {ry})")
                click_at(rx, ry)
                time.sleep(2.0)

    if has_harvest_action:
        logging.info("检测到收获行为，等待 3 秒以待动画完成...")
        time.sleep(3.0)
        
        cx, cy = get_window_center(window_rect, dy=-370)
        logging.info(f"👉 动作后清理干扰 -> ({cx}, {cy})")
        click_at(cx, cy)
        time.sleep(2.0)
        
        frame, window_rect, owner_pid = capture_wechat_mini_program("QQ经典农场", resize_to=TARGET_SIZE)
        if frame is None:
            logging.info("=" * 24 + "本轮巡查完毕" + "=" * 24)
            return

        empty_results = identify_empty_lands(frame, window_rect)
        
        found_any = False
        all_empty_ids = []
        for name, lands in empty_results.items():
            if lands:
                logging.info(f"      🪴 识别到空土地【{name}】：{sorted(lands)}")
                all_empty_ids.extend(lands)
                found_any = True
        
        if found_any:
            if owner_pid:
                focus_window(owner_pid)
                
            lids_queue = sorted(all_empty_ids)
            while lids_queue:
                lid = lids_queue.pop(0)
                
                rel_x1 = int(window_rect['Width'] / 2) + 35
                rel_y1 = int(window_rect['Height'] / 2) + 20
                sx, sy = get_land_pos(lid, rel_x1, rel_y1)
                
                absolute_x1, absolute_y1 = get_window_center(window_rect, dx=35, dy=20)
                tx, ty = get_land_pos(lid, absolute_x1, absolute_y1)
                
                logging.info(f"      🎯 执行空土地点击 [编号 {lid:02d}] -> ({tx}, {ty})")
                click_at(tx, ty)
                
                time.sleep(random.uniform(1.0, 1.4))
                
                new_frame, _, _ = capture_wechat_mini_program("QQ经典农场", resize_to=TARGET_SIZE)
                if new_frame is not None:
                    seed_pos, guide_pos = find_seed_pos(new_frame, window_rect, sx, sy, seed_name=DEFAULT_SEED_NAME)
                    
                    if guide_pos:
                        pyautogui.moveTo(guide_pos[0], guide_pos[1], duration=0.3)
                        time.sleep(1.2)
                    
                    if seed_pos:
                        logging.info(f"      🌱 找到种子 [{DEFAULT_SEED_NAME}]，开始【全图满扫】播种模式...")
                        
                        absolute_x1, absolute_y1 = get_window_center(window_rect, dx=35, dy=20)
                        
                        snake_land_ids = [
                            1, 2, 3, 4, 
                            8, 7, 6, 5, 
                            9, 10, 11, 12, 
                            16, 15, 14, 13, 
                            17, 18, 19, 20, 
                            24, 23, 22, 21
                        ]

                        pyautogui.moveTo(seed_pos[0], seed_pos[1], duration=0.2)
                        pyautogui.mouseDown()
                        time.sleep(0.1)
                        
                        logging.info(f"      👉 优先覆盖当前土地 {lid} ...")
                        pyautogui.moveTo(tx, ty, duration=0.1)
                        
                        logging.info(f"      👉 开始全场滑动 01 -> 24 号 ...")
                        for step_id in snake_land_ids:
                            kx, ky = get_land_pos(step_id, absolute_x1, absolute_y1)
                            pyautogui.moveTo(kx, ky, duration=0.07)
                        
                        pyautogui.mouseUp()
                        logging.info(f"      ✅ 全图满扫播种已完成。")
                        
                        cx, cy = get_window_center(window_rect, dy=-370)
                        pyautogui.moveTo(cx, cy, duration=0.3)
                        
                        seed_not_found_streak = 0
                        break
                    else:
                        cx_c, cy_c = get_window_center(window_rect, dy=-370)
                        logging.info(f"      👉 动作后清理干扰 -> ({cx_c}, {cy_c})")
                        click_at(cx_c, cy_c)
                        time.sleep(0.5)

                        seed_not_found_streak += 1
                        logging.warning(f"      ⚠️ 未在土地 {lid} 下方找到“{DEFAULT_SEED_NAME}” (连续 {seed_not_found_streak} 次)")
                        
                        if seed_not_found_streak >= 2:
                            logging.info("      🚨 连续 2 次未找到种子，触发自动购买流程...")
                            trading.buy_seeds(DEFAULT_SEED_NAME, window_rect, capture_wechat_mini_program, recognize_text_vision, click_at, get_window_center)
                            seed_not_found_streak = 0
                            lids_queue.insert(0, lid)
                            continue 
                time.sleep(1.0)
        else:
            logging.info("      ✅ 未发现可补种的空土地")
    else:
        if action_tasks:
            logging.info("本轮执行了非收获类操作，跳过补种逻辑。")

    # --- 每隔一定次数巡查后，执行好友场巡查 ---
    if not has_harvest_action and TOTAL_PATROL_COUNT >= FRIEND_PATROL_INTERVAL:
        TOTAL_PATROL_COUNT = 0
        
        target_keyword = None
        for text, bbox in vision_results:
            if "好友求助" in text:
                target_keyword = "好友求助"
                break
            if not target_keyword and "好友" in text:
                target_keyword = "好友"
        
        if target_keyword:
            for text, bbox in vision_results:
                if target_keyword in text:
                    cx_r = bbox.origin.x + bbox.size.width / 2
                    cy_r = bbox.origin.y + bbox.size.height / 2
                    sx = int(window_rect['X'] + cx_r * window_rect['Width'])
                    sy = int(window_rect['Y'] + (1 - cy_r) * window_rect['Height'])
                    
                    logging.info(f"👉 点击主界面“{target_keyword}”入口 -> ({sx}, {sy})")
                    click_at(sx, sy)
                    break
            
            if target_keyword == "好友求助":
                time.sleep(5.0)
                logging.info(f"【 🚀 】 正在跳转至好友农场...")
                logging.info("=" * 24 + "本轮巡查完毕" + "=" * 24)
                return
            else:
                time.sleep(5.0)
                if friend.select_first_friend(window_rect, capture_wechat_mini_program, recognize_text_vision, click_at, get_window_center):
                    logging.info(f"【 🚀 】 正在进入好友列表并拜访...")
                    logging.info("=" * 24 + "本轮巡查完毕" + "=" * 24)
                    return
        else:
            logging.warning("未在主界面识别到“好友”或“好友求助”按钮。")

    if not recovery_tasks and not action_tasks:
        if TOTAL_PATROL_COUNT > 0: 
            logging.info("无可执行的任务，继续等待下一轮检查")
    
    logging.info("=" * 24 + "本轮巡查完毕" + "=" * 24)

if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info("【 📢 】 程序已启动")
    
    # 获取游戏窗口的真实参考大小 - 默认游戏参考大小：473x884
    frame, _, _ = capture_wechat_mini_program("QQ经典农场")
    if frame is not None:
        h, w = frame.shape[:2]
        game_size_info = f"{w}x{h}"
    else:
        game_size_info = "未获取到（请确保窗口已打开）"

    logging.info("【 💡 】 提示：按下 Ctrl+C 可在此处停止并退出程序")
    logging.info(f"【 ⚙️ 】 配置信息：")
    logging.info(f"      - 游戏参考大小：{game_size_info}")
    logging.info(f"      - 默认种植种子：{DEFAULT_SEED_NAME}")
    logging.info(f"      - 巡查好友总数：{FRIEND_MAX_PATROL} 名")
    logging.info(f"      - 好友巡查触发：每 {FRIEND_PATROL_INTERVAL} 次主场巡查后")
    logging.info(f"      - 点击延时时间：{CLICK_DELAY_MIN}–{CLICK_DELAY_MAX} 秒（随机）")
    logging.info(f"      - 故障恢复后等待时间：{RECOVERY_WAIT_MIN}–{RECOVERY_WAIT_MAX} 秒（随机）")
    logging.info(f"      - 巡查间隔时间：{LOOP_INTERVAL_MIN}–{LOOP_INTERVAL_MAX} 秒（随机）")
    logging.info("=" * 60)
    
    while True:
        try:
            main_qqnc()
            time.sleep(random.uniform(LOOP_INTERVAL_MIN, LOOP_INTERVAL_MAX))
        except KeyboardInterrupt:
            logging.info("【 ⛔ 】 用户停止程序")
            break
        except Exception as e:
            logging.error(f"程序运行异常: {e}")
            import traceback
            logging.error(traceback.format_exc())
            time.sleep(random.uniform(LOOP_INTERVAL_MIN, LOOP_INTERVAL_MAX))