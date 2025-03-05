from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import datetime
import os
from dotenv import load_dotenv
from supabase import create_client
from dateutil.parser import parse
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-please-change')

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_ANON_KEY = os.getenv('SUPABASE_ANON_KEY')

supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_data):
        self.id = user_data['id']
        self.username = user_data['username']
        # Add other attributes as needed

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

@login_manager.user_loader
def load_user(user_id):
    response = supabase.table("users").select("*").eq("id", user_id).single().execute()
    user_data = response.data
    if user_data:
        return User(user_data)
    return None

@app.route("/")
def home():
    if current_user.is_authenticated:
        # Fetch tasks for the current user
        tasks_response = supabase.table("tasks").select("*").eq("user_id", current_user.id).execute()
        tasks = tasks_response.data if tasks_response.data else []

        # Initialize a dictionary to count tasks by category
        categories = {}

        # Count only incomplete tasks by category
        for task in tasks:
            if not task.get('completed'):  # Only count incomplete tasks
                category = task.get('category', 'Uncategorized')
                categories[category] = categories.get(category, 0) + 1

        return render_template("home.html", tasks=tasks, upcoming_events=[], categories=categories)
    return render_template("home.html")

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user_response = supabase.table("users").select("*").eq("username", username).single().execute()
        user_data = user_response.data
        
        if user_data and user_data["password"] == password:  # Replace with hash check in production
            user_obj = User(user_data)
            login_user(user_obj)
            return redirect(url_for('tasks_page'))
        flash('Invalid username or password')
    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        new_user = {
            "username": request.form.get('username'),
            "email": request.form.get('email'),
            "password": request.form.get('password')  # Hash before storing
        }
        response = supabase.table("users").insert(new_user).execute()
        if response.data:
            login_user(response.data[0])
            return redirect(url_for('tasks_page'))
    return render_template("register.html")

@app.route("/tasks")
@login_required
def tasks_page():
    try:
        tasks_response = supabase.table("tasks").select("*").eq("user_id", current_user.id).execute()
        tasks = tasks_response.data if tasks_response.data else []
        return render_template("tasks.html", tasks=tasks)
    except Exception as e:
        print(f"Error fetching tasks: {e}")
        return jsonify({'error': 'Failed to fetch tasks'}), 500

@app.route("/tasks/add", methods=['POST'])
@login_required
def add_task():
    new_task = {
        "title": request.form.get('title'),
        "description": request.form.get('description'),
        "due_date": request.form.get('due_date'),
        "priority": request.form.get('priority', 'medium'),
        "category": request.form.get('category'),
        "user_id": current_user.id
    }
    supabase.table("tasks").insert(new_task).execute()
    return redirect(url_for('tasks_page'))

@app.route("/calendar")
@login_required
def calendar_page():
    events_response = supabase.table("calendar_events").select("*").eq("user_id", current_user.id).execute()
    events = events_response.data if events_response.data else []

    # Convert string dates to datetime objects
    for event in events:
        if 'start_time' in event:
            event['start_time'] = parse(event['start_time'])
        if 'end_time' in event:
            event['end_time'] = parse(event['end_time'])

    return render_template("calendar.html", events=events)

@app.route("/calendar/events", methods=['GET'])
@login_required
def get_events():
    try:
        response = supabase.table("calendar_events").select("*").eq("user_id", current_user.id).execute()
        events = response.data if response.data else []

        # Convert event data to FullCalendar format
        formatted_events = [
            {
                'id': event['id'],
                'title': event['title'],
                'start': event['start_time'],
                'end': event['end_time'],
                'allDay': event['all_day']
            }
            for event in events
        ]

        return jsonify(formatted_events)
    except Exception as e:
        print(f"Error fetching events: {e}")
        return jsonify({'error': 'Failed to fetch events'}), 500

@app.route("/calendar/events", methods=['POST'])
@login_required
def add_event():
    data = request.get_json()
    new_event = {
        "title": data.get('title', 'Untitled Event'),
        "start_time": data.get('start'),
        "end_time": data.get('end'),
        "all_day": data.get('allDay', False),
        "user_id": current_user.id
    }
    response = supabase.table("calendar_events").insert(new_event).execute()
    return jsonify({'status': 'success', 'event': response.data[0]}), 201

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/notifications')
def notifications():
    try:
        response = supabase.table("tasks").select("*").eq("user_id", current_user.id).execute()
        due_tasks = [task for task in response.data if parse(task['due_date']) <= datetime.now() and not task['completed']]
    except Exception as e:
        print(f"Error fetching tasks: {e}")
        due_tasks = []
    return render_template('notifications.html', due_tasks=due_tasks)

