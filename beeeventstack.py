#    Beedraw/Hive network capable client and server allowing collaboration on a single image
#    Copyright (C) 2009 Thomas Becker
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
import PyQt4.QtGui as qtgui

from beeutil import *
from beetypes import *
from beeapp import BeeApp

# object to handle the undo/redo history
class CommandStack:
	def __init__(self,window,type,maxundo=50):
		self.commandstack=[]
		self.index=0
		self.changessincesave=0
		self.type=type

		self.win=window

		self.maxundo=maxundo
		if self.maxundo<0:
			self.maxundo=0

		# start this at 0, it will get reset shortly with data from server if this is a network session
		self.networkmaxundo=0

		self.networkinhist=0

	def changeToLocal(self):
		self.type=CommandStackTypes.singleuser

	def setHistorySize(self,newsize):
		if self.type==CommandStackTypes.remoteonly:
			self.setNetworkHistorySize(newsize)
		else:
			self.maxundo=newsize
			if self.maxundo<0:
				self.maxundo=0
			self.checkStackSize()

	def setNetworkHistorySize(self,newsize):
		self.networkmaxundo=newsize
		if self.networkmaxundo<0:
			self.networkmaxundo=0
		self.checkStackSize()

	def deleteLayerHistory(self,layerkey):
		""" remove all references to given layer in history """
		# make copy of stack so I can iterate through it correctly while deleting
		newstack=self.commandstack[:]

		for c in self.commandstack:
			# if the currnet time involves the item in question
			if c.layerkey==layerkey:
				# if this is behind the current index (not undone)
				if newstack.index(c)<self.index:
					self.index-=1
					# if we care about which events are network events, then keep track
					if self.type==CommandStackTypes.network:
						self.networkinhist-=1
				# remove the event from the history
				newstack.remove(c)

		self.commandstack=newstack

	def checkStackSize(self):
		while len(self.commandstack)>self.maxundo or (self.type==CommandStackTypes.network and self.networkinhist > self.networkmaxundo):
			if self.type==CommandStackTypes.network and self.commandstack[0].undotype==UndoCommandTypes.remote:
				self.networkinhist-=1
			self.commandstack=self.commandstack[1:]
			self.index-=1

	def add(self,command):
		# if there are commands ahead of this one delete them
		if self.index<len(self.commandstack):
			# if we need to then decrement the network in history numbers for the ones we remove
			#if self.type==CommandStackTypes.network:
			#	for cmd in self.commandstack[self.index+1:]:
			#		if cmd.undotype==UndoCommandTypes.remote:
			#			self.networkinhist-=1
			self.commandstack=self.commandstack[:self.index]

		if self.type==CommandStackTypes.network and command.undotype==UndoCommandTypes.remote:
			self.networkinhist+=1

		# if the command stack is full, delete the oldest one
		self.checkStackSize()

		self.commandstack.append(command)
		self.index=len(self.commandstack)
		self.changessincesave+=1

	def undo(self):
		if self.index<=0:
			return UndoCommandTypes.none

		command=self.commandstack[self.index-1]

		if self.type==CommandStackTypes.network and command.undotype==UndoCommandTypes.remote:
			self.networkinhist-=1

		self.index-=1
		command.undo(self.win)
		BeeApp().master.refreshLayerThumb(self.win)

		return command.undotype

	def redo(self):
		if self.index>=len(self.commandstack):
			return UndoCommandTypes.none

		command=self.commandstack[self.index]

		if self.type==CommandStackTypes.network and command.undotype==UndoCommandTypes.remote:
			self.networkinhist+=1

		command.redo(self.win)
		self.index+=1
		BeeApp().master.refreshLayerThumb(self.win)
		return command.undotype

# parent class for all commands that get put in undo/redo stack
class AbstractCommand:
	undotype=UndoCommandTypes.localonly
	def __init__(self):
		self.layerkey=0
	def undo(self):
		pass

	def redo(self):
		pass

# this class is for any command that changes the image on a layer
class DrawingCommand(AbstractCommand):
	undotype=UndoCommandTypes.remote
	def __init__(self,layerkey,oldimage,location):
		AbstractCommand.__init__(self)
		self.layerkey=layerkey
		self.oldimage=oldimage
		self.location=location

	def undo(self,win):
		print_debug("running undo in drawing command")
		layer=win.getLayerForKey(self.layerkey)
		if layer:
			self.redoimage=layer.image.copy(self.location)
			layer.compositeFromCorner(self.oldimage,self.location.x(),self.location.y(),qtgui.QPainter.CompositionMode_Source)
			win.requestLayerListRefresh()

	def redo(self,win):
		print_debug("running redo in drawing command")
		layer=win.getLayerForKey(self.layerkey)
		if layer:
			layer.compositeFromCorner(self.redoimage,self.location.x(),self.location.y(),qtgui.QPainter.CompositionMode_Source)
			win.requestLayerListRefresh()

