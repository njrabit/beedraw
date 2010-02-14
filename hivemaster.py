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

from beenetwork import BeeTCPServer

try:
	from PyQt4.QtXml import QXmlStreamReader
except:
	from PyQt4.QtCore import QXmlStreamReader

from beenetwork import BeeSocket
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

		self.width=600
		self.height=400

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
		self.curwindow=None
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
		print_debug("unregistering client: %d" % id)
		lock=qtcore.QWriteLocker(self.clientslistmutex)
		if not id in self.clientnames:
			return

		# remove from dictionary of clients
		username=self.clientnames[id]
		del self.clientnames[id]

		# remove from list of outgoing queues
		del self.clientwriterqueues[id]

		# remove from gui
		items=self.ui.clientsList.findItems(username,qtcore.Qt.MatchFixedString)
		for item in items:
			index=self.ui.clientsList.row(item)
			self.ui.clientsList.takeItem(index)

		# set layers owned by that client to unowned
		lock=qtcore.QWriteLocker(self.curwindow.layerslistlock)
		for layer in self.curwindow.layers:
			if layer.owner==id:
				print_debug("setting layer %d to unowned" % layer.key)
				self.curwindow.addGiveUpLayerToQueue(layer.key,id)

	def closeEvent(self,event):
		qtgui.QMainWindow.closeEvent(self,event)
#		self.stopServer()

	def resetState(self):
		# only do this if the server isn't running yet
		if not self.serverthread:
			self.curwindow=HiveSessionState(self,self.width,self.height,WindowTypes.standaloneserver,20)
			self.curwindow.startRemoteDrawingThreads()

	def startServer(self):
		# make sure the state exists
		if not self.curwindow:
			self.resetState()

		# make sure no other instance is running
		self.stopServer()

		self.serverthread=HiveServerThread(self,self.port)
		self.serverthread.start()

	def event(self,event):
		if event.type()==BeeCustomEventTypes.hiveserverstatus:
			if event.status==HiveServerStatusTypes.running:
				self.changeStatusLabel("Serving on port: %d" % self.port)
			elif event.status==HiveServerStatusTypes.starterror:
				if event.errorstring:
					body=event.errorstring
				else:
					body="Failed to start server on port %d.\nMake sure port is not already in use." % self.port
				qtgui.QMessageBox.critical(self,"Could not start server",body)
				self.changeStatusLabel("Failed to start on port %d" % self.port)
			elif event.status==HiveServerStatusTypes.stopped:
				self.changeStatusLabel("Server not running")

		return qtgui.QMainWindow.event(self,event)

	def changeStatusLabel(self,text):
		self.ui.statusLabel.setText(text)

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
				self.width=dialog.ui.width_box.value()
				self.height=dialog.ui.height_box.value()

# class to handle running the TCP server and handling new connections
class HiveServerThread(qtcore.QThread):
	def __init__(self,master,port=8333):
		qtcore.QThread.__init__(self,master)
		self.threads=[]
		self.port=port
		self.master=master

		# connect the signals we want
		qtcore.QObject.connect(self, qtcore.SIGNAL("finished()"), self.finished)
		qtcore.QObject.connect(self, qtcore.SIGNAL("started()"), self.started)

	def started(self):
		# needs to be done here because this is running in the proper thread
		self.server=BeeTCPServer(BeeSocketTypes.qt,8333,self,self.master)
		self.server.start()

	def finished(self):
		print_debug("server thread has finished")

	def run(self):
		self.exec_()

	# signal for the server getting a new connection
#	def newConnection(self):
#		print_debug("found new connection")
#		while self.server.hasPendingConnections():
#			newsock=self.server.nextPendingConnection()

			# start the listener, that will authenticate client and finish setup
#			newlistener=HiveClientListener(self,BeeSocket(BeeSocketTypes.qt,newsock),self.master,self.nextid)
#			self.nextid+=1

			# push responsibility to new thread
#			newsock.setParent(None)
#			newsock.moveToThread(newlistener)

#			newlistener.start()

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
				print "putting in queue:", self.master.clientwriterqueues[id]
				self.master.clientwriterqueues[id].put(command)

	def sendToSingleClient(self,id,command):
		lock=qtcore.QReadLocker(self.master.clientslistmutex)
		if id in self.master.clientwriterqueues:
			self.master.clientwriterqueues[id].put(command)
		else:
			print_debug("WARNING: Can't find client %d for sending data to" % id)
