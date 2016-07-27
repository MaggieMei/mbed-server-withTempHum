import mbed_connector_api 				# mbed Device Connector library
import pybars 							# use to fill in handlebar templates
from   flask 			import Flask	# framework for hosting webpages
from   flask_socketio 	import SocketIO, emit,send,join_room, leave_room  
from   base64 			import standard_b64decode as b64decode
import os
import sys
import time
import MySQLdb as mdb
import Tkinter
from Tkinter import *
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter

app = Flask(__name__)
socketio = SocketIO(app,async_mode='threading')

if 'ACCESS_KEY' in os.environ.keys():
	token = os.environ['ACCESS_KEY'] # get access key from environment variable
else:
	token = "VbYjRRKaFjtD8wfL9qnXz8tt2lFcnERgwSfEwKFZUXEKLgc6jkxXvCk4DvAutRwX44yhiyN5VCRo2reOfDziPAj4atNGnmyZ5nuA" # replace with your API token

connector = mbed_connector_api.connector(token)
con = mdb.connect('localhost', 'root', '')      # connect to mysql
cur = con.cursor()                              # get the module of cursor

@app.route('/')
def index():
	# get list of endpoints, for each endpoint get the pattern (/3201/0/5853) value
	epList = connector.getEndpoints().result
	for index in range(len(epList)):
		print "Endpoint Found: ",epList[index]['name']
		e = connector.getResourceValue(epList[index]['name'],"/3201/0/5853")
		while not e.isDone():
			None
		epList[index]['blinkPattern'] = e.result
	print "Endpoint List :",epList
	# fill out html using handlebar template
	handlebarJSON = {'endpoints':epList}
	comp = pybars.Compiler()
	source = unicode(open("./views/index.hbs",'r').read())
	template = comp.compile(source)
	
	# create database TempHumTable if it not exists
	cur.execute("create database if not exists TempHumTable")
	# select the database TempHumTable
	cur.execute("use TempHumTable")
	# create table temp for storing the temparature data if it not exists
	cur.execute("create table if not exists temp(time TIME, temperature FLOAT(4,2), date DATE)")
	# create table hum for storing humidity data if it not exists
	cur.execute("create table if not exists hum(time TIME, humidity FLOAT(4,2), date DATE)")
	# clean the temp & hum table everyday
	curdate = time.strftime('%y:%m:%d')
	cur.execute("delete from temp where date < %s", [curdate])
	cur.execute("delete from hum where date < %s", [curdate])
	# commit update to the database
	con.commit()
	print 'init database successfully!'
	
	# Subscribe to all changes of resource /3300/0/5700 and /3300/0/5701 (temp & hum resource)
	for index in range(len(epList)):
		e = connector.putResourceSubscription(epList[index]['name'],'/3300/0/5700')
		e = connector.putResourceSubscription(epList[index]['name'],'/3300/0/5701')
		while not e.isDone():
			None
	return "".join(template(handlebarJSON))

@socketio.on('connect')
def connect():
	print('connect ')
	join_room('room')

@socketio.on('disconnect')
def disconnect():
	print('Disconnect')
	leave_room('room')

@socketio.on('subscribe_to_presses')
def subscribeToPresses(data):
	# Subscribe to all changes of resource /3200/0/5501 (button presses)
	print('subscribe_to_presses: ',data)
	e = connector.putResourceSubscription(data['endpointName'],'/3200/0/5501')
	while not e.isDone():
		None
	if e.error:
		print("Error: ",e.error.errType, e.error.error, e.raw_data)
	else:
		print("Subscribed Successfully!")
		emit('subscribed-to-presses')
	
@socketio.on('unsubscribe_to_presses')
def unsubscribeToPresses(data):
	print('unsubscribe_to_presses: ',data)
	e = connector.deleteResourceSubscription(data['endpointName'],'/3200/0/5501')
	while not e.isDone():
		None
	if e.error:
		print("Error: ",e.error.errType, e.error.error, e.raw_data)
	else:
		print("Unsubscribed Successfully!")
	emit('unsubscribed-to-presses',{"endpointName":data['endpointName'],"value":'True'})
    
@socketio.on('get_presses')
def getPresses(data):
	# Read data from GET resource /3200/0/5501 (num button presses)
	print("get_presses ",data)
	e = connector.getResourceValue(data['endpointName'],'/3200/0/5501')
	while not e.isDone():
		None
	if e.error:
		print("Error: ",e.error.errType, e.error.error, e.raw_data)
	else:
		data_to_emit = {"endpointName":data['endpointName'],"value":e.result}
		print data_to_emit
		emit('presses', data_to_emit)

