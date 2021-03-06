from PyQt4 import QtCore, QtGui
from utilities.backend_config import Configuration
from qt_interfaces.client_configuration_ui import Ui_ClientConfiguration
from utilities.log_manager import logger


# Configuration Ui section
class ClientConfigurationUI(QtGui.QMainWindow):

    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)

        # register UI
        self.client_configuration_ui = Ui_ClientConfiguration()
        self.client_configuration_ui.setupUi(self)

        self.configuration_manager = Configuration()

        QtCore.QObject.connect(self.client_configuration_ui.apply_bt, QtCore.SIGNAL("clicked()"),
                               self.save_settings)  # valudate and register user

    def save_settings(self):
        # validate settings

        self.configuration_manager.save_client_configuration(self.client_configuration_ui)  # save configuration

    def reset_settings_to_default(self):
        logger.debug(1)
