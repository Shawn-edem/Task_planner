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
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///planner.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
with app.app_context():
    db.init_app(app)
    migrate = Migrate(app, db)
    if not os.path.exists('instance'):
        os.makedirs('instance', exist_ok=True)
    if not os.path.exists('instance/planner.db'):
        db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/")
def home():
    """Serve the homepage."""
    if current_user.is_authenticated:
        tasks = Task.query.filter_by(user_id=current_user.id).all()
        today = datetime.now().date()
        today_tasks = Task.query.filter_by(user_id=current_user.id)\
            .filter(db.func.date(Task.due_date) == today)\
            .order_by(Task.due_date)\
            .all()
        
        upcoming_events = CalendarEvent.query.filter_by(user_id=current_user.id)\
            .filter(CalendarEvent.start_time >= datetime.now())\
            .order_by(CalendarEvent.start_time)\
            .all()
        
        # Get task categories with counts
        categories = {}
        for task in tasks:
            category = task.category or 'Uncategorized'
            categories[category] = categories.get(category, 0) + 1
            
        return render_template("home.html", 
                             tasks=tasks,
                             today_tasks=today_tasks,
                             upcoming_events=upcoming_events,
                             categories=categories)
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
    """Serve the tasks page."""
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
    """Serve the calendar page."""
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

    # Check for required keys in the incoming data
    if 'start' not in data or 'end' not in data:
        return jsonify({'error': 'Missing start or end time'}), 400

    try:
        new_event = CalendarEvent(
            title=data.get('title', 'Untitled Event'),  # Default title if not provided
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


@app.route("/api/tasks", methods=['GET'])
@login_required
def get_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'due_date': task.due_date.isoformat() if task.due_date else None,
        'completed': task.completed,
        'priority': task.priority,
        'category': task.category
    } for task in tasks])

@app.route("/api/tasks/<int:task_id>", methods=['PUT'])
@login_required
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    if task.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    task.title = data.get('title', task.title)
    task.description = data.get('description', task.description)
    task.completed = data.get('completed', task.completed)
    task.priority = data.get('priority', task.priority)
    task.category = data.get('category', task.category)
    
    if data.get('due_date'):
        task.due_date = datetime.fromisoformat(data['due_date'])
    
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route("/api/tasks/<int:task_id>", methods=['DELETE'])
@login_required
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    
    # Ensure the task belongs to the current user
    if task.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(task)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Task deleted successfully'}), 204

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route("/api/tasks/<int:task_id>", methods=['GET'])
@login_required
def get_task(task_id):
    # Fetch the task from the database
    task = Task.query.get_or_404(task_id)
    
    # Ensure the task belongs to the current user
    if task.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    # Return the task details as JSON
    return jsonify({
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'due_date': task.due_date.isoformat() if task.due_date else None,
        'priority': task.priority,
        'category': task.category,
        'completed': task.completed
    })

@app.route("/calendar/events/<int:event_id>", methods=['PUT'])
@login_required
def update_event(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    
    if event.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    
    # Update event details
    event.title = data.get('title', event.title)
    event.start_time = datetime.fromisoformat(data['start'])
    event.end_time = datetime.fromisoformat(data['end'])
    event.all_day = data.get('allDay', event.all_day)
    
    db.session.commit()
    return jsonify({'status': 'success', 'event': {
        'id': event.id,
        'title': event.title,
        'start': event.start_time.isoformat(),
        'end': event.end_time.isoformat(),
        'allDay': event.all_day
    }}), 200

@app.route("/calendar/events/<int:event_id>", methods=['DELETE'])
@login_required
def delete_event(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    
    if event.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(event)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Event deleted successfully'}), 204

# Function to check due tasks
# Function to check due tasks
def check_due_tasks():
    current_time = datetime.now()
    user_id = current_user.id  # Use current_user.id from Flask-Login

    # Query for tasks that are due and not completed
    due_tasks = Task.query.filter(
        Task.user_id == user_id,
        Task.due_date <= current_time,
        Task.completed == False
    ).all()
    
    return due_tasks


# Route to render notifications page
@app.route('/notifications')
def notifications():
    due_tasks = check_due_tasks()  # Get the list of due tasks
    return render_template('notifications.html', due_tasks=due_tasks)

# Route to get notification count
@app.route('/notification_count')
def notification_count():
    due_tasks = check_due_tasks()  # Get the list of due tasks
    return jsonify({'count': len(due_tasks)})

@app.route('/notifications_data')
@login_required
def notifications_data():
    due_tasks = check_due_tasks()  # Get the list of due tasks
    tasks_data = [{'title': task.title, 'due_time': task.due_date.strftime('%Y-%m-%d %H:%M')} for task in due_tasks]
    return jsonify(tasks_data)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
