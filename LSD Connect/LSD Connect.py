import socket
import json
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import time
import requests
from PIL import Image, ImageTk
import os
import traceback

API_BASE_URL = "https://lds-7e2n.onrender.com"
TCP_PORT = 7000
TIMEOUT_SECONDS = 5
CONFIG_FILE = "config.json"
LOG_FILE = "error.log"

class LoginWindow:
    def __init__(self, root, on_success):
        self.root = root
        self.on_success = on_success
        self.root.title("Login")
        self.root.geometry("420x360")

        try:
            logo = Image.open("logo.png").resize((350, 100))
            logo_image = ImageTk.PhotoImage(logo)
            tk.Label(root, image=logo_image).pack(pady=5)
            self.root.logo_image = logo_image
        except:
            tk.Label(root, text="[Logo Missing]", font=("Arial", 12), fg="gray").pack(pady=5)

        tk.Label(root, text="Username:").pack()
        self.username_entry = ttk.Entry(root)
        self.username_entry.pack()

        tk.Label(root, text="Password:").pack()
        self.password_entry = ttk.Entry(root, show="*")
        self.password_entry.pack()

        self.remember_var = tk.BooleanVar()
        ttk.Checkbutton(root, text="Remember me", variable=self.remember_var).pack(pady=5)

        ttk.Button(root, text="Login", command=self.login).pack(pady=5)
        ttk.Label(root, text="Support: chris.afford@gmail.com", foreground="blue").pack(side="bottom", pady=5)

        self.load_saved_credentials()

    def load_saved_credentials(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                self.username_entry.insert(0, config.get("username", ""))
                self.password_entry.insert(0, config.get("password", ""))
                self.remember_var.set(True)

    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password.")
            return

        try:
            response = requests.post(f"{API_BASE_URL}/login", json={"username": username, "password": password})
            response.raise_for_status()
            data = response.json()
            club_id = data.get("club_id")
            venues = data.get("venues", [])

            if self.remember_var.get():
                with open(CONFIG_FILE, "w") as f:
                    json.dump({"username": username, "password": password}, f)

            self.root.destroy()
            main_app_root = tk.Tk()
            LSDConnect(main_app_root, club_id, venues)
            main_app_root.mainloop()

        except Exception as e:
            with open(LOG_FILE, "a") as log:
                log.write(f"[LOGIN ERROR] {datetime.now().isoformat()}\n")
                traceback.print_exc(file=log)
            messagebox.showerror("Login Failed", f"Error: {e}")

class LSDConnect:
    def __init__(self, root, club_id, venues):
        self.root = root
        self.club_id = club_id
        self.venues = venues
        self.root.title("LSD Connect")
        self.root.geometry("420x360")
        self.running = True
        self.last_update_time = time.time()
        self.latest_raw_message = ""
        self.correct_weight = False
        self.track_condition = "Good 4"
        self.message1 = ""
        self.message2 = ""

        self.selected_venue = tk.StringVar(value=self.venues[0] if self.venues else "")

        try:
            self.logo = Image.open("logo.png").resize((350, 100))
            self.logo_image = ImageTk.PhotoImage(self.logo)
            self.logo_label = tk.Label(root, image=self.logo_image)
        except:
            self.logo_label = tk.Label(root, text="[Logo Missing]", font=("Arial", 12), fg="gray")
        self.logo_label.pack(pady=5)

        self.status_label = ttk.Label(root, text="Starting...", foreground="gray")
        self.status_label.pack()

        self.last_received = tk.StringVar(value="Last update: None")
        self.last_label = ttk.Label(root, textvariable=self.last_received)
        self.last_label.pack()

        ttk.Label(root, text="Venue:").pack()
        self.venue_menu = ttk.Combobox(root, textvariable=self.selected_venue, values=self.venues, state="readonly")
        self.venue_menu.pack(pady=5)

        msg1_frame = ttk.Frame(root)
        msg1_frame.pack(pady=2)
        ttk.Label(msg1_frame, text="Message 1 (Margins):").pack(side="left")
        self.msg1_entry = ttk.Entry(msg1_frame, width=25)
        self.msg1_entry.pack(side="left", padx=5)
        ttk.Button(msg1_frame, text="Send", command=self.send_message1).pack(side="left")

        msg2_frame = ttk.Frame(root)
        msg2_frame.pack(pady=2)
        ttk.Label(msg2_frame, text="Message 2:").pack(side="left")
        self.msg2_entry = ttk.Entry(msg2_frame, width=25)
        self.msg2_entry.pack(side="left", padx=5)
        ttk.Button(msg2_frame, text="Send", command=self.send_message2).pack(side="left")

        cond_frame = ttk.Frame(root)
        cond_frame.pack(pady=2)
        ttk.Label(cond_frame, text="Track Condition:").pack(side="left")
        self.condition_var = tk.StringVar(value=self.track_condition)
        cond_options = ["Firm 1", "Firm 2", "Good 3", "Good 4", "Soft 5", "Soft 6", "Soft 7", "Heavy 8", "Heavy 9", "Heavy 10"]
        self.condition_menu = ttk.OptionMenu(cond_frame, self.condition_var, self.track_condition, *cond_options)
        self.condition_menu.pack(side="left", padx=5)
        ttk.Button(cond_frame, text="Update", command=self.update_track_condition).pack(side="left")

        cw_frame = ttk.Frame(root)
        cw_frame.pack(pady=10)
        self.cw_status = tk.StringVar(value="No")
        self.cw_label = ttk.Label(cw_frame, text="Correct Weight:")
        self.cw_label.pack(side="left")
        self.cw_value_label = tk.Label(cw_frame, textvariable=self.cw_status, fg="red", font=("Arial", 10, "bold"))
        self.cw_value_label.pack(side="left", padx=5)
        ttk.Button(cw_frame, text="Toggle", command=self.toggle_correct_weight).pack(side="left")

        self.contact_label = ttk.Label(root, text="Support: chris.afford@gmail.com", foreground="blue")
        self.contact_label.pack(side="bottom", pady=5)

        self.listener_thread = threading.Thread(target=self.listen_tcp, daemon=True)
        self.listener_thread.start()

        self.root.after(1000, self.check_connection)

    def send_message1(self):
        self.message1 = self.msg1_entry.get()
        self.save_json()

    def send_message2(self):
        self.message2 = self.msg2_entry.get()
        self.save_json()

    def update_track_condition(self):
        self.track_condition = self.condition_var.get()
        self.save_json()

    def toggle_correct_weight(self):
        self.correct_weight = not self.correct_weight
        self.update_cw_display()
        self.save_json()

    def update_cw_display(self):
        if self.correct_weight:
            self.cw_status.set("Yes")
            self.cw_value_label.config(fg="green")
        else:
            self.cw_status.set("No")
            self.cw_value_label.config(fg="red")

    def save_json(self):
        data = {
            "timestamp": datetime.now().isoformat(),
            "club_id": self.club_id,
            "venue_name": self.selected_venue.get(),
            "status": "Live",
            "message1": self.message1,
            "message2": self.message2,
            "track_condition": self.track_condition,
            "correct_weight": "Yes" if self.correct_weight else "No",
            "raw_message": self.latest_raw_message
        }
        try:
            requests.post(f"{API_BASE_URL}/submit/{self.club_id}", json=data)
        except Exception as e:
            with open(LOG_FILE, "a") as log:
                log.write(f"[POST ERROR] {datetime.now().isoformat()}\n")
                traceback.print_exc(file=log)

    def listen_tcp(self):
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.bind(("0.0.0.0", TCP_PORT))
            server_socket.listen(1)
            self.status_label.config(text=f"Listening on TCP {TCP_PORT}", foreground="green")
        except Exception as e:
            self.status_label.config(text=f"Socket Error: {e}", foreground="red")
            return

        while self.running:
            try:
                client_socket, addr = server_socket.accept()
                with client_socket:
                    data = client_socket.recv(4096).decode(errors="replace").strip()
                    if not data:
                        continue

                    self.last_received.set(f"Last update: {datetime.now().strftime('%H:%M:%S')}")
                    self.last_update_time = time.time()

                    if "Command=LayoutDraw;Clear=2;" in data:
                        self.correct_weight = False
                        self.message1 = ""
                        self.message2 = ""
                        self.msg1_entry.delete(0, tk.END)
                        self.msg2_entry.delete(0, tk.END)
                        self.update_cw_display()
                    else:
                        self.latest_raw_message = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {data}"

                    self.save_json()

            except Exception as e:
                self.status_label.config(text=f"Error: {e}", foreground="red")
                with open(LOG_FILE, "a") as log:
                    log.write(f"[TCP ERROR] {datetime.now().isoformat()}\n")
                    traceback.print_exc(file=log)

    def check_connection(self):
        if time.time() - self.last_update_time > TIMEOUT_SECONDS:
            self.status_label.config(text="No Data", foreground="orange")
        self.root.after(1000, self.check_connection)

    def stop(self):
        self.running = False
        self.root.destroy()

if __name__ == "__main__":
    try:
        root = tk.Tk()
        login = LoginWindow(root, None)
        root.mainloop()
    except Exception as e:
        with open(LOG_FILE, "a") as log:
            log.write(f"[FATAL ERROR] {datetime.now().isoformat()}\n")
            traceback.print_exc(file=log)
        raise
