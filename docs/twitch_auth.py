import requests
import webbrowser
import time
import json
import os
from urllib.parse import urlencode

class TwitchAuth:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_endpoint = "https://id.twitch.tv/oauth2"
        self.api_endpoint = "https://api.twitch.tv/helix"
        self.access_token = None
        self.refresh_token = None
        
    def get_device_code(self):
        """ขอ device code จาก Twitch"""
        url = f"{self.auth_endpoint}/device"
        data = {
            "client_id": self.client_id,
            "scope": "channel:read:subscriptions"
        }
        
        response = requests.post(url, data=data)
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"ไม่สามารถขอ device code ได้: {response.text}")
    
    def poll_for_token(self, device_code, interval=5):
        """รอการยืนยันจากผู้ใช้และขอ access token"""
        url = f"{self.auth_endpoint}/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "device_code": device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
        }
        
        while True:
            response = requests.post(url, data=data)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data["access_token"]
                self.refresh_token = token_data.get("refresh_token")
                return token_data
            elif response.status_code == 400:
                error_data = response.json()
                if error_data.get("message") == "authorization_pending":
                    time.sleep(interval)
                    continue
                elif error_data.get("message") == "authorization_declined":
                    raise Exception("ผู้ใช้ปฏิเสธการอนุญาต")
                elif error_data.get("message") == "expired_token":
                    raise Exception("Device code หมดอายุแล้ว")
                else:
                    raise Exception(f"เกิดข้อผิดพลาด: {error_data}")
            else:
                raise Exception(f"ไม่สามารถขอ token ได้: {response.text}")
    
    def refresh_access_token(self):
        """ใช้ refresh token เพื่อขอ access token ใหม่"""
        if not self.refresh_token:
            raise Exception("ไม่มี refresh token")
            
        url = f"{self.auth_endpoint}/token"
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "grant_type": "refresh_token"
        }
        
        response = requests.post(url, data=data)
        if response.status_code == 200:
            token_data = response.json()
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data.get("refresh_token", self.refresh_token)
            return token_data
        else:
            raise Exception(f"ไม่สามารถ refresh token ได้: {response.text}")
    
    def save_tokens(self, filename="tokens.json"):
        """บันทึก tokens ลงไฟล์"""
        token_data = {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token
        }
        with open(filename, "w") as f:
            json.dump(token_data, f)
    
    def load_tokens(self, filename="tokens.json"):
        """โหลด tokens จากไฟล์"""
        if os.path.exists(filename):
            with open(filename, "r") as f:
                token_data = json.load(f)
                self.access_token = token_data.get("access_token")
                self.refresh_token = token_data.get("refresh_token")
                return True
        return False
    
    def validate_token(self):
        """ตรวจสอบว่า token ยังใช้งานได้หรือไม่"""
        if not self.access_token:
            return False
            
        url = f"{self.auth_endpoint}/validate"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        
        response = requests.get(url, headers=headers)
        return response.status_code == 200

