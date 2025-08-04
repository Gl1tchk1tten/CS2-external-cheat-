import json
import pymem.process
import os
import win32api
import win32con
import ctypes
import win32gui
import win32process
import threading
import time
import keyboard
import random
import psutil
import sys
import requests
from pynput.mouse import Controller, Button
from PySide6 import QtWidgets, QtGui, QtCore

last_positions = [{} for _ in range(64)]

bone_color = QtGui.QColor(0, 255, 0)
box_color = QtGui.QColor(255, 0, 0)


def bones1(pm, ent, view_matrix, width, height):
    bones = {}
    try:
        node = pm.read_longlong(ent + m_pGameSceneNode)
        bone_matrix = pm.read_longlong(node + m_modelState + 0x80)
        if not bone_matrix:
            print("[ERROR] ❌ bone_matrix invalide")
            return None

        bone_ids = {
            "head": 6, "neck": 5, "spine": 4, "pelvis": 0,
            "l_shoulder": 13, "l_elbow": 14, "l_hand": 15,
            "r_shoulder": 9,  "r_elbow": 10, "r_hand": 11,
            "l_knee": 26, "l_foot": 27,
            "r_knee": 23, "r_foot": 24
        }

        for name, idx in bone_ids.items():
            x = pm.read_float(bone_matrix + idx * 0x20)
            y = pm.read_float(bone_matrix + idx * 0x20 + 4)
            z = pm.read_float(bone_matrix + idx * 0x20 + 8)
            screen = w2s(view_matrix, x, y, z, width, height)
            if screen:
                bones[name] = screen

        return bones if "head" in bones else None
    except Exception as e:
        print(f"[ERROR] Bone read exception: {e}")
        return None

mouse = Controller()


aim_enabled = False
aim_key_code = 0x06       
trigger_key_code = 0x06   
trigger_enabled = False
esp_enabled = True
aim_radius = 120
aim_smooth = 6
aim_target = "head"
esp_mode_mode = 1  



if getattr(sys, 'frozen', False):
    application_path = sys._MEIPASS
else:
    application_path = os.path.dirname(os.path.abspath(__file__))


def load_json_from_url(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"[ERROR] ❌ Impossible de charger {url} : {e}")
        exit(1)

offsets = load_json_from_url("https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/offsets.json")
client_dll = load_json_from_url("https://raw.githubusercontent.com/a2x/cs2-dumper/main/output/client_dll.json")

dwEntityList = offsets['client.dll']['dwEntityList']
dwLocalPlayerPawn = offsets['client.dll']['dwLocalPlayerPawn']
dwViewMatrix = offsets['client.dll']['dwViewMatrix']

m_entitySpottedState = client_dll['client.dll']['classes']['C_CSPlayerPawn']['fields']['m_entitySpottedState']
m_bSpottedByMask = client_dll['client.dll']['classes']['EntitySpottedState_t']['fields']['m_bSpottedByMask']
m_modelState = client_dll['client.dll']['classes']['CSkeletonInstance']['fields']['m_modelState']

m_pCSkeletonInstance = client_dll['client.dll']['classes']['C_BaseEntity']['fields'].get('m_pCSkeletonInstance', 0x1C8)
m_pGameSceneNode = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_pGameSceneNode']

m_iTeamNum = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_iTeamNum']
m_iHealth = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_iHealth']
m_lifeState = client_dll['client.dll']['classes']['C_BaseEntity']['fields']['m_lifeState']
m_hPlayerPawn = client_dll['client.dll']['classes']['CCSPlayerController']['fields']['m_hPlayerPawn']
m_vecAbsOrigin = client_dll['client.dll']['classes']['CGameSceneNode']['fields']['m_vecAbsOrigin']
m_iIDEntIndex = client_dll['client.dll']['classes']['C_CSPlayerPawnBase']['fields']['m_iIDEntIndex']
m_iszPlayerName = client_dll['client.dll']['classes']['CBasePlayerController']['fields']['m_iszPlayerName']

