#    Beedraw/Hive network capable client and server allowing collaboration on a single image
#    Copyright (C) 2009 B. Becker
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import sys
sys.path.append("designer")

import PyQt4.QtCore as qtcore
import PyQt4.QtGui as qtgui
import PyQt4.QtNetwork as qtnet

try:
	from PyQt4.QtXml import QXmlStreamReader
except:
	from PyQt4.QtCore import QXmlStreamReader

from HiveMasterUi import Ui_HiveMasterSpec
from HiveOptionsUi import Ui_HiveOptionsDialog
from beedrawingwindow import BeeDrawingWindow
from beetypes import *
from beeutil import *
from beetools import BeeToolBox
from animation import XmlToQueueEventsConverter
from sketchlog import SketchLogWriter
from abstractbeemaster import AbstractBeeMaster
from hivestate import HiveSessionState

from Queue import Queue
import time

class HiveMasterWindow(qtgui.QMainWindow, AbstractBeeMaster):
	# this constructor should never be called directly, use an alternate
	def __init__(self):
		qtgui.QMainWindow.__init__(self)
		AbstractBeeMaster.__init__(self)

		# set defaults
		self.port=8333

		# Initialize values
		self.nextclientid=1
		self.nextclientidmutex=qtcore.QMutex()

		self.password=""

		# setup interface
		self.ui=Ui_HiveMasterSpec()
		self.ui.setupUi(self)
		self.show()

		# setup queues used for all thread communication
		self.routinginput=Queue(0)
		self.routingthread=HiveRoutingThread(self)
		self.routingthread.start()

		# this will be keyed on the client ids and values will be queue objects
		self.clientwriterqueues={}
		self.socketsmap={}

		# this dictionary will be keyed on id and map to the username
		self.clientnames={}

		# set up client list mutex for messing with either of the above 2 dictinoaries
		self.clientslistmutex=qtcore.QReadWriteLock()

		# default value stuff that needs to be here
		self.fgcolor=qtgui.QColor(0,0,0)
		self.bgcolor=qtgui.QColor(255,255,255)

		# drawing window which holds the current state of the network session
		self.curwindow=HiveSessionState(self,600,400,WindowTypes.standaloneserver,20)

		self.curwindow.startRemoteDrawingThreads()
		self.serverthread=None

	# since there should only be one window just return 1
	def getNextWindowId(self):
		return 1

	def getWindowById(self,id):
		return self.curwindow

	def getToolClassByName(self,name):
		return self.toolbox.getToolDescByName(name)

	def registerClient(self,username,id,socket):
		lock=qtcore.QWriteLocker(self.clientslistmutex)

		for name in self.clientnames.values():
			if name==username:
				return False

		self.clientwriterqueues[id]=Queue(100)
		self.clientnames[id]=username
		self.ui.clientsList.addItem(username)
		self.socketsmap[id]=socket

		command=(DrawingCommandTypes.networkcontrol,NetworkControlCommandTypes.resyncrequest)
		self.curwindow.addResyncRequestToQueue(id)

		return True

	def unregisterClient(self,id):
		lock=qtcore.QReadLocker(self.clientslistmutex)
		if not id in self.clientnames:
			return

		# remove from dictionary of clients
		username=self.clientnames[id]
		del self.clientnames[id]

		# remove from gui
		items=self.ui.clientsList.findItems(username,qtcore.Qt.MatchFixedString)
		for item in items:
			index=self.ui.clientsList.row(item)
			self.ui.clientsList.takeItem(index)

		# set layers owned by that client to unowned
		layerlistlock=qtcore.QMutexLocker(self.curwindow.layersmutex)
		for layer in self.curwindow.layers:
			if layer.owner==id:
				self.curwindow.addGiveUpLayerToQueue(layer.key,id)

	def closeEvent(self,event):
		qtgui.QMainWindow.closeEvent(self,event)
#		self.stopServer()

	def startServer(self):
		# make sure no other instance is running
		self.stopServer()

		self.serverthread=HiveServerThread(self,self.port)
		self.serverthread.start()
		self.ui.statusLabel.setText("Serving on port %d" % self.port )

	def stopServer(self):
		if self.serverthread:
			#self.serverthread.terminate()
			#self.serverthread.quit()
			self.serverthread.exit()
			self.serverthread.wait()
			self.serverthread=None
			self.ui.statusLabel.setText("Serving not running")

	def on_kick_button_pressed(self):
		curselection=self.ui.clientsList.selectedIndexes()
		# if there are any items in the list that means that something was selected
		if curselection:
			target=curselection[0].data().toString()
			self.kickClient(target)

	def kickClient(self,name):
		for i in self.clientnames.keys():
			if self.clientnames[i]==name:
				# todo: figure out what goes here to kick off client
				#self.socketsmap[i].close()
				break

	def on_actionStart_triggered(self,accept=True):
		if accept:
			self.startServer()

	def on_actionStop_triggered(self,accept=True):
		if accept:
			self.stopServer()

	def on_actionOptions_triggered(self,accept=True):
		if accept:
			dialog=qtgui.QDialog()
			dialog.ui=Ui_HiveOptionsDialog()
			dialog.ui.setupUi(dialog)

			dialog.ui.port_box.setValue(self.port)
			dialog.ui.password_entry.setText(self.password)

			dialog.exec_()

			if dialog.result():
				self.port=dialog.ui.port_box.value()
				self.password=dialog.ui.password_entry.text()

