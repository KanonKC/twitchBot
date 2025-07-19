# Twitch JWT Authorization Flow

ระบบ JWT authorization สำหรับ Twitch API ที่ไม่ต้องการ callback server

## ไฟล์ที่เกี่ยวข้อง

### 1. `twitch_auth.py`
ไฟล์หลักสำหรับจัดการ JWT authorization flow

**คลาสหลัก:**
- `TwitchAuth`: จัดการการขอและจัดการ tokens
- `TwitchAuthGUI`: จัดการ UI สำหรับการยืนยัน

**ฟีเจอร์:**
- Device Authorization Flow (ไม่ต้องการ callback server)
- บันทึก/โหลด tokens อัตโนมัติ
- รีเฟรช token อัตโนมัติ
- ตรวจสอบความถูกต้องของ token

### 2. `twitch_auth_example.py`
ตัวอย่างการใช้งาน JWT authorization ใน Tkinter application

**ฟีเจอร์:**
- GUI สำหรับล็อกอิน/ล็อกเอาท์
- แสดงสถานะ token
- แสดงข้อมูล token (scope, expiration)
- รีเฟรช token อัตโนมัติ

## การติดตั้ง

```bash
pip install requests
pip install PyJWT  # สำหรับอ่าน JWT token
```

## การใช้งาน

### 1. ใช้งานพื้นฐาน

```python
from twitch_auth import TwitchAuth

# สร้าง TwitchAuth instance
twitch_auth = TwitchAuth(
    client_id="your_client_id",
    client_secret="your_client_secret"
)

# ลองโหลด tokens ที่มีอยู่
if twitch_auth.load_tokens() and twitch_auth.validate_token():
    print("✅ ใช้ tokens ที่มีอยู่แล้ว")
else:
    # ขอ tokens ใหม่
    device_data = twitch_auth.get_device_code()
    print(f"รหัสยืนยัน: {device_data['user_code']}")
    print(f"เว็บไซต์: {device_data['verification_uri']}")
    
    # รอการยืนยัน
    twitch_auth.poll_for_token(device_data["device_code"], device_data["interval"])
    twitch_auth.save_tokens()
    print("✅ ล็อกอินสำเร็จแล้ว!")
```

### 2. ใช้งานใน Tkinter

```python
import tkinter as tk
from twitch_auth_example import TwitchAuthApp

root = tk.Tk()
app = TwitchAuthApp(root)
root.mainloop()
```

## ขั้นตอนการทำงาน

### Device Authorization Flow

1. **ขอ Device Code**
   - ส่ง request ไปที่ `https://id.twitch.tv/oauth2/device`
   - ได้ device_code และ user_code

2. **แสดงรหัสยืนยัน**
   - แสดง user_code ให้ผู้ใช้
   - เปิดเว็บไซต์ Twitch ให้ผู้ใช้ใส่รหัส

3. **รอการยืนยัน**
   - Polling ไปที่ `https://id.twitch.tv/oauth2/token`
   - รอจนกว่าผู้ใช้จะยืนยัน

4. **ได้รับ Access Token**
   - ได้ access_token และ refresh_token
   - บันทึกลงไฟล์ `tokens.json`

### Token Management

- **Auto Refresh**: รีเฟรช token อัตโนมัติเมื่อหมดอายุ
- **Persistent Storage**: บันทึก tokens ไว้ใช้ครั้งต่อไป
- **Validation**: ตรวจสอบความถูกต้องของ token

## ข้อดี

1. **ไม่ต้องการ Callback Server**: ใช้ Device Authorization Flow
2. **ปลอดภัย**: ไม่ต้องเปิด port หรือ server
3. **User-Friendly**: UI ที่เข้าใจง่าย
4. **Persistent**: เก็บ tokens ไว้ใช้ครั้งต่อไป
5. **Auto Refresh**: รีเฟรช token อัตโนมัติ

## การปรับแต่ง

### เปลี่ยน Client ID และ Secret

```python
twitch_auth = TwitchAuth(
    client_id="your_new_client_id",
    client_secret="your_new_client_secret"
)
```

### เปลี่ยน Scopes

```python
def get_device_code(self):
    url = f"{self.auth_endpoint}/device"
    data = {
        "client_id": self.client_id,
        "scope": "channel:read:subscriptions channel:read:redemptions"  # เปลี่ยน scopes ตามต้องการ
    }
    # ...
```

### เปลี่ยนไฟล์เก็บ Tokens

```python
twitch_auth.save_tokens("my_tokens.json")
twitch_auth.load_tokens("my_tokens.json")
```

## ข้อผิดพลาดที่อาจเกิดขึ้น

1. **Invalid Client ID/Secret**: ตรวจสอบ client credentials
2. **Authorization Declined**: ผู้ใช้ปฏิเสธการอนุญาต
3. **Expired Token**: Device code หมดอายุ
4. **Network Error**: ปัญหาการเชื่อมต่อ

## การแก้ไขปัญหา

### Token หมดอายุ
```python
try:
    twitch_auth.refresh_access_token()
except:
    # ล็อกอินใหม่
    device_data = twitch_auth.get_device_code()
    # ...
```

### ลบ Tokens
```python
import os
if os.path.exists("tokens.json"):
    os.remove("tokens.json")
```

## ตัวอย่างการใช้งานในโปรเจคเดิม

```python
# ใน Twich_Bot.py
from twitch_auth import TwitchAuth

class App:
    def __init__(self, root):
        # ...
        self.twitch_auth = TwitchAuth(
            client_id="gp762nuuoqcoxypju8c569th9wz7q5",
            client_secret="abslv2nydym6w2i1kf8db8ug8od4kt"
        )
    
    def connect_bot(self):
        # ตรวจสอบการล็อกอิน
        if not self.twitch_auth.access_token:
            messagebox.showerror("Error", "กรุณาล็อกอินก่อน")
            return
        
        # ใช้ access token
        self.bot = TwitchVoteBot(
            token=self.twitch_auth.access_token,
            # ...
        )
```

## หมายเหตุ

- ไฟล์ `tokens.json` จะถูกสร้างอัตโนมัติ
- Tokens จะหมดอายุใน 60 วัน
- Refresh token จะหมดอายุใน 1 ปี
- ควรเก็บ client_secret ไว้เป็นความลับ 