def w2s(matrix, x, y, z, width, height):
    clip_x = matrix[0] * x + matrix[1] * y + matrix[2] * z + matrix[3]
    clip_y = matrix[4] * x + matrix[5] * y + matrix[6] * z + matrix[7]
    clip_w = matrix[12] * x + matrix[13] * y + matrix[14] * z + matrix[15]

    if clip_w <= 0.1:
        return None

    ndc_x = clip_x / clip_w
    ndc_y = clip_y / clip_w

    screen_x = (width / 2) * (ndc_x + 1)
    screen_y = (height / 2) * (1 - ndc_y)

    if not (0 <= screen_x <= width) or not (0 <= screen_y <= height):
        return None

    return (screen_x, screen_y)


class OverlayWindow(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setGeometry(0, 0, win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1))
        hwnd = int(self.winId())
        style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x80000 | 0x20)
        self.players = []
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update)
        self.timer.start(16)

    def set_players(self, players):  
        self.players = players



    def paintEvent(self, event):
        if not esp_enabled or esp_mode_mode == 3:
            return

        painter = QtGui.QPainter(self)
        center_x = self.width() // 2
        center_y = self.height() // 2

        for p in self.players:
            x, y, h, name, bones, is_visible = p
            w = h / 2

            if esp_mode_mode in [0, 2]:
                painter.setPen(QtGui.QPen(box_color, 2))
                painter.drawRect(int(x - w / 2), int(y), int(w), int(h))
                painter.setPen(QtCore.Qt.white)
                painter.setFont(QtGui.QFont("Arial", 10, QtGui.QFont.Bold))
                painter.drawText(int(x - w / 2), int(y - 5), name)

            if esp_mode_mode in [1, 2]:
                painter.setPen(QtGui.QPen(bone_color, 2))
                for (x1, y1), (x2, y2) in bones:
                    painter.drawLine(int(x1), int(y1), int(x2), int(y2))

            if "head" in bones:
                head_x, head_y = bones["head"]
            elif "neck" in bones:
                head_x, head_y = bones["neck"]
            else:
                continue  
            radius = 15  
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 0, 0), 2)) 
            painter.drawEllipse(int(head_x) - radius, int(head_y) - radius, 2 * radius, 2 * radius)

        painter.end()



def esp(pm, client, overlay):
    while True:
        try:
            width = win32api.GetSystemMetrics(0)
            height = win32api.GetSystemMetrics(1)
            view_matrix = [pm.read_float(client + dwViewMatrix + i * 4) for i in range(16)]
            local = pm.read_longlong(client + dwLocalPlayerPawn)
            if not local:
                time.sleep(0.01)
                continue

            team = pm.read_int(local + m_iTeamNum)
            local_index = pm.read_int(local + 0x64)
            entlist = pm.read_longlong(client + dwEntityList)
            baseptr = pm.read_longlong(entlist + 0x10)
            players = []

            for i in range(1, 64):
                try:
                    ec = pm.read_longlong(baseptr + 0x78 * (i & 0x1FF))
                    if not ec:
                        continue

                    pawn = pm.read_longlong(ec + m_hPlayerPawn)
                    if not pawn or pawn == local:
                        continue

                    entry = pm.read_longlong(entlist + 0x8 * ((pawn & 0x7FFF) >> 9) + 0x10)
                    ent = pm.read_longlong(entry + 0x78 * (pawn & 0x1FF))
                    if not ent:
                        continue

                    hp = pm.read_int(ent + m_iHealth)
                    state = pm.read_int(ent + m_lifeState)
                    eteam = pm.read_int(ent + m_iTeamNum)
                    if hp <= 0 or state != 256 or eteam == team:
                        continue

                    name = pm.read_string(ec + m_iszPlayerName, 32)
                    bones = bones1(pm, ent, view_matrix, width, height)

                    if not bones or "head" not in bones:
                        continue

                    head = bones["head"]
                    if "r_foot" in bones:
                        foot = bones["r_foot"]
                    elif "pelvis" in bones:
                        foot = bones["pelvis"]
                    else:
                        foot = (head[0], head[1] + 80)

                    box_height = abs(foot[1] - head[1])
                    if box_height < 10 or box_height > 500:
                        box_height = 90  

                    bone_lines = []
                    connections = [
                        ("head", "neck"), ("neck", "spine"), ("spine", "pelvis"),
                        ("pelvis", "l_knee"), ("l_knee", "l_foot"),
                        ("pelvis", "r_knee"), ("r_knee", "r_foot"),
                        ("neck", "l_shoulder"), ("l_shoulder", "l_elbow"), ("l_elbow", "l_hand"),
                        ("neck", "r_shoulder"), ("r_shoulder", "r_elbow"), ("r_elbow", "r_hand")
                    ]
                    for a, b in connections:
                        if a in bones and b in bones:
                            bone_lines.append((bones[a], bones[b]))

                    try:
                        spotted_mask = pm.read_uint(pawn + m_entitySpottedState + m_bSpottedByMask)
                        is_visible = (spotted_mask & (1 << local_index)) != 0
                    except:
                        is_visible = False

                    players.append((head[0], head[1], box_height, name, bone_lines, is_visible))

                except:
                    continue

            overlay.set_players(players)
            overlay.update()
            time.sleep(0.03)
        except:
            time.sleep(0.1)


 
