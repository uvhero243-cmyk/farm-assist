from datetime import datetime
import sqlite3
from pathlib import Path

import requests
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session
)
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

app = Flask(__name__)
app.secret_key = "farm-assist-change-this-secret-key"

DB_PATH = Path(__file__).resolve().parent / "farm_assist.db"
# Admin credentials for local development
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "yugank1234"


# ---------------- DATABASE ----------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL
            )
        """)

        # Add registration date to an existing users table if needed
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }

        if "created_at" not in columns:
            conn.execute("""
                ALTER TABLE users
                ADD COLUMN created_at TEXT
            """)

            conn.execute("""
                UPDATE users
                SET created_at = CURRENT_TIMESTAMP
                WHERE created_at IS NULL
            """)

        # Store successful login activity
        conn.execute("""
            CREATE TABLE IF NOT EXISTS login_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                login_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

# ---------------- HOME ----------------

@app.route("/")
def home():
    return render_template("landing.html")


@app.route("/about")
def about():
    return "Welcome to Farm Assist!"


# ---------------- REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("Please fill in all fields.")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must contain at least 8 characters.")
            return redirect(url_for("register"))

        password_hash = generate_password_hash(password)

        try:
            with get_db() as conn:
                conn.execute(
                    """
                    INSERT INTO users (name, email, password_hash)
                    VALUES (?, ?, ?)
                    """,
                    (name, email, password_hash)
                )

            flash("Registration successful! Please log in.")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("This email is already registered.")
            return redirect(url_for("register"))

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        if user and check_password_hash(
            user["password_hash"], password
        ):
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO login_activity (user_id, email)
                    VALUES (?, ?)
                """, (user["id"], user["email"]))

            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")
        return redirect(url_for("login"))

    return render_template("login.html")


# ---------------- DASHBOARD ----------------

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        flash("Please log in to access your dashboard.")
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        name=session.get("user_name", "Farmer")
    )


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.")
    return redirect(url_for("home"))


# ---------------- CROP RECOMMENDATION ----------------

@app.route("/crop-recommendation", methods=["GET", "POST"])
def crop_recommendation():
    if "user_id" not in session:
        flash("Please log in first.")
        return redirect(url_for("login"))

    recommendations = []

    selected = {
        "soil": "",
        "season": "",
        "location": ""
    }

    crop_data = {
        "Alluvial": {
            "Kharif": ["Rice", "Maize", "Sugarcane"],
            "Rabi": ["Wheat", "Mustard", "Peas"],
            "Zaid": ["Watermelon", "Cucumber"]
        },
        "Black": {
            "Kharif": ["Cotton", "Soybean", "Sorghum"],
            "Rabi": ["Wheat", "Chickpea"],
            "Zaid": ["Green gram", "Watermelon"]
        },
        "Red": {
            "Kharif": ["Groundnut", "Millets", "Pulses"],
            "Rabi": ["Chickpea", "Mustard"],
            "Zaid": ["Watermelon", "Vegetables"]
        },
        "Sandy": {
            "Kharif": ["Pearl millet", "Guar"],
            "Rabi": ["Mustard", "Chickpea"],
            "Zaid": ["Watermelon", "Muskmelon"]
        },
        "Clay": {
            "Kharif": ["Rice", "Jute"],
            "Rabi": ["Wheat", "Lentils"],
            "Zaid": ["Vegetables"]
        },
        "Loamy": {
            "Kharif": ["Maize", "Rice", "Soybean"],
            "Rabi": ["Wheat", "Potato", "Peas"],
            "Zaid": ["Cucumber", "Watermelon"]
        }
    }

    if request.method == "POST":
        soil = request.form.get("soil", "")
        season = request.form.get("season", "")
        location = request.form.get("location", "").strip()

        selected = {
            "soil": soil,
            "season": season,
            "location": location
        }

        if (
            not location
            or soil not in crop_data
            or season not in ("Kharif", "Rabi", "Zaid")
        ):
            flash("Please enter a location and select valid options.")
        else:
            recommendations = crop_data[soil].get(season, [])

            if not recommendations:
                flash("No suggestions found for these selections.")

    return render_template(
        "crop_recommendation.html",
        recommendations=recommendations,
        selected=selected
    )


# ---------------- WEATHER INFORMATION ----------------

@app.route("/weather", methods=["GET", "POST"])
def weather():
    if "user_id" not in session:
        flash("Please log in first.")
        return redirect(url_for("login"))

    city = ""
    weather_data = None
    error = None

    if request.method == "POST":
        city = request.form.get("city", "").strip()

        if not city:
            error = "Please enter a city or district name."

        else:
            try:
                # Search for the location
                geo_response = requests.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={
                        "name": city,
                        "count": 1,
                        "language": "en",
                        "format": "json",
                        "countryCode": "IN"
                    },
                    timeout=15
                )

                geo_response.raise_for_status()

                locations = geo_response.json().get("results", [])

                if not locations:
                    error = (
                        "Location not found. "
                        "Please enter another Indian city or district."
                    )

                else:
                    location = locations[0]

                    latitude = location["latitude"]
                    longitude = location["longitude"]

                    # Get current weather information
                    weather_response = requests.get(
                        "https://api.open-meteo.com/v1/forecast",
                        params={
                            "latitude": latitude,
                            "longitude": longitude,
                            "current": (
                                "temperature_2m,"
                                "relative_humidity_2m,"
                                "apparent_temperature,"
                                "is_day,"
                                "precipitation,"
                                "weather_code,"
                                "wind_speed_10m"
                            ),
                            "timezone": "auto"
                        },
                        timeout=15
                    )

                    weather_response.raise_for_status()

                    current = weather_response.json().get("current", {})

                    if "temperature_2m" not in current:
                        error = "Current weather data is unavailable."

                    else:
                        descriptions = {
                            0: "Clear sky",
                            1: "Mainly clear",
                            2: "Partly cloudy",
                            3: "Overcast",
                            45: "Fog",
                            48: "Depositing rime fog",
                            51: "Light drizzle",
                            53: "Moderate drizzle",
                            55: "Dense drizzle",
                            56: "Freezing drizzle",
                            57: "Dense freezing drizzle",
                            61: "Slight rain",
                            63: "Moderate rain",
                            65: "Heavy rain",
                            66: "Freezing rain",
                            67: "Heavy freezing rain",
                            71: "Slight snowfall",
                            73: "Moderate snowfall",
                            75: "Heavy snowfall",
                            77: "Snow grains",
                            80: "Rain showers",
                            81: "Moderate rain showers",
                            82: "Heavy rain showers",
                            85: "Snow showers",
                            86: "Heavy snow showers",
                            95: "Thunderstorm",
                            96: "Thunderstorm with hail",
                            99: "Thunderstorm with heavy hail"
                        }

                        code = current.get("weather_code", -1)

                        weather_data = {
                            "city": location["name"],
                            "region": location.get("admin1", ""),
                            "temperature": current["temperature_2m"],
                            "feels_like": current.get(
                                "apparent_temperature", "N/A"
                            ),
                            "humidity": current.get(
                                "relative_humidity_2m", "N/A"
                            ),
                            "wind_speed": current.get(
                                "wind_speed_10m", "N/A"
                            ),
                            "precipitation": current.get(
                                "precipitation", "N/A"
                            ),
                            "condition": descriptions.get(
                                code,
                                "Weather condition unavailable"
                            ),
                            "is_day": current.get("is_day", 1),
                            "time": current.get("time", "")
                        }

            except requests.RequestException:
                error = (
                    "Unable to connect to the weather service. "
                    "Check your internet connection and try again."
                )

            except (ValueError, KeyError, TypeError):
                error = (
                    "Unable to read weather data. Please try again."
                )

    return render_template(
        "weather.html",
        city=city,
        weather_data=weather_data,
        error=error
    )
# ---------------- ADMIN PANEL ----------------

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):
            session.clear()
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin username or password.")

    return render_template("admin_login.html")


@app.route("/admin")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        flash("Please log in as an administrator.")
        return redirect(url_for("admin_login"))

    with get_db() as conn:
        users = conn.execute("""
            SELECT id, name, email, created_at
            FROM users
            ORDER BY id DESC
        """).fetchall()

        total_users = conn.execute("""
            SELECT COUNT(*) FROM users
        """).fetchone()[0]

        recent_logins = conn.execute("""
            SELECT login_activity.email,
                   login_activity.login_at,
                   users.name
            FROM login_activity
            LEFT JOIN users
                ON users.id = login_activity.user_id
            ORDER BY login_activity.id DESC
            LIMIT 100
        """).fetchall()

        total_logins = conn.execute("""
            SELECT COUNT(*) FROM login_activity
        """).fetchone()[0]

    return render_template(
        "admin.html",
        users=users,
        total_users=total_users,
        recent_logins=recent_logins,
        total_logins=total_logins
    )




# ---------------- ADMIN PANEL ----------------
@app.route("/admin-logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Admin logged out successfully.")
    return redirect(url_for("admin_login"))

# ---------------- START APPLICATION ----------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
