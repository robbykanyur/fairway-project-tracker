from flask import Flask, request, redirect, render_template, url_for, flash, session
from dotenv import load_dotenv
import flask_login
import os
import requests
import json
import re
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()
login_manager = flask_login.LoginManager()

app = Flask(__name__)

login_manager.init_app(app)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

users = {'user'}

class User(flask_login.UserMixin):
    pass

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))

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

    numeric_password = re.sub('[^0-9]','',request.form['phone'])
    user.is_authenticated = check_password(numeric_password)

    return user

def check_password(password):
    r_employees = airtable('Employees','GET')
    password_list = generate_auth_list(r_employees)

    for value in password_list:
        if value == password:
            return True

    return False

@app.template_filter('pluralize')
def pluralize(number, singular = '', plural = 's'):
    if number == 1:
        return singular
    else:
        return plural

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    username = request.form['username']
    numeric_password = re.sub('[^0-9]','',request.form['phone'])
    if check_password(numeric_password):
        user = User()
        user.id = username
        flask_login.login_user(user)
        return redirect(url_for('home'))

    flash('Unauthorized phone number')
    return redirect(url_for('login'))

@app.route('/submit', methods=['GET', 'POST'])
@flask_login.login_required
def submit():
    if request.method == 'GET':
        r_variables = airtable('Variables','GET')

        data = fetch_and_filter_issues()

        story_points = 0
        for issue in data:
            story_points += issue['points']
        points_per_week = [variable['fields']['Value'] for variable in r_variables['records'] if variable['fields']['Key'] == 'ticket_story_points'][0]
        backlog = int(round(story_points / points_per_week, 0))

        return render_template('submit.html', backlog=backlog, data=data)

    record_data = {"fields": {}}
    record_data["fields"]["Submission Requestor"] = request.form['requestor']
    record_data["fields"]["Submission Description"] = request.form['description']
    record_data["fields"]["Submission Due Date"] = request.form['duedate']
    record_data["fields"]["Status"] = "Submitted"
    record_data["fields"]["Project Type"] = "User Ticket"
    record_data["fields"]["Position"] = 9999
    record_data["fields"]["Public"] = "Under review"

    r = airtable('Issues', "POST", record_data).json()
    send_notification_email(r['fields']['Submission Requestor'], r['fields']['Submission Description'], r['fields']['Key'], r['fields']['Submission Due Date'], r['id'])
    session['submission'] = r

    return redirect(url_for('success'))

@app.route('/success')
@flask_login.login_required
def success():
    key = session['submission']['fields']['Key']
    return render_template('success.html', key=key)

@app.route('/logout')
def logout():
    flask_login.logout_user()
    return redirect(url_for('login'))

@app.route('/')
@flask_login.login_required
def home():
    payload = fetch_and_filter_issues()

    issues = payload['data']
    print_jobs = payload['print']

    data = split_tickets(issues)

    return render_template('home.html', active=data[0], inactive=data[1], print_jobs=print_jobs)

def split_tickets(issues):
    data = []
    active = []
    inactive = []

    for issue in issues:
        if issue["status_public"] == "Waiting":
            inactive.append(issue)
        else:
            active.append(issue)

    for index, item in enumerate(active):
        item["queue"] = index + 1

    for index, item in enumerate(inactive):
        item["queue"] = index + 1

    data.append(active)
    data.append(inactive)

    return data

def send_notification_email(requestor, description, key, duedate, record_id):
    message = Mail(
        from_email='noreply@fairway321.com',
        to_emails='robert.kanyur@fairwaymc.com',
        subject='New project request from ' + requestor,
        html_content='A new project has been submitted through the online tool:<br><br>Submitted by: ' + requestor + '<br>Description: ' + description + '<br>Due Date: ' + duedate + '<br><br>This project was assigned the key <strong>' + key + '</strong>.<br><br><a href="https://airtable.com/tblAt6PFHi27t3RoQ/' + record_id + '">View this issue on airtable</a>'
    )
    sg = SendGridAPIClient(os.getenv('SENDGRID'))
    response = sg.send(message)

def fetch_and_filter_issues():
    r_print = airtable('Print Jobs', 'GET')
    r_issues = airtable('Issues','GET')
    r_employees = airtable('Employees','GET')

    payload = {}
    data = []

    all_print_jobs = []
    active_print_jobs = []

    for issue in r_print["records"]:
        print(issue)
        item = {}

        if 'Key' in issue['fields']:
            item["key"] = issue["fields"]["Key"]
        else:
            item["key"] = ''

        if 'Name' in issue['fields']:
            item["description"] = issue["fields"]["Name"]
        else:
            item["description"] = ''

        if 'Requestor' in issue['fields']:
            item["requestor_id"] = issue["fields"]["Requestor"]
        else:
            item["requestor"] = ''

        if 'Public Status' in issue['fields']:
            item["status"] = issue["fields"]["Public Status"]
        else:
            item["status"] = ''

        if 'Expected Completion' in issue['fields']:
            item["completion"] = issue["fields"]["Expected Completion"]
        else:
            item["completion"] = ''

        if 'Delivery Instructions' in issue['fields']:
            item["delivery"] = issue["fields"]["Delivery Instructions"]
        else:
            item["delivery"] = ''

        all_print_jobs.append(item)

    for issue in all_print_jobs:
        status = issue['status']
        if status == 'In Production' or status == 'Ready for Pickup' or status == 'Delivery Scheduled':
            active_print_jobs.append(issue)

    for index, issue in enumerate(active_print_jobs):
        issue['queue'] = index + 1

    for issue in r_issues["records"]:
        item = {}

        if 'Key' in issue['fields']:
            item["key"] = issue["fields"]["Key"]
        else:
            item["key"] = ''

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
    data = list(sorted(data, key = lambda issue: (issue["position"], issue["key"])))

    for i in range (0, len(data)):
        data[i]["queue"] = 0
        if data[i]["estimate"] == '':
            data[i]["estimate"] = 'TBD'
        if data[i]["requestor_id"] != '':
            data[i]["requestor_name"] = [employee['fields']['Name'] for employee in r_employees['records'] if employee['id'] == data[i]["requestor_id"]][0]
        else:
            data[i]["requestor_name"] = 'New Submission'
        if data[i]["status"] == "Sprint":
            data[i]["status_public"] = "In Progress"
        elif data[i]["status"] == "Waiting":
            data[i]["status_public"] = "Waiting"
            data[i]["estimate"] = 'N/A'
        elif data[i]["status"] == "Submitted":
            data[i]["status_public"] = "Submitted"
        elif data[i]["status"] == "Staged":
            data[i]["status_public"] = "Received"

    payload["data"] = data
    payload["print"] = active_print_jobs

    return payload

def airtable(table, method, data={}):
    airtable_key = os.getenv('AIRTABLE')
    airtable_headers = {"Authorization": "Bearer %s" % airtable_key}
    airtable_url = 'https://api.airtable.com/v0/appPKruGpsONqlT1g/'

    table_url = airtable_url + table

    if method == 'GET':
        r = requests.get(url = table_url, headers = airtable_headers).json()
        return(r)

    r = requests.post(url = table_url, headers = airtable_headers, json = data)
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

if __name__ == "__main__":
    app.run()
