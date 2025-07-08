import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from twitchio.ext import commands
import asyncio
import threading
import requests

class TwitchAPI:
    def __init__(self, client_id, client_secret, access_token):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.endpoint = "https://api.twitch.tv/helix"
    
    def get_broadcaster_subscriptions(self, broadcaster_id, cursor=None):
        url = f"{self.endpoint}/subscriptions?broadcaster_id={broadcaster_id}&first=100"
        if cursor:
            url += f"&after={cursor}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
        }
        response = requests.get(url, headers=headers)
        return response.json()
        
    def get_user(self, login):
        url = f"{self.endpoint}/users?login={login}"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
        }
        response = requests.get(url, headers=headers)
        return response.json()

class TwitchVoteBot(commands.Bot):
    def __init__(self, token, channel, vote_choices, queue_keywords, duration, root, update_countdown_callback, finish_vote_callback, update_queue_callback):
        super().__init__(
            token=token,
            prefix='!',
            initial_channels=[channel]
        )
        self.vote_choices = vote_choices
        self.queue_keywords = queue_keywords
        self.votes = {}
        self.duration = duration
        self.countdown = duration
        self.root = root
        self.update_countdown_callback = update_countdown_callback
        self.finish_vote_callback = finish_vote_callback
        self.update_queue_callback = update_queue_callback
        self.voted_users = set()
        self.vote_running = False
        self.queue_list = []
        self.vote_stopped = False  # Flag to track if voting was stopped manually
        self.broadcaster_subscriptions_table = {}
        self.helix = TwitchAPI(
            client_id="gp762nuuoqcoxypju8c569th9wz7q5",
            client_secret="abslv2nydym6w2i1kf8db8ug8od4kt",
            access_token=token
        )
        self.channel_id = ""

    async def event_ready(self):
        print(f'Logged in as | {self.nick} ({self.connected_channels[0]})')
        if self.connected_channels:
            try:
                user_res = self.helix.get_user(self.connected_channels[0].name)
                self.channel_id = user_res["data"][0]["id"]
            except Exception as e:
                print("ไม่สามารถดึงข้อมูลช่องของคุณได้", e)

            try:
                first_time = True
                cursor = None
                while cursor or first_time:
                    broadcaster_sub_res = self.helix.get_broadcaster_subscriptions(self.channel_id, cursor)
                    print('broadcaster_sub_res',broadcaster_sub_res)
                    for sub in broadcaster_sub_res["data"]:
                        self.broadcaster_subscriptions_table[sub["user_login"]] = sub
                    if "cursor" in broadcaster_sub_res["pagination"]:
                        cursor = broadcaster_sub_res["pagination"]["cursor"]
                    else:
                        cursor = None
                    first_time = False
                    print('cursor',cursor, first_time)
            except Exception as e:
                print("ไม่สามารถดึงข้อมูลสมาชิกช่องของคุณได้", e)

            await self.connected_channels[0].send(f"🔐 คอมพี่มาสถูกล็อคเเล้ว กรุณาติดต่อเพื่อปลดล็อค!")
            print("✅ พร้อมใช้งาน")
        else:
            print("ยังไม่ได้เชื่อมต่อกับช่อง!")

    async def event_message(self, message):
        if message.echo:
            return
        print("Message received", message.content)
        content = message.content.strip().upper()
        user = message.author.name

        # โหวต: บันทึกการโหวตเฉพาะเมื่อโหวตระหว่างที่กำลังรันโหวต
        if self.vote_running and content in self.vote_choices:
            if user not in self.voted_users:
                self.voted_users.add(user)
                self.votes[user] = content
                await message.channel.send(f"{user} เลือก {content} แล้ว!")

        # คิว: เพิ่มหรือเอาผู้ใช้จากคิว
        if content in self.queue_keywords:
            if user not in self.queue_list:
                self.queue_list.append(user)
                self.update_queue_callback(self.queue_list)
                await message.channel.send(f"{user} เข้าคิวแล้ว!")  # ส่งข้อความว่าเข้าคิวแล้ว
            else:
                await message.channel.send(f"{user} ไปต่อแถวใหม่ไป๊!.")  # แจ้งว่าผู้ใช้ในคิวแล้ว

        if content == "!QUEUE":
            if self.queue_list:
                queue_message = "รายชื่อในคิว:\n" + "\n".join(f"{idx+1}. {user}" for idx, user in enumerate(self.queue_list[:5]))
            else:
                queue_message = "คิวว่างไม่มีใครอยากเล่นด้วย ว๊ายๆๆ😂"
            await message.channel.send(queue_message)

    def start_countdown(self):
        self.vote_running = True
        self.countdown = self.duration
        self.update_countdown_callback(self.get_remaining_time())
        self.run_countdown()

    def run_countdown(self):
        if self.countdown > 0:
            self.countdown -= 1
            self.update_countdown_callback(self.get_remaining_time())
            print(f"เวลาถอยหลัง: {self.countdown} วินาที")

            if self.countdown == 10:
                self.root.after(0, self.send_twitch_message, f"⏳ เหลือเวลา 10 วินาที!")

            self.root.after(1000, self.run_countdown)

        else:
            if not self.vote_stopped:  # ส่งข้อความ "หมดเวลาโหวตแล้ว!" ถ้ายังไม่ได้กด stop vote
                self.send_twitch_message("หมดเวลาโหวตแล้ว!")
            self.vote_running = False
            self.finish_vote()  # เรียก finish_vote โดยไม่ส่ง result

    def get_remaining_time(self):
        return self.countdown

    def finish_vote(self, result=None):
        if result is None:
            # แปลง dict เป็น list ของ tuple (user, choice)
            result = list(self.votes.items())  # ใช้ items() ของ dict เพื่อแปลงเป็น tuple
        self.finish_vote_callback(result)  # ส่งผลโหวตไปที่ finish_vote_callback
        self.save_results_to_file(result)

        # รีเซ็ทผลโหวตหลังจากจบ
        self.votes.clear()
        self.voted_users.clear()

    def send_twitch_message(self, message):
        loop = asyncio.get_event_loop()
        if self.connected_channels:
            asyncio.run_coroutine_threadsafe(self.connected_channels[0].send(message), loop)
        else:
            print("ไม่สามารถส่งข้อความได้ เนื่องจากยังไม่มีการเชื่อมต่อกับช่อง")

    def save_results_to_file(self, result):
        # This file generate user, choice, subscription sort by time
        file_path = "vote_results.txt"
        with open(file_path, "w", encoding="utf-8") as file:
            for user, choice in result:  # รับผลโหวตในรูปแบบ tuple
                subscription = self.get_subscription(user)
                match subscription:
                    case "1000":
                        subscription = "T1"
                    case "2000":
                        subscription = "T2"
                    case "3000":
                        subscription = "T3"
                    case "0000":
                        subscription = "None"
                file.write(f"{user},{choice},{subscription}\n")
                if subscription != "None":
                    file.write(f"{user},{choice},{subscription}\n")
        print(f"Results saved to {file_path}")

        # This file generate only username group by choice
        file_path = "vote_results_choice_seperated.txt"
        group_by_choice = {}
        for user, choice in result:
            if choice not in group_by_choice:
                group_by_choice[choice] = []
            group_by_choice[choice].append(user)
            if self.get_subscription(user) != "0000":
                group_by_choice[choice].append(user)
        with open(file_path, "w", encoding="utf-8") as file:
            for choice, users in group_by_choice.items():
                file.write(f"------------- Choice: {choice} -------------\n")
                file.write('\n'.join(users))
                file.write('\n')
            
        print(f"Results saved to {file_path}")

    def stop_vote(self):
        self.vote_stopped = True  # Set flag to true when vote is manually stopped
        self.countdown = 0
        self.send_twitch_message("⏹️ โหวตถูกหยุดแล้ว!")
        self.save_results_to_file(self.votes)  # Save the results when stop vote is clicked
        self.finish_vote()  # Finish vote after stopping

    def get_subscription(self, user):
        if user in self.broadcaster_subscriptions_table:
            return self.broadcaster_subscriptions_table[user]["tier"]
        return "0000"

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Twitch Vote and Queue Bot")
        self.root.configure(bg="#2e2e2e")

        style = ttk.Style()
        style.theme_use('default')
        style.configure("Treeview",
                        background="#3c3f41",
                        foreground="white",
                        rowheight=25,
                        fieldbackground="#3c3f41")
        style.map('Treeview', background=[('selected', '#5a5a5a')])

        # --- Top Frame (Input Form) ---
        form_frame = tk.Frame(root, bg="#2e2e2e")
        form_frame.pack(pady=10)

        tk.Label(form_frame, text="Access Token:", fg="white", bg="#2e2e2e").grid(row=0, column=0, sticky="w")
        self.token_entry = tk.Entry(form_frame, width=50, show='*')
        self.token_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(form_frame, text="Channel Name:", fg="white", bg="#2e2e2e").grid(row=1, column=0, sticky="w")
        self.channel_entry = tk.Entry(form_frame, width=30)
        self.channel_entry.grid(row=1, column=1, padx=10, pady=5)

        tk.Label(form_frame, text="Vote Choices (comma separated):", fg="white", bg="#2e2e2e").grid(row=2, column=0, sticky="w")
        self.choices_entry = tk.Entry(form_frame, width=30)
        self.choices_entry.grid(row=2, column=1, padx=10, pady=5)

        tk.Label(form_frame, text="Queue Keywords (comma separated):", fg="white", bg="#2e2e2e").grid(row=3, column=0, sticky="w")
        self.queue_keywords_entry = tk.Entry(form_frame, width=30)
        self.queue_keywords_entry.grid(row=3, column=1, padx=10, pady=5)

        tk.Label(form_frame, text="Vote Time (seconds):", fg="white", bg="#2e2e2e").grid(row=4, column=0, sticky="w")
        self.time_entry = tk.Entry(form_frame, width=10)
        self.time_entry.grid(row=4, column=1, padx=10, pady=5, sticky="w")
    
        self.countdown_label = tk.Label(root, text="Countdown: 0", font=("Arial", 16), fg="white", bg="#2e2e2e")
        self.countdown_label.pack(pady=10)

        # --- Button Frame ---
        button_frame = tk.Frame(root, bg="#2e2e2e")
        button_frame.pack(pady=10)

        self.connect_button = tk.Button(button_frame, text="Connect Bot", command=self.connect_bot, bg="#5a5a5a", fg="white")
        self.connect_button.grid(row=0, column=0, padx=5)

        self.start_button = tk.Button(button_frame, text="Start Vote", command=self.start_vote, state=tk.DISABLED, bg="#5a5a5a", fg="white")
        self.start_button.grid(row=0, column=1, padx=5)

        self.set_queue_button = tk.Button(button_frame, text="Set Queue Keywords", command=self.set_queue_keywords, state=tk.DISABLED, bg="#5a5a5a", fg="white")
        self.set_queue_button.grid(row=0, column=2, padx=5)

        self.stop_button = tk.Button(button_frame, text="Stop Vote", command=self.stop_vote, state=tk.DISABLED, bg="#5a5a5a", fg="white")
        self.stop_button.grid(row=0, column=3, padx=5)

        # --- Vote Result Table ---
        tk.Label(root, text="Vote Results", font=("Arial", 14), fg="white", bg="#2e2e2e").pack(pady=(20, 5))
        self.result_table = ttk.Treeview(root, columns=("No", "Username","Subscription", "Choice"), show="headings")
        # Heading
        self.result_table.heading("No", text="No.")
        self.result_table.heading("Username", text="Username")
        self.result_table.heading("Subscription", text="Subscription")
        self.result_table.heading("Choice", text="Choice")
        # Column
        self.result_table.column("No", width=50, anchor="center")
        self.result_table.column("Username", width=150)
        self.result_table.column("Subscription", width=50, anchor="center")
        self.result_table.column("Choice", width=150)
        self.result_table.pack(pady=5)

        # --- Queue Section ---
        tk.Label(root, text="Queue List", font=("Arial", 14), fg="white", bg="#2e2e2e").pack(pady=(20, 5))
        self.queue_table = ttk.Treeview(root, columns=("No", "Username"), show="headings", height=10)
        self.queue_table.heading("No", text="No.")
        self.queue_table.heading("Username", text="Username")
        self.queue_table.column("No", width=50, anchor="center")
        self.queue_table.column("Username", width=150)
        self.queue_table.pack(pady=5)

        queue_button_frame = tk.Frame(root, bg="#2e2e2e")
        queue_button_frame.pack(pady=10)

        self.remove_button = tk.Button(queue_button_frame, text="Remove from Queue", command=self.remove_selected_from_queue, bg="#5a5a5a", fg="white")
        self.remove_button.grid(row=0, column=0, padx=5)

        self.clear_queue_button = tk.Button(queue_button_frame, text="Clear Queue", command=self.clear_queue, bg="#5a5a5a", fg="white")
        self.clear_queue_button.grid(row=0, column=1, padx=5)

        self.bot = None

    def connect_bot(self):
        token = self.token_entry.get()
        channel = self.channel_entry.get()

        if not token or not channel:
            messagebox.showerror("Error", "Please enter the access token and channel name.")
            return

        self.bot = TwitchVoteBot(
            token=token,
            channel=channel,
            vote_choices=[],
            queue_keywords=[],
            duration=0,
            root=self.root,
            update_countdown_callback=self.update_countdown,
            finish_vote_callback=self.finish_vote,
            update_queue_callback=self.update_queue
        )
        self.bot.run_task = threading.Thread(target=self.run_bot)
        self.bot.run_task.start()

        # Enable buttons after the bot connects
        self.connect_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)
        self.set_queue_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)

        # ส่งข้อความเชื่อมต่อบอท
        self.bot.send_twitch_message("🔐 คอมพี่มาสถูกล็อคเเล้ว กรุณาติดต่อเพื่อปลดล็อค!")

    def run_bot(self):
        asyncio.run(self.bot.run())

    def start_vote(self):
        vote_choices = [c.strip().upper() for c in self.choices_entry.get().split(',') if c.strip()]
        queue_keywords = [k.strip().upper() for k in self.queue_keywords_entry.get().split(',') if k.strip()]
        try:
            duration = int(self.time_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Vote time must be an integer.")
            return

        # รีเซ็ทตารางผลโหวตเมื่อเริ่มโหวตใหม่
        for row in self.result_table.get_children():
            self.result_table.delete(row)

        self.bot.vote_choices = vote_choices
        self.bot.queue_keywords = queue_keywords
        self.bot.duration = duration
        self.bot.start_countdown()

        # ส่งข้อความเริ่มโหวต
        self.bot.send_twitch_message(f"🚨 เริ่มโหวตแล้ว! พิมพ์ {', '.join(self.bot.vote_choices)} เพื่อเลือก มีเวลา {self.bot.duration} วินาที!")

    def set_queue_keywords(self):
        queue_keywords = [k.strip().upper() for k in self.queue_keywords_entry.get().split(',') if k.strip()]
        self.bot.queue_keywords = queue_keywords
        messagebox.showinfo("Success", "Queue keywords have been set.")

    def stop_vote(self):
        if self.bot and self.bot.vote_running:
            self.bot.stop_vote()  # Call stop_vote from bot class to stop voting

    def update_countdown(self, time_left):
        self.countdown_label.config(text=f"Countdown: {time_left}")

    def finish_vote(self, result):
        self.result_table.delete(*self.result_table.get_children())
        diff = 0
        for idx, (user, choice) in enumerate(result, start=1):
            subscription = self.bot.get_subscription(user)
            match subscription:
                case "1000":
                    subscription = "Tier 1"
                case "2000":
                    subscription = "Tier 2"
                case "3000":
                    subscription = "Tier 3"
                case "0000":
                    subscription = "-"
            self.result_table.insert("", "end", values=(idx + diff, user, subscription, choice))
            if subscription != "-":
                diff += 1
                self.result_table.insert("", "end", values=(idx + diff, user, subscription, choice))

    def update_queue(self, queue_list):
        self.queue_table.delete(*self.queue_table.get_children())
        for idx, user in enumerate(queue_list, start=1):
            self.queue_table.insert("", "end", values=(idx, user))

    def remove_selected_from_queue(self):
        selected_items = self.queue_table.selection()
        for item in selected_items:
            user = self.queue_table.item(item, "values")[1]
            self.bot.queue_list.remove(user)
        self.update_queue(self.bot.queue_list)

    def clear_queue(self):
        self.bot.queue_list.clear()
        self.update_queue(self.bot.queue_list)

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
