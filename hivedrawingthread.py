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

import PyQt4.QtCore as qtcore

from beetypes import *
from beeutil import *
from hivecache import *

import copy

from drawingthread import DrawingThread

class ServerDrawingThread(DrawingThread):
	def __init__(self,queue,windowid,master=None,historysize=20):
		DrawingThread.__init__(self,queue,windowid,type=ThreadTypes.server,master=master)
		self.commandcaches={}
		self.commandindexes={}
		self.historysize=historysize

	def processNetworkCommand(self,command):
		window=self.master.getWindowById(self.windowid)
		subtype=command[1]
		requester=command[2]
		if subtype==NetworkControlCommandTypes.resyncrequest:
			self.sendResyncToClient(requester,window)
		elif subtype==NetworkControlCommandTypes.giveuplayer:
			layerkey=command[3]
			layer=window.getLayerForKey(layerkey)
			proplock=qtcore.QWriteLocker(layer.propertieslock)
			self.layerOwnerChangeCommand(layer,0)
		elif subtype==NetworkControlCommandTypes.requestlayer:
			layerkey=command[3]
			layer=window.getLayerForKey(layerkey)
			proplock=qtcore.QWriteLocker(layer.propertieslock)
			if layer.owner==0:
				self.layerOwnerChangeCommand(layer,requester)

		elif subtype==NetworkControlCommandTypes.fatalerror:
			self.master.routinginput.put((command,requester*-1))

	def sendResyncToClient(self,requester,window):
		# first tell client to get rid of list of layers
		resynccommand=(DrawingCommandTypes.networkcontrol,NetworkControlCommandTypes.resyncstart,window.docwidth,window.docheight,requester)
		dest=-1*requester
		self.master.routinginput.put((resynccommand,dest))

		window.sendLayersToClient(requester)

		#send event cache to client
		for c in self.commandcaches.keys():
			for command in self.commandcaches[c]:
				command.send(requester,self.master.routinginput)

			backlength=len(self.commandcaches[c]) - self.commandindexes[c]
			if backlength>0:
				undocommand=(DrawingCommandTypes.history,HistoryCommandTypes.undo,c)
				for i in range(backlength):
					self.master.routinginput.put((undocommand,requester*-1))
					

	# Change layer owner, must lock down properties layer before calling this
	def layerOwnerChangeCommand(self,layer,newowner):
		print "changing owner of layer:", layer.key
		oldowner=layer.owner
		print "layer was owned by:", oldowner
		print "layer now owned by:", newowner
		if oldowner in self.commandcaches:
			print "found old owner in command caches"
			# make copy of list so removing while iterating works
			newcache=self.commandcaches[oldowner][:]
			# go through the command stack for the owner to remove commands that relate to that layer
			for command in self.commandcaches[oldowner]:
				print "found command for old owner"
				if command.layer.key==layer.key:
					# if the command is before the current index then decrement the index
					if newcache.index(command)<self.commandindexes[oldowner]:
						self.commandindexes[oldowner]-=1
					print "DEBUG: processing command onto layer"
					command.process()
					newcache.remove(command)

			# update cache of old owner to not include references to that layer
			self.commandcaches[oldowner]=newcache

		layer.owner=newowner
		command=(DrawingCommandTypes.networkcontrol,NetworkControlCommandTypes.layerowner,newowner,layer.key)
		# if the old owner was 0, meaning it was unowned, then send it to everyone, otherwise the old owner has already changed it locally to 0 and doesn't need it again
		self.master.routinginput.put((command,oldowner))

	def processLayerCommand(self,command):
		cachedcommand=None
		window=self.master.getWindowById(self.windowid)
		subtype=command[1]
		layer=window.getLayerForKey(command[2])
		if not layer:
			return
		owner=layer.owner
		# if the layer is owned locally then no one should be able to change it since this is a server session
		if owner==0:
			print "ERROR: recieved layer command for unowned layer in server session:", command
			return

		if subtype==LayerCommandTypes.alpha:
			cachedcommand=CachedAlphaEvent(layer,command[3])
			self.master.routinginput.put((command,layer.owner))

		elif subtype==LayerCommandTypes.mode:
			cachedcommand=CachedModeEvent(layer,command[3])
			self.master.routinginput.put((command,layer.owner))

		elif subtype==LayerCommandTypes.pendown:
			x=command[3]
			y=command[4]
			pressure=command[5]
			tool=command[6]

			self.inprocesstools[layer]=CachedToolEvent(layer,tool)
			self.inprocesstools[layer].points=[(x,y,pressure)]
			self.inprocesstools[layer].prevpoints=[]

		elif subtype==LayerCommandTypes.penmotion:
			#print "Pen motion event:", command
			x=command[3]
			y=command[4]
			pressure=command[5]

			self.inprocesstools[layer].points.append((x,y,pressure))

		elif subtype==LayerCommandTypes.penup:
			x=command[3]
			y=command[4]

			cachedcommand=self.inprocesstools[layer]

			# make a shallow copy so that the points history won't get changed in the middle of any operations
			tool=copy.copy(cachedcommand.tool)
			tool.pointshistory=cachedcommand.points
			tool.prevpointshistory=cachedcommand.prevpoints

			toolcommand=(DrawingCommandTypes.layer,LayerCommandTypes.tool,cachedcommand.layer.key,tool)

			self.master.routinginput.put((toolcommand,owner))

			del self.inprocesstools[layer]

		elif subtype==LayerCommandTypes.rawevent:
			x=command[3]
			y=command[4]
			image=command[5]
			path=command[6]
			compmode=qtgui.QPainter.CompositionMode_Source

			cachedcommand=CachedRawEvent(layer,x,y,image,path,compmode,owner)

			self.master.routinginput.put((command,owner))

		elif subtype==LayerCommandTypes.penleave:
			pass
			

		elif subtype==LayerCommandTypes.penenter:
			self.inprocesstools[layer].prevpoints.append(self.inprocesstools[layer].points)
			self.inprocesstools[layer].points=[]

		else:
			sendcommand=False
			print "unknown processLayerCommand subtype:", subtype

		if cachedcommand:
			print "found cached command, adding to cache"
			self.addToCache(cachedcommand)

	def addToCache(self,command):
		owner=command.layer.owner
		print "adding command for owner:", owner
		if not owner in self.commandcaches:
			print "creating command cache for owner:", owner
			self.commandcaches[owner]=[]
			self.commandindexes[owner]=0

		# if there are commands ahead of this one delete them
		if self.commandindexes[owner] < len(self.commandcaches[owner]):
			self.commandcaches[owner]=self.commandcaches[owner][0:self.commandindexes[owner]]

		# if the command stack is full, execute and delete the oldest one
		if self.commandindexes[owner] > self.historysize:
			self.commandcaches[owner][0].process()
			self.commandcaches[owner]=self.commandcaches[owner][1:]

		self.commandcaches[owner].append(command)
		print "added command to cache:", command, owner
		self.commandindexes[owner]=len(self.commandcaches[owner])

	def processHistoryCommand(self,command):
		""" Handles undo and redo commands sent from clients by updating local history counter and sending the commands out to all other clients, all of the print statements here should never trigger, but I'm putting them in for debugging purposes in case something goes wrong
		"""
		subtype=command[1]
		owner=command[2]

		if not owner in self.commandindexes:
			self.commandcaches[owner]=[]
			self.commandindexes[owner]=0

		if subtype==HistoryCommandTypes.undo:
			# test to make sure there should be some history to undo
			if self.commandindexes[owner]>0:
				self.commandindexes[owner]-=1
				self.master.routinginput.put((command,owner))
			else:
				print "Error, got undo but no more past history for client", owner
		elif subtype==HistoryCommandTypes.redo:
			if self.commandindexes[owner]<len(self.commandcaches[owner]):
				self.commandindexes[owner]+=1
				self.master.routinginput.put((command,owner))
			else:
				print "Error, got redo but no more future history for client", owner

	def processAllLayerCommand(self,command):
		DrawingThread.processAllLayerCommand(self,command)
		self.master.routinginput.put((command,0))
