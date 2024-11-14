#!/usr/bin/env python3

import os
from sqlalchemy import *
from sqlalchemy.pool import NullPool
from flask import Flask, request, render_template, g, redirect, Response, session

tmpl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
app = Flask(__name__, template_folder=tmpl_dir)
app.secret_key = 'bz2540'

DATABASEURI = "postgresql://bz2540:bz2540@w4111.cisxo09blonu.us-east-1.rds.amazonaws.com/w4111"
engine = create_engine(DATABASEURI)

with open('Create_Table.txt', 'r', encoding="utf-8") as f:
	createTableSQL = f.read()
	engine.execute(createTableSQL)

with open('Initial_Data.txt', 'r', encoding="utf-8") as f:
	initialDataSQL = f.read()
	engine.execute(initialDataSQL)

@app.before_request
def before_request():
	try:
		g.conn = engine.connect()
	except:
		print("uh oh, problem connecting to database")
		import traceback; traceback.print_exc()
		g.conn = None

@app.teardown_request
def teardown_request(exception):
	"""
	At the end of the web request, this makes sure to close the database connection.
	If you don't the database could run out of memory!
	"""
	try:
		g.conn.close()
	except Exception as e:
		pass


@app.route('/')
def index():

	print(request.args)

	cursor = g.conn.execute("""
		SELECT E.event_Name, E.event_Description, U.user_Name, E.event_ID
		FROM Event_Aggregation E, User_List U, Request_List R
		WHERE E.organizer_ID = U.user_ID
		AND E.request_ID = R.request_ID
		AND R.request_Approval = 1
		""")
	eventList = []
	for result in cursor:
		eventList.append([result[0], result[1], result[2], '/eventdetail/'+str(result[3])])
	cursor.close()

	context = dict(data = eventList, userID = session.get('userID'), adminID = session.get('adminID'))

	return render_template("index.html", **context)


@app.route('/login', methods=['GET', 'POST'])
def login(): 
	if request.method == 'POST':
		userID = eval(request.form['userID'])
		adminID = eval(request.form['adminID'])
		cursor = g.conn.execute("""
			SELECT U.user_ID
			FROM User_List U
			""")
		userRange = cursor.all()
		cursor.close()
		cursor = g.conn.execute("""
			SELECT A.admin_ID
			FROM Admin_List A
			""")
		adminRange = cursor.all()
		cursor.close()
		if (userID,) in userRange:
			session['userID'] = userID
			if (adminID,) in adminRange:
				session['adminID'] = adminID
			return redirect('/')
		else:
			print(userID)
			error = 'Invalid user ID.'
			return render_template('login.html', error=error)
	return render_template('login.html')

@app.route('/logout', methods=['POST', 'GET'])
def logout(): 
	session.clear()
	return redirect('/')


@app.route('/addevent', methods=['POST', 'GET'])
def add_event():
	if request.method == 'POST':
		cursor = g.conn.execute("""SELECT COUNT(*) FROM Event_Aggregation""")
		eventCounter = cursor.all()[0][0] + 1
		cursor.close()

		cmd = 'INSERT INTO Request_List(request_ID, request_Comment, request_Approval) VALUES (:request_ID, :request_Comment, 0)'
		g.conn.execute(
			text(cmd),
			request_ID = eventCounter,
			request_Comment = request.form['event_Name']
		)

		cmd = 'INSERT INTO Event_Aggregation(event_Name, event_Description, participant_Limit, organizer_ID, request_ID) VALUES (:event_Name, :event_Description, :participant_Limit, :organizer_ID, :request_ID)'
		g.conn.execute(
			text(cmd),
			event_Name = request.form['event_Name'],
			event_Description = request.form['event_Description'],
			participant_Limit = request.form['participant_Limit'],
			organizer_ID = session['userID'],
			request_ID = eventCounter
		)
		return redirect('/')

	if session.get('userID'):
		return render_template("addevent.html")
	return redirect("/login")


