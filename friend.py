import time
import random
import logging
import pyautogui

# 好友场操作关键词
FRIEND_ACTION_KEYWORDS = ["一键浇水", "一键除草", "一键除虫", "一键摘取"]

# 拜访关键词
VISIT_KEYWORDS = ["拜访"]

# 返回主场关键词
BACK_HOME_KEYWORDS = ["回家"]

# 故障恢复关键词
RECOVERY_KEYWORDS = ["点击空白处关闭", "重新登录", "重新连接", "账号已在其他地方登入", "下次再来"]

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

def select_first_friend(window_rect, capture_fn, recognize_fn, click_fn, get_center_fn):
    
    logging.info("正在搜索可拜访的好友...")
    
    frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
    if frame is None:
        return False
        
    results = recognize_fn(frame)
    visit_buttons = []
    
    for text, bbox in results:
        if any(v in text for v in VISIT_KEYWORDS):
            center_x_ratio = bbox.origin.x + bbox.size.width / 2
            center_y_ratio = bbox.origin.y + bbox.size.height / 2
            
            screen_x = int(rect['X'] + center_x_ratio * rect['Width'])
            screen_y = int(rect['Y'] + (1 - center_y_ratio) * rect['Height'])

            visit_buttons.append({"x": screen_x, "y": screen_y, "top": bbox.origin.y})

    if not visit_buttons:
        logging.warning("未找到任何“拜访”按钮。")
        cx, cy = get_center_fn(window_rect, dy=-370)
        logging.info(f"      👉 关闭窗口 -> ({cx}, {cy})")
        click_fn(cx, cy)
        return False

    visit_buttons.sort(key=lambda t: t['top'], reverse=True)
    
    target = visit_buttons[0]
    logging.info(f"👉 点击第一个好友拜访 -> ({target['x']}, {target['y']})")
    click_fn(target['x'], target['y'])
    return True

def patrol_friend_farm(window_rect, capture_fn, recognize_fn, click_fn, get_center_fn, recovery_keywords, max_patrol=5):
    current_count = 1
    
    while current_count <= max_patrol:
        logging.info("-" * 19 + f" 🔄 第 {current_count} 好友农场巡查 " + "-" * 19)

        if current_count == 1:
            _, loc_y = get_center_fn(rect if 'rect' in locals() else window_rect, dy=350)

            loc_x = int((rect if 'rect' in locals() else window_rect)['X'] + (rect if 'rect' in locals() else window_rect)['Width'] * 0.16)
            logging.info(f"👉 强化定位第 1 名好友: 1号位 -> ({loc_x}, {loc_y})")
            click_fn(loc_x, loc_y)
            time.sleep(0.5)
            click_fn(loc_x, loc_y)
            time.sleep(3.0)

        frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
        if frame is None:
            logging.error("无法获取好友农场画面，终止巡查。")
            break
            
        results = recognize_fn(frame)
        if not results:
            logging.warning("未能识别到任何文字内容。")
            break

        match = next(((t, b, rk) for t, b in results for rk in recovery_keywords if fuzzy_match(rk, [(t, b)])[0]), None)
        if match:
            t, b, k = match
            rx = int(rect['X'] + (b.origin.x + b.size.width/2) * rect['Width'])
            ry = int(rect['Y'] + (1 - (b.origin.y + b.size.height/2)) * rect['Height'])
            logging.info(f"🚨 发现异常提示 [{k}]，执行精准点击 -> ({rx}, {ry})")
            click_fn(rx, ry)
            time.sleep(5.0 if any(x in k for x in ["登录", "连接"]) else 2.0)
            continue

        task_list = []
        for kw in FRIEND_ACTION_KEYWORDS:
            found, actual_text, bbox = fuzzy_match(kw, results)
            if found:
                task_list.append({"keyword": kw, "actual_text": actual_text, "bbox": bbox})
        
        if task_list:
            logging.info(f"检测到好友农场可执行任务: {[t['keyword'] for t in task_list]}")
            for task in task_list:
                kw = task['keyword']
                bbox = task['bbox']
                center_x_ratio = bbox.origin.x + bbox.size.width / 2
                center_y_ratio = bbox.origin.y + bbox.size.height / 2
                screen_x = int(rect['X'] + center_x_ratio * rect['Width'])
                screen_y = int(rect['Y'] + (1 - center_y_ratio) * rect['Height'])
                
                offset_y = int(bbox.size.height * rect['Height'] * 1.5)
                click_y = screen_y - offset_y
                
                logging.info(f"✨ 执行操作: [{kw}] -> ({screen_x}, {click_y})")
                click_fn(screen_x, click_y)
                time.sleep(random.uniform(0.6, 1.0))

                for _ in range(2):
                    f_c, r_c, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
                    if f_c is None: break
                    match = next(((t, b, rk) for t, b in recognize_fn(f_c) for rk in recovery_keywords if fuzzy_match(rk, [(t, b)])[0]), None)
                    if not match: break
                    t, b, k = match
                    rx = int(r_c['X'] + (b.origin.x + b.size.width/2) * r_c['Width'])
                    ry = int(r_c['Y'] + (1 - (b.origin.y + b.size.height/2)) * r_c['Height'])
                    logging.info(f"      🚨 [自动恢复] 检测到 [{k}] -> ({rx}, {ry})")
                    click_fn(rx, ry)
                    time.sleep(5.0 if any(x in k for x in ["登录", "连接"]) else 2.0)
        else:
            logging.info("本农场暂无可执行任务。")

        if current_count >= max_patrol:
            logging.info(f"✅ 已完成预设的 {max_patrol} 名好友巡查。")
            break

        _, next_y = get_center_fn(rect, dy=350) 
        
        if current_count == 1:
            next_x_ratio = 0.40
            layout_name = "2号位"
        elif current_count == 2:
            next_x_ratio = 0.64
            layout_name = "3号位"
        else:
            next_x_ratio = 0.74
            layout_name = "后面位置"
            
        next_x = int(rect['X'] + rect['Width'] * next_x_ratio)
        logging.info(f"👉 准备切换下一位好友: {layout_name} -> ({next_x}, {next_y})")
        click_fn(next_x, next_y)
        time.sleep(5.0)
        
        current_count += 1

    logging.info("正在寻找“回家”按钮返回主农场...")
    frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
    if frame is not None:
        results = recognize_fn(frame)
        for text, bbox in results:
            if any(b in text for b in BACK_HOME_KEYWORDS):
                center_x_ratio = bbox.origin.x + bbox.size.width / 2
                center_y_ratio = bbox.origin.y + bbox.size.height / 2
                screen_x = int(rect['X'] + center_x_ratio * rect['Width'])
                screen_y = int(rect['Y'] + (1 - center_y_ratio) * rect['Height'])
                
                logging.info(f"👉 点击返回主场 -> ({screen_x}, {screen_y})")
                click_fn(screen_x, screen_y)
                time.sleep(2.0)
                return True
                
    bx, by = int(rect['X'] + 60), int(rect['Y'] + rect['Height'] - 60)
    logging.warning("未识别到返回按钮，尝试点击左下角退出...")
    click_fn(bx, by)
    time.sleep(2.0)
    return True