#!/usr/bin/env python
 
import PyQt4.QtGui as qtgui
import PyQt4.QtCore as qtcore
import math
from beeutil import *
from beetypes import *
from beeeventstack import *
 
from PencilOptionsDialogUi import *
from BrushOptionsDialogUi import *
from EraserOptionsDialogUi import *
 
# Class to manage tools and make instances as needed
class BeeToolBox:
	def __init__(self):
		self.toolslist=[]
		self.loadDefaultTools()
		self.curtoolindex=0
 
	def loadDefaultTools(self):
		self.toolslist.append(PencilToolDesc())
		self.toolslist.append(PaintBrushToolDesc())
		self.toolslist.append(EraserToolDesc())
		self.toolslist.append(RectSelectionToolDesc())
 
	def toolNameGenerator(self):
		for tool in self.toolslist:
			yield tool.name
 
	def getCurToolDesc(self):
		return self.toolslist[self.curtoolindex]
 
	def setCurToolIndex(self,index):
		self.curtoolindex=index
 
	def getToolDescByName(self,name):
		for tool in self.toolslist:
			if name==tool.name:
				return tool
		print "Error, toolbox couldn't find tool with name:", name
		return None
 
# Base class for a class to describe all tools and spawn tool instances
class AbstractToolDesc:
	def __init__(self,name):
		self.clippath=None
		self.options={}
		self.name=name
		self.setDefaultOptions()
 
	def getCursor(self):
		return qtcore.Qt.ArrowCursor
 
	def getDownCursor(self):
		return qtcore.Qt.ArrowCursor
 
	def setDefaultOptions(self):
		pass
 
	def getOptionsWidget(self,parent):
		return qtgui.QWidget(parent)
 
	def runOptionsDialog(self,parent):
		qtgui.QMessageBox(qtgui.QMessageBox.Information,"Sorry","No Options Avialable for this tool",qtgui.QMessageBox.Ok).exec_()
 
	# setup needed parts of tool using knowledge of current window
	# this should be implemented in subclass if needed
	def setupTool(self,window):
		return self.getTool(window)
 
	def getTool(self,window):
		return None
 
# base class for all drawing tools
class AbstractTool:
	def __init__(self,options,window):
		self.fgcolor=None
		self.bgcolor=None
		self.clippath=None
		self.options=options
		self.window=window
 
	def setOption(self,key,value):
		self.options[key]=value
 
	# what to do when pen is down to be implemented in subclasses
	def penDown(self,x,y,pressure=None):
		pass
 
	def penMotion(self,x,y,pressure):
		pass
 
	def penUp(self,x=None,y=None,source=0):
		pass
 
	def penLeave(self):
		pass
 
	def penEnter(self):
		pass
 