@socketio.on('get_curves')
def getCurves(data):
	# plot the temp/hum curves during a period of time
	print("get_curves", data)
	
	# create a new figure
	fig = plt.figure()
	ax = fig.add_subplot(111)
	
	# get the data to be plotted
	type = data['value']['type']
	sdate = data['value']['sdate']
	stime = data['value']['stime']
	etime = data['value']['etime']
	
	# get the rows from database
	if type == 'temp':
		sql = "select * from temp where time between %s and %s and date=%s"
	elif type == 'hum':
		sql = "select * from hum where time between %s and %s and date=%s"
	cur.execute("use TempHumTable")
	cur.execute(sql, (stime, etime, sdate))
	rows = cur.fetchall()
	# get the num of rows
	num = cur.rowcount
	# get the data for x & y axis from rows and set the gap of a axis
	x = [row[0] for row in rows]
	y = [row[1] for row in rows]
	gap = num/10 if num>10 else 1
	
	# calculate the average value of temp/hum
	sum = 0.0
	for item in y:
		sum = sum + item
	if num > 0:
		ave = sum * 1.00 / num
	else:
		ave = 0
		print("ERROR: There is no data in the table!")
	
	# set the properties of the figure
	if type=='temp':
		plt.title('Temperature Curves')
		plt.ylabel('Celcius Degrees')
	else:
		plt.title('Humidity Curves')
		plt.ylabel('%rh')
	xticks = range(0, num, gap)
	xlabel = [x[index] for index in xticks]
	ax.set_xticks(xticks)
	ax.set_xticklabels(xlabel,rotation=40)
	plt.xlabel('Time')
	# plot the curve
	ax.plot(y)
	
	data_to_emit = {"endpointName":data['endpointName'],"value":ave}
	# store the figure to file Temparatue.png / Humidity.png
	if type=='temp':
		fig.savefig('Temperature.png')
		emit('Average-temp', data_to_emit)
	else:
		fig.savefig('Humidity.png')
		emit('Average-hum', data_to_emit)

@socketio.on('clean_temp')
def cleanTemp(data):
	print("clean the temp data in the temp table", data)
	cur.execute("use TempHumTable")
	cur.execute("delete from temp")
	con.commit()
	print("Restart Temperature Detection successfully!")
	emit('cleanTemp', data)
	
@socketio.on('clean_hum')
def cleanHum(data):
	print("clean the hum data in the hum table", data)
	cur.execute("use TempHumTable")
	cur.execute("delete from hum")
	con.commit()
	print("Restart Humidity Detection successfully!")
	emit('cleanHum', data)
	
# 'notifications' are routed here, handle subscriptions and update webpage
def notificationHandler(data):
	global socketio
	print "\r\nNotification Data Received : %s" %data['notifications']
	notifications = data['notifications']
	for thing in notifications:
		stuff = {"endpointName":thing["ep"],"value":b64decode(thing["payload"])}
		print "Emitting :",stuff
		path = thing["path"]
		# Notification from button Resource
		if '5501' in path:
			socketio.emit('presses',stuff)
		# Notification from tempareture resource
		if '5700' in path:
			# store the update data into temp table
			cur.execute("use TempHumTable")
			cur.execute("SELECT * FROM temp")
			sql = "insert into temp values(%s, %s, %s)"
			param = (time.strftime('%H:%M:%S'), b64decode(thing["payload"]), time.strftime('%y:%m:%d'))
			cur.execute(sql, param)
			con.commit()
			socketio.emit('display-temp',stuff)
		# Notification from humidity resource
		if '5701' in path:
			# store the update data into hum table
			cur.execute("use TempHumTable")
			cur.execute("SELECT * FROM hum")
			sql = "insert into hum values(%s, %s, %s)"
			param = (time.strftime('%H:%M:%S'), b64decode(thing["payload"]), time.strftime('%y-%m-%d'))
			cur.execute(sql, param)
			con.commit()
			socketio.emit('display-hum',stuff)

if __name__ == "__main__":
	connector.deleteAllSubscriptions()							# remove all subscriptions, start fresh
	connector.startLongPolling()								# start long polling connector.mbed.com
	connector.setHandler('notifications', notificationHandler) 	# send 'notifications' to the notificationHandler FN
	socketio.run(app,host='0.0.0.0', port=8080)
