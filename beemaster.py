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

from beeapp import BeeApp

import sip

from abstractbeemaster import AbstractBeeMaster
from beedrawingwindow import BeeDrawingWindow, NetworkClientDrawingWindow

class BeeSwatchScrollArea(qtgui.QScrollArea):
	def __init__(self,master,oldwidget):
		parent=oldwidget.parentWidget()
		qtgui.QScrollArea.__init__(self,parent)


		self.setHorizontalScrollBarPolicy(qtcore.Qt.ScrollBarAlwaysOn)
		self.setVerticalScrollBarPolicy(qtcore.Qt.ScrollBarAlwaysOn)

		self.swatchrows=10
		self.swatchcolumns=10

		# steal attributes from old widget
		self.setSizePolicy(oldwidget.sizePolicy())
		self.setObjectName(oldwidget.objectName())

		# remove old widget and insert this one
		index=parent.layout().indexOf(oldwidget)
		parent.layout().removeWidget(oldwidget)
		parent.layout().insertWidget(index,self)

		self.setLayout(qtgui.QGridLayout(self))

		self.show()

		self.resetSwatches()

	def resetSwatches(self):
		for i in range(self.swatchrows):
			for j in range(self.swatchcolumns):
				self.layout().addWidget(ColorSwatch(self,parent=self),i,j)

class BeeMasterWindow(qtgui.QMainWindow,object,AbstractBeeMaster):
	def __init__(self):
		qtgui.QMainWindow.__init__(self)
		AbstractBeeMaster.__init__(self)

		# setup interface according to designer code
		self.ui=Ui_BeeMasterSpec()
		self.ui.setupUi(self)
		self.show()

		# list to hold drawing windows created
		self.drawingwindows=[]

		# add list of tools to tool choice drop down
		for tool in self.toolbox.toolNameGenerator():
			self.ui.toolChoiceBox.addItem(tool)

		# set signal so we know when the tool changes
		self.connect(self.ui.toolChoiceBox,qtcore.SIGNAL("activated(int)"),self.on_tool_changed)

		self.curwindow=None

		# set initial tool
		self.curtoolindex=0

		# setup foreground and background swatches
		# default foreground to black and background to white
		self.fgcolor=qtgui.QColor(0,0,0)
		self.bgcolor=qtgui.QColor(255,255,255)
		self.ui.BGSwatch=BGSwatch(self,self.ui.BGSwatch)
		self.ui.BGSwatch.updateColor(self.bgcolor)
		self.ui.FGSwatch=FGSwatch(self,self.ui.FGSwatch)
		self.ui.FGSwatch.updateColor(self.fgcolor)

		# vars for dialog windows that there should only be one of each
		self.layerswindow=BeeLayersWindow(self)

		# keep track of current ID so each window gets a unique ID
		self.nextwindowid=0

		# replace widget with scroll area to hold them
		self.ui.swatch_frame=BeeSwatchScrollArea(self,self.ui.swatch_frame)

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
		else:
			print "Warning: can't find layer with id:", layer_id, "in window:", win_id
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
		self.ui.BGSwatch.changeColorDialog()

	def on_foregroundbutton_pressed(self):
		self.ui.FGSwatch.changeColorDialog()

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
		self.serverwin=HiveMasterWindow(BeeApp().app)
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