# basic tool for everything that draws points on the canvas
class DrawingTool(AbstractTool):
	def __init__(self,options,window):
		AbstractTool.__init__(self,options,window)
		self.name="Pencil"
		self.lastpressure=-1
		self.compmode=qtgui.QPainter.CompositionMode_SourceOver
		self.pointshistory=None
		self.layer=None
 
	def getColorRGBA(self):
		return self.fgcolor.rgba()
 
	def makeFullSizedBrush(self):
		diameter=self.options["diameter"]
		self.diameter=self.options["diameter"]

		color=self.getColorRGBA()
 
		center=diameter/2.0
		self.fullsizedbrush=qtgui.QImage(diameter,diameter,qtgui.QImage.Format_ARGB32_Premultiplied)
		self.fullsizedbrush.fill(0)
		for i in range(diameter):
			for j in range(diameter):
				# add in .5 to each point so we measure from the center of the pixel
				distance=math.sqrt(((i+.5-center)**2)+((j+.5-center)**2))
				if distance <= center:
					self.fullsizedbrush.setPixel(i,j,color)

	def updateBrushForPressure(self,pressure):
		# see if we need to update at all
		if self.lastpressure==pressure:
			return
 
		self.lastpressure=pressure
 
		# if we can use the full sized brush, then do it
		if self.options["pressuresize"]==0 or pressure==1:
			self.brushimage=self.fullsizedbrush
			self.lastpressure=1
			return
 
		# scaled size for brush
		bdiameter=self.options["diameter"]*pressure
		self.diameter=int(math.ceil(bdiameter))
 
		# bounding radius for pixels to update
		side=self.diameter
 
		fullsizedrect=qtcore.QRectF(0,0,self.fullsizedbrush.width(),self.fullsizedbrush.height())
		cursizerect=qtcore.QRectF(0,0,bdiameter,bdiameter)
 
		self.brushimage=qtgui.QImage(side,side,qtgui.QImage.Format_ARGB32_Premultiplied)
		self.brushimage.fill(0)
		painter=qtgui.QPainter()
		painter.begin(self.brushimage)
 
		painter.drawImage(cursizerect,self.fullsizedbrush,fullsizedrect)

		painter.end()
 
	def penDown(self,x,y,pressure=1):
		self.layer=self.window.getLayerForKey(self.layerkey)
		x=int(x)
		y=int(y)
		self.oldlayerimage=qtgui.QImage(self.layer.image)
		self.pointshistory=[(x,y,pressure)]
		self.lastpoint=(x,y)
		self.makeFullSizedBrush()
		self.updateBrushForPressure(pressure)
		self.layer.compositeFromCenter(self.brushimage,x,y,self.compmode,self.clippath)
 
	def penMotion(self,x,y,pressure=None):
		x=int(x)
		y=int(y)
 
		# if it hasn't moved just do nothing
		if (x,y)==self.lastpoint:
			return
 
		self.pointshistory.append((x,y,pressure))
 
		# get size of layer
		layerwidth=self.layer.window.docwidth
		layerheight=self.layer.window.docheight
 
		# get points inbetween according to step option and layer size
		path=getPointsPath(self.lastpoint[0],self.lastpoint[1],x,y,self.options['step'],layerwidth,layerheight,self.lastpressure,pressure)

		# if no points are on the layer just return
		if len(path)==0:
			return

		self.updateBrushForPressure(max(pressure,self.lastpressure))
		radius=int(math.ceil(self.diameter/2.0))

		# calculate the bounding rect for this operation
		left=min(path[0][0],path[-1][0])-radius
		top=min(path[0][1],path[-1][1])-radius
		right=max(path[0][0],path[-1][0])+radius
		bottom=max(path[0][1],path[-1][1])+radius
 
		left=max(0,left)
		top=max(0,top)
		right=min(layerwidth,right)
		bottom=min(layerheight,bottom)
 
		# calulate area needed to hold everything
		width=right-left
		height=bottom-top
 
		# then make an image for that bounding rect
		lineimage=qtgui.QImage(width,height,qtgui.QImage.Format_ARGB32_Premultiplied)
		lineimage.fill(0)

		# put points in that image
		painter=qtgui.QPainter()
		painter.begin(lineimage)
		painter.setRenderHint(qtgui.QPainter.HighQualityAntialiasing)
 
		for point in path:
			self.updateBrushForPressure(point[2])
			lineimgpoint=(point[0]-left-radius,point[1]-top-radius)
			painter.drawImage(lineimgpoint[0],lineimgpoint[1],self.brushimage)
 
		painter.end()
 
		self.layer.compositeFromCorner(lineimage,left,top,self.compmode,self.clippath)
 
		self.lastpoint=path[-1]
 
	# record this event in the history
	def penUp(self,x=None,y=None,source=0):
		radius=int(math.ceil(self.options["diameter"]))
 
		# get maximum bounds of whole brush stroke
		left=self.pointshistory[0][0]
		right=self.pointshistory[0][0]
		top=self.pointshistory[0][1]
		bottom=self.pointshistory[0][1]
		for point in self.pointshistory:
			if point[0]<left:
				left=point[0]
			elif point[0]>right:
				right=point[0]
 
			if point[1]<top:
				top=point[1]
			elif point[1]>bottom:
				bottom=point[1]
 
		# calculate bounding area of whole event
		dirtyrect=qtcore.QRect(left-radius,top-radius,right+(radius*2),bottom+(radius*2))
		# bound it by the area of the layer
		dirtyrect=rectIntersectBoundingRect(dirtyrect,self.layer.image.rect())
 
		# get image of what area looked like before
		oldimage=self.oldlayerimage.copy(dirtyrect)
 
		command=DrawingCommand(self.layer.key,oldimage,dirtyrect)
		self.layer.window.addCommandToHistory(command,source)
 
		self.layer.window.master.refreshLayerThumb(self.layer.key)
 
