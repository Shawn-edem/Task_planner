from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from datetime import datetime, timedelta
import os
from models import db, User, Task, CalendarEvent
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-please-change')

# Configure SQLite database properly for Vercel
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', f"sqlite:///{os.path.join(app.instance_path, 'app.db')}")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure the instance folder exists for SQLite storage
os.makedirs(app.instance_path, exist_ok=True)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def home():
    if current_user.is_authenticated:
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        today = datetime.now().date()
        today_tasks = Task.query.filter_by(user_id=current_user.id).filter(db.func.date(Task.due_date) == today).order_by(Task.due_date).all()
        upcoming_events = CalendarEvent.query.filter_by(user_id=current_user.id).filter(CalendarEvent.start_time >= datetime.now()).order_by(CalendarEvent.start_time).all()

        categories = {}
        for task in tasks:
            category = task.category or 'Uncategorized'
            categories[category] = categories.get(category, 0) + 1

        return render_template("home.html", tasks=tasks, today_tasks=today_tasks, upcoming_events=upcoming_events, categories=categories)
    return render_template("home.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            return redirect(url_for('tasks_page'))
        flash('Invalid username or password')
    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user = User(
            username=request.form.get('username'),
            email=request.form.get('email')
        )
        user.set_password(request.form.get('password'))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        return redirect(url_for('tasks_page'))
    return render_template("register.html")

@app.route("/tasks")
@login_required
def tasks_page():
    tasks = Task.query.filter_by(user_id=current_user.id).order_by(Task.due_date).all()
    return render_template("tasks.html", tasks=tasks)

@app.route("/tasks/add", methods=['POST'])
@login_required
def add_task():
    task = Task(
        title=request.form.get('title'),
        description=request.form.get('description'),
        due_date=datetime.strptime(request.form.get('due_date'), '%Y-%m-%d') if request.form.get('due_date') else None,
        priority=request.form.get('priority', 'medium'),
        category=request.form.get('category'),
        user_id=current_user.id
    )
    db.session.add(task)
    db.session.commit()
    return redirect(url_for('tasks_page'))

@app.route("/calendar")
@login_required
def calendar_page():
    events = CalendarEvent.query.filter_by(user_id=current_user.id).all()
    return render_template("calendar.html", events=events)

@app.route("/calendar/events", methods=['GET'])
@login_required
def get_events():
    start = request.args.get('start')
    end = request.args.get('end')
    events = CalendarEvent.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': event.id,
        'title': event.title,
        'start': event.start_time.isoformat(),
        'end': event.end_time.isoformat(),
        'allDay': event.all_day
    } for event in events])

@app.route("/calendar/events", methods=['POST'])
@login_required
def add_event():
    data = request.get_json()

    if 'start' not in data or 'end' not in data:
        return jsonify({'error': 'Missing start or end time'}), 400

    try:
        new_event = CalendarEvent(
            title=data.get('title', 'Untitled Event'),
            start_time=datetime.fromisoformat(data['start']),
            end_time=datetime.fromisoformat(data['end']),
            all_day=data.get('allDay', False),
            user_id=current_user.id
        )
        db.session.add(new_event)
        db.session.commit()
        return jsonify({'status': 'success', 'event': {
            'id': new_event.id,
            'title': new_event.title,
            'start': new_event.start_time.isoformat(),
            'end': new_event.end_time.isoformat(),
            'allDay': new_event.all_day
        }}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

if __name__ == "__main__":
    app.run(debug=True)
