import tkinter as tk
from tkinter import messagebox
from tkinter import ttk
from twitchio.ext import commands
import asyncio
import threading
import requests
import webbrowser
import time
import random
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import socket

class CallbackHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, callback_queue=None, **kwargs):
        self.callback_queue = callback_queue
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle callback from Twitch OAuth"""
        if self.path.startswith('/callback'):
            # Parse query parameters
            query = self.path.split('?')[1] if '?' in self.path else ''
            params = urllib.parse.parse_qs(query)
            
            # Send data back to main thread
            if self.callback_queue:
                self.callback_queue.put(params)
            
            # Send response back to browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html_content = """
            <html>
            <head><title>Twitch Auth Success</title></head>
            <body>
                <h1>✅ Authorization successful!</h1>
                <p>You can close this window now</p>
                <script>window.close();</script>
            </body>
            </html>
            """
            self.wfile.write(html_content.encode())
        else:
            self.send_response(404)
            self.end_headers()

class TwitchAuth:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_endpoint = "https://id.twitch.tv/oauth2"
        self.api_endpoint = "https://api.twitch.tv/helix"
        self.access_token = None
        self.refresh_token = None
        self.scopes = ["channel:read:subscriptions", "chat:read", "chat:edit"]
        self.redirect_uri = "http://localhost:8080/callback"
        self.expected_state = None
        self.callback_queue = None

    def generate_random_string(self, length=10):
        pool = "abcdefghijklmnopqrstuvwxyz0123456789"
        return ''.join(random.choices(pool, k=length))
    
    def find_free_port(self):
        """Find available port"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.listen(1)
            port = s.getsockname()[1]
        return port
    
    def get_implicit_grant_url(self):
        """Create URL for Implicit Grant Flow"""
        self.expected_state = self.generate_random_string(32)
        scopes = " ".join(self.scopes).replace(" ", "%20").replace(":", "%3A")
        return f"{self.auth_endpoint}/authorize?client_id={self.client_id}&redirect_uri={self.redirect_uri}&scope={scopes}&state={self.expected_state}&response_type=token"
    
    def start_callback_server(self):
        print("start_callback_server")
        """Start web server to receive callback"""
        port = 8080
        try:
            # Create custom handler with callback_queue
            handler = type('CustomHandler', (BaseHTTPRequestHandler,), {
                'do_GET': lambda self: self.handle_callback()
            })
            
            def handle_callback(self):
                print("Self ", self.fragment)
                # TODO: Get fragment
                if self.path.startswith('/callback'):
                    print("self.path", self.path)
                    # Parse fragment parameters (access_token is in fragment)
                    if '#' in self.path:
                        fragment = self.path.split('#')[1]
                        params = urllib.parse.parse_qs(fragment)
                        
                        # Check state
                        state = params.get('state', [None])[0]
                        if state != self.expected_state:
                            self.send_error(400, "State mismatch")
                            return
                        
                        # Get access token
                        access_token = params.get('access_token', [None])[0]
                        if access_token:
                            self.access_token = access_token
                            if self.callback_queue:
                                self.callback_queue.put({
                                    'access_token': access_token,
                                    'scope': params.get('scope', [''])[0],
                                    'token_type': params.get('token_type', ['bearer'])[0]
                                })
                        
                        # Send response back
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        
                        html_content = """
                        <html>
                        <head><title>Twitch Auth Success</title></head>
                        <body>
                            <h1>✅ Authorization successful!</h1>
                            <p>You can close this window now</p>
                            <script>window.close();</script>
                        </body>
                        </html>
                        """
                        self.wfile.write(html_content.encode())
                    else:
                        self.send_error(400, "Access token not found")
                else:
                    self.send_error(404, "Not Found")
            
            # Set method for handler
            handler.do_GET = handle_callback
            
            # Start server
            server = HTTPServer(('localhost', port), handler)
            server.callback_queue = self.callback_queue
            server.expected_state = self.expected_state
            server.access_token = None
            
            return server
        except Exception as e:
            print(f"Cannot start server: {e}")
            return None
    
    def login_with_implicit_grant(self):
        """Login with Implicit Grant Flow"""
        try:
            # Create queue to receive data from callback
            import queue
            self.callback_queue = queue.Queue()
            
            # Start callback server
            server = self.start_callback_server()
            if not server:
                raise Exception("Cannot start callback server")
            
            # Start server in separate thread
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            # Create authorization URL
            auth_url = self.get_implicit_grant_url()
            print(f" Authorization URL: {auth_url}")
            
            # Open browser
            webbrowser.open(auth_url)
            
            # Wait for callback
            print("⏳ Waiting for user authorization...")
            try:
                callback_data = self.callback_queue.get(timeout=300)  # Wait 5 minutes
                
                # Get access token
                if 'access_token' in callback_data:
                    self.access_token = callback_data['access_token']
                    print("✅ Received access token!")
                    return {
                        'access_token': callback_data['access_token'],
                        'scope': callback_data.get('scope', ''),
                        'token_type': callback_data.get('token_type', 'bearer')
                    }
                else:
                    raise Exception("Access token not received")
                    
            except queue.Empty:
                raise Exception("Authorization timeout")
            finally:
                # Close server
                server.shutdown()
                server.server_close()
                
        except Exception as e:
            print(f"❌ Login failed: {str(e)}")
            raise e

    def validate_token(self):
        """Check if token is still valid"""
        if not self.access_token:
            return False
            
        url = f"{self.auth_endpoint}/validate"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        
        response = requests.get(url, headers=headers)
        return response.status_code == 200

