import PyQt4.QtCore as qtcore

# Global variables
fileformatversion=1

# custom event types
class BeeCustomEventTypes:
	refreshlayerslist = qtcore.QEvent.User

# custom enumerated types
class DrawingCommandTypes:
	quit, nonlayer, layer, alllayer, networkcontrol = range(5)

# events that may effect one or more layers
class NonLayerCommandTypes:
	undo, redo = range(2)

# events that effect only one layer
class LayerCommandTypes:
	alpha, mode, pendown, penmotion, penup, rawevent, tool = range(7)

# events that effect the list of layers, all layers or layer ownership
class AllLayerCommandTypes:
	scale, resize, layerup, layerdown, deletelayer, insertlayer, deleteall, releaselayer, layerownership = range(9)

# commands that are only used to communicate when in a network session
class NetworkControlCommandTypes:
	""" Represents types of network control commands"""
	resyncrequest, resyncstart, resyncend = range(3)

class LayerTypes:
	""" Represents types of layers:
				user: layer that can be drawn on by the user
        animation: layer that is being drawn on by a local process reading it out of a file
        network: layer in a network session that the user cannot draw on
	"""
	user, animation, network = range(3)

class WindowTypes:
	""" Represents types of windows:
        singleuser: The window is not connected to any processes that are reading things out of a file or from the network
        animation: The window has at least some layers that are reading events out of a file
        networkclient: The window is connected to a server in a network session
        standaloneserver: The window being used to keep the master internal state for a network session
        integratedserver: A window running as both a client and keeping track of server state (Note that this is not supported yet and may never be
	"""
	singleuser, animation, networkclient, integratedserver, standaloneserver = range(5)

class ThreadTypes:
	user, animation, network, server = range(4)

# types of ways to modify the current selection
class SelectionModTypes:
	clear, new, intersect, add, subtract = range(5)

# types of brush shapes
class BrushShapes:
	ellipse = range(1)

# types of stamp mode
class DrawingToolStampMode:
	darkest, overlay = range(2)

# types of applications
class BeeAppType:
	server, daemon, client = range(3)