class AnchorCommand(DrawingCommand):
	undotype=UndoCommandTypes.remote
	def __init__(self,layerkey,oldimage,location,floating):
		DrawingCommand.__init__(self,layerkey,oldimage,location)
		self.floating=floating

	def undo(self,win):
		DrawingCommand.undo(self,win)
		layer=win.getLayerForKey(self.layerkey)
		if layer:
			lock=qtcore.QWriteLocker(win.layerslistlock)
			layer.scene().addItem(self.floating)
			self.floating.setParentItem(layer)
			win.requestLayerListRefresh(lock)
			BeeApp().master.updateLayerHighlight(win,self.floating.key)

	def redo(self,win):
		DrawingCommand.redo(self,win)
		layer=win.getLayerForKey(self.layerkey)
		if layer:
			lock=qtcore.QWriteLocker(win.layerslistlock)
			layer.scene().removeItem(self.floating)
			win.setValidActiveLayer(listlock=lock)
			win.requestLayerListRefresh(lock=lock)

class AddLayerCommand(AbstractCommand):
	undotype=UndoCommandTypes.notinnetwork
	def __init__(self,layerkey):
		AbstractCommand.__init__(self)
		self.layerkey=layerkey

	def undo(self,win):
		(self.oldlayer,self.index)=win.removeLayerByKey(self.layerkey,history=-1)

	def redo(self,win):
		win.insertRawLayer(self.oldlayer,self.index,history=-1)

class DelLayerCommand(AbstractCommand):
	undotype=UndoCommandTypes.notinnetwork
	def __init__(self,layer,index):
		AbstractCommand.__init__(self)
		self.layerkey=layer.key
		self.layer=layer
		self.index=index

	def undo(self,win):
		win.insertRawLayer(self.layer,self.index,history=-1)

	def redo(self,win):
		win.removeLayerByKey(self.layer.key,history=-1)

class LayerUpCommand(AbstractCommand):
	undotype=UndoCommandTypes.notinnetwork
	def __init__(self,layerkey):
		AbstractCommand.__init__(self)
		self.layerkey=layerkey

	def undo(self,win):
		win.layerDown(self.layerkey,history=False)

	def redo(self,win):
		win.layerUp(self.layerkey,history=False)

class LayerDownCommand(AbstractCommand):
	undotype=UndoCommandTypes.notinnetwork
	def __init__(self,layerkey):
		AbstractCommand.__init__(self)
		self.layerkey=layerkey

	def undo(self,win):
		win.layerUp(self.layerkey,history=False)

	def redo(self,win):
		win.layerDown(self.layerkey,history=False)

class CutCommand(DrawingCommand):
	undotype=UndoCommandTypes.remote
	def __init__(self,layerkey,oldimage,location,path):
		DrawingCommand.__init__(self)
		self.path=path

	def undo(self,win):
		DrawingCommand.undo(self,win)
		win.changeSelection(SelectionModTypes.new,path,history=False)

	def redo(self,win):
		DrawingCommand.redo(self,win)
		win.changeSelection(SelectionModTypes.clear,history=False)

class ChangeSelectionCommand(AbstractCommand):
	undotype=UndoCommandTypes.localonly
	def __init__(self,oldpath,newpath):
		AbstractCommand.__init__(self)
		self.oldpath=oldpath
		self.newpath=newpath

	def undo(self,win):
		if self.oldpath:
			win.changeSelection(SelectionModTypes.setlist,self.oldpath,history=False)
		else:
			win.changeSelection(SelectionModTypes.clear,history=False)

	def redo(self,win):
		if self.newpath:
			win.changeSelection(SelectionModTypes.setlist,self.newpath,history=False)
		else:
			win.changeSelection(SelectionModTypes.clear,history=False)

class PasteCommand(ChangeSelectionCommand):
	undotype=UndoCommandTypes.localonly
	def __init__(self,layerkey,oldpath,newpath):
		ChangeSelectionCommand.__init__(self,oldpath,newpath)
		self.layerkey=layerkey

	def undo(self,win):
		ChangeSelectionCommand.undo(self,win)
		layer=win.getLayerForKey(self.layerkey)
		self.scene=layer.scene()
		self.layerparent=layer.parentItem()
		if layer:
			self.oldlayer,self.index=win.removeLayer(layer,history=False)

	def redo(self,win):
		ChangeSelectionCommand.redo(self,win)
		if self.oldlayer:
			self.scene.addItem(self.oldlayer)
			self.oldlayer.setParentItem(self.layerparent)
			win.requestLayerListRefresh()

class MoveSelectionCommand(AbstractCommand):
	undotype=UndoCommandTypes.localonly
	def __init__(self,layerkey,oldpos,newpos):
		AbstractCommand.__init__(self)
		self.oldpos=oldpos
		self.newpos=newpos

	def undo(self,win):
		layer=win.getLayerForKey(self.layerkey)
		layer.setPos(oldpos)

	def redo(self,win):
		layer=win.getLayerForKey(self.layerkey)
		layer.setPos(newpos)

class MoveFloatingCommand(AbstractCommand):
	undotype=UndoCommandTypes.localonly
	def __init__(self,oldx,oldy,newx,newy,layerkey):
		AbstractCommand.__init__(self)
		self.oldx=oldx
		self.oldy=oldy
		self.newx=newx
		self.newy=newy
		self.layerkey=layerkey

	def undo(self,win):
		layer=win.getLayerForKey(self.layerkey)
		if layer:
			layer.setPos(self.oldx,self.oldy)
			layer.scene().update()

	def redo(self,win):
		layer=win.getLayerForKey(self.layerkey)
		if layer:
			layer.setPos(self.newx,self.newy)
			layer.scene().update()
