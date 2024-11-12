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

# they should be read out from the database
userRange = range(1, 77)
adminRange = range(1, 13)


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
		FROM Event_Aggregation E, User_List U
		WHERE E.organizer_ID = U.user_ID
		""")
	eventList = []
	for result in cursor:
		eventList.append([result[0], result[1], result[2], '\\eventdetail\\'+str(result[3])])
	cursor.close()

	context = dict(data = eventList, login = session.get('userID'))

	return render_template("index.html", **context)


@app.route('/login', methods=['GET', 'POST'])
def login(): 
	if request.method == 'POST':
		userID = eval(request.form['userID'])
		if userID in userRange:
			session['userID'] = userID
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
		cmd = 'INSERT INTO Event_Aggregation(event_Name, event_Description, participant_Limit, organizer_ID) VALUES (:event_Name, :event_Description, :participant_Limit, :organizer_ID)';
		g.conn.execute(
			text(cmd),
			event_Name = request.form['event_Name'],
			event_Description = request.form['event_Description'],
			participant_Limit = request.form['participant_Limit'],
			organizer_ID = session['userID']
		)
		return redirect('/')
	if session.get('userID'):
		return render_template("addevent.html")
	return redirect("/login")


@app.route('/eventdetail/<int:eventID>/', methods = ['GET'])
def event_detail(eventID):
	context = dict(eventID = eventID)
	return render_template("eventdetail.html", **context)

@app.route('/register', methods = ['POST'])
def register():
	return redirect('/')

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
		app.run(host=HOST, port=PORT, debug=debug, threaded=threaded)

	run() 