class TwitchAuthGUI:
    def __init__(self, parent, twitch_auth):
        self.parent = parent
        self.twitch_auth = twitch_auth
        self.auth_dialog = None
        
    def show_auth_dialog(self, device_data):
        """แสดง dialog สำหรับการยืนยัน"""
        self.auth_dialog = tk.Toplevel(self.parent)
        self.auth_dialog.title("Twitch Authorization")
        self.auth_dialog.geometry("500x400")
        self.auth_dialog.configure(bg="#2e2e2e")
        self.auth_dialog.resizable(False, False)
        
        # ทำให้ dialog อยู่ด้านหน้าเสมอ
        self.auth_dialog.transient(self.parent)
        self.auth_dialog.grab_set()
        
        # หัวข้อ
        title_label = tk.Label(self.auth_dialog, 
                              text="กรุณายืนยันการเข้าสู่ระบบ Twitch", 
                              font=("Arial", 14, "bold"), 
                              fg="white", bg="#2e2e2e")
        title_label.pack(pady=20)
        
        # รหัสยืนยัน
        code_frame = tk.Frame(self.auth_dialog, bg="#2e2e2e")
        code_frame.pack(pady=10)
        
        tk.Label(code_frame, text="รหัสยืนยัน:", 
                font=("Arial", 12), fg="white", bg="#2e2e2e").pack()
        
        code_label = tk.Label(code_frame, 
                             text=device_data["user_code"], 
                             font=("Arial", 20, "bold"), 
                             fg="#00ff00", bg="#2e2e2e",
                             relief="solid", borderwidth=2, padx=20, pady=10)
        code_label.pack(pady=10)
        
        # คำแนะนำ
        instruction_frame = tk.Frame(self.auth_dialog, bg="#2e2e2e")
        instruction_frame.pack(pady=20)
        
        instructions = [
            "1. เปิดเว็บไซต์ Twitch",
            "2. ใส่รหัสยืนยันข้างต้น",
            "3. กดยืนยันการเข้าสู่ระบบ",
            "4. รอสักครู่ระบบจะล็อกอินให้อัตโนมัติ"
        ]
        
        for instruction in instructions:
            tk.Label(instruction_frame, text=instruction, 
                    fg="white", bg="#2e2e2e", font=("Arial", 11)).pack(anchor="w")
        
        # ปุ่มเปิดเว็บไซต์
        button_frame = tk.Frame(self.auth_dialog, bg="#2e2e2e")
        button_frame.pack(pady=20)
        
        open_browser_btn = tk.Button(button_frame, 
                                    text="เปิดเว็บไซต์ Twitch", 
                                    command=lambda: webbrowser.open(device_data["verification_uri"]),
                                    bg="#9146ff", fg="white", 
                                    font=("Arial", 12, "bold"),
                                    relief="flat", padx=20, pady=10)
        open_browser_btn.pack(side="left", padx=10)
        
        cancel_btn = tk.Button(button_frame, 
                              text="ยกเลิก", 
                              command=self.cancel_auth,
                              bg="#ff4646", fg="white", 
                              font=("Arial", 12),
                              relief="flat", padx=20, pady=10)
        cancel_btn.pack(side="left", padx=10)
        
        # แสดงเวลาที่เหลือ
        self.time_label = tk.Label(self.auth_dialog, 
                                  text=f"เวลาที่เหลือ: {device_data['expires_in']} วินาที", 
                                  fg="yellow", bg="#2e2e2e", font=("Arial", 10))
        self.time_label.pack(pady=10)
        
        # เริ่ม countdown
        self.start_countdown(device_data["expires_in"])
        
        # เริ่ม polling
        self.start_polling(device_data["device_code"], device_data["interval"])
    
    def start_countdown(self, seconds):
        """เริ่มนับถอยหลัง"""
        if seconds > 0 and self.auth_dialog:
            self.time_label.config(text=f"เวลาที่เหลือ: {seconds} วินาที")
            self.auth_dialog.after(1000, lambda: self.start_countdown(seconds - 1))
        elif self.auth_dialog:
            self.time_label.config(text="หมดเวลาแล้ว!", fg="red")
    
    def start_polling(self, device_code, interval):
        """เริ่ม polling สำหรับ token"""
        def poll():
            try:
                self.twitch_auth.poll_for_token(device_code, interval)
                self.twitch_auth.save_tokens()
                if self.auth_dialog:
                    self.auth_dialog.destroy()
                messagebox.showinfo("สำเร็จ", "ล็อกอินสำเร็จแล้ว!")
                return True
            except Exception as e:
                if "authorization_pending" in str(e):
                    # ยังรอการยืนยัน
                    if self.auth_dialog:
                        self.auth_dialog.after(interval * 1000, poll)
                    return False
                else:
                    # เกิดข้อผิดพลาด
                    if self.auth_dialog:
                        self.auth_dialog.destroy()
                    messagebox.showerror("ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(e)}")
                    return False
        
        # เริ่ม polling
        self.auth_dialog.after(interval * 1000, poll)
    
    def cancel_auth(self):
        """ยกเลิกการยืนยัน"""
        if self.auth_dialog:
            self.auth_dialog.destroy()
        messagebox.showinfo("ยกเลิก", "การล็อกอินถูกยกเลิก")

# ตัวอย่างการใช้งาน
if __name__ == "__main__":
    import tkinter as tk
    from tkinter import messagebox
    
    # สร้าง TwitchAuth instance
    twitch_auth = TwitchAuth(
        client_id="y8xpxp0qd5vrzx4yy7tnj71sxkokd1",
        client_secret="d96t22p7i41bjcrvli5mylw2rybpfq"
    )
    
    # ทดสอบการล็อกอิน
    try:
        # ลองโหลด tokens ที่มีอยู่
        if twitch_auth.load_tokens() and twitch_auth.validate_token():
            print("✅ ใช้ tokens ที่มีอยู่แล้ว")
        else:
            print("🔄 ขอ tokens ใหม่...")
            device_data = twitch_auth.get_device_code()
            print(f"รหัสยืนยัน: {device_data['user_code']}")
            print(f"เว็บไซต์: {device_data['verification_uri']}")
            
            # รอการยืนยัน
            twitch_auth.poll_for_token(device_data["device_code"], device_data["interval"])
            twitch_auth.save_tokens()
            print("✅ ล็อกอินสำเร็จแล้ว!")
            
    except Exception as e:
        print(f"❌ เกิดข้อผิดพลาด: {str(e)}") 