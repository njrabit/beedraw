from base64 import b64decode
import time
from beeglobals import *
from beetypes import *
from beeutil import *
from sketchlog import SketchLogWriter

import PyQt4.QtCore as qtcore
import PyQt4.QtGui as qtgui
import PyQt4.QtXml as qtxml

# for some reason the location changed between versions
try:
	from PyQt4.QtXml import QXmlStreamReader
except:
	from PyQt4.QtCore import QXmlStreamReader

class XmlToQueueEventsConverter:
	"""  Represents a parser to to turn an incomming xml stream into drawing events
	"""
	def __init__(self,device,window,stepdelay,type=ThreadTypes.animation,id=0):
		self.xml=QXmlStreamReader()

		#turn off namespace processing
		self.xml.setNamespaceProcessing(False)

		if device:
			self.xml.setDevice(device)

		self.id=id
		self.window=window
		self.type=type
		self.inrawevent=False
		self.stepdelay=stepdelay
		self.keymap={}

		if type==ThreadTypes.animation:
			self.layertype=LayerTypes.animation
		else:
			self.layertype=LayerTypes.network

	def translateKey(self,key):
		""" only needs to do something in animation threads
		"""
		return key

	def addKeyTranslation(self,key,dockey):
		""" only needs to do something in animation threads
		"""
		pass

	def read(self):
		""" Read tokens in the xml document until the end or until an error occurs, this function serves as a switchboard to call other functions based on the type of token
		"""
		while not self.xml.atEnd():
			tokentype=self.xml.readNext()
			if tokentype==QXmlStreamReader.StartElement:
				self.processStartElement()
			elif tokentype==QXmlStreamReader.EndElement:
				self.processEndElement()
			elif tokentype==QXmlStreamReader.Characters:
				self.processCharacterData()

		# if it's an error that might actually be a problem then print it out
		if self.xml.hasError() and self.xml.error() != QXmlStreamReader.PrematureEndOfDocumentError:
				print_debug("error while parsing XML: %s" % self.xml.errorString())

		return self.xml.error()

	def processStartElement(self):
		""" Handle any type of starting XML tag and turn it into a drawing event if needed
		"""
		type=self.type
		name=self.xml.name()
		attrs=self.xml.attributes()

		if name == 'createdoc':
			(width,ok)=attrs.value('width').toString().toInt()
			(height,ok)=attrs.value('height').toString().toInt()
			self.window.addSetCanvasSizeRequestToQueue(width,height,type)


		elif name == 'addlayer':
			if self.type==ThreadTypes.server:
				# create our own key data in this case
				key=self.window.nextLayerKey()
			else:
				(key,ok)=attrs.value("key").toString().toInt()

			(pos,ok)=attrs.value("position").toString().toInt()

			# if this is the server don't trust the client to give the right ID, insthead pull it from the ID given to this thread
			if self.type==ThreadTypes.server:
				owner=self.id
			# otherwise trust the ID in the message
			else:
				(owner,ok)=attrs.value("owner").toString().toInt()

			if self.type!=ThreadTypes.animation:
				dockey=key
			# if it's an animation I need to map the key to a local one
			else:
				dockey=self.window.nextLayerKey()

			self.addKeyTranslation(key,dockey)

			self.window.addInsertLayerEventToQueue(pos,dockey,self.type,owner=owner)

		elif name == 'sublayer':
			(key,ok)=attrs.value("index").toString().toInt()
			self.window.addRemoveLayerRequestToQueue(key,type)

		elif name == 'movelayer':
			(change,ok)=attrs.value("change").toString().toInt()
			(index,ok)=attrs.value("index").toString().toInt()
			if change==1:
				self.window.addLayerUpToQueue(index,type)
			else:
				self.window.addLayerDownToQueue(index,type)

		elif name == 'layeralpha':
			(key,ok)=attrs.value("key").toString().toInt()
			(opacity,ok)=attrs.value("alpha").toString().toFloat()
			self.window.addOpacityChangeToQueue(key,opacity,type)

		elif name == 'layermode':
			time.sleep(self.stepdelay)
			(index,ok)=attrs.value('index').toString().toInt()
			mode=BlendTranslations.intToMode(attrs.value('mode').toString().toInt())
			self.window.addBlendModeChangeToQueue(self.translateKey(index),mode,type)

		elif name == 'undo':
			(owner,ok)=attrs.value('owner').toString().toInt()
			self.window.addUndoToQueue(owner,type)

		elif name == 'redo':
			(owner,ok)=attrs.value('owner').toString().toInt()
			self.window.addRedoToQueue(owner,type)

		elif name == 'toolevent':
			self.strokestart=False
			toolname="%s" % attrs.value('name').toString()
			(layerkey,ok)=attrs.value('layerkey').toString().toInt()
			(owner,ok)=attrs.value('owner').toString().toInt()
			self.curlayer=self.translateKey(layerkey)

			tool=self.window.master.getToolClassByName(toolname.strip())

			#print error if we can't find the tool
			if tool == None:
				print_debug("Error, couldn't find tool with name: %s" % toolname)
				return

			self.curtool=tool.setupTool(self.window,self.curlayer)
			self.curtool.layerkey=self.curlayer
			self.curtool.owner=owner

		elif name == 'fgcolor':
			(r,ok)=attrs.value('r').toString().toInt()
			(g,ok)=attrs.value('g').toString().toInt()
			(b,ok)=attrs.value('b').toString().toInt()
			self.curtool.fgcolor=qtgui.QColor(r,g,b)
		elif name == 'bgcolor':
			(r,ok)=attrs.value('r').toString().toInt()
			(g,ok)=attrs.value('g').toString().toInt()
			(b,ok)=attrs.value('b').toString().toInt()
			self.curtool.bgcolor=qtgui.QColor(r,g,b)
		elif name == 'clippath':
			self.clippoints=[]
		elif name == 'polypoint':
			(x,ok)=attrs.value('x').toString().toInt()
			(y,ok)=attrs.value('y').toString().toInt()
			self.clippoints.append(qtcore.QPointF(x,y))
		elif name == 'toolparam':
			(value,ok)=attrs.value('value').toString().toInt()
			self.curtool.setOption("%s" % attrs.value('name').toString(),value)
		elif name == 'rawevent':
			self.inrawevent=True
			self.raweventargs=[]
			(self.x,ok)=attrs.value('x').toString().toInt()
			(self.y,ok)=attrs.value('y').toString().toInt()
			(layerkey,ok)=attrs.value('layerkey').toString().toInt()
			self.layerkey=self.translateKey(layerkey)
			self.rawstring=self.xml.readElementText()

			data=qtcore.QByteArray()
			data=data.append(self.rawstring)
			data=qtcore.QByteArray.fromBase64(data)
			data=qtcore.qUncompress(data)

			image=qtgui.QImage()
			image.loadFromData(data,"PNG")

			self.window.addRawEventToQueue(self.layerkey,image,self.x,self.y,None,type)

		elif name == 'point':
			time.sleep(self.stepdelay)
			(x,ok)=attrs.value('x').toString().toFloat()
			(y,ok)=attrs.value('y').toString().toFloat()
			self.lastx=x
			self.lasty=y
			(pressure,ok)=attrs.value('pressure').toString().toFloat()
			if self.strokestart == False:
				self.window.addPenDownToQueue(x,y,pressure,self.curlayer,self.curtool,type)
				self.strokestart=True
			else:
				self.window.addPenMotionToQueue(x,y,pressure,self.curlayer,type)
		elif name == 'resyncrequest':
			self.window.addResyncRequestToQueue(self.id)
		elif name == 'resyncstart':
			(width,ok)=attrs.value('width').toString().toInt()
			(height,ok)=attrs.value('height').toString().toInt()
			(remoteid,ok)=attrs.value('remoteid').toString().toInt()
			self.window.addResyncStartToQueue(remoteid,width,height)

		elif name == 'giveuplayer':
			(layerkey,ok)=attrs.value('key').toString().toInt()

			# make sure command is legit from this source
			layer=self.window.getLayerForKey(layerkey)
			proplock=qtcore.QReadLocker(layer.propertieslock)
			if layer.owner!=self.id:
				print_debug("ERROR: got bad give up layer command from client: %d for layer key: %d" % (self.id,layerkey))
			else:
				self.window.addGiveUpLayerToQueue(layerkey,self.id,type)

		elif name == 'changelayerowner':
			(layerkey,ok)=attrs.value('key').toString().toInt()
			(owner,ok)=attrs.value('owner').toString().toInt()
			self.window.addChangeLayerOwnerToQueue(layerkey,owner,type)

		elif name == 'layerrequest':
			(layerkey,ok)=attrs.value('key').toString().toInt()
			self.window.addLayerRequestToQueue(layerkey,self.id,type)

		elif name == 'fatalerror':
			errormessage="%s" % attrs.value('errormessage').toString()
			self.window.addFatalErrorNotificationToQueue(0,errormessage,type)

		elif name == 'event':
			pass

		elif name == 'sketchlog':
			print_debug("DEBUG: got document start tag")

		else:
			print_debug("WARNING: Don't know how to handle tag: %s" % name.toString())

	def processEndElement(self):
		name=self.xml.name()
		if name == 'toolevent':
			print_debug("Adding end tool event to queue on layer %d" % self.curlayer)
			self.window.addPenUpToQueue(self.lastx,self.lasty,self.curlayer,type)
			self.curtool=None
		elif name == 'rawevent':
			return
			self.inrawevent=False

			# convert data out of base 64 then uncompress
			data=qtcore.QByteArray()
			data=data.append(self.rawstring)
			data=qtcore.QByteArray.fromBase64(data)
			data=qtcore.qUncompress(data)

			image=qtgui.QImage()
			image.loadFromData(data,"PNG")

			self.window.addRawEventToQueue(self.layerkey,image,self.x,self.y,None,type)
		elif name == 'clippath':
			poly=qtgui.QPolygonF(self.clippoints)
			self.curtool.clippath=qtgui.QPainterPath()
			self.curtool.clippath.addPolygon(poly)

	def processCharacterData(self):
		pass

