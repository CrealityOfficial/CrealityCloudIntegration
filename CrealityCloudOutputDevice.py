import os
from . CrealityCloudUtils import CrealityCloudUtils
from PyQt5.QtCore import QObject
from PyQt5.QtGui import *
from PyQt5.QtNetwork import *
from PyQt5.QtQml import *
# from PyQt5.QtQuick import (QQuickView)

from UM.Application import Application
from UM.Logger import Logger
from UM.Mesh.MeshWriter import MeshWriter
from UM.FileHandler.WriteFileJob import WriteFileJob
from UM.Message import Message
from UM.PluginRegistry import PluginRegistry
from UM.OutputDevice.OutputDevice import OutputDevice
from UM.OutputDevice import OutputDeviceError
from UM.i18n import i18nCatalog
catalog = i18nCatalog("uranium")


class CrealityCloudOutputDevice(OutputDevice):
    def __init__(self, pluginId: str):
        super().__init__("crealitycloud")

        self._pluginId = pluginId
        self.setName(catalog.i18nc("@item:inmenu", "Local File"))
        self.setShortDescription(catalog.i18nc("@action:button Preceded by 'Ready to'.", "Upload to Creality Cloud"))
        self.setDescription(catalog.i18nc(
            "@action:button Preceded by 'Ready to'.", "Upload to Creality Cloud"))
        self.setIconName("upload_gcode")
        self.utils = CrealityCloudUtils()
        self.utils.saveGCodeStarted.connect(self.saveGCode)

        self.plugin_window = None
        self._writing = False
        self._nodes = None
        self._stream = None

    def requestWrite(self, nodes, file_name = None, limit_mimetypes = None, file_handler = None, **kwargs) -> None:
        if self._writing:
            raise OutputDeviceError.DeviceBusyError()

        self.utils.setDefaultFileName(file_name)

        self._nodes = None
        self._nodes = nodes
        if self.plugin_window is not None:
            self.plugin_window = None
        self.writeStarted.emit(self)

        self.plugin_window = self._createDialogue()
        self.plugin_window.show()

    def _createDialogue(self) -> QObject:
        Application.getInstance()._qml_engine.rootContext().setContextProperty("CloudUtils", self.utils)
        # Application.getInstance()._qml_engine.rootContext(
        # ).setContextProperty("catalog", catalog)
        qml_file = os.path.join(PluginRegistry.getInstance().getPluginPath(self._pluginId), "PluginMain.qml")
        component = Application.getInstance().createQmlComponent(qml_file)
        
        return component

    def saveGCode(self, file_name: str) -> None:
        file_writer = Application.getInstance().getMeshFileHandler().getWriter("GCodeWriter")
        Logger.log("d", "Writing GCode to %s", file_name)
        self._stream = open(file_name, "wt", encoding = "utf-8")
        try:
            job = WriteFileJob(file_writer, self._stream, self._nodes, MeshWriter.OutputMode.TextMode)
            job.setFileName(file_name)
            job.progress.connect(self._onJobProgress)
            job.finished.connect(self._onWriteJobFinished)
            message = Message(catalog.i18nc("@info:progress Don't translate the XML tags <filename>!", "Saving to <filename>{0}</filename>").format(file_name),
                              0, False, -1, catalog.i18nc("@info:title", "Saving"))
            message.show()
            job.setMessage(message)
            self._writing = True
            job.start()
            self.utils.updatedProgressTextSlot(catalog.i18nc("@info:status", "1/4 Output gcode file to local..."))
            self.utils.updateStatus.emit("upload")
        except PermissionError as e:
            Logger.log("e", "Permission denied when trying to write to %s: %s", file_name, str(e))
            raise OutputDeviceError.PermissionDeniedError(catalog.i18nc(
                "@info:status Don't translate the XML tags <filename>!", "Permission denied when trying to save <filename>{0}</filename>").format(file_name)) from e
        except OSError as e:
            Logger.log("e", "Operating system would not let us write to %s: %s", file_name, str(e))
            raise OutputDeviceError.WriteRequestFailedError(catalog.i18nc(
                "@info:status Don't translate the XML tags <filename> or <message>!", "Could not save to <filename>{0}</filename>: <message>{1}</message>").format(file_name)) from e

    def _onJobProgress(self, job: WriteFileJob, progress) -> None:
        self.writeProgress.emit(self, progress)

    def _onWriteJobFinished(self, job: WriteFileJob) -> None:
        self._writing = False
        self._stream.close()
        self.writeFinished.emit(self)
        if job.getResult():
            self.writeSuccess.emit(self)
            job.getStream().close()
            self.utils.gzipFile()
            
        else:
            message = Message(catalog.i18nc("@info:status Don't translate the XML tags <filename> or <message>!", "Could not save to <filename>{0}</filename>: <message>{1}</message>").format(job.getFileName(), str(job.getError())), lifetime = 0, title = catalog.i18nc("@info:title", "Warning"))
            message.show()
            self.writeError.emit(self)
            job.getStream().close()

