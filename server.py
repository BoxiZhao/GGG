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
    # Get search parameters from the query string
    organizer = request.args.get('organizer', None)
    event_name = request.args.get('event_name', None)
    event_description = request.args.get('description', None)

    print("Search parameters:", request.args)

    # Start building the base SQL query
    query = """
        SELECT E.event_Name, E.event_Description, U.user_Name, E.event_ID
        FROM Event_Aggregation E
        JOIN User_List U ON E.organizer_ID = U.user_ID
        JOIN Request_List R ON E.request_ID = R.request_ID
        WHERE R.request_Approval = 1
    """
    
    # Dynamically add filters based on the query parameters
    filters = []
    params = []

    if organizer:
        filters.append("U.user_Name LIKE %s")
        params.append(f"%{organizer}%")  # Using % for partial matching
    if event_name:
        filters.append("E.event_Name LIKE %s")
        params.append(f"%{event_name}%")  # Using % for partial matching
    if event_description:
        filters.append("E.event_Description LIKE %s")
        params.append(f"%{event_description}%")  # Using % for partial matching
    
    # Add the filters to the query if any exist
    if filters:
        query += " AND " + " AND ".join(filters)
    
    # Debug print to verify the query
    #print("Executing query:", query)
    #print("With parameters:", params)

    # Execute the query with the parameters (or without if no parameters)
    cursor = g.conn.execute(query, params) if params else g.conn.execute(query)
    
    eventList = []
    for result in cursor:
        eventList.append([result[0], result[1], result[2], '/eventdetail/' + str(result[3])])
    cursor.close()

    context = dict(data=eventList, userID=session.get('userID'), adminID=session.get('adminID'))

    return render_template("index.html", **context)

@app.route('/login', methods=['GET', 'POST'])
def login(): 
    if request.method == 'POST':
        try:
            # Safely cast userID and adminID to integers (if they should be integers)
            userID = int(request.form['userID'])
            adminID = int(request.form['adminID'])
        except ValueError:
            # If the inputs are not valid integers, return an error message
            error = 'Invalid user ID or admin ID.'
            return render_template('login.html', error=error)

        # Query to check if the userID exists in User_List
        cursor = g.conn.execute("""SELECT U.user_ID FROM User_List U""")
        userRange = cursor.fetchall()
        cursor.close()

        # Query to check if the adminID exists in Admin_List
        cursor = g.conn.execute("""SELECT A.admin_ID FROM Admin_List A""")
        adminRange = cursor.fetchall()
        cursor.close()

        # Check if userID exists in the user range
        if (userID,) in userRange:
            session['userID'] = userID
            # Check if adminID exists in the admin range and store it in the session if it does
            if (adminID,) in adminRange:
                session['adminID'] = adminID
            return redirect('/')
        else:
            # Invalid userID
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
        # Open a transaction context
        with g.conn.begin():  # This automatically handles committing or rolling back
            # Count the number of events to determine eventCounter
            cursor = g.conn.execute("SELECT COUNT(*) FROM Event_Aggregation")
            eventCounter = cursor.fetchall()[0][0] + 1
            cursor.close()

            # Insert into Location_List
            locationCapacity = 'NULL' if request.form['locationCapacity'] == '' else request.form['locationCapacity']
            cmd = """INSERT INTO Location_List VALUES (%s, '%s', '%s', %s)""" % (eventCounter, request.form['locationName'], request.form['locationAddress'], locationCapacity)
            g.conn.execute(text(cmd))

            # Insert into When_List
            timeStart = 'NULL' if request.form['timeStart'] == '' else '\'' + request.form['timeStart'].replace('T', ' ') + ':00-5\''
            timeEnd = 'NULL' if request.form['timeEnd'] == '' else '\'' + request.form['timeEnd'].replace('T', ' ') + ':00-5\''
            cmd = """INSERT INTO When_List VALUES (%s, %s, %s)""" % (eventCounter, timeStart, timeEnd)  # 注意 NULL 不能有引号
            g.conn.execute(text(cmd))

            # Insert into Location_When
            cmd = """INSERT INTO Location_When VALUES (%s, %s, %s)""" % (eventCounter, eventCounter, eventCounter)
            g.conn.execute(text(cmd))

            # Insert into Request_List
            cmd = """INSERT INTO Request_List(request_ID, request_Comment, request_Approval) VALUES (%s, '%s', 0)""" % (eventCounter, request.form['eventName'])
            g.conn.execute(text(cmd))

            # Insert into Event_Aggregation
            participantLimit = 'NULL' if request.form['participantLimit'] == '' else request.form['participantLimit']
            cmd = """
            INSERT INTO Event_Aggregation(event_Name, event_Description, participant_Limit, organizer_ID, request_ID, location_when_ID)
            VALUES ('%s', '%s', %s, %s, %s, %s)
            """ % (request.form['eventName'], request.form['eventDescription'], participantLimit, session['userID'], eventCounter, eventCounter)
            g.conn.execute(text(cmd))

            # Insert into User_Event
            cmd = """INSERT INTO User_Event VALUES (%s, %s)""" % (session['userID'], eventCounter)
            g.conn.execute(text(cmd))

        # No need for explicit commit since `with g.conn.begin()` handles it
        return redirect('/')  # Redirect to the homepage
    return render_template("addevent.html")

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