class TwitchAPI:
    def __init__(self, client_id="", client_secret="", access_token=""):
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
    
    def get_user_by_token(self, token):
        url = f"{self.endpoint}/users"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {token}",
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
            client_id="y8xpxp0qd5vrzx4yy7tnj71sxkokd1",
            client_secret="a116vy2diw00h67d9wh5yb64ocf43n",
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
                print("Cannot get channel data", e)

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
                print("Cannot get channel subscriber data", e)

            await self.connected_channels[0].send(f"🔐 Computer is locked! Please contact to unlock!")
            print("✅ Ready to use")
        else:
            print("Not connected to channel!")

    async def event_message(self, message):
        if message.echo:
            return
        print("Message received", message.content)
        content = message.content.strip().upper()
        user = message.author.name

        # Vote: Record votes only when voting is running
        if self.vote_running and content in self.vote_choices:
            if user not in self.voted_users:
                self.voted_users.add(user)
                self.votes[user] = content
                await message.channel.send(f"{user} chose {content}!")

        # Queue: Add or remove users from queue
        if content in self.queue_keywords:
            if user not in self.queue_list:
                self.queue_list.append(user)
                self.update_queue_callback(self.queue_list)
                await message.channel.send(f"{user} joined the queue!")  # Send message that joined queue
            else:
                await message.channel.send(f"{user} go to the back of the line!")  # Notify that user is already in queue

        if content == "!QUEUE":
            if self.queue_list:
                queue_message = "Queue list:\n" + "\n".join(f"{idx+1}. {user}" for idx, user in enumerate(self.queue_list[:5]))
            else:
                queue_message = "Queue is empty, no one wants to play 😂"
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
            print(f"Countdown: {self.countdown} seconds")

            if self.countdown == 10:
                self.root.after(0, self.send_twitch_message, f"⏳ 10 seconds remaining!")

            self.root.after(1000, self.run_countdown)

        else:
            if not self.vote_stopped:  # Send message "Vote time is up!" if stop vote wasn't clicked
                self.send_twitch_message("Vote time is up!")
            self.vote_running = False
            self.finish_vote()  # Call finish_vote without sending result

    def get_remaining_time(self):
        return self.countdown

    def finish_vote(self, result=None):
        if result is None:
            # Convert dict to list of tuples (user, choice)
            result = list(self.votes.items())  # Use items() of dict to convert to tuple
        self.finish_vote_callback(result)  # Send vote results to finish_vote_callback
        self.save_results_to_file(result)

        # Reset vote results after finishing
        self.votes.clear()
        self.voted_users.clear()

    def send_twitch_message(self, message):
        loop = asyncio.get_event_loop()
        if self.connected_channels:
            asyncio.run_coroutine_threadsafe(self.connected_channels[0].send(message), loop)
        else:
            print("Cannot send message because not connected to channel")

    def save_results_to_file(self, result):
        # This file generate user, choice, subscription sort by time
        file_path = "vote_results.txt"
        with open(file_path, "w", encoding="utf-8") as file:
            for user, choice in result:  # Receive vote results in tuple format
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
        self.send_twitch_message("⏹️ Vote stopped!")
        self.save_results_to_file(self.votes)  # Save the results when stop vote is clicked
        self.finish_vote()  # Finish vote after stopping

    def get_subscription(self, user):
        if user in self.broadcaster_subscriptions_table:
            return self.broadcaster_subscriptions_table[user]["tier"]
        return "0000"

