from flask import Flask, request, redirect, render_template, url_for
from dotenv import load_dotenv
import flask_login
import os
import requests
import json
import re

load_dotenv()
login_manager = flask_login.LoginManager()

app = Flask(__name__)
login_manager.init_app(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

users = {'user'}

class User(flask_login.UserMixin):
    pass

@login_manager.user_loader
def user_loader(username):
    if username not in users:
        return

    user = User()
    user.id = username
    return user

@login_manager.request_loader
def request_loader(request):
    username = request.form.get('username')
    if username not in users:
        return

    user = User()
    user.id = username

    numeric_password = re.sub('[^0-9]','',request.form['password'])
    user.is_authenticated = check_password(numeric_password)

    return user

def check_password(password):
    r_employees = airtable('Employees')
    password_list = generate_auth_list(r_employees)

    for value in password_list:
        if value == password:
            return True

    return False

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return '''
            <form action="login" method="POST">
                <input type="text" name="username" id="username" placeholder="username" />
                <input type="password" name="password" id="password" placeholder="password" />
                <input type="submit" name="submit" />
            </form>
        '''

    username = request.form['username']
    numeric_password = re.sub('[^0-9]','',request.form['password'])
    if check_password(numeric_password):
        user = User()
        user.id = username
        flask_login.login_user(user)
        return redirect(url_for('home'))

    return 'Bad login'

@app.route('/logout')
def logout():
    flask_login.logout_user()
    return 'Logged out'

@login_manager.unauthorized_handler
def unauthorized_handler():
    return 'Unauthorized'

@app.route('/')
@flask_login.login_required
def home():
    r_issues = airtable('Issues')
    r_employees = airtable('Employees')
    r_variables = airtable('Variables')

    data = []
    for issue in r_issues["records"]:
        item = {}
        if 'Key' in issue['fields']:
            item["key"] = issue["fields"]["Key"]
        else:
            item["key"] = ('')
        if 'Status' in issue['fields']:
            item["status"] = issue["fields"]["Status"]
        else:
            item["status"] = ''
        if 'Project Type' in issue['fields']:
            item["type"] = issue["fields"]["Project Type"]
        else:
            item["type"] = ''
        if 'Public' in issue['fields']:
            item["public"] = issue["fields"]["Public"]
        else:
            item["public"] = ''
        if 'Position' in issue['fields']:
            item["position"] = issue["fields"]["Position"]
        else:
            item["position"] = ''
        if 'Requestor' in issue['fields']:
            item["requestor_id"] = issue["fields"]["Requestor"][0]
        else:
            item["requestor_id"] = ''
        if 'Story Points' in issue['fields']:
            item["points"] = issue["fields"]["Story Points"]
        else:
            item["points"] = 0
        if 'Est. Completion Date' in issue['fields']:
            item["estimate"] = issue["fields"]["Est. Completion Date"]
        else:
            item["estimate"] = ''
        data.append(item)

    data = list(filter(lambda issue: issue['status'] != 'Completed' and issue['status'] != 'Cancelled' and issue['type'] == 'User Ticket', data))
    data = list(sorted(data, key = lambda issue: issue["position"]))

    for i in range (0, len(data)):
        data[i]["queue"] = i + 1
        data[i]["requestor_name"] = [employee['fields']['Name'] for employee in r_employees['records'] if employee['id'] == data[i]["requestor_id"]][0]
        if data[i]["status"] == "Sprint":
            data[i]["status_public"] = "In Progress"
        elif data[i]["status"] == "Waiting":
            data[i]["status_public"] = "Waiting"
        elif data[i]["status"] == "Submitted":
            data[i]["status_public"] = "Submitted"
        elif data[i]["status"] == "Staged":
            data[i]["status_public"] = "Received"

    story_points = 0
    for issue in data:
        story_points += issue['points']
    points_per_week = [variable['fields']['Value'] for variable in r_variables['records'] if variable['fields']['Key'] == 'ticket_story_points'][0]
    backlog = int(round(story_points / points_per_week, 0))

    display = {'display': data}
    return render_template('home.html', data=data, backlog=backlog)

def airtable(table):
    airtable_key = os.getenv('AIRTABLE')
    airtable_headers = {"Authorization": "Bearer %s" % airtable_key}
    airtable_url = 'https://api.airtable.com/v0/appPKruGpsONqlT1g/'

    table_url = airtable_url + table

    r = requests.get(url = table_url, headers = airtable_headers).json()
    return(r)

def generate_auth_list(data):
    numbers = []
    filtered_numbers = []
    formatted_numbers = []

    for employee in data["records"]:
        if 'Direct' in employee['fields']:
            numbers.append(employee['fields']['Direct'])
        if 'Cell' in employee['fields']:
            numbers.append(employee['fields']['Cell'])
    for number in numbers:
        if not re.match(r'^.*[a-zA-Z].*$', number):
            filtered_numbers.append(number)
    for number in filtered_numbers:
        formatted_numbers.append(re.sub('[^0-9]','',number))

    return(formatted_numbers)