@app.route('/statistics', methods=['GET'])
def view_statistics():
    cursor = g.conn.execute("""
        SELECT User_List.user_ID, User_List.user_Name, COUNT(User_Event.event_ID) AS event_Count 
        FROM User_List 
        LEFT JOIN User_Event ON User_List.user_ID = User_Event.user_ID
        GROUP BY User_List.user_ID
        ORDER BY event_Count DESC, user_ID ASC
    """)
    
    sorted_users = []
    for result in cursor:
        sorted_users.append({"user_ID": result[0], "user_Name": result[1], "event_Count": result[2]})
    cursor.close()

    cursor = g.conn.execute("""
        WITH uiuic AS (
            SELECT u1.user_ID AS ID_1, u1.user_Name AS name_1, u2.user_ID AS ID_2, u2.user_Name AS name_2, COUNT(*) AS common_Count 
            FROM User_List u1, User_Event ue1, User_List u2, User_Event ue2
            WHERE u1.user_ID = ue1.user_ID 
            AND u2.user_ID = ue2.user_ID 
            AND ue1.event_ID = ue2.event_ID
            AND u1.user_ID < u2.user_ID 
            GROUP BY u1.user_ID, u2.user_ID
        ) 
        SELECT ID_1, name_1, ID_2, name_2, common_Count 
        FROM uiuic 
        WHERE common_Count > 1
        ORDER BY common_Count DESC, ID_1 ASC 
    """)

    common_users = []
    for result in cursor:
        common_users.append({"ID_1": result[0], "name_1": result[1], "ID_2": result[2], "name_2": result[3], "common_Count": result[4]})
    cursor.close()

    context = dict(sorted_users=sorted_users, common_users=common_users)
    return render_template("statistics.html", **context)


@app.route('/notifications', methods=['GET'])
def notifications():

    cmd = """
        SELECT E.event_Name, N.notification_Title, N.notification_Content, N.post_Time 
        FROM User_Event ue
        JOIN Event_Aggregation E ON E.event_ID = ue.event_ID 
        JOIN Notification_List N ON N.event_ID = E.event_ID 
        WHERE ue.user_ID = :user_id
        AND N.post_Time > :start_time
    """
    cursor = g.conn.execute(
        text(cmd),
        user_id=session.get('userID'),
        start_time='2000-01-01 00:00:01-5'
    )

    notifications = []
    for result in cursor:
        notifications.append({"event_Name": result[0], "notification_Title": result[1], "notification_Content": result[2], "post_Time": result[3]})
    cursor.close()

    context = dict(notifications=notifications)
    return render_template("notifications.html", **context)



if __name__ == "__main__":
	import click

	@click.command()
	@click.option('--debug', is_flag=True)
	@click.option('--threaded', is_flag=True)
	@click.argument('HOST', default='0.0.0.0')
	@click.argument('PORT', default=8111, type=int)

	def run(debug, threaded, host, port):
		HOST, PORT = host, port
		print("running on %s:%d" % (HOST, PORT))
		app.run(host=HOST, port=PORT, debug=False, threaded=threaded)

	run() 