# basic tool for drawing fuzzy edged stuff on the canvas
class PaintBrushTool(DrawingTool):
	def __init__(self,options,window):
		DrawingTool.__init__(self,options,window)
		self.name="brush"
		self.lastpressure=-1
		self.compmode=qtgui.QPainter.CompositionMode_SourceOver
 
	def updateBrushForPressure(self,pressure):
		# see if we need to update at all
		if self.lastpressure==pressure:
			return
		self.lastpressure=pressure
 
		# if we can use the full sized brush, then do it
		if self.options["pressuresize"]==0 or pressure==1:
			self.brushimage=self.fullsizedbrush
			self.diameter=self.options["diameter"]
			return
 
		transform=qtgui.QTransform()
		transform=transform.scale(pressure,pressure)
 
		# scale the brush to proper size
		#self.brushimage=self.fullsizedbrush.transformed(transform,qtcore.Qt.SmoothTransformation)
 
 		centeroffset=0
 		#centeroffset=(1-((self.options["diameter"])%1))/2.0
 		#transformoffset=(1-((self.options["diameter"])%1))/2.0

		#transform=transform.translate(transformoffset,transformoffset)

		# scale the brush to proper size (alternate method)
		diameter=int(math.ceil(self.fullsizedbrush.width()*pressure))
		self.brushimage=qtgui.QImage(diameter,diameter,qtgui.QImage.Format_ARGB32_Premultiplied)
		self.brushimage.fill(0)
		painter=qtgui.QPainter()
		painter.begin(self.brushimage)
		#painter.setRenderHint(qtgui.QPainter.Antialiasing)
		painter.setRenderHint(qtgui.QPainter.SmoothPixmapTransform)
		painter.setRenderHint(qtgui.QPainter.HighQualityAntialiasing)
		painter.setTransform(transform)
		painter.drawImage(qtcore.QPointF(centeroffset,centeroffset),self.fullsizedbrush)
 
		print "updated brush for pressure:", pressure
		printImage(self.brushimage)
 
		# update radius so we know how much area to refresh on the screen
		self.diameter=self.brushimage.width()
 
	def makeFullSizedBrush(self):
		diameter=self.options["diameter"]
		radius=diameter/2.0
		blur=self.options["blur"]
 
		fgr=self.fgcolor.red()
		fgg=self.fgcolor.green()
		fgb=self.fgcolor.blue()
 
		center=diameter/2.0
		self.fullsizedbrush=qtgui.QImage(diameter,diameter,qtgui.QImage.Format_ARGB32_Premultiplied)
		self.fullsizedbrush.fill(0)
		for i in range(diameter):
			for j in range(diameter):
				# add in .5 to each point so we measure from the center of the pixel
				distance=math.sqrt(((i+.5-center)**2)+((j+.5-center)**2))
				if distance < radius:
					# fade the brush out a little if it is too close to the edge according to the blur percentage
					fade=(1-(distance/(radius)))/(blur/100.0)
					if fade > 1:
						fade=1
					# need to muliply the color by the alpha becasue it's going into
					# a premuliplied image
					curcolor=qtgui.qRgba(fgr*fade,fgg*fade,fgb*fade,fade*255)
					self.fullsizedbrush.setPixel(i,j,curcolor)
 