# thread to setup connection, authenticate and then
# listen to a socket and add incomming client commands to queue
class HiveClientListener(qtcore.QThread):
	def __init__(self,parent,socket,master,id):
		qtcore.QThread.__init__(self,parent)
		self.socket=socket

		self.master=master
		self.id=id

		self.authenticationerror="Unknown Error"

	def authenticate(self):
		# attempt to read stream of data, which should include version, username and password
		# make sure someone dosen't overload the buffer while wating for authentication info
		authstring=qtcore.QString()
		while authstring.count('\n')<3 and len(authstring)<100:
			if self.socket.waitForReadyRead(-1):
				data=self.socket.read(100)
				authstring.append(data)

			# if error exit
			else:
				self.authenticationerror="Error: Lost connection during authentication request"
				return False

		authlist=authstring.split('\n')

		# if loop ended without getting enough separators just return false
		if len(authlist)<3:
			self.authenticationerror="Error parsing authentication information"
			return False

		self.username=authlist[0]
		password=authlist[1]
		try:
			version=int(authlist[2])
		except ValueError:
			self.authenticationerror="Error parsing authentication information"
			return False

		if version != PROTOCOL_VERSION:
			self.authenticationerror="Protocol version mismatch, please change to server version: %d" % PROTOCOL_VERSION
			return False

		# if password is blank, let authentication pass
		if self.master.password=="":
			return True

		# otherwise trim off whitespace and compare to password string
		if password.trimmed().toAscii()==self.master.password:
			return True

		self.authenticationerror="Incorrect Password"
		return False

	def register(self):
		# register this new connection
		return self.master.registerClient(self.username,self.id,self.socket)

	def disconnected(self):
		print_debug("disconnecting client with ID: %d" % self.id)
		self.master.unregisterClient(self.id)

	def readyRead(self):
		readybytes=self.socket.bytesAvailable()

		if readybytes>0:
			data=self.socket.read(readybytes)
			print_debug("got animation data from socket: %s" % qtcore.QString(data))
			self.parser.xml.addData(data)
			error=self.parser.read()

			self.socket.waitForBytesWritten()

			if error!=QXmlStreamReader.PrematureEndOfDocumentError and error!=QXmlStreamReader.NoError:
				return error

			return None

	def run(self):
		# try to authticate user
		if not self.authenticate():
			# if authentication fails send close socket and exit
			print_debug("authentication failed")
			self.socket.write(qtcore.QByteArray("Authtication failed\n%s\n" % self.authenticationerror))
			self.socket.waitForBytesWritten()
			self.socket.disconnectFromHost()
			self.socket.waitForDisconnected(1000)
			return

		print_debug("authentication succeded")

		if not self.register():
			print_debug("register failed, probably due to duplicate username")
			self.socket.write(qtcore.QByteArray("Regististration failed\nRegistration with server failed, the username you chose is probably in use already, try a different one\n"))
			self.socket.waitForBytesWritten()
			self.socket.disconnectFromHost()
			self.socket.waitForDisconnected(1000)
			return

		print_debug("registered")
		self.parser=XmlToQueueEventsConverter(None,self.master.curwindow,0,type=ThreadTypes.server,id=self.id)
		print_debug("created parser")

		# pass initial data to client here
		self.socket.write(qtcore.QByteArray("Success\nConnected To Server\n"))

		# wait for client to respond so it doesn't get confused and mangle the setup data with the start of the XML file
		self.socket.waitForReadyRead(-1)
		print_debug("got client response")

		#qtcore.QObject.connect(self.socket, qtcore.SIGNAL("readyRead()"), self.readyRead)
		#qtcore.QObject.connect(self.socket, qtcore.SIGNAL("disconnected()"), self.disconnected)

		# start writing thread
		newwriter=HiveClientWriter(self,self.socket,self.master,self.id)
		newwriter.start()

		# while the "correct" way to do this might be to start an event loop, but for some reason that causes the socket to not read correctly.   It was reading the same data multiple times like it was reading before it had a chance to reset.
		while 1:
			# make sure we've waited long enough
			self.socket.waitForReadyRead(-1)
			error=self.readyRead()

			if error:
				# queue up command for client to be disconnected
				self.master.curwindow.addFatalErrorNotificationToQueue(self.id,"XML Stream Parse Error")
				return

			if self.socket.state() != qtnet.QAbstractSocket.ConnectedState:
				break

		# this should be run when the socket is disconnected
		self.disconnected()


