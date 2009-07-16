import PyQt4.QtCore as qtcore
import PyQt4.QtXml as qtxml
from beetypes import *
from beeutil import *

# changed locations between versions
try:
	from PyQt4.QtCore import QXmlStreamWriter
except:
	from PyQt4.QtXml import QXmlStreamWriter

class SketchLogWriter:
	def __init__(self, output):
		self.output=output

		self.log=QXmlStreamWriter(output)

		# mutex so we don't write to file from mulitple sources at once
		self.mutex=qtcore.QMutex()

		self.log.writeStartDocument()

		# add parent element
		self.log.writeStartElement('sketchlog')

	def logCommand(self,command,owner=0):
		self.startEvent(owner)
		type=command[0]

		if type==DrawingCommandTypes.history:
			self.logHistoryCommand(command)

		elif type==DrawingCommandTypes.layer:
			self.logLayerCommand(command)

		elif type==DrawingCommandTypes.alllayer:
			self.logAllLayerCommand(command)

		elif type==DrawingCommandTypes.networkcontrol:
			self.logNetworkControl(command)

		self.endEvent()

		# flush right away so network sessions won't have a delay here
		bytestowrite=self.output.bytesToWrite()
		while self.output.bytesToWrite()>0:
			self.output.flush()
			bytestowrite=self.output.bytesToWrite()
		self.output.flush()
		self.output.waitForBytesWritten(-1)
		print_debug("finished writing output")

	def logHistoryCommand(self,command):
		subtype=command[1]
		if subtype==HistoryCommandTypes.undo:
			self.log.writeStartElement('undo')
			self.log.writeAttribute('owner',str(command[2]))

		elif subtype==HistoryCommandTypes.redo:
			self.log.writeStartElement('redo')
			self.log.writeAttribute('owner',str(command[2]))

	def logLayerCommand(self,command):
		subtype=command[1]
		layer=command[2]
		if subtype==LayerCommandTypes.alpha:
			self.logLayerAlphaChange(layer,command[3])

		elif subtype==LayerCommandTypes.mode:
			self.logLayerModeChange(layer,command[3])

		elif subtype==LayerCommandTypes.rawevent:
			self.logRawEvent(command[3],command[4],layer,command[5],command[6])

		elif subtype==LayerCommandTypes.tool:
			self.logToolEvent(layer,command[3])

		else:
			print "WARNING: don't know how to log layer command type:", subtype

	def logAllLayerCommand(self,command):
		subtype=command[1]
		if subtype==AllLayerCommandTypes.resize:
			pass

		elif subtype==AllLayerCommandTypes.scale:
			pass

		elif subtype==AllLayerCommandTypes.layerup:
			self.logLayerMove(command[2],1)

		elif subtype==AllLayerCommandTypes.layerdown:
			self.logLayerMove(command[2],-1)

		elif subtype==AllLayerCommandTypes.deletelayer:
			self.logLayerSub(command[2])

		elif subtype==AllLayerCommandTypes.insertlayer:
			self.logLayerAdd(command[3], command[2], command[4])

	def logNetworkControl(self,command):
		subtype=command[1]
		if subtype==NetworkControlCommandTypes.resyncrequest:
			self.logResyncRequest()

		elif subtype==NetworkControlCommandTypes.resyncstart:
			self.logResyncStart(command[2],command[3],command[4])

		elif subtype==NetworkControlCommandTypes.giveuplayer:
			self.logGiveUpLayer(command[3])

		elif subtype==NetworkControlCommandTypes.layerowner:
			self.logLayerOwnerChange(command[2],command[3])

		elif subtype==NetworkControlCommandTypes.requestlayer:
			self.logLayerRequest(command[3])

	def startEvent(self,owner):
		self.log.writeStartElement('event')

	def endEvent(self):
		self.log.writeEndElement()

	def logLayerAdd(self, position, key, owner=0):
		lock=qtcore.QMutexLocker(self.mutex)

		# start addlayer event
		self.log.writeStartElement('addlayer')
		self.log.writeAttribute('position',str(position))
		self.log.writeAttribute('key',str(key))
		self.log.writeAttribute('owner',str(owner))

		# end addlayer event
		self.log.writeEndElement()

	def logLayerSub(self, index):
		lock=qtcore.QMutexLocker(self.mutex)

		# start sublayer event
		self.log.writeStartElement('sublayer')
		self.log.writeAttribute('index',str(index))

		# end sublayer event
		self.log.writeEndElement()

	def logLayerModeChange(self, index, mode):
		lock=qtcore.QMutexLocker(self.mutex)

		self.log.writeStartElement('layermode')
		self.log.writeAttribute('index',str(index))
		self.log.writeAttribute('mode',str(mode))

		# end sublayer event
		self.log.writeEndElement()

	def logLayerAlphaChange(self, key, alpha):
		lock=qtcore.QMutexLocker(self.mutex)

		self.log.writeStartElement('layeralpha')
		self.log.writeAttribute('key',str(key))
		self.log.writeAttribute('alpha',str(alpha))

		# end sublayer event
		self.log.writeEndElement()

	# log a move with index and number indicating change (ie -1 for 1 down)
	def logLayerMove(self, index, change):
		lock=qtcore.QMutexLocker(self.mutex)

		# start sublayer event
		self.log.writeStartElement('movelayer')
		self.log.writeAttribute('index',str(index))
		self.log.writeAttribute('change',str(change))

		# end sublayer event
		self.log.writeEndElement()

	def logToolEvent(self,layerkey,tool):
		lock=qtcore.QMutexLocker(self.mutex)

		points=tool.pointshistory

		# start tool event
		self.log.writeStartElement('toolevent')
		self.log.writeAttribute('name',tool.name)
		self.log.writeAttribute('layerkey',str(layerkey))

		if tool.fgcolor:
			self.log.writeStartElement('fgcolor')
			self.log.writeAttribute('r',str(tool.fgcolor.red()))
			self.log.writeAttribute('g',str(tool.fgcolor.green()))
			self.log.writeAttribute('b',str(tool.fgcolor.blue()))
			self.log.writeEndElement()

		if tool.bgcolor:
			self.log.writeStartElement('bgcolor')
			self.log.writeAttribute('r',str(tool.bgcolor.red()))
			self.log.writeAttribute('g',str(tool.bgcolor.green()))
			self.log.writeAttribute('b',str(tool.bgcolor.blue()))
			self.log.writeEndElement()

		if tool.clippath:
			poly=tool.clippath.toFillPolygon().toPolygon()
			self.log.writeStartElement('clippath')

			for p in range(poly.size()):
				self.log.writeStartElement('polypoint')
				self.log.writeAttribute('x',str(poly.at(p).x()))
				self.log.writeAttribute('y',str(poly.at(p).y()))
				self.log.writeEndElement()

			# end clip path
			self.log.writeEndElement()

		# add tool params to log
		for key in tool.options.keys():
			self.log.writeStartElement('toolparam')
			self.log.writeAttribute('name', key )
			self.log.writeAttribute('value',str(tool.options[key]))
			self.log.writeEndElement()

		# add points to log
		for point in points:
			self.log.writeStartElement('point')
			self.log.writeAttribute('x',str(point[0]))
			self.log.writeAttribute('y',str(point[1]))
			self.log.writeAttribute('pressure',str(point[2]))
			self.log.writeEndElement()
			
		# end tool event
		self.log.writeEndElement()

	def logCreateDocument(self,width,height):
		lock=qtcore.QMutexLocker(self.mutex)

		self.log.writeStartElement('createdoc')
		self.log.writeAttribute('width',str(width))
		self.log.writeAttribute('height',str(height))

		# end createdoc event
		self.log.writeEndElement()

	def logRawEvent(self,x,y,layerkey,image,path=None):
		lock=qtcore.QMutexLocker(self.mutex)

		x=str(x)
		y=str(y)
		layerkey=str(layerkey)

		self.log.writeStartElement('rawevent')
		self.log.writeAttribute('x',x)
		self.log.writeAttribute('y',y)
		self.log.writeAttribute('layerkey',layerkey)

		# if there is a clip path for this raw event
		if path:
			poly=path.toFillPolygon().toPolygon()
			self.log.writeStartElement('clippath')

			for p in range(poly.size()):
				self.log.writeStartElement('polypoint')
				self.log.writeAttribute('x',str(poly.at(p).x()))
				self.log.writeAttribute('y',str(poly.at(p).y()))
				self.log.writeEndElement()

			# end clip path
			self.log.writeEndElement()

		bytearray=qtcore.QByteArray()
		buf=qtcore.QBuffer(bytearray)
		buf.open(qtcore.QIODevice.WriteOnly)
		image.save(buf,"PNG")

		# compress then convert to base 64 so it can be printed in ascii
		bytearray=qtcore.qCompress(bytearray)
		bytearray=bytearray.toBase64()

		rawstring='%s' % bytearray

		self.log.writeCharacters(rawstring)
		self.log.writeEndElement()

	def logResyncRequest(self):
		print_debug("DEBUG: logging resync")
		lock=qtcore.QMutexLocker(self.mutex)

		self.log.writeStartElement('resyncrequest')
		self.log.writeEndElement()

	def logResyncStart(self,width,height,remoteid):
		lock=qtcore.QMutexLocker(self.mutex)

		self.log.writeStartElement('resyncstart')
		self.log.writeAttribute('width',str(width))
		self.log.writeAttribute('height',str(height))
		self.log.writeAttribute('remoteid',str(remoteid))
		self.log.writeEndElement()

	def logGiveUpLayer(self,key):
		self.log.writeStartElement('giveuplayer')
		self.log.writeAttribute('key',str(key))
		self.log.writeEndElement()

	def logLayerOwnerChange(self,owner,key):
		self.log.writeStartElement('changelayerowner')
		self.log.writeAttribute('owner',str(owner))
		self.log.writeAttribute('key',str(key))
		self.log.writeEndElement()

	def logLayerRequest(self,key):
		self.log.writeStartElement('layerrequest')
		self.log.writeAttribute('key',str(key))
		self.log.writeEndElement()

	def endLog(self):
		lock=qtcore.QMutexLocker(self.mutex)
		self.log.writeEndElement()
		self.output.close()