# this is the most basic drawing tool
class PencilToolDesc(AbstractToolDesc):
	def __init__(self):
		AbstractToolDesc.__init__(self,"Pencil")
 
	def getCursor(self):
		return qtcore.Qt.CrossCursor
 
	def getDownCursor(self):
		return getBlankCursor()
 
	def setDefaultOptions(self):
		self.options["diameter"]=21
		self.options["step"]=1
		self.options["pressuresize"]=1
		self.options["pressurebalance"]=100
 
	def getTool(self,window):
		tool=DrawingTool(self.options,window)
		tool.name=self.name
		return tool
 
	def setupTool(self,window):
		tool=self.getTool(window)
		# copy the foreground color
		tool.fgcolor=qtgui.QColor(window.master.fgcolor)
		tool.layerkey=window.curlayerkey
 
		# if there is a selection get a copy of it
		if window.selection:
			tool.clippath=qtgui.QPainterPath(window.clippath)
 
		return tool
 
	def runOptionsDialog(self,parent):
		dialog=qtgui.QDialog()
		dialog.ui=Ui_PencilOptionsDialog()
		dialog.ui.setupUi(dialog)
 
		dialog.ui.brushdiameter.setValue(self.options["diameter"])
		dialog.ui.pressurebalance.setValue(self.options["pressurebalance"])
		dialog.ui.stepsize.setValue(self.options["step"])
 
		dialog.exec_()
 
		if dialog.result():
			self.options["diameter"]=dialog.ui.brushdiameter.value()
			self.options["pressurebalance"]=dialog.ui.pressurebalance.value()
			self.options["step"]=dialog.ui.stepsize.value()
 
class PaintBrushToolDesc(PencilToolDesc):
	def __init__(self):
		AbstractToolDesc.__init__(self,"paintbrush")
 
	def setDefaultOptions(self):
		self.options["diameter"]=7
		self.options["step"]=1
		self.options["pressuresize"]=1
		self.options["blur"]=70
		self.options["pressurebalance"]=100
 
	def getTool(self,window):
		tool=PaintBrushTool(self.options,window)
		tool.name=self.name
		return tool
 
	def runOptionsDialog(self,parent):
		dialog=qtgui.QDialog()
		dialog.ui=Ui_BrushOptionsDialog()
		dialog.ui.setupUi(dialog)
 
		dialog.ui.brushdiameter.setValue(self.options["diameter"])
		dialog.ui.pressurebalance.setValue(self.options["pressurebalance"])
		dialog.ui.stepsize.setValue(self.options["step"])
		dialog.ui.blurslider.setValue(self.options["blur"])
 
		dialog.exec_()
 
		if dialog.result():
			self.options["diameter"]=dialog.ui.brushdiameter.value()
			self.options["pressurebalance"]=dialog.ui.pressurebalance.value()
			self.options["step"]=dialog.ui.stepsize.value()
			self.options["blur"]=dialog.ui.blurslider.value()
 
class EraserToolDesc(AbstractToolDesc):
	# describe actual tool
	class Tool(DrawingTool):
		def __init__(self,options,window):
			DrawingTool.__init__(self,options,window)
			self.compmode=qtgui.QPainter.CompositionMode_DestinationOut
 
		def getColorRGBA(self):
			return 0xFFFFFFFF
			#return self.fgcolor.rgba()
 
	# back to description stuff
	def __init__(self):
		AbstractToolDesc.__init__(self,"eraser")
 
	def setDefaultOptions(self):
		self.options["diameter"]=21
		self.options["step"]=1
		self.options["pressuresize"]=1
		self.options["pressurebalance"]=100
		self.options["blur"]=100
 
	def runOptionsDialog(self,parent):
		dialog=qtgui.QDialog()
		dialog.ui=Ui_EraserOptionsDialog()
		dialog.ui.setupUi(dialog)
 
		dialog.ui.eraserdiameter.setValue(self.options["diameter"])
		dialog.ui.stepsize.setValue(self.options["step"])
		dialog.ui.blurpercent.setValue(self.options["blur"])
 
		dialog.exec_()
 
		if dialog.result():
			self.options["diameter"]=dialog.ui.eraserdiameter.value()
			self.options["step"]=dialog.ui.stepsize.value()
			self.options["blur"]=dialog.ui.blurpercent.value()
 
	def getTool(self,window):
		tool=self.Tool(self.options,window)
		tool.name=self.name
		return tool
 
	def setupTool(self,window):
		tool=self.getTool(window)
		if window.selection:
			tool.clippath=qtgui.QPainterPath(window.clippath)
		tool.layerkey=window.curlayerkey
		return tool
 
