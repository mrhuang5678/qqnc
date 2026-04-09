import cv2
import numpy as np
import os
import logging

# 土地网格坐标偏移
COL_DX = 38.0
COL_DY = 20.0
ROW_DX = 38.0
ROW_DY = 20.0

# 种子识别阈值
SCALE = 0.35

# 播种界面寻找偏移
SEED_OFFSET_Y = 70.0

# 默认巡查的土地编号（方便修改）
TARGET_LANDS = [1, 5, 6, 9, 10, 11, 13, 14, 15, 16, 18, 19, 20, 23, 24]

# 模板文件基础路径
LAND_TEMPLATE_DIR = "./templates/land/"
SEED_TEMPLATE_DIR = "./templates/seed/"

# 土地模板
TEMPLATES = {
    "黑": os.path.join(LAND_TEMPLATE_DIR, "黑.png"),
    "红": os.path.join(LAND_TEMPLATE_DIR, "红.png"),
    "金": os.path.join(LAND_TEMPLATE_DIR, "金.png"),
}

# 每种土地的特征参数
FEATURES = {
    # 颜色类型: {匹配门槛, 整体标准差上限, [中心检测开关, 中心标准差上限, 绿色像素上限, 颜色偏离门槛, 边缘点数上限]}
    "黑": {"threshold": 0.72, "purity_limit": 55.0, "center_check": True, "center_std": 8.0, "green_limit": 3, "diff_limit": 80.0, "edge_limit": 12},
    "红": {"threshold": 0.72, "purity_limit": 40.0, "center_check": False},
    "金": {"threshold": 0.64, "purity_limit": 25.0, "center_check": False},
}

def get_land_pos(land_id, x1, y1):
    row = (land_id - 1) // 4
    col = (land_id - 1) % 4
    target_x = x1 + (col * COL_DX) - (row * ROW_DX)
    target_y = y1 + (col * COL_DY) + (row * ROW_DY)
    return int(target_x), int(target_y)

def calculate_purity(crop):
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return np.std(gray)