def trigger(pm, client):
    global trigger_enabled, trigger_key_code
    trigger_delay = 0.005
    max_shots = 3
    shot_count = 0
    cooldown_time = 0.1
    last_shot_time = time.time()

    screen_center = (
        win32api.GetSystemMetrics(0) // 2,
        win32api.GetSystemMetrics(1) // 2
    )
    trigger_fov = 5

    while True:
        try:
            if not trigger_enabled or not win32api.GetAsyncKeyState(trigger_key_code) & 0x8000:
                time.sleep(0.01)
                continue

            local = pm.read_longlong(client + dwLocalPlayerPawn)
            if not local:
                continue

            ent_id = pm.read_int(local + m_iIDEntIndex)
            if ent_id <= 0:
                continue

            entlist = pm.read_longlong(client + dwEntityList)
            ent_entry = pm.read_longlong(entlist + 0x8 * (ent_id >> 9) + 0x10)
            entity = pm.read_longlong(ent_entry + 0x78 * (ent_id & 0x1FF))
            if not entity:
                continue

            hp = pm.read_int(entity + m_iHealth)
            eteam = pm.read_int(entity + m_iTeamNum)
            pteam = pm.read_int(local + m_iTeamNum)
            if hp <= 0 or eteam == pteam:
                continue

            width, height = win32api.GetSystemMetrics(0), win32api.GetSystemMetrics(1)
            view_matrix = [pm.read_float(client + dwViewMatrix + i * 4) for i in range(16)]
            bones = bones1(pm, entity, view_matrix, width, height)
            if not bones or "head" not in bones:
                continue

            head_x, head_y = bones["head"]
            dist_x = abs(screen_center[0] - head_x)
            dist_y = abs(screen_center[1] - head_y)

            if dist_x < trigger_fov and dist_y < trigger_fov:
                if shot_count < max_shots and (time.time() - last_shot_time) > trigger_delay:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    time.sleep(0.015)
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    shot_count += 1

                if shot_count >= max_shots:
                    last_shot_time = time.time()
                    shot_count = 0

            time.sleep(trigger_delay)
        except Exception as e:
            print(f"[ERROR] Exception in trigger function: {e}")
            time.sleep(0.1)



def visible(pm, local_index, pawn):
    try:
        spotted_mask = pm.read_uint(pawn + m_entitySpottedState + m_bSpottedByMask)
        return (spotted_mask & (1 << local_index)) != 0
    except:
        return False


