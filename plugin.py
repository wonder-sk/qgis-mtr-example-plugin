"""
Example QGIS plugin (version >= 2.4) that shows how plugin layers can handle multi-threaded rendering.
In some cases there is a need that some code related to rendering is run in the GUI thread. This is the
case also for QWebPage class which does not work in non-GUI threads. Because the multi-threaded
rendering always runs rendering in worker threads, it is necessary to employ some means of communication
between GUI thread and worker threads. Fortunately Qt makes this task quite easy with queued connections
between QObject instances.

It is absolutely necessary to understand how QObject instances work together with threads, especially
about per-thread event loops and signals/slots across threads:
http://qt-project.org/doc/qt-4.8/threads-qobject.html

Copyright 2014 Martin Dobias

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtWebKit import *

from qgis.core import *
import os.path
import sys


class MtrExampleController(QObject):
    """
    Helper class that deals with QWebPage.
    The object lives in GUI thread, its request() slot is asynchronously called from worker thread.
    """

    # signal that reports to the worker thread that the image is ready
    finished = pyqtSignal()

    def __init__(self, parent):
        QObject.__init__(self, parent)

        self.viewportSize = QSize(400, 400)
        self.img = QImage(self.viewportSize, QImage.Format_ARGB32)

        self.page = QWebPage(self)
        self.page.setViewportSize(self.viewportSize)
        self.page.loadFinished.connect(self.pageFinished)

    @pyqtSlot()
    def request(self):
        sys.stderr.write("[GUI THREAD] Processing request\n")
        self.cancelled = False
        #url = QUrl("http://qgis.org/")
        url = QUrl(os.path.join(os.path.dirname(__file__), "testpage.html"))
        self.page.mainFrame().load(url)

    def pageFinished(self):
        sys.stderr.write("[GUI THREAD] Request finished\n")
        if not self.cancelled:
            painter = QPainter(self.img)
            self.page.mainFrame().render(painter)
            painter.end()
        else:
            self.img.fill(Qt.gray)

        self.finished.emit()


class MtrExampleRenderer(QgsMapLayerRenderer):
    def __init__(self, layer, context):
        """ Initialize the object. This function is still run in the GUI thread.
            Should refrain from doing any heavy work.
        """
        QgsMapLayerRenderer.__init__(self, layer.id())
        self.context = context
        self.controller = MtrExampleController(None)
        self.loop = None

    def render(self):
        """ do the rendering. This function is called in the worker thread """

        sys.stderr.write("[WORKER THREAD] Calling request() asynchronously\n")
        QMetaObject.invokeMethod(self.controller, "request")

        # setup a timer that checks whether the rendering has not been stopped in the meanwhile
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(self.onTimeout)
        timer.start()

        sys.stderr.write("[WORKER THREAD] Waiting for the async request to complete\n")
        self.loop = QEventLoop()
        self.controller.finished.connect(self.loop.exit)
        self.loop.exec_()

        sys.stderr.write("[WORKER THREAD] Async request finished\n")

        painter = self.context.painter()
        painter.drawImage(0, 0, self.controller.img)
        return True

    def onTimeout(self):
        """ periodically check whether the rendering should not be stopped """
        if self.context.renderingStopped():
            sys.stderr.write("[WORKER THREAD] Cancelling rendering\n")
            self.loop.exit()


class MtrExamplePluginLayer(QgsPluginLayer):

    LAYER_TYPE = "MtrExample"

    def __init__(self):
        QgsPluginLayer.__init__(self, MtrExamplePluginLayer.LAYER_TYPE, "MTR Example Layer")
        self.setValid(True)

    def createMapRenderer(self, context):
        return MtrExampleRenderer(self, context)


class MtrExamplePluginLayerType(QgsPluginLayerType):

    def __init__(self):
        QgsPluginLayerType.__init__(self, MtrExamplePluginLayer.LAYER_TYPE)

    def createLayer(self):
        return MtrExamplePluginLayer()

    def showLayerProperties(self, layer):
        return False


class MtrExamplePlugin:
    def __init__(self, iface):
        self.iface = iface

    def initGui(self):

        # register plugin layer type
        self.lt = MtrExamplePluginLayerType()
        QgsPluginLayerRegistry.instance().addPluginLayerType(self.lt)

        QObject.connect(self.iface, SIGNAL("newProjectCreated()"), self.newProject)

    def newProject(self):
        # add one sample layer
        self.layer = MtrExamplePluginLayer()
        assert(self.layer.isValid())
        QgsMapLayerRegistry.instance().addMapLayer(self.layer)

    def unload(self):

        # unregister plugin layer type
        QgsPluginLayerRegistry.instance().removePluginLayerType(MtrExamplePluginLayer.LAYER_TYPE)
