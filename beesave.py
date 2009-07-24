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

# changed locations between versions
try:
	from PyQt4.QtCore import QXmlStreamWriter
except:
	from PyQt4.QtXml import QXmlStreamWriter

class PaletteXmlWriter:
	def __init__(self, output):
		self.out=QXmlStreamWriter(output)

	def logPalette(self,palettelist):
		if not palettelist:
			print_debug("Error, can't find list of colors to write out")
			return

		rows=len(palettelist)
		columns=len(palettelist[0])

		self.out.writeStartElement('beepalette')
		self.out.writeAttribute('rows',str(rows))
		self.out.writeAttribute('columns',str(columns))

		for row in palettelist:
			for swatch in row:
				self.out.writeStartElement('color')
				self.out.writeAttribute('r',str(swatch.color.red()))
				self.out.writeAttribute('g',str(swatch.color.green()))
				self.out.writeAttribute('b',str(swatch.color.blue()))

				self.out.writeEndElement()

		self.out.writeEndElement()