class AnimationEventsConverter(XmlToQueueEventsConverter):
	def translateKey(self,key):
		""" Translate key from local id to current window ID
		"""
		return self.keymap[key]

	def addKeyTranslation(self,key,dockey):
		""" add in key translation, since this is an animation thread
		"""
		self.keymap[key]=key

# thread for playing local animations out of a file
class PlayBackAnimation (qtcore.QThread):
	def __init__(self,window,filename,stepdelay=.05):
	#def __init__(self,window,filename,stepdelay=0):
		qtcore.QThread.__init__(self)
		self.window=window
		self.filename=filename
		self.stepdelay=stepdelay

	def run(self):
		f=qtcore.QFile(self.filename)
		f.open(qtcore.QIODevice.ReadOnly)
		parser=AnimationEventsConverter(f,self.window,self.stepdelay)
		parser.read()
		f.close()

class NetworkListenerThread (qtcore.QThread):
	def __init__(self,window,socket):
		qtcore.QThread.__init__(self)
		self.window=window
		self.socket=socket
		self.disconnectmessage="Unknown reason for disconnecting"

		# during the destructor this seems to forget about qtnet so keep this around to check aginst it then
		self.connectedstate=qtnet.QAbstractSocket.ConnectedState

	def run(self):
		# if we failed to get a socket then destroy the window and exit
		if not self.socket:
			print_debug("failed to get socket connection")
			self.window.close()
			return

		# get ready for next contact from server
		self.parser=XmlToQueueEventsConverter(None,self.window,0,type=ThreadTypes.network)
		#qtcore.QObject.connect(self.socket, qtcore.SIGNAL("readyRead()"), self.readyRead)
		#qtcore.QObject.connect(self.socket, qtcore.SIGNAL("disconnected()"), self.disconnected)

		sendingthread=NetworkWriterThread(self.window,self.socket)
		self.window.sendingthread=sendingthread
		print_debug("created thread, about to start sending thread")
		sendingthread.start()

		# enter read loop, read till socket closes
		while 1:
			# make sure we've waited long enough and if something goes wrong just disconnect
			print_debug("Ready to read from server")
			if not self.socket.waitForReadyRead(-1):
				print_debug("Error due to closed remote connection")
				self.disconnectmessage="Server has closed connection"
				break

			error=self.readyRead()

			# if there was an error then disconnect
			if error:
				self.disconnectmessage="Error in XML stream"
				self.window.addExitEventToQueue(source=ThreadTypes.network)
				break

		# this should be run when the socket is disconnected and the buffer is empty
		self.window.disconnected(self.disconnectmessage)

	def readyRead(self):
		readybytes=self.socket.bytesAvailable()

		if readybytes>0:
			data=self.socket.read(readybytes)
			print_debug("got animation data from socket: %s" % qtcore.QString(data))

			self.parser.xml.addData(data)
			error=self.parser.read()

			self.socket.waitForBytesWritten()

			# if there was an error and it wasn't a premature end of document error then we can't recover and need to disconnect
			if error!=QXmlStreamReader.PrematureEndOfDocumentError and error!=QXmlStreamReader.NoError:
				return error

			return None
				
class NetworkWriterThread (qtcore.QThread):
	def __init__(self,window,socket):
		qtcore.QThread.__init__(self)
		self.socket=socket
		self.gen=SketchLogWriter(self.socket)

		self.window=window
		self.queue=window.remoteoutputqueue

	def run(self):
		while 1:
			if self.socket.state()==qtnet.QAbstractSocket.UnconnectedState:
				break

			print_debug("attempting to get item from queue")
			command=self.queue.get()
			print_debug("Network Writer Thread got command from queue: %s" % str(command))
			if command[0]==DrawingCommandTypes.quit:
				return

			self.gen.logCommand(command)
			self.socket.flush()
			self.socket.waitForBytesWritten(-1)
			print_debug("finished flushing socket")