# this thread will write to a specific client
class HiveClientWriter(qtcore.QThread):
	def __init__(self,parent,socket,master,id):
		qtcore.QThread.__init__(self)
		self.setParent(self)

		self.socket=socket
		self.master=master
		self.id=id

		# add to list of writing threads
		lock=qtcore.QReadLocker(self.master.clientslistmutex)
		self.queue=self.master.clientwriterqueues[id]

		# create custom QXmlStreamWriter
		self.xmlgenerator=SketchLogWriter(self.socket)

	def run(self):
		while 1:
			# block until item is available from thread safe queue
			data=self.queue.get()
			if self.socket.state()==qtnet.QAbstractSocket.UnconnectedState:
				self.master.unregisterClient(self.id)
				return

			# write xml data to socket
			self.xmlgenerator.logCommand(data)

			# flush so command goes out on network right away
			self.socket.flush()

			# test to make sure the delay isn't in the XML buffer
			self.socket.write(" ")
			self.socket.waitForBytesWritten(-1)
			self.socket.flush()

# class to handle running the TCP server and handling new connections
class HiveServerThread(qtcore.QThread):
	def __init__(self,master,port=8333):
		qtcore.QThread.__init__(self,master)
		self.threads=[]
		self.port=port
		self.master=master
		self.nextid=1

		# connect the signals we want
		qtcore.QObject.connect(self, qtcore.SIGNAL("finished()"), self.finished)
		qtcore.QObject.connect(self, qtcore.SIGNAL("started()"), self.started)

	def started(self):
		# needs to be done here because this is running in the proper thread
		self.server=qtnet.QTcpServer(self)

		# tell me when the server has gotten a new connection
		qtcore.QObject.connect(self.server, qtcore.SIGNAL("newConnection()"), self.newConnection)

		ret=self.server.listen(qtnet.QHostAddress("0.0.0.0"),self.port)

	def finished(self):
		print_debug("running finished")

	def run(self):
		self.exec_()

	# signal for the server getting a new connection
	def newConnection(self):
		print_debug("found new connection")
		while self.server.hasPendingConnections():
			newsock=self.server.nextPendingConnection()

			# start the listener, that will authenticate client and finish setup
			newlistener=HiveClientListener(self,newsock,self.master,self.nextid)
			self.nextid+=1

			# push responsibility to new thread
			newsock.setParent(None)
			newsock.moveToThread(newlistener)

			newlistener.start()

# this thread will route communication as needed between client listeners, the gui and client writers
class HiveRoutingThread(qtcore.QThread):
	def __init__(self,master):
		qtcore.QThread.__init__(self,master)
		self.master=master
		self.queue=master.routinginput

	def run(self):
		while 1:
			data=self.queue.get()
			print_debug("routing info recieved: %s" % str(data))
			(command,owner)=data
			# a negative number is a flag that we only send it to one client
			if owner<0:
				self.sendToSingleClient(abs(owner),command)
			elif command[0]==DrawingCommandTypes.alllayer or command[0]==DrawingCommandTypes.networkcontrol:
				self.sendToAllClients(command)
			else:
				self.sendToAllButOwner(owner,command)

	# I'd eventually put a check in here for if the queue is full and if so clear the queue and replace it with a raw event update to the current state
	def sendToAllClients(self,command):
		lock=qtcore.QReadLocker(self.master.clientslistmutex)
		for id in self.master.clientwriterqueues.keys():
			print_debug("sending to client: %d, command: %s" % (id, str(command)))
			self.master.clientwriterqueues[id].put(command)

	def sendToAllButOwner(self,source,command):
		lock=qtcore.QReadLocker(self.master.clientslistmutex)
		print_debug("sending command to all, but the owner: %s" % str(command))
		for id in self.master.clientwriterqueues.keys():
			if source!=id:
				print_debug("sending to client: %d" % id)
				self.master.clientwriterqueues[id].put(command)

	def sendToSingleClient(self,id,command):
		lock=qtcore.QReadLocker(self.master.clientslistmutex)
		if id in self.master.clientwriterqueues:
			self.master.clientwriterqueues[id].put(command)
		else:
			print_debug("WARNING: Can't find client %d for sending data to" % id)