class App:
    def __init__(self, root):

        self.twitch_auth = TwitchAuth(
            client_id="y8xpxp0qd5vrzx4yy7tnj71sxkokd1",
            client_secret="a116vy2diw00h67d9wh5yb64ocf43n"
        )

        self.helix = TwitchAPI(
            client_id="y8xpxp0qd5vrzx4yy7tnj71sxkokd1",
            client_secret="a116vy2diw00h67d9wh5yb64ocf43n",
            access_token=""
        )

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
        
        self.login_button = tk.Button(button_frame, text="Login to Twitch", command=self.login_to_twitch, bg="#611a15", fg="white")
        self.login_button.grid(row=0, column=1, padx=5)

        self.start_button = tk.Button(button_frame, text="Start Votezzz", command=self.start_vote, state=tk.DISABLED, bg="#5a5a5a", fg="white")
        self.start_button.grid(row=0, column=2, padx=5)

        self.set_queue_button = tk.Button(button_frame, text="Set Queue Keywords", command=self.set_queue_keywords, state=tk.DISABLED, bg="#5a5a5a", fg="white")
        self.set_queue_button.grid(row=0, column=3, padx=5)

        self.stop_button = tk.Button(button_frame, text="Stop Vote", command=self.stop_vote, state=tk.DISABLED, bg="#5a5a5a", fg="white")
        self.stop_button.grid(row=0, column=4, padx=5)

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

        self.setup_twitch_bot(token, channel)

    def setup_twitch_bot(self, token, channel):
        print("setup_twitch_bot", token, channel)
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
        self.login_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)
        self.set_queue_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL)

        # Send bot connection message
        self.bot.send_twitch_message("🔐 Computer is locked! Please contact to unlock!")

    def login_to_twitch(self):
        try:
            # Try to use existing token
            if self.twitch_auth.access_token and self.twitch_auth.validate_token():
                print("✅ Using existing tokens")
                token = self.twitch_auth.access_token
            else:
                print("🔄 Requesting new tokens with Implicit Grant Flow...")
                token_data = self.twitch_auth.login_with_implicit_grant()
                token = token_data["access_token"]
                print("✅ Login successful!")
            
            # Get user data
            response = self.helix.get_user_by_token(token)
            channel = response['data'][0]['login']
            
            # Setup bot
            self.setup_twitch_bot(token, channel)
                
        except Exception as e:
            print(f"❌ Login to Twitch failed: {str(e)}")
            messagebox.showerror("Error", f"Login failed: {str(e)}")

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

        # Reset vote results table when starting new vote
        for row in self.result_table.get_children():
            self.result_table.delete(row)

        self.bot.vote_choices = vote_choices
        self.bot.queue_keywords = queue_keywords
        self.bot.duration = duration
        self.bot.start_countdown()

        # Send vote start message
        self.bot.send_twitch_message(f"🚨 Vote started! Type {', '.join(self.bot.vote_choices)} to choose. You have {self.bot.duration} seconds!")

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
