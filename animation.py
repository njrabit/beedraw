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
		""" Translate key from local id to current window ID this is only needed in animation threads, in other thread types just return what was passed
		"""
		if self.type!=ThreadTypes.animation:
			return key
		return self.keymap[key]

	def addKeyTranslation(self,key,dockey):
		if self.type!=ThreadTypes.animation:
			self.keymap[key]=key
		else:
			self.keymap[key]=dockey

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
				print "error while parsing XML:", self.xml.errorString()

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

			# print error if we can't find the tool
			if tool == None:
				print "Error, couldn't find tool with name: ", toolname
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
			#print "found point element for", x, y
			self.lastx=x
			self.lasty=y
			(pressure,ok)=attrs.value('pressure').toString().toFloat()
			if self.strokestart == False:
				#print "Adding start tool event to queue on layer", self.curlayer
				self.window.addPenDownToQueue(x,y,pressure,self.curlayer,self.curtool,type)
				self.strokestart=True
			else:
				#print "Adding tool motion event to queue on layer", self.curlayer
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
				print "ERROR: got bad give up layer command from client:", self.id, "for layer key:", layerkey
			else:
				self.window.addGiveUpLayerToQueue(layerkey,self.id,type)

		elif name == 'changelayerowner':
			(layerkey,ok)=attrs.value('key').toString().toInt()
			(owner,ok)=attrs.value('owner').toString().toInt()
			self.window.addChangeLayerOwnerToQueue(layerkey,owner,type)

		elif name == 'layerrequest':
			(layerkey,ok)=attrs.value('key').toString().toInt()
			self.window.addLayerRequestToQueue(layerkey,self.id,type)

		elif name == 'event':
			pass

		elif name == 'sketchlog':
			print_debug("DEBUG: got document start tag")

		else:
			print "WARNING: Don't know how to handle tag: %s" % name.toString()

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

# thread for playing local animations out of a file
class PlayBackAnimation (qtcore.QThread):
	#def __init__(self,window,filename,stepdelay=.05):
	def __init__(self,window,filename,stepdelay=0):
		qtcore.QThread.__init__(self)
		self.window=window
		self.filename=filename
		self.stepdelay=stepdelay

	def run(self):
		f=qtcore.QFile(self.filename)
		f.open(qtcore.QIODevice.ReadOnly)
		parser=XmlToQueueEventsConverter(f,self.window,self.stepdelay)
		parser.read()
		f.close()

class NetworkListenerThread (qtcore.QThread):
	def __init__(self,window,username,password,host,port):
		qtcore.QThread.__init__(self)
		self.window=window
		self.username=username
		self.password=password
		self.host=host
		self.port=port

		# during the destructor this seems to forget about qtnet so keep this around to check aginst it then
		self.connectedstate=qtnet.QAbstractSocket.ConnectedState

	# connect to host and authticate
	def getServerConnection(self,username,password,host,port):
		socket=qtnet.QTcpSocket()

		socket.connectToHost(host,port)
		print_debug("waiting for socket connection:")
		connected=socket.waitForConnected()
		print_debug("finished waiting for socket connection")

		# return error if we couldn't get a connection after 30 seconds
		if not connected:
			qtgui.QMessageBox.warning(None,"Failed to connect to server",socket.errorString())
			#qtgui.QMessageBox(qtgui.QMessageBox.Information,"Connection Error","Failed to connect to server",qtgui.QMessageBox.Ok).exec_()
			return None

		authrequest=qtcore.QByteArray()
		authrequest=authrequest.append("%s\n%s\n%s\n" % (username,password,PROTOCOL_VERSION))
		# send authtication info
		socket.write(authrequest)

		responsestring=qtcore.QString()

		# wait for response
		while responsestring.count('\n')<2 and len(responsestring)<500:
			if socket.waitForReadyRead(-1):
				data=socket.read(500)
				print "got authentication answer: %s" % qtcore.QString(data)
				responsestring.append(data)

			# if error exit
			else:
				qtgui.QMessageBox.warning(None,"Connection Error","server dropped connection")
				return None

		# if we get here we have a response that probably wasn't a disconnect
		responselist=responsestring.split('\n')
		if len(responselist)>1:
			answer="%s" % responselist[0]
			message="%s" % responselist[1]
		else:
			answer="Failure"
			message="Unknown Status"

		if answer=="Success":
			return socket

		socket.close()
		qtgui.QMessageBox.warning(None,"Server Refused Connection",message)
		return None

	def run(self):
		print_debug("attempting to get socket:")
		# setup initial connection
		self.socket=self.getServerConnection(self.username,self.password,self.host,self.port)

		# if we failed to get a socket then destroy the window and exit
		if not self.socket:
			print_debug("failed to get socket connection")
			self.window.close()
			return

		# get ready for next contact from server
		self.parser=XmlToQueueEventsConverter(None,self.window,0,type=ThreadTypes.network)
		#qtcore.QObject.connect(self.socket, qtcore.SIGNAL("readyRead()"), self.readyRead)
		#qtcore.QObject.connect(self.socket, qtcore.SIGNAL("disconnected()"), self.disconnected)

		print_debug("got socket connection")
		sendingthread=NetworkWriterThread(self.window,self.socket)
		self.window.sendingthread=sendingthread
		print_debug("created thread, about to start sending thread")
		sendingthread.start()

		# enter read loop, read till socket gets closed
		while 1:
			# make sure we've waited long enough and if something goes wrong just disconnect
			if not self.socket.waitForReadyRead(-1):
				break
			self.readyRead()

		# after the socket has closed make sure there isn't more to read
		self.readyRead()

		# this should be run when the socket is disconnected and the buffer is empty
		self.disconnected()

	# what to do when a disconnected signal is recieved
	def disconnected(self):
		print_debug("disconnected from server")
		self.window.switchAllLayersToLocal()
		self.exit()
		return

	def readyRead(self):
		readybytes=self.socket.bytesAvailable()

		if readybytes>0:
			data=self.socket.read(readybytes)
			print_debug("got animation data from socket: %s" % qtcore.QString(data))

			self.parser.xml.addData(data)
			self.parser.read()

			self.socket.waitForBytesWritten()

class NetworkWriterThread (qtcore.QThread):
	def __init__(self,window,socket):
		qtcore.QThread.__init__(self)
		self.socket=socket
		self.gen=SketchLogWriter(self.socket)

		self.window=window
		self.queue=window.remoteoutputqueue

	def run(self):
		while 1:
			print_debug("attempting to get item from queue")
			command=self.queue.get()
			print_debug("Network Writer Thread got command from queue: %s" % str(command))
			if command[0]==DrawingCommandTypes.quit:
				return
			self.gen.logCommand(command)
			self.socket.flush()
			self.socket.waitForBytesWritten(-1)
