# append designer dir to search path
import sys
sys.path.append("designer")

import PyQt4.QtGui as qtgui
import PyQt4.QtCore as qtcore

import cPickle as pickle

from beeglobals import *
from beetypes import *
from BeeMasterUI import Ui_BeeMasterSpec
from ConnectionDialogUi import Ui_ConnectionInfoDialog
from colorswatch import *
from beelayer import BeeLayersWindow
from beeutil import getSupportedReadFileFormats
import beetools

import sip

from beedrawingwindow import BeeDrawingWindow, NetworkClientDrawingWindow


class BeeMasterWindow(qtgui.QMainWindow,object):
	instances = {}
	def __new__(cls, *args, **kwargs):
		""" this redefinition of new is here to make the object a singleton
		"""
		# if there is no instance of this class just make a new one and save what the init function was
		if BeeMasterWindow.instances.get(cls) is None:
			cls.__original_init__ = cls.__init__
			BeeMasterWindow.instances[cls] = sip.wrapper.__new__(cls, *args, **kwargs)
		# if there already was an instance and the init function is the same then make init do nothing so it's not run again and return the already created instance
		elif cls.__init__ == cls.__original_init__:
			def nothing(*args, **kwargs):
				pass
			cls.__init__ = nothing
		return BeeMasterWindow.instances[cls]

	def __init__(self,app):
		qtgui.QMainWindow.__init__(self)

		# setup interface according to designer code
		self.ui=Ui_BeeMasterSpec()
		self.ui.setupUi(self)
		self.show()

		self.app=app

		self.curwindow=None

		# list to hold drawing windows created
		self.drawingwindows=[]

		self.toolbox=beetools.BeeToolBox()

		# add list of tools to tool choice drop down
		for tool in self.toolbox.toolNameGenerator():
			self.ui.toolChoiceBox.addItem(tool)

		# set signal so we know when the tool changes
		self.connect(self.ui.toolChoiceBox,qtcore.SIGNAL("activated(int)"),self.on_tool_changed)

		# set initial tool
		self.curtoolindex=0

		# setup foreground and background swatches
		# default foreground to black and background to white
		self.fgcolor=qtgui.QColor(0,0,0)
		self.bgcolor=qtgui.QColor(255,255,255)
		self.ui.BGSwatch=ColorSwatch(self.ui.BGSwatch)
		self.ui.BGSwatch.updateColor(self.bgcolor)
		self.ui.FGSwatch=ColorSwatch(self.ui.FGSwatch)
		self.ui.FGSwatch.updateColor(self.fgcolor)

		# vars for dialog windows that there should only be one of each
		self.layerswindow=BeeLayersWindow(self)

		# keep track of current ID so each window gets a unique ID
		self.nextwindowid=0

	def registerWindow(self,window):
		self.drawingwindows.append(window)

	def unregisterWindow(self,window):
		#print "unregistering window with references:", sys.getrefcount(window)
		self.drawingwindows.remove(window)

	def getNextWindowId(self):
		self.nextwindowid+=1
		return self.nextwindowid

	def getWindowById(self,id):
		for win in self.drawingwindows:
			if win.id==id:
				return win
		print "Error: Couldn't find window with ID:", id
		return None

	def getLayerById(self,win_id,layer_id):
		win=self.getWindowById(win_id)
		if win:
			return win.getLayerForKey(layer_id)
		return None

	def removeWindow(self,window):
		try:
			self.drawingwindows.remove(window)
		except:
			pass
		if self.curwindow==window:
			self.curwindow=None

	def getCurToolInst(self,window):
		curtool=self.getCurToolDesc()
		return curtool.setupTool(window)

	def getCurToolDesc(self):
		return self.toolbox.getCurToolDesc()

	def on_tool_changed(self,index):
		self.toolbox.setCurToolIndex(index)
		for win in self.drawingwindows:
			win.view.setCursor(self.toolbox.getCurToolDesc().getCursor())

	def on_tooloptionsbutton_pressed(self):
		self.getCurToolDesc().runOptionsDialog(self)

	def on_backgroundbutton_pressed(self):
		color=qtgui.QColorDialog.getColor(self.bgcolor,self)
		if color.isValid():
			self.bgcolor=color
			self.ui.BGSwatch.updateColor(self.bgcolor)

	def on_foregroundbutton_pressed(self):
		color=qtgui.QColorDialog.getColor(self.fgcolor,self)
		if color.isValid():
			self.updateFGColor(color)

	# update the foreground color and refresh the swatch widget on screen
	def updateFGColor(self,color):
		self.fgcolor=color
		self.ui.FGSwatch.updateColor(self.fgcolor)

	def on_action_File_Exit_triggered(self,accept=True):
		if not accept:
			return

		self.close();

	def on_action_File_Play_triggered(self,accept=True):
		if not accept:
			return

		filename=str(qtgui.QFileDialog.getOpenFileName(self,"Select log file to play","","Sketch logfiles (*.slg)"))

		if filename:
			self.curwin=BeeDrawingWindow.newAnimationWindow(self,filename)
			newwin.animationthread.start()

	def on_action_File_Open_triggered(self,accept=True):
		if not accept:
			return

		formats=getSupportedReadFileFormats()
		filterstring=qtcore.QString("Images (")

		for f in formats:
			filterstring.append(" *.")
			filterstring.append(f)

		filterstring.append(" *.bee)")

		filename=qtgui.QFileDialog.getOpenFileName(self,"Choose File To Open","",filterstring)

		if filename:
			self.openFile(filename)

	def openFile(self,filename):
		# create a drawing window to start with
		# if we are saving my custom format
		if filename.endsWith(".bee"):
			f=open(filename,"r")
			try:
				l=pickle.load(f)
			except:
				print "Error, file dosen't seem to be in bee image format"
				return

			self.curwindow=None
			# first take version number and document size out of front of list
			version=l[0][0]
			width=l[0][1]
			height=l[0][2]

			if version > fileformatversion:
				print "Error unsuppored file format version, please upgrade bee version"

			self.curwindow=BeeDrawingWindow(self,width,height,False)

			layers=l[1:]

			# for each layer in the file uncompress the image data and set options
			for layer in layers:
				bytearray=qtcore.qUncompress(layer[0])
				image=qtgui.QImage()
				image.loadFromData(bytearray,"PNG")
				self.curwindow.loadLayer(image,opacity=layer[1],visible=layer[2],compmode=layer[3])

		else:
			reader=qtgui.QImageReader(filename)
			image=reader.read()

			self.curwindow=BeeDrawingWindow(self,image.width(),image.height(),False)
			self.curwindow.loadLayer(image)

			self.refreshLayersList()

	def on_actionFileMenuNew_triggered(self,accept=True):
		if not accept:
			return
		self.curwindow=BeeDrawingWindow(self)

		self.refreshLayersList()

	def on_action_File_Connect_triggered(self,accept=True):
		if not accept:
			return

		# launch dialog
		dialog=qtgui.QDialog(self)
		dialogui=Ui_ConnectionInfoDialog()
		dialogui.setupUi(dialog)
		ok=dialog.exec_()

		if not ok:
			return

		hostname=dialogui.hostnamefield.text()
		port=dialogui.portbox.value()
		username=dialogui.usernamefield.text()
		password=dialogui.passwordfield.text()

		self.curwindow=NetworkClientDrawingWindow(self,username,password,hostname,port)
		self.refreshLayersList()

	def on_action_File_Start_Server_triggered(self,accept=True):
		if not accept:
			return
		self.serverwin=HiveMasterWindow(app)
		self.curwindow=BeeDrawingWindow.startNetworkServer(self)
		self.refreshLayersList()

	def on_actionLayers_toggled(self,state):
		if state:
			self.layerswindow.show()
			self.refreshLayersList()
		else:
			self.layerswindow.hide()

	# destroy all subwindows
	def cleanUp(self):
		# copy list of windows otherwise destroying the windows as we iterate through will skip some
		tmplist=self.drawingwindows[:]

		# sending close will cause the windows to remove themselves from the window list
		for window in tmplist:
			window.close()

		self.layerswindow.close()
		self.layerswindow=None

	def closeEvent(self,event):
		# destroy subwindows
		self.cleanUp()
		# then do the standard main window close event
		qtgui.QMainWindow.closeEvent(self,event)

	def refreshLayersList(self):
		if self.curwindow and self.layerswindow:
			self.layerswindow.refreshLayersList(self.curwindow.layers,self.curwindow.curlayerkey)

	# function for a window to take the focus from other windows
	def takeFocus(self,window):
		if window != self.curwindow:
			self.curwindow=window
			self.refreshLayersList()

	def updateLayerHighlight(self,key):
		if self.layerswindow:
			self.layerswindow.refreshLayerHighlight(key)

	# refresh thumbnail of layer with inidcated key
	def refreshLayerThumb(self,windowid,key=None):
		if self.curwindow and self.curwindow.id==windowid:
			self.layerswindow.refreshLayerThumb(key)

	# handle the custom event I created to trigger refreshing the list of layers
	def customEvent(self,event):
		if event.type()==BeeCustomEventTypes.refreshlayerslist:
			self.refreshLayersList()

	def getToolClassByName(self,name):
		return self.toolbox.getToolDescByName(name)