@app.route('/eventdetail/<int:eventID>/', methods = ['GET'])
def event_detail(eventID):
	session['eventID'] = eventID

	cursor = g.conn.execute("""
		SELECT E.event_Name, E.event_Description, L.location_Name, W.time_Start, W.time_End, E.organizer_ID
		FROM Event_Aggregation E
		LEFT JOIN Location_When LW ON E.location_when_ID = LW.location_when_ID
		LEFT JOIN Location_List L ON LW.location_ID = L.location_ID
		LEFT JOIN When_List W ON LW.when_ID = W.when_ID
		WHERE E.event_ID = %d
	""" % eventID)
	eventDetail = cursor.fetchone()
	cursor.close()

	userID = session.get('userID')
	isOrganizer = userID == eventDetail[5]
	cursor = g.conn.execute("""SELECT * FROM User_Event""")
	registered = (userID, eventID) in cursor.all()
	cursor.close()

	cursor = g.conn.execute("""
		SELECT *
		FROM Notification_List N
		WHERE N.event_ID = %d
	""" % eventID)
	notificationList = []
	for result in cursor:
		notificationList.append([result[1], result[2], result[3]])
	cursor.close()

	context = dict(eventDetail=eventDetail, notificationList=notificationList, registered = registered, userID = userID, isOrganizer = isOrganizer)
	return render_template("eventdetail.html", **context)


@app.route('/register', methods = ['POST'])
def register():
	cmd = 'INSERT INTO User_Event VALUES (:user_ID, :event_ID)'
	g.conn.execute(
		text(cmd),
		user_ID = session['userID'],
		event_ID = session['eventID']
	)
	return redirect('/eventdetail/%d/' % session['eventID'])


@app.route('/requests', methods = ['GET'])
def requests():

	result_dict = {-1:'Rejected', 0:'Under Review', 1:'Approved'}
	cursor = g.conn.execute("""SELECT * FROM Request_List""")
	requestList = []
	for result in cursor:
		requestList.append([result[0], result[1], result_dict[result[2]], '/requestdetail/'+str(result[0])])
	cursor.close()

	context = dict(data = requestList)

	return render_template("requests.html", **context)


@app.route('/requestdetail/<int:requestID>/', methods = ['GET'])
def request_detail(requestID):
	session['requestID'] = requestID
	cursor = g.conn.execute("""
		SELECT E.event_Name, E.event_Description, U.user_Name, E.event_ID
		FROM Event_Aggregation E, User_List U
		WHERE E.organizer_ID = U.user_ID AND
			E.request_ID = %d
		""" % requestID)
	eventList = []
	for result in cursor:
		eventList.append([result[0], result[1], result[2], '/eventdetail/'+str(result[3])])
	cursor.close()

	cursor = g.conn.execute("""
		SELECT R.request_Approval
		FROM Request_List R
		WHERE R.request_ID = %d
		""" % requestID)
	reviewed = cursor.all()[0][0]
	cursor.close()

	context = dict(data = eventList, reviewed = reviewed, requestID = requestID)

	return render_template("requestdetail.html", **context)


@app.route('/review', methods = ['POST'])
def review():
	cmd = 'UPDATE Request_List SET request_Approval = :result WHERE request_ID = :requestID'
	g.conn.execute(
		text(cmd),
		result = eval(request.form['feedback']),
		requestID = session['requestID']
	)
	return redirect('/requests')


@app.route('/addnotification', methods=['POST', 'GET'])
def add_notification():
    if request.method == 'POST':

        cmd = """
            INSERT INTO Notification_List(notification_Title, notification_Content, post_Time, event_ID)
            VALUES (:notification_Title, :notification_Content, NOW(), :event_ID)
        """
        g.conn.execute(
            text(cmd),
            notification_Title=request.form['notification_Title'],
            notification_Content=request.form['notification_Content'],
            event_ID=session['eventID']
        )
        return redirect('/eventdetail/' + str(session['eventID']))

    return render_template("addnotification.html")


if __name__ == "__main__":
	import click

	@click.command()
	@click.option('--debug', is_flag=True)
	@click.option('--threaded', is_flag=True)
	@click.argument('HOST', default='0.0.0.0')
	@click.argument('PORT', default=1111, type=int)

	def run(debug, threaded, host, port):
		HOST, PORT = host, port
		print("running on %s:%d" % (HOST, PORT))
		app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

	run() 