def softaim(pm, client):
    global aim_radius, aim_smooth, aim_target, aim_key_code

    while True:
        try:
            if not aim_enabled or not win32api.GetAsyncKeyState(aim_key_code) & 0x8000:
                time.sleep(0.01)
                continue

            width = win32api.GetSystemMetrics(0)
            height = win32api.GetSystemMetrics(1)
            center_x = width // 2
            center_y = height // 2

            view_matrix = [pm.read_float(client + dwViewMatrix + i * 4) for i in range(16)]
            local = pm.read_longlong(client + dwLocalPlayerPawn)
            if not local:
                time.sleep(0.01)
                continue

            team = pm.read_int(local + m_iTeamNum)
            local_index = pm.read_int(local + 0x64)
            entlist = pm.read_longlong(client + dwEntityList)
            baseptr = pm.read_longlong(entlist + 0x10)

            best_target = None
            closest_dist = 9999

            for i in range(1, 64):
                try:
                    ec = pm.read_longlong(baseptr + 0x78 * (i & 0x1FF))
                    if not ec:
                        continue

                    pawn = pm.read_longlong(ec + m_hPlayerPawn)
                    if not pawn or pawn == local:
                        continue

                    entry = pm.read_longlong(entlist + 0x8 * ((pawn & 0x7FFF) >> 9) + 0x10)
                    ent = pm.read_longlong(entry + 0x78 * (pawn & 0x1FF))
                    if not ent:
                        continue

                    hp = pm.read_int(ent + m_iHealth)
                    state = pm.read_int(ent + m_lifeState)
                    eteam = pm.read_int(ent + m_iTeamNum)
                    if hp <= 0 or state != 256 or eteam == team:
                        continue

                    bones = bones1(pm, ent, view_matrix, width, height)
                    if not bones:
                        continue

                    target_bone = "head" if aim_target == "head" else "pelvis"
                    if target_bone not in bones:
                        continue

                    x, y = bones[target_bone]

                    if not (0 <= x <= width and 0 <= y <= height):
                        continue

                    enemy_node = pm.read_longlong(ent + m_pGameSceneNode)
                    ex = pm.read_float(enemy_node + m_vecAbsOrigin)
                    ey = pm.read_float(enemy_node + m_vecAbsOrigin + 4)
                    ez = pm.read_float(enemy_node + m_vecAbsOrigin + 8)

                    local_node = pm.read_longlong(local + m_pGameSceneNode)
                    lx = pm.read_float(local_node + m_vecAbsOrigin)
                    ly = pm.read_float(local_node + m_vecAbsOrigin + 4)
                    lz = pm.read_float(local_node + m_vecAbsOrigin + 8)

                    dist_3d = ((ex - lx)**2 + (ey - ly)**2 + (ez - lz)**2) ** 0.5

                    dx = x - center_x
                    dy = y - center_y
                    dist_2d = (dx ** 2 + dy ** 2) ** 0.5

                    if dist_3d < closest_dist and dist_2d < aim_radius:
                        closest_dist = dist_3d
                        best_target = (dx, dy)

                except:
                    continue

            if best_target:
                win32api.mouse_event(
                    win32con.MOUSEEVENTF_MOVE,
                    int(best_target[0] / aim_smooth),
                    int(best_target[1] / aim_smooth),
                    0, 0
                )

            time.sleep(0.005)
        except:
            time.sleep(0.1)




