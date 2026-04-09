import time
import logging

def batch_sell_fruits(window_rect, capture_fn, recognize_fn, click_fn, get_center_fn):

    logging.info("--- 🚀 开始执行：批量出售果实过程 ---")

    frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
    if frame is None: return
    results = recognize_fn(frame)
    
    warehouse_btn = next(((t, b) for t, b in results if "仓库" in t.replace(" ", "")), None)
    if not warehouse_btn:
        logging.warning("【交易】未能在主界面找到“仓库”按钮，终止出售流程。")
        return
    
    t, b = warehouse_btn
    cx = int(rect['X'] + (b.origin.x + b.size.width/2) * rect['Width'])
    cy = int(rect['Y'] + (1-(b.origin.y + b.size.height/2)) * rect['Height'])
    logging.info(f"      👉 点击 [仓库] -> ({cx}, {cy})")
    click_fn(cx, cy)
    
    logging.info("等待 3 秒加载仓库界面...")
    time.sleep(3.0)
    
    frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
    if frame is None: return
    results = recognize_fn(frame)
    
    if any("没有果实了" in t.replace(" ", "") for t, b in results):
        logging.info("【交易】识别到“没有果实了”，直接退出仓库。")
        close_ui(window_rect, click_fn, get_center_fn)
        return

    batch_btn = next(((t, b) for t, b in results if "批量出售" in t.replace(" ", "")), None)
    if not batch_btn:
        logging.warning("【交易】进入仓库后未找到“批量出售”按钮。")
        close_ui(window_rect, click_fn, get_center_fn)
        return
    
    t, b = batch_btn
    cx = int(rect['X'] + (b.origin.x + b.size.width/2) * rect['Width'])
    cy = int(rect['Y'] + (1-(b.origin.y + b.size.height/2)) * rect['Height'])
    logging.info(f"      👉 点击 [批量出售] -> ({cx}, {cy})")
    click_fn(cx, cy)
    time.sleep(1.5)
    
    frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
    if frame is None: return
    results = recognize_fn(frame)
    
    confirm_btn = next(((t, b) for t, b in results if "确认" in t.replace(" ", "")), None)
    if not confirm_btn:
        logging.warning("【交易】未找到出售“确认”按钮。")
        close_ui(window_rect, click_fn, get_center_fn)
        return
    
    t, b = confirm_btn
    cx = int(rect['X'] + (b.origin.x + b.size.width/2) * rect['Width'])
    cy = int(rect['Y'] + (1-(b.origin.y + b.size.height/2)) * rect['Height'])
    logging.info(f"      👉 点击 [确认] 出售 -> ({cx}, {cy})")
    click_fn(cx, cy)
    
    time.sleep(2.0)
    
    close_ui(window_rect, click_fn, get_center_fn)
    logging.info("--- ✅ 批量出售果实流程已完成 ---")

def close_ui(window_rect, click_fn, get_center_fn):
    cx, cy = get_center_fn(window_rect, dy=-370)
    logging.info(f"      👉 关闭窗口 -> ({cx}, {cy})")
    click_fn(cx, cy)
    time.sleep(0.3)
    click_fn(cx, cy)
    time.sleep(1.0)

def buy_seeds(seed_name, window_rect, capture_fn, recognize_fn, click_fn, get_center_fn):

    logging.info("-" * 15 + f" 🚀 开始执行：购买 {seed_name} 种子 " + "-" * 15)
    
    frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
    if frame is None: return
    results = recognize_fn(frame)
    
    store_btn = next(((t, b) for t, b in results if "商店" in t.replace(" ", "")), None)
    if not store_btn:
        logging.warning("【商店】未能在界面找到“商店”按钮。")
        return
    
    t, b = store_btn
    cx = int(rect['X'] + (b.origin.x + b.size.width/2) * rect['Width'])
    cy = int(rect['Y'] + (1-(b.origin.y + b.size.height/2)) * rect['Height'])
    logging.info(f"      👉 点击 [商店] -> ({cx}, {cy})")
    click_fn(cx, cy)
    
    logging.info("等待 3 秒加载商店界面...")
    time.sleep(3.0)
    
    import pyautogui
    for i in range(4):
        frame, rect, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
        if frame is None: break
        results = recognize_fn(frame)
        
        target_seed = next(((t, b) for t, b in results if seed_name in t.replace(" ", "")), None)
        if target_seed:
            t, b = target_seed
            scx = int(rect['X'] + (b.origin.x + b.size.width/2) * rect['Width'])
            scy = int(rect['Y'] + (1-(b.origin.y + b.size.height/2)) * rect['Height'])
            logging.info(f"      ✨ 找到种子 [{seed_name}] -> ({scx}, {scy})，执行购买...")
            click_fn(scx, scy)
            time.sleep(3)
            frame_post, rect_post, _ = capture_fn("QQ经典农场", resize_to=(2000, 3720))
            if frame_post is None: break
            results_post = recognize_fn(frame_post)
            
            buy_confirm = next(((t, b) for t, b in results_post if any(k in t for k in ["确定", "确认"])), None)
            if buy_confirm:
                tk, bk = buy_confirm
                ccx = int(rect_post['X'] + (bk.origin.x + bk.size.width/2) * rect_post['Width'])
                ccy = int(rect_post['Y'] + (1-(bk.origin.y + bk.size.height/2)) * rect_post['Height'])
                logging.info(f"      👉 点击 [确认] 按钮 -> ({ccx}, {ccy})")
                click_fn(ccx, ccy)
                time.sleep(1.0)
            
            logging.info(f"      ✅ 购买种子 [{seed_name}] 处理完毕。")
            break
            
        if i < 3: 
            logging.info(f"      ⚠️ 未发现种子，执行第 {i+1} 次按住下滑...")
            mcx, mcy = get_center_fn(window_rect)
            pyautogui.moveTo(mcx, mcy)
            pyautogui.mouseDown()
            pyautogui.moveTo(mcx, mcy + 260, duration=1.2)
            time.sleep(0.5)
            pyautogui.mouseUp()
            time.sleep(2.0)
        else:
            logging.warning(f"      ❌ 已滑动 3 次，仍未找到种子 [{seed_name}]。")

    time.sleep(2.0)
    close_ui(window_rect, click_fn, get_center_fn)
    logging.info("-" * 17 + f" 🚀 购买 {seed_name} 种子 结束 " + "-" * 17)
