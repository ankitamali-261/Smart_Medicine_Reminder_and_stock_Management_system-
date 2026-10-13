import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime, date
import threading
import re
import os

# SMART MEDICINE REMINDER & STOCK MANAGEMENT SYSTEM

APP_TITLE = "Smart Medicine Reminder & Stock Management System"
DB_NAME = "medicine.db"

# DATABASE SETUP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, DB_NAME)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute("PRAGMA journal_mode = WAL")
cursor = conn.cursor()

def column_names(table_name):
    return {
        row[1]
        for row in cursor.execute(
            f"PRAGMA table_info({table_name})"
        ).fetchall()
    }

def add_column_if_missing(table_name, column_name, definition):
    if column_name not in column_names(table_name):
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
        )

# USERS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
)
""")

# MEDICINES TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS medicines (
    medicine_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    medicine_type TEXT NOT NULL DEFAULT '',
    dosage TEXT NOT NULL DEFAULT '',
    schedule TEXT NOT NULL DEFAULT 'Morning',
    morning_time TEXT,
    afternoon_time TEXT,
    night_time TEXT,
    quantity_value REAL NOT NULL DEFAULT 0,
    quantity_unit TEXT NOT NULL DEFAULT '',
    low_limit_value REAL NOT NULL DEFAULT 0,
    low_limit_unit TEXT NOT NULL DEFAULT '',
    expiry_date TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
""")