def check_center_status(crop):
    ch, cw = crop.shape[:2]
    roi_w, roi_h = 35, 30
    x1 = max(0, cw // 2 - roi_w // 2)
    y1 = max(0, ch // 2 - roi_h // 2)
    roi = crop[y1:y1+roi_h, x1:x1+roi_w]
    
    gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    center_std = np.std(gray_roi)
    
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_green = np.array([35, 30, 30])
    upper_green = np.array([90, 255, 255])
    mask = cv2.inRange(hsv, lower_green, upper_green)
    green_pixels = cv2.countNonZero(mask)
    
    avg_total = np.mean(crop, axis=(0, 1))
    avg_roi = np.mean(roi, axis=(0, 1))
    color_diff = np.linalg.norm(avg_total - avg_roi)
    
    edges = cv2.Canny(gray_roi, 20, 60)
    edge_count = cv2.countNonZero(edges)
    
    return center_std, green_pixels, color_diff, edge_count

def identify_empty_lands(frame, window_rect):
    scale_x = frame.shape[1] / window_rect['Width']
    scale_y = frame.shape[0] / window_rect['Height']
    base_x1_rel = int(window_rect['Width'] / 2) + 35
    base_y1_rel = int(window_rect['Height'] / 2) + 20
    
    empty_results = {"黑": [], "红": [], "金": []}
    
    template_imgs = {}
    for name, path in TEMPLATES.items():
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is not None:
                template_imgs[name] = img

    if not template_imgs:
        return empty_results

    logging.info(f"正在识别指定土地 {TARGET_LANDS} 是否有空土地...")

    for lid in TARGET_LANDS:
        sx, sy = get_land_pos(lid, base_x1_rel, base_y1_rel)
        fx, fy = int(sx * scale_x), int(sy * scale_y)
        
        cw, ch = 120, 100
        y_start, y_end = max(0, fy - ch // 2), min(frame.shape[0], fy + ch // 2)
        x_start, x_end = max(0, fx - cw // 2), min(frame.shape[1], fx + cw // 2)
        
        land_crop = frame[y_start:y_end, x_start:x_end]

        valid_candidates = []
        raw_best_name, raw_best_val = None, -1
        
        for name, t_img in template_imgs.items():
            res = cv2.matchTemplate(land_crop, t_img, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(res)
            
            if max_val > raw_best_val:
                raw_best_val, raw_best_name = max_val, name
                
            if max_val >= FEATURES[name]["threshold"]:
                valid_candidates.append((name, max_val))

        best_name, best_val = None, -1
        if valid_candidates:
            best_name, best_val = max(valid_candidates, key=lambda x: x[1])
        else:
            best_name, best_val = raw_best_name, raw_best_val

        std_dev = calculate_purity(land_crop)
        
        if best_name and best_val >= FEATURES[best_name]["threshold"]:
            feat = FEATURES[best_name]
            limit = feat["purity_limit"]
            
            if std_dev > limit:
                continue
                
            if feat.get("center_check"):
                c_std, g_pix, c_diff, e_cnt = check_center_status(land_crop)
                c_std_limit = feat.get("center_std", 25.0)
                g_limit = feat.get("green_limit", 10)
                d_limit = feat.get("diff_limit", 70.0)
                e_limit = feat.get("edge_limit", 50)
                
                is_planted = (g_pix > g_limit) or (c_std > c_std_limit) or (c_diff > d_limit) or (e_cnt > e_limit)
                
                if is_planted:
                    continue
            else:
                pass

            empty_results[best_name].append(lid)
        else:
            pass

    return empty_results

def find_seed_pos(frame, window_rect, land_sx, land_sy, seed_name):

    scale_x = frame.shape[1] / window_rect['Width']
    scale_y = frame.shape[0] / window_rect['Height']
    
    path = os.path.join(SEED_TEMPLATE_DIR, f"seed_{seed_name}.png")
    if not os.path.exists(path):
        return None, None
    
    t_img_raw = cv2.imread(path)
    if t_img_raw is None:
        return None, None
    
    center_sy = land_sy + SEED_OFFSET_Y
    fy = int(center_sy * scale_y)
    
    roi_h, x_end = 450, frame.shape[1]
    y_start, y_end = max(0, fy - roi_h // 2), min(frame.shape[0], fy + roi_h // 2)
    roi = frame[y_start:y_end, 0:x_end]
    
    guide_x = int(window_rect['X'] + window_rect['Width'] / 2)
    guide_y = int(window_rect['Y'] + center_sy)
    
    best_max_val = -1
    best_max_loc = (0, 0)
    best_t_size = (0, 0)
    
    scales = [0.9, 0.95, 1.0, 1.05, 1.1]
    for sc in scales:
        th, tw = t_img_raw.shape[:2]
        new_th, new_tw = int(th * sc), int(tw * sc)
        if new_th > roi.shape[0] or new_tw > roi.shape[1]: continue
            
        t_img_scaled = cv2.resize(t_img_raw, (new_tw, new_th), interpolation=cv2.INTER_LANCZOS4)
        res = cv2.matchTemplate(roi, t_img_scaled, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        
        if max_val > best_max_val:
            best_max_val = max_val
            best_max_loc = max_loc
            best_t_size = (new_tw, new_th)

    logging.info(f"      🌱 全屏横向搜索 (多尺度) - [{seed_name}] 最高分: {best_max_val:.2f}")
    
    if best_max_val >= SCALE:
        seed_rx = best_max_loc[0] + best_t_size[0] // 2
        seed_ry = best_max_loc[1] + best_t_size[1] // 2

        seed_fx, seed_fy = seed_rx, y_start + seed_ry
        
        screen_x = int(window_rect['X'] + seed_fx / scale_x)
        screen_y = int(window_rect['Y'] + seed_fy / scale_y)
        return (screen_x, screen_y), (guide_x, guide_y)
    
    return None, (guide_x, guide_y)