def ui():
    class UI(QtWidgets.QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Exodia Test")
            self.setFixedSize(450, 400)
            self.setStyleSheet("background-color: #1e1e2f; color: white; font-family: Consolas; font-size: 12px;")

            main_layout = QtWidgets.QVBoxLayout(self)

            tabs = QtWidgets.QTabWidget()
            tabs.setStyleSheet("""
                QTabBar::tab { background: #2e2e3f; padding: 6px; }
                QTabBar::tab:selected { background: #3e8ef7; font-weight: bold; color: white; }
            """)
            main_layout.addWidget(tabs)

            tabs.addTab(self.aimbot_tab(), "Aimbot")
            tabs.addTab(self.visual_tab(), "Visuals")
            tabs.addTab(self.trigger_tab(), "TriggerBot")

        def aimbot_tab(self):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QFormLayout(page)

            cb = QtWidgets.QCheckBox("Enable Aimbot")
            cb.setChecked(aim_enabled)
            cb.stateChanged.connect(lambda s: globals().__setitem__('aim_enabled', bool(s)))
            layout.addRow(cb)

            key_selector = QtWidgets.QComboBox()
            key_selector.addItems(["XButton1", "Shift", "Alt"])
            key_selector.setCurrentIndex(0)
            def set_aim_key(index):
                keys = [0x06, 0x10, 0x12]
                globals()['aim_key_code'] = keys[index]
            key_selector.currentIndexChanged.connect(set_aim_key)
            layout.addRow("Aimbot Key", key_selector)

            radius_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            radius_slider.setRange(10, 500)
            radius_slider.setValue(aim_radius)
            radius_slider.valueChanged.connect(lambda v: globals().__setitem__('aim_radius', v))
            layout.addRow("Radius", radius_slider)

            smooth_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            smooth_slider.setRange(1, 20)
            smooth_slider.setValue(aim_smooth)
            smooth_slider.valueChanged.connect(lambda v: globals().__setitem__('aim_smooth', v))
            layout.addRow("Smooth", smooth_slider)

            target_menu = QtWidgets.QComboBox()
            target_menu.addItems(["head", "body"])
            target_menu.setCurrentText(aim_target)
            target_menu.currentTextChanged.connect(lambda v: globals().__setitem__('aim_target', v))
            layout.addRow("Target", target_menu)

            return page

        def visual_tab(self):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)

            cb = QtWidgets.QCheckBox("Enable ESP")
            cb.setChecked(esp_enabled)
            cb.stateChanged.connect(lambda s: globals().__setitem__('esp_enabled', bool(s)))
            layout.addWidget(cb)

            box_cb = QtWidgets.QCheckBox("Draw Box")
            bones_cb = QtWidgets.QCheckBox("Draw Bones")

            if esp_mode_mode == 0:
                box_cb.setChecked(True)
            elif esp_mode_mode == 1:
                bones_cb.setChecked(True)
            elif esp_mode_mode == 2:
                box_cb.setChecked(True)
                bones_cb.setChecked(True)

            def update_mode():
                global esp_mode_mode
                if box_cb.isChecked() and bones_cb.isChecked():
                    esp_mode_mode = 2
                elif box_cb.isChecked():
                    esp_mode_mode = 0
                elif bones_cb.isChecked():
                    esp_mode_mode = 1
                else:
                    esp_mode_mode = 3

            box_cb.stateChanged.connect(update_mode)
            bones_cb.stateChanged.connect(update_mode)
            layout.addWidget(box_cb)
            layout.addWidget(bones_cb)

            btn_box = QtWidgets.QPushButton("Change Box Color")
            btn_box.clicked.connect(self.choose_box_color)
            layout.addWidget(btn_box)

            btn_bone = QtWidgets.QPushButton("Change Bone Color")
            btn_bone.clicked.connect(self.choose_bone_color)
            layout.addWidget(btn_bone)

            return page

        def trigger_tab(self):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QFormLayout(page)

            cb = QtWidgets.QCheckBox("Enable TriggerBot")
            cb.setChecked(trigger_enabled)
            cb.stateChanged.connect(lambda s: globals().__setitem__('trigger_enabled', bool(s)))
            layout.addRow(cb)

            key_selector = QtWidgets.QComboBox()
            key_selector.addItems(["XButton1", "Shift", "Alt"])
            key_selector.setCurrentIndex(0)
            def set_trigger_key(index):
                keys = [0x06, 0x10, 0x12]
                globals()['trigger_key_code'] = keys[index]
            key_selector.currentIndexChanged.connect(set_trigger_key)
            layout.addRow("Trigger Key", key_selector)

            return page

        def choose_box_color(self):
            global box_color
            color = QtWidgets.QColorDialog.getColor(box_color)
            if color.isValid():
                box_color = color

        def choose_bone_color(self):
            global bone_color
            color = QtWidgets.QColorDialog.getColor(bone_color)
            if color.isValid():
                bone_color = color

    return UI()

def main():
    app = QtWidgets.QApplication(sys.argv)
    pm = pymem.Pymem("cs2.exe")
    client = pymem.process.module_from_name(pm.process_handle, "client.dll").lpBaseOfDll

    overlay = OverlayWindow()
    overlay.show()
    panel = ui()
    panel.show()
    threading.Thread(target=esp, args=(pm, client, overlay), daemon=True).start()
    threading.Thread(target=trigger, args=(pm, client), daemon=True).start()
    threading.Thread(target=softaim, args=(pm, client), daemon=True).start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()