# HISTORY TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS medicine_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    medicine_id INTEGER NOT NULL,
    medicine_name TEXT NOT NULL,
    scheduled_time TEXT NOT NULL,
    action_time TEXT NOT NULL,
    status TEXT NOT NULL,
    quantity_after TEXT NOT NULL,
    FOREIGN KEY(medicine_id) REFERENCES medicines(medicine_id)
)
""")

# MIGRATIONS
medicine_columns = column_names("medicines")
old_columns_to_add = {
    "time": "TEXT",
    "quantity": "INTEGER DEFAULT 0",
    "low_stock_limit": "INTEGER DEFAULT 0",
    "schedule": "TEXT",
    "morning_time": "TEXT",
    "afternoon_time": "TEXT",
    "night_time": "TEXT",
    "medicine_type": "TEXT",
    "quantity_text": "TEXT",
    "low_limit_text": "TEXT",
    "quantity_value": "REAL DEFAULT 0",
    "quantity_unit": "TEXT DEFAULT ''",
    "low_limit_value": "REAL DEFAULT 0",
    "low_limit_unit": "TEXT DEFAULT ''",
    "created_at": "TEXT DEFAULT ''",
}

for col, definition in old_columns_to_add.items():
    if col not in medicine_columns:
        cursor.execute(f"ALTER TABLE medicines ADD COLUMN {col} {definition}")

conn.commit()

# VOICE ASSISTANT

try:
    import pyttsx3
    VOICE_AVAILABLE = True
except ImportError:
    VOICE_AVAILABLE = False

def speak(text):
    if not VOICE_AVAILABLE:
        return

    def voice_thread():
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except Exception:
            pass

    threading.Thread(target=voice_thread, daemon=True).start()

# FLEXIBLE HELPER FUNCTIONS (NO RESTRICTIONS)

def clean_number(value):
    try:
        number = float(value)
        if number.is_integer():
            return int(number)
        return round(number, 3)
    except (ValueError, TypeError):
        return 0

def parse_quantity(text):
    """Extracts numbers and units smoothly from ANY text input."""
    if not text:
        return 0, ""
    text_str = str(text).strip()
    match = re.search(r"(\d+(?:\.\d+)?)", text_str)
    if match:
        val = float(match.group(1))
        unit = re.sub(r"(\d+(?:\.\d+)?)", "", text_str).strip()
        return clean_number(val), unit
    return 0, text_str

def parse_dosage(dosage_text):
    """Parses dosage text gracefully without restricting format."""
    if not dosage_text:
        return 1.0, ""
    text_str = str(dosage_text).strip()
    match = re.search(r"(\d+(?:\.\d+)?)", text_str)
    if match:
        val = float(match.group(1))
        unit = re.sub(r"(\d+(?:\.\d+)?)", "", text_str).strip()
        return clean_number(val), unit
    return 1.0, text_str

def format_quantity(value, unit):
    if value is None:
        return ""
    val_str = str(clean_number(value))
    if unit:
        return f"{val_str} {unit}".strip()
    return val_str

def same_unit(unit1, unit2):
    return True

def date_display(value):
    return value or ""

def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()

def parse_time(value):
    return datetime.strptime(value, "%I:%M %p")

def time_sort_key(value):
    try:
        return parse_time(value)
    except ValueError:
        return datetime.max

def days_to_expiry(expiry):
    try:
        return (parse_date(expiry) - date.today()).days
    except ValueError:
        return None

def print_database_contents():
    print("\n" + "=" * 78)
    print("[DATABASE CONTENTS - medicine.db]")
    users = cursor.execute("SELECT user_id, name FROM users ORDER BY user_id").fetchall()
    print("\n[ALL USERS]")
    for u in users:
        print(f"  user_id={u[0]} | name={u[1]}")
    print("=" * 78 + "\n")

# MAIN APPLICATION

class MedicineApp:

    PERIODS = ("Morning", "Afternoon", "Night")

    def __init__(self, root, user_id, user_name):
        self.root = root
        self.user_id = user_id
        self.user_name = user_name

        self.root.title(APP_TITLE)
        self.root.geometry("1280x800")
        self.root.minsize(1120, 720)

        self.running = True
        self.reminded_today = set()

        self.setup_style()
        self.create_gui()

        self.refresh_all()
        self.update_clock()
        self.check_reminders()

        self.root.protocol("WM_DELETE_WINDOW", self.close_app)

    def setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TLabel", font=("Segoe UI", 10), padding=2)
        style.configure("TLabelframe.Label", font=("Segoe UI", 11, "bold"), foreground="#1f4e78")
        style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=(14, 8))
        style.configure("TEntry", font=("Segoe UI", 10), padding=6)
        style.configure("TCombobox", font=("Segoe UI", 10), padding=5)
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground="#1f4e78")
        style.configure("Heading.TLabel", font=("Segoe UI", 12, "bold"), foreground="#2c3e50")
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=32)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=(6, 6))

    def create_gui(self):
        header = tk.Frame(self.root, bg="#1f4e78", height=70)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(
            header,
            text="SMART MEDICINE REMINDER & STOCK MANAGEMENT",
            bg="#1f4e78",
            fg="white",
            font=("Segoe UI", 18, "bold")
        ).pack(side="left", padx=24)

        header_right = tk.Frame(header, bg="#1f4e78")
        header_right.pack(side="right", padx=24)

        tk.Label(
            header_right,
            text=f"User: {self.user_name}",
            bg="#1f4e78",
            fg="#e0e0e0",
            font=("Segoe UI", 11, "bold")
        ).pack(side="left", padx=(0, 12))

        ttk.Button(
            header_right,
            text="Switch User",
            command=self.switch_user
        ).pack(side="left")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=15)

        self.dashboard_tab = ttk.Frame(self.notebook)
        self.add_tab = ttk.Frame(self.notebook)
        self.stock_tab = ttk.Frame(self.notebook)
        self.history_tab = ttk.Frame(self.notebook)
        self.alert_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.dashboard_tab, text=" Dashboard ")
        self.notebook.add(self.add_tab, text=" Add Medicine ")
        self.notebook.add(self.stock_tab, text=" Medicine Stock ")
        self.notebook.add(self.history_tab, text=" Medicine History ")
        self.notebook.add(self.alert_tab, text=" Alerts ")

        self.create_dashboard()
        self.create_add_medicine()
        self.create_stock_tab()
        self.create_history_tab()
        self.create_alert_tab()

    def create_dashboard(self):
        top = ttk.Frame(self.dashboard_tab)
        top.pack(fill="x", padx=20, pady=(15, 10))

        ttk.Label(top, text=f"Medicine Dashboard  •  {self.user_name}", style="Title.TLabel").pack(side="left")
        self.clock_label = ttk.Label(top, font=("Segoe UI", 11, "bold"), foreground="#333333")
        self.clock_label.pack(side="right")

        cards = ttk.Frame(self.dashboard_tab)
        cards.pack(fill="x", padx=20, pady=(5, 10))

        self.total_label = self.create_card(cards, "Total Medicines", 0)
        self.low_label = self.create_card(cards, "Low Stock", 0)
        self.expiry_label = self.create_card(cards, "Expiry Alerts", 0)
        self.missed_label = self.create_card(cards, "Missed Doses", 0)

        ttk.Label(self.dashboard_tab, text="Today's Medicine Schedule", style="Heading.TLabel").pack(anchor="w", padx=20, pady=(12, 8))

        frame = ttk.Frame(self.dashboard_tab)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        columns = ("id", "name", "type", "dosage", "period", "time", "quantity", "expiry", "status")
        self.dashboard_tree = ttk.Treeview(frame, columns=columns, show="headings")

        headings = {
            "id": "ID", "name": "Medicine Name", "type": "Type", "dosage": "Dosage",
            "period": "Period", "time": "Scheduled Time", "quantity": "Stock Quantity",
            "expiry": "Expiry Date", "status": "Dose Status"
        }
        widths = {"id": 55, "name": 180, "type": 100, "dosage": 120, "period": 100, "time": 120, "quantity": 130, "expiry": 110, "status": 130}

        for col in columns:
            self.dashboard_tree.heading(col, text=headings[col])
            self.dashboard_tree.column(col, width=widths[col], anchor="center")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.dashboard_tree.yview)
        self.dashboard_tree.configure(yscrollcommand=scrollbar.set)
        self.dashboard_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        button_frame = ttk.Frame(self.dashboard_tab)
        button_frame.pack(fill="x", padx=20, pady=(5, 15))

        ttk.Button(button_frame, text="Mark Selected as TAKEN", command=self.mark_selected_taken).pack(side="left", padx=(0, 8))
        ttk.Button(button_frame, text="Mark Selected as MISSED", command=self.mark_selected_missed).pack(side="left", padx=4)
        ttk.Button(button_frame, text="Refresh Dashboard", command=self.refresh_all).pack(side="right")

    def create_card(self, parent, title, value):
        box = ttk.LabelFrame(parent, text=f"  {title}  ")
        box.pack(side="left", fill="x", expand=True, padx=5)
        label = ttk.Label(box, text=str(value), font=("Segoe UI", 22, "bold"), anchor="center", foreground="#1f4e78")
        label.pack(fill="x", pady=10)
        return label

    def create_add_medicine(self):
        container = ttk.Frame(self.add_tab)
        container.pack(fill="both", expand=True, padx=25, pady=20)

        ttk.Label(container, text="Add New Medicine", style="Title.TLabel").pack(anchor="w", pady=(0, 15))
        form = ttk.LabelFrame(container, text=" Medicine Details ")
        form.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)

        self.name_var = tk.StringVar()
        self.type_var = tk.StringVar()
        self.dosage_var = tk.StringVar()
        self.quantity_var = tk.StringVar()
        self.low_limit_var = tk.StringVar()
        self.expiry_var = tk.StringVar()
        self.schedule_var = tk.StringVar(value="Morning")

        self.morning_var = tk.StringVar()
        self.afternoon_var = tk.StringVar()
        self.night_var = tk.StringVar()

        # Row 0
        ttk.Label(form, text="Medicine Name:").grid(row=0, column=0, padx=15, pady=10, sticky="w")
        ttk.Entry(form, textvariable=self.name_var, width=32).grid(row=0, column=1, padx=15, pady=10)

        ttk.Label(form, text="Medicine Type:").grid(row=0, column=2, padx=15, pady=10, sticky="w")
        self.type_combo = ttk.Combobox(
            form, textvariable=self.type_var, width=30,
            values=("Tablet", "Syrup", "Capsule", "Injection", "Drops", "Powder", "Other")
        )
        self.type_combo.grid(row=0, column=3, padx=15, pady=10)

        # Row 1
        ttk.Label(form, text="Dosage:").grid(row=1, column=0, padx=15, pady=10, sticky="w")
        ttk.Entry(form, textvariable=self.dosage_var, width=32).grid(row=1, column=1, padx=15, pady=10)

        ttk.Label(form, text="Total Quantity:").grid(row=1, column=2, padx=15, pady=10, sticky="w")
        ttk.Entry(form, textvariable=self.quantity_var, width=32).grid(row=1, column=3, padx=15, pady=10)

        # Row 2
        ttk.Label(form, text="Low Stock Limit:").grid(row=2, column=0, padx=15, pady=10, sticky="w")
        ttk.Entry(form, textvariable=self.low_limit_var, width=32).grid(row=2, column=1, padx=15, pady=10)

        ttk.Label(form, text="Expiry Date (YYYY-MM-DD):").grid(row=2, column=2, padx=15, pady=10, sticky="w")
        ttk.Entry(form, textvariable=self.expiry_var, width=32).grid(row=2, column=3, padx=15, pady=10)

        # Row 3
        ttk.Label(form, text="Daily Schedule:").grid(row=3, column=0, padx=15, pady=10, sticky="w")
        schedule_combo = ttk.Combobox(
            form, textvariable=self.schedule_var, state="readonly", width=30,
            values=(
                "Morning", "Afternoon", "Night",
                "Morning + Afternoon", "Morning + Night",
                "Afternoon + Night", "Morning + Afternoon + Night"
            )
        )
        schedule_combo.grid(row=3, column=1, padx=15, pady=10)
        schedule_combo.bind("<<ComboboxSelected>>", lambda e: self.update_time_fields())

        time_frame = ttk.LabelFrame(container, text=" Medicine Time Slots ")
        time_frame.pack(fill="x", pady=10, ipadx=10, ipady=10)

        time_fields = [
            ("Morning Time (HH:MM AM/PM):", self.morning_var),
            ("Afternoon Time (HH:MM AM/PM):", self.afternoon_var),
            ("Night Time (HH:MM AM/PM):", self.night_var)
        ]

        for i, (label_text, variable) in enumerate(time_fields):
            ttk.Label(time_frame, text=label_text).grid(row=0, column=i * 2, padx=12, pady=10, sticky="w")
            ttk.Entry(time_frame, textvariable=variable, width=20).grid(row=0, column=i * 2 + 1, padx=12, pady=10)

        buttons = ttk.Frame(container)
        buttons.pack(fill="x", pady=15)

        ttk.Button(buttons, text="ADD MEDICINE", command=self.add_medicine).pack(side="left", padx=(0, 10))
        ttk.Button(buttons, text="CLEAR FORM", command=self.clear_add_form).pack(side="left")

        self.update_time_fields()

    def update_time_fields(self):
        schedule = self.schedule_var.get()
        if "Morning" not in schedule:
            self.morning_var.set("")
        if "Afternoon" not in schedule:
            self.afternoon_var.set("")
        if "Night" not in schedule:
            self.night_var.set("")

    def add_medicine(self):
        name = self.name_var.get().strip()
        medicine_type = self.type_var.get().strip()
        dosage = self.dosage_var.get().strip()
        quantity_text = self.quantity_var.get().strip()
        low_limit_text = self.low_limit_var.get().strip()
        expiry = self.expiry_var.get().strip()
        schedule = self.schedule_var.get().strip()

        if not name or not dosage or not quantity_text or not expiry:
            messagebox.showwarning("Missing Information", "Please fill in all required fields.")
            return

        quantity_value, quantity_unit = parse_quantity(quantity_text)
        low_value, low_unit = parse_quantity(low_limit_text)

        try:
            expiry_date = parse_date(expiry)
        except ValueError:
            messagebox.showerror("Invalid Date", "Enter the expiry date in YYYY-MM-DD format.")
            return

        times = {
            "Morning": self.morning_var.get().strip(),
            "Afternoon": self.afternoon_var.get().strip(),
            "Night": self.night_var.get().strip()
        }

        for period, time_value in times.items():
            if period in schedule:
                if not time_value:
                    messagebox.showwarning("Time Required", f"Please enter {period} time.")
                    return
                try:
                    parsed = parse_time(time_value)
                    times[period] = parsed.strftime("%I:%M %p")
                except ValueError:
                    messagebox.showerror("Invalid Time", f"Invalid {period} time format (use HH:MM AM/PM).")
                    return

        morning = times["Morning"] if "Morning" in schedule else None
        afternoon = times["Afternoon"] if "Afternoon" in schedule else None
        night = times["Night"] if "Night" in schedule else None
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            cursor.execute("""
                INSERT INTO medicines (
                    user_id, name, medicine_type, dosage, schedule,
                    morning_time, afternoon_time, night_time,
                    quantity_value, quantity_unit, low_limit_value, low_limit_unit,
                    expiry_date, active, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.user_id, name, medicine_type, dosage, schedule,
                morning, afternoon, night,
                quantity_value, quantity_unit, low_value, low_unit,
                expiry, 1, created_at
            ))

            conn.commit()
            self.clear_add_form()
            self.refresh_all()
            self.notebook.select(self.dashboard_tab)

            messagebox.showinfo(
                "Success",
                f"'{name}' was added successfully!\n\n"
                f"Quantity: {format_quantity(quantity_value, quantity_unit)}\n"
                f"Dosage: {dosage}"
            )

        except sqlite3.Error as error:
            conn.rollback()
            messagebox.showerror("Database Error", f"Medicine could not be saved.\n\n{error}")

    def clear_add_form(self):
        self.name_var.set("")
        self.type_var.set("")
        self.dosage_var.set("")
        self.quantity_var.set("")
        self.low_limit_var.set("")
        self.expiry_var.set("")
        self.schedule_var.set("Morning")
        self.morning_var.set("")
        self.afternoon_var.set("")
        self.night_var.set("")

    def get_medicines(self):
        cursor.execute("""
            SELECT
                medicine_id, name, medicine_type, dosage, schedule,
                morning_time, afternoon_time, night_time,
                quantity_value, quantity_unit, low_limit_value, low_limit_unit,
                expiry_date, active
            FROM medicines
            WHERE user_id=? AND active=1
            ORDER BY name COLLATE NOCASE
        """, (self.user_id,))
        return cursor.fetchall()

    def dose_rows(self):
        rows = []
        for med in self.get_medicines():
            med_id, name, med_type, dosage, schedule, morning, afternoon, night, q_val, q_unit, l_val, l_unit, expiry, active = med
            times = (("Morning", morning), ("Afternoon", afternoon), ("Night", night))
            for period, time_val in times:
                if time_val:
                    rows.append({
                        "medicine_id": med_id, "name": name, "type": med_type, "dosage": dosage,
                        "period": period, "time": time_val, "quantity": format_quantity(q_val, q_unit),
                        "quantity_value": q_val, "quantity_unit": q_unit, "low_value": l_val,
                        "low_unit": l_unit, "expiry": expiry
                    })
        rows.sort(key=lambda r: time_sort_key(r["time"]))
        return rows

    def history_exists(self, medicine_id, scheduled_time):
        today = date.today().isoformat()
        cursor.execute("""
            SELECT history_id FROM medicine_history
            WHERE medicine_id=? AND scheduled_time=? AND substr(action_time, 1, 10)=?
            LIMIT 1
        """, (medicine_id, scheduled_time, today))
        return cursor.fetchone() is not None

    def stock_status(self, quantity_value, quantity_unit, low_value, low_unit):
        if quantity_value <= 0:
            return "OUT OF STOCK"
        if quantity_value <= low_value:
            return "LOW STOCK"
        return "OK"

    def status_for(self, medicine_id, scheduled, quantity_value, quantity_unit, expiry):
        try:
            if parse_date(expiry) < date.today():
                return "EXPIRED"
        except ValueError:
            pass

        if quantity_value <= 0:
            return "OUT OF STOCK"

        cursor.execute("""
            SELECT status FROM medicine_history
            WHERE medicine_id=? AND scheduled_time=? AND substr(action_time, 1, 10)=?
            ORDER BY history_id DESC LIMIT 1
        """, (medicine_id, scheduled, date.today().isoformat()))

        history = cursor.fetchone()
        if history:
            return history[0]

        now = datetime.now()
        try:
            scheduled_dt = parse_time(scheduled)
            current_dt = now.replace(hour=scheduled_dt.hour, minute=scheduled_dt.minute, second=0, microsecond=0)
            if now.strftime("%I:%M %p") == scheduled:
                return "TIME TO TAKE"
            if current_dt < now:
                return "PENDING"
        except ValueError:
            pass

        return "UPCOMING"

    def refresh_dashboard(self):
        for item in self.dashboard_tree.get_children():
            self.dashboard_tree.delete(item)

        rows = self.dose_rows()
        for row in rows:
            status = self.status_for(row["medicine_id"], row["time"], row["quantity_value"], row["quantity_unit"], row["expiry"])
            self.dashboard_tree.insert(
                "", "end",
                values=(
                    row["medicine_id"], row["name"], row["type"], row["dosage"],
                    row["period"], row["time"], row["quantity"], date_display(row["expiry"]), status
                )
            )

        medicines = self.get_medicines()
        low_count = sum(1 for m in medicines if self.stock_status(m[8], m[9], m[10], m[11]) == "LOW STOCK")
        expiry_count = sum(1 for m in medicines if (days := days_to_expiry(m[12])) is not None and 0 <= days <= 30)

        cursor.execute("""
            SELECT COUNT(*) FROM medicine_history h
            JOIN medicines m ON h.medicine_id=m.medicine_id
            WHERE m.user_id=? AND h.status='MISSED' AND m.active=1
        """, (self.user_id,))
        missed_count = cursor.fetchone()[0]

        self.total_label.config(text=str(len(medicines)))
        self.low_label.config(text=str(low_count))
        self.expiry_label.config(text=str(expiry_count))
        self.missed_label.config(text=str(missed_count))

    def create_stock_tab(self):
        ttk.Label(self.stock_tab, text="Medicine Stock Management", style="Title.TLabel").pack(anchor="w", padx=20, pady=(15, 10))

        frame = ttk.Frame(self.stock_tab)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        columns = ("id", "name", "type", "dosage", "quantity", "limit", "expiry", "status")
        self.stock_tree = ttk.Treeview(frame, columns=columns, show="headings")

        headings = {
            "id": "ID", "name": "Medicine Name", "type": "Type", "dosage": "Dosage",
            "quantity": "Current Stock", "limit": "Low Limit", "expiry": "Expiry Date", "status": "Stock Status"
        }
        widths = {"id": 55, "name": 180, "type": 110, "dosage": 120, "quantity": 130, "limit": 130, "expiry": 115, "status": 135}

        for col in columns:
            self.stock_tree.heading(col, text=headings[col])
            self.stock_tree.column(col, width=widths[col], anchor="center")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.stock_tree.yview)
        self.stock_tree.configure(yscrollcommand=scrollbar.set)
        self.stock_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        buttons = ttk.Frame(self.stock_tab)
        buttons.pack(fill="x", padx=20, pady=(5, 15))

        ttk.Button(buttons, text="Add Stock", command=self.add_stock).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Delete Medicine", command=self.delete_medicine).pack(side="left", padx=4)
        ttk.Button(buttons, text="Refresh Stock", command=self.refresh_all).pack(side="right")

    def refresh_stock(self):
        for item in self.stock_tree.get_children():
            self.stock_tree.delete(item)

        for med in self.get_medicines():
            med_id, name, med_type, dosage, schedule, morning, afternoon, night, q_val, q_unit, l_val, l_unit, expiry, active = med
            status = self.stock_status(q_val, q_unit, l_val, l_unit)
            self.stock_tree.insert(
                "", "end",
                values=(
                    med_id, name, med_type, dosage,
                    format_quantity(q_val, q_unit), format_quantity(l_val, l_unit),
                    date_display(expiry), status
                )
            )

    def add_stock(self):
        selected = self.stock_tree.selection()
        if not selected:
            messagebox.showwarning("Select Medicine", "Please select a medicine from the list first.")
            return

        values = self.stock_tree.item(selected[0])["values"]
        medicine_id = int(values[0])
        medicine_name = str(values[1])
        old_quantity_text = str(values[4])

        dialog = tk.Toplevel(self.root)
        dialog.title("Add Stock")
        dialog.geometry("440x260")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=medicine_name, font=("Segoe UI", 14, "bold"), foreground="#1f4e78").pack(pady=(20, 5))
        ttk.Label(dialog, text=f"Current Stock: {old_quantity_text}", font=("Segoe UI", 10)).pack(pady=5)

        quantity_var = tk.StringVar()
        ttk.Label(dialog, text="Quantity to Add (e.g. 10 tablets, 50 ml):").pack(pady=(10, 2))
        ttk.Entry(dialog, textvariable=quantity_var, width=28).pack(pady=5)

        def save_stock():
            amount_text = quantity_var.get().strip()
            if not amount_text:
                messagebox.showwarning("Input Required", "Please enter quantity.")
                return

            add_value, add_unit = parse_quantity(amount_text)

            row = cursor.execute("""
                SELECT quantity_value, quantity_unit FROM medicines
                WHERE medicine_id=? AND user_id=? AND active=1
            """, (medicine_id, self.user_id)).fetchone()

            if not row:
                dialog.destroy()
                return

            old_value, old_unit = row
            new_value = (old_value or 0) + add_value
            new_unit = old_unit if old_unit else add_unit

            cursor.execute("""
                UPDATE medicines SET quantity_value=?, quantity_unit=?
                WHERE medicine_id=? AND user_id=? AND active=1
            """, (new_value, new_unit, medicine_id, self.user_id))

            conn.commit()
            dialog.destroy()
            self.refresh_all()

            messagebox.showinfo(
                "Stock Updated",
                f"{medicine_name} stock updated successfully.\n\nNew Stock: {format_quantity(new_value, new_unit)}"
            )

        ttk.Button(dialog, text="SAVE STOCK", command=save_stock).pack(pady=15)

    def delete_medicine(self):
        selected = self.stock_tree.selection()
        if not selected:
            messagebox.showwarning("Select Medicine", "Please select a medicine first.")
            return

        values = self.stock_tree.item(selected[0])["values"]
        medicine_id = int(values[0])
        medicine_name = str(values[1])

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to remove '{medicine_name}'?"):
            cursor.execute("UPDATE medicines SET active=0 WHERE medicine_id=? AND user_id=?", (medicine_id, self.user_id))
            conn.commit()
            self.refresh_all()
            messagebox.showinfo("Medicine Removed", f"'{medicine_name}' was removed successfully.")

    def create_history_tab(self):
        ttk.Label(self.history_tab, text="Medicine History & Missed Doses", style="Title.TLabel").pack(anchor="w", padx=20, pady=(15, 10))

        frame = ttk.Frame(self.history_tab)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        columns = ("id", "medicine", "scheduled", "action", "status", "stock")
        self.history_tree = ttk.Treeview(frame, columns=columns, show="headings")

        headings = {"id": "ID", "medicine": "Medicine Name", "scheduled": "Scheduled Time", "action": "Action Date & Time", "status": "Dose Status", "stock": "Remaining Stock"}
        widths = {"id": 60, "medicine": 190, "scheduled": 130, "action": 190, "status": 110, "stock": 140}

        for col in columns:
            self.history_tree.heading(col, text=headings[col])
            self.history_tree.column(col, width=widths[col], anchor="center")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=scrollbar.set)
        self.history_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def refresh_history(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        cursor.execute("""
            SELECT h.history_id, h.medicine_name, h.scheduled_time, h.action_time, h.status, h.quantity_after
            FROM medicine_history h
            JOIN medicines m ON h.medicine_id=m.medicine_id
            WHERE m.user_id=? AND m.active=1
            ORDER BY h.history_id DESC
        """, (self.user_id,))

        for row in cursor.fetchall():
            self.history_tree.insert("", "end", values=row) 
       
    def create_alert_tab(self):
        ttk.Label(self.alert_tab, text="Medicine Alerts & Notifications", style="Title.TLabel").pack(anchor="w", padx=20, pady=(15, 10))

        frame = ttk.Frame(self.alert_tab)
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 15))

        columns = ("type", "medicine", "message")
        self.alert_tree = ttk.Treeview(frame, columns=columns, show="headings")

        self.alert_tree.heading("type", text="Alert Type")
        self.alert_tree.heading("medicine", text="Medicine Name")
        self.alert_tree.heading("message", text="Notification Message")

        self.alert_tree.column("type", width=150, anchor="center")
        self.alert_tree.column("medicine", width=200, anchor="center")
        self.alert_tree.column("message", width=600, anchor="w")

        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.alert_tree.yview)
        self.alert_tree.configure(yscrollcommand=scrollbar.set)
        self.alert_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    def refresh_alerts(self):
        for item in self.alert_tree.get_children():
            self.alert_tree.delete(item)

        for med in self.get_medicines():
            med_id, name, med_type, dosage, schedule, morning, afternoon, night, q_val, q_unit, l_val, l_unit, expiry, active = med
            status = self.stock_status(q_val, q_unit, l_val, l_unit)

            if status == "OUT OF STOCK":
                self.alert_tree.insert("", "end", values=("OUT OF STOCK", name, "Medicine stock is completely finished."))
            elif status == "LOW STOCK":
                self.alert_tree.insert("", "end", values=("LOW STOCK", name, "Medicine stock has reached low stock limit."))

            days = days_to_expiry(expiry)
            if days is not None:
                if days < 0:
                    self.alert_tree.insert("", "end", values=("EXPIRED", name, "Medicine expiry date has passed."))
                elif days <= 30:
                    self.alert_tree.insert("", "end", values=("EXPIRY ALERT", name, f"Medicine will expire in {days} day(s)."))

        cursor.execute("""
            SELECT h.medicine_name, COUNT(*)
            FROM medicine_history h
            JOIN medicines m ON h.medicine_id=m.medicine_id
            WHERE m.user_id=? AND h.status='MISSED'
            GROUP BY h.medicine_name
        """, (self.user_id,))

        for name, count in cursor.fetchall():
            self.alert_tree.insert("", "end", values=("MISSED DOSE", name, f"{count} missed dose(s) recorded in history."))

    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_stock()
        self.refresh_history()
        self.refresh_alerts()

    def selected_dose(self):
        selected = self.dashboard_tree.selection()
        if not selected:
            messagebox.showwarning("Select Dose", "Please select a medicine dose from Dashboard.")
            return None
        values = self.dashboard_tree.item(selected[0])["values"]
        return int(values[0]), str(values[5])

    def record_taken(self, medicine_id, scheduled, show=True):
        row = cursor.execute("""
            SELECT name, dosage, quantity_value, quantity_unit FROM medicines
            WHERE medicine_id=? AND user_id=? AND active=1
        """, (medicine_id, self.user_id)).fetchone()

        if not row:
            return

        name, dosage_text, quantity_value, quantity_unit = row

        if self.history_exists(medicine_id, scheduled):
            if show:
                messagebox.showinfo("Already Recorded", "This dose has already been recorded today.")
            return

        if quantity_value <= 0:
            if show:
                messagebox.showwarning("Out of Stock", f"{name} has no stock left.")
            return

        # Flexible Deduction Logic
        dosage_val, dosage_unit = parse_dosage(dosage_text)
        
        # Smart deduction: If dosage number is reasonable deduct it.
        if dosage_val > 0 and dosage_val <= quantity_value:
            deduct_val = dosage_val
        else:
            deduct_val = 1.0  # Default to 1 count if dosage value is e.g. 500 mg against 10 tablets stock

        new_quantity = max(0, quantity_value - deduct_val)
        action_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute("""
            UPDATE medicines SET quantity_value=? WHERE medicine_id=? AND user_id=?
        """, (new_quantity, medicine_id, self.user_id))

        cursor.execute("""
            INSERT INTO medicine_history (
                medicine_id, medicine_name, scheduled_time, action_time, status, quantity_after
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (medicine_id, name, scheduled, action_time, "TAKEN", format_quantity(new_quantity, quantity_unit)))

        conn.commit()

        if show:
            messagebox.showinfo(
                "Medicine Taken",
                f"'{name}' marked as TAKEN.\n\nRemaining Stock: {format_quantity(new_quantity, quantity_unit)}"
            )

        self.refresh_all()

    def record_missed(self, medicine_id, scheduled, show=True):
        row = cursor.execute("""
            SELECT name, quantity_value, quantity_unit FROM medicines
            WHERE medicine_id=? AND user_id=? AND active=1
        """, (medicine_id, self.user_id)).fetchone()

        if not row:
            return

        name, quantity_value, quantity_unit = row

        if self.history_exists(medicine_id, scheduled):
            if show:
                messagebox.showinfo("Already Recorded", "This dose has already been recorded today.")
            return

        action_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO medicine_history (
                medicine_id, medicine_name, scheduled_time, action_time, status, quantity_after
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (medicine_id, name, scheduled, action_time, "MISSED", format_quantity(quantity_value, quantity_unit)))

        conn.commit()

        if show:
            messagebox.showwarning("Missed Dose", f"'{name}' marked as MISSED.")

        self.refresh_all()

    def mark_selected_taken(self):
        selected = self.selected_dose()
        if selected:
            self.record_taken(*selected)

    def mark_selected_missed(self):
        selected = self.selected_dose()
        if selected:
            self.record_missed(*selected)

    def check_reminders(self):
        if not self.running:
            return

        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        for row in self.dose_rows():
            medicine_id = row["medicine_id"]
            name = row["name"]
            medicine_type = row["type"]
            dosage = row["dosage"]
            period = row["period"]
            scheduled_time = row["time"]
            quantity_value = row["quantity_value"]

            key = f"{today}_{medicine_id}_{scheduled_time}"

            if key in self.reminded_today:
                continue

            if self.history_exists(medicine_id, scheduled_time):
                self.reminded_today.add(key)
                continue

            try:
                scheduled_dt = parse_time(scheduled_time)
                dose_time_today = now.replace(
                    hour=scheduled_dt.hour,
                    minute=scheduled_dt.minute,
                    second=0,
                    microsecond=0
                )
            except ValueError:
                continue

            if now >= dose_time_today:
                self.reminded_today.add(key)

                is_overdue = (now - dose_time_today).total_seconds() > 120
                title_text = "OVERDUE MEDICINE REMINDER" if is_overdue else "MEDICINE REMINDER"

                if quantity_value <= 0:
                    self.show_reminder(
                        "Out of Stock",
                        f"{name} was scheduled for {scheduled_time}.\nStock is empty.",
                        medicine_id,
                        scheduled_time,
                        False
                    )
                else:
                    if is_overdue:
                        msg = (
                            f"Overdue Dose Notice!\n\n"
                            f"Scheduled Time: {scheduled_time}\n"
                            f"Medicine: {name} ({medicine_type})\n"
                            f"Dosage: {dosage} | Schedule: {period}\n\n"
                            f"Did you take this medicine?"
                        )
                    else:
                        msg = (
                            f"Time to take {name}.\n"
                            f"Type: {medicine_type} | Dosage: {dosage}\n"
                            f"Schedule: {period}"
                        )

                    self.show_reminder(
                        title_text,
                        msg,
                        medicine_id,
                        scheduled_time,
                        True
                    )

        self.root.after(1000, self.check_reminders)

    def show_reminder(self, title, message, medicine_id, scheduled, voice):
        if voice:
            speak(message)

        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("480x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(dialog, text=title, font=("Segoe UI", 16, "bold"), foreground="#1f4e78").pack(pady=(25, 10))
        ttk.Label(dialog, text=message, font=("Segoe UI", 10), justify="center").pack(pady=10)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)

        def taken():
            dialog.destroy()
            self.record_taken(medicine_id, scheduled)

        def missed():
            dialog.destroy()
            self.record_missed(medicine_id, scheduled)

        ttk.Button(button_frame, text="TAKEN", command=taken).pack(side="left", padx=10)
        ttk.Button(button_frame, text="MISSED", command=missed).pack(side="left", padx=10)

        dialog.protocol("WM_DELETE_WINDOW", missed)

    def update_clock(self):
        if not self.running:
            return
        self.clock_label.config(text=datetime.now().strftime("%Y-%m-%d   %I:%M:%S %p"))
        self.root.after(1000, self.update_clock)

    def switch_user(self):
        self.logout_requested = True
        self.close_app()

    def close_app(self):
        self.running = False
        try:
            conn.commit()
        except sqlite3.Error:
            pass
        self.root.destroy()
        
# LOGIN WINDOW

class LoginWindow:

    def __init__(self, root):
        self.root = root
        self.root.title("Smart Medicine System - Login")
        self.root.geometry("520x400")
        self.root.resizable(False, False)
        self.user_info = None
        self.create_login()

    def create_login(self):
        header = tk.Frame(self.root, bg="#1f4e78", height=100)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="SMART MEDICINE", bg="#1f4e78", fg="white", font=("Segoe UI", 22, "bold")).pack(pady=(18, 2))
        tk.Label(header, text="Reminder & Stock Management System", bg="#1f4e78", fg="#e0e0e0", font=("Segoe UI", 10)).pack()

        frame = ttk.LabelFrame(self.root, text=" User Login ")
        frame.pack(fill="x", padx=45, pady=30, ipadx=10, ipady=10)

        self.name_var = tk.StringVar()

        ttk.Label(frame, text="Enter Your Name:", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, padx=15, pady=20, sticky="w")
        ttk.Entry(frame, textvariable=self.name_var, width=28).grid(row=0, column=1, padx=15, pady=20)

        ttk.Button(frame, text="Login / Continue", command=self.login).grid(row=1, column=0, columnspan=2, pady=10)

    def login(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Name Required", "Please enter your name.")
            return

        row = cursor.execute("SELECT user_id, name FROM users WHERE lower(name)=lower(?) LIMIT 1", (name,)).fetchone()

        if row:
            user_id, stored_name = row[0], row[1]
        else:
            try:
                cursor.execute("INSERT INTO users(name) VALUES(?)", (name,))
                conn.commit()
                user_id, stored_name = cursor.lastrowid, name
            except sqlite3.IntegrityError:
                row = cursor.execute("SELECT user_id, name FROM users WHERE lower(name)=lower(?) LIMIT 1", (name,)).fetchone()
                user_id, stored_name = row[0], row[1]

        self.user_info = {"id": user_id, "name": stored_name}
        self.root.destroy()

# ENTRY POINT

if __name__ == "__main__":
    while True:
        root = tk.Tk()
        login = LoginWindow(root)
        root.mainloop()

        if not login.user_info:
            try:
                conn.close()
            except sqlite3.Error:
                pass
            break

        main_window = tk.Tk()
        app = MedicineApp(main_window, login.user_info["id"], login.user_info["name"])
        main_window.mainloop()

        if not getattr(app, "logout_requested", False):
            try:
                conn.close()
            except sqlite3.Error:
                pass
            break