@app.route('/notification_count')
def notification_count():
    if not current_user.is_authenticated:
        return jsonify({'error': 'User not authenticated'}), 401  # Return an error if not authenticated

    response = supabase.table("tasks").select("*").eq("user_id", current_user.id).execute()
    due_tasks = [task for task in response.data if task['due_date'] <= datetime.now().isoformat() and not task['completed']]
    return jsonify({'count': len(due_tasks)})

@app.route('/notifications_data')
def notifications_data():
    if not current_user.is_authenticated:
        return jsonify({'error': 'User not authenticated'}), 401

    # Fetch tasks that are due or meet your notification criteria
    response = supabase.table("tasks").select("*").eq("user_id", current_user.id).execute()
    due_tasks = [task for task in response.data if task['due_date'] <= datetime.now().isoformat() and not task['completed']]

    # Return the due tasks as JSON
    return jsonify(due_tasks)

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@login_required
def update_task(task_id):
    try:
        data = request.get_json()
        
        # Get the existing task to verify ownership
        task_response = supabase.table("tasks").select("*").eq("id", task_id).single().execute()
        task = task_response.data
        
        if not task or task['user_id'] != current_user.id:
            return jsonify({'error': 'Task not found'}), 404
            
        # Update the task
        supabase.table("tasks").update(data).eq("id", task_id).execute()
        
        return jsonify({'status': 'success'}), 200
        
    except Exception as e:
        print(f"Error updating task: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<int:task_id>', methods=['GET'])
@login_required
def get_task(task_id):
    try:
        task_response = supabase.table("tasks").select("*").eq("id", task_id).single().execute()
        task = task_response.data
        
        if not task or task['user_id'] != current_user.id:
            return jsonify({'error': 'Task not found'}), 404
            
        return jsonify(task)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@login_required
def delete_task(task_id):
    try:
        # Verify task ownership
        task_response = supabase.table("tasks").select("*").eq("id", task_id).single().execute()
        task = task_response.data
        
        if not task or task['user_id'] != current_user.id:
            return jsonify({'error': 'Task not found'}), 404
            
        # Delete the task
        supabase.table("tasks").delete().eq("id", task_id).execute()
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/calendar/events/<int:event_id>", methods=['DELETE'])
@login_required
def delete_event(event_id):
    try:
        response = supabase.table("calendar_events").delete().eq("id", event_id).execute()
        if response.data:
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'fail', 'message': 'Event not found'}), 404
    except Exception as e:
        print(f"Error deleting event: {e}")
        return jsonify({'status': 'error', 'message': 'Internal Server Error'}), 500

@app.route("/calendar/events/<int:event_id>", methods=['PUT'])
@login_required
def edit_event(event_id):
    data = request.get_json()
    print(f"Received data for update: {data}")  # Debugging line

    if not data:
        return jsonify({'status': 'fail', 'message': 'Invalid data'}), 400

    # Validate required fields
    required_fields = ['title', 'start_time', 'end_time']
    for field in required_fields:
        if field not in data:
            return jsonify({'status': 'fail', 'message': f'Missing field: {field}'}), 400

    try:
        response = supabase.table("calendar_events").update(data).eq("id", event_id).execute()
        if response.data:
            return jsonify({'status': 'success', 'event': response.data[0]}), 200
        else:
            return jsonify({'status': 'fail', 'message': 'Event not found'}), 404
    except Exception as e:
        print(f"Error editing event: {e}")
        return jsonify({'status': 'error', 'message': 'Internal Server Error'}), 500

@app.route('/api/events/<int:event_id>', methods=['GET'])
@login_required
def get_event(event_id):
    try:
        event_response = supabase.table("calendar_events").select("*").eq("id", event_id).single().execute()
        event = event_response.data
        
        if not event or event['user_id'] != current_user.id:
            return jsonify({'error': 'Event not found'}), 404
            
        return jsonify(event)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)