# selection overlay information
class SelectionOverlay:
	def __init__(self,path,pen=None,brush=None):
		if not pen:
			pen=qtgui.QPen()
		self.pen=pen
 
		if not brush:
			brush=qtgui.QBrush()
		self.brush=brush
 
		self.path=path
 
# basic selection tool
class SelectionTool(AbstractTool):
	def __init__(self,options,window):
		AbstractTool.__init__(self,options,window)
 
	def updateOverlay(self,x,y):
		oldrect=None
		# calculate rectangle defined by the start and current
		left=min(x,self.startpoint[0])
		top=min(y,self.startpoint[1])
		width=max(x,self.startpoint[0])-left
		height=max(y,self.startpoint[1])-top
 
		if self.window.cursoroverlay:
			oldrect=self.window.cursoroverlay.path.boundingRect().toAlignedRect()
 
		overlay=qtgui.QPainterPath()
		overlay.addRect(left,top,width,height)
 
		# calculate area we need to refresh, it should be the union of rect to draw
		# next and the last one that was drawn
		self.window.cursoroverlay=SelectionOverlay(overlay)
		newrect=self.window.cursoroverlay.path.boundingRect().toAlignedRect()
		newrect.adjust(-1,-1,2,2)
		refreshregion=qtgui.QRegion(newrect)
 
		if oldrect:
			oldrect.adjust(-1,-1,2,2)
			refreshregion=refreshregion.unite(qtgui.QRegion(oldrect))
 
		self.window.view.updateView(refreshregion.boundingRect())
 
	def penDown(self,x,y,pressure=None):
		self.startpoint=(x,y)
		self.lastpoint=(x,y)
 
	def penUp(self,x,y,source=0):
		# just for simplicty the dirty region will be the old selection unioned
		# with the current overlay
		if len(self.window.selection)>0:
			srect=qtcore.QRect()
			for select in self.window.selection:
				srect=srect.united(select.boundingRect().toAlignedRect())
 
			srect.adjust(-1,-1,2,2)
			dirtyregion=qtgui.QRegion(srect)
		else:
			dirtyregion=qtgui.QRegion()
 
		# get modifier keys currently being held down
		modkeys=self.window.master.app.keyboardModifiers()
 
		# change selection according to current modifier keys
		if modkeys==qtcore.Qt.ShiftModifier:
			self.window.changeSelection(SelectionModTypes.add)
		elif modkeys==qtcore.Qt.ControlModifier:
			self.window.changeSelection(SelectionModTypes.subtract)
		elif modkeys==qtcore.Qt.ControlModifier|qtcore.Qt.ShiftModifier:
			self.window.changeSelection(SelectionModTypes.intersect)
		# if we don't recognize the modifier types just replace the selection
		else:
			self.window.changeSelection(SelectionModTypes.new)
 
		if self.window.cursoroverlay:
			srect=self.window.cursoroverlay.path.boundingRect().toAlignedRect()
			srect.adjust(-1,-1,2,2)
			dirtyregion=dirtyregion.unite(qtgui.QRegion(srect))
			self.window.cursoroverlay=None
 
		self.window.view.updateView(dirtyregion.boundingRect())
 
	# set overlay to display area that would be selected if user lifted up button
	def penMotion(self,x,y,pressure=None):
		if self.startpoint[0]==x or self.startpoint[1]==y:
			self.window.cursoroverlay=None
			return
 
		self.updateOverlay(x,y)
		self.lastpoint=(x,y)
 
# this is the most basic selection tool (rectangular)
class RectSelectionToolDesc(AbstractToolDesc):
	def __init__(self):
		AbstractToolDesc.__init__(self,"rectangle select")
	def setupTool(self,window):
		tool=self.getTool(window)
		return tool
 
	def getTool(self,window):
		tool=SelectionTool(self.options,window)
		tool.name=self.name
		return tool
 
# elipse selection tool
class ElipseSelectionToolDesc(AbstractToolDesc):
	def __init__(self):
		AbstractToolDesc.__init__(self,"elipse select")
	def setupTool(self,window):
		tool=self.getTool(window)
		return tool
 
	def getTool(self,window):
		return SelectionTool(self.options,window)
