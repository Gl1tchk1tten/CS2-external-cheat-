import cv2
import numpy as np
import mss
import serial
import win32api
import threading
import time
import customtkinter as ctk

# ==== CONFIG ====
SERIAL_PORT = 'COM3'  # ← Mets ici ton vrai port COM
BAUD_RATE = 9600
SCREEN_WIDTH = 1680
SCREEN_HEIGHT = 1080
ACTIVATION_BUTTON = 0x06  # XButton2 (à changer si nécessaire)
# ==== TRIGGER BOT ====
class TriggerBot:
    def __init__(self):
        self.fov = 80
        self.tolerance = 40
        self.running = False
        self.ser = serial.Serial(SERIAL_PORT, BAUD_RATE)
        self.center_x = SCREEN_WIDTH // 2
        self.center_y = SCREEN_HEIGHT // 2

    def get_mask(self, img):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        lower = np.array([125, 50, 50])
        upper = np.array([155, 255, 255])
        return cv2.inRange(hsv, lower, upper)

    def find_target(self, mask):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 50 or area > 10000:
                continue

            M = cv2.moments(cnt)
            if M['m00'] == 0:
                continue

            cx = int(M['m10'] / M['m00'])
            cy = int(M['m01'] / M['m00'])
            dx = cx - self.center_x
            dy = cy - self.center_y
            dist = (dx**2 + dy**2)**0.5

            if dist < self.fov:
                return True
        return False

    def is_button_pressed(self):
        return win32api.GetAsyncKeyState(ACTIVATION_BUTTON) != 0

    def run(self):
        print("[*] TriggerBot lancé.")
        screen = mss.mss()  # <-- Fix ici

        while self.running:
            if self.is_button_pressed():
                monitor = {"top": 0, "left": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}
                frame = np.array(screen.grab(monitor))[:, :, :3]
                mask = self.get_mask(frame)
                if self.find_target(mask):
                    self.ser.write(b"FIRE\n")
                    print("[🔥] TIR envoyé")
                    time.sleep(0.1)
            time.sleep(0.01)

        print("[*] TriggerBot arrêté.")

    def start(self):
        self.running = True
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self.running = False

# ==== GUI ====
class App(ctk.CTk):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot
        self.title("TriggerBot UD")
        self.geometry("300x280")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.running = False

        ctk.CTkLabel(self, text="FOV").pack(pady=(10, 0))
        self.fov_slider = ctk.CTkSlider(self, from_=20, to=300, number_of_steps=28, command=self.set_fov)
        self.fov_slider.set(bot.fov)
        self.fov_slider.pack()

        ctk.CTkLabel(self, text="Color Tolerance").pack(pady=(10, 0))
        self.tolerance_slider = ctk.CTkSlider(self, from_=0, to=100, command=self.set_tolerance)
        self.tolerance_slider.set(bot.tolerance)
        self.tolerance_slider.pack()

        self.start_button = ctk.CTkButton(self, text="Start TriggerBot", command=self.toggle_bot)
        self.start_button.pack(pady=20)

    def set_fov(self, value):
        self.bot.fov = int(value)

    def set_tolerance(self, value):
        self.bot.tolerance = int(value)

    def toggle_bot(self):
        if not self.running:
            self.bot.start()
            self.start_button.configure(text="Stop TriggerBot")
        else:
            self.bot.stop()
            self.start_button.configure(text="Start TriggerBot")
        self.running = not self.running

# ==== MAIN ====
if __name__ == "__main__":
    bot = TriggerBot()
    app = App(bot)
    app.mainloop()
