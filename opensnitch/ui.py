# This file is part of OpenSnitch.
#
# Copyright(c) 2017 Simone Margaritelli
# evilsocket@gmail.com
# http://www.evilsocket.net
#
# This file may be licensed under the terms of of the
# GNU General Public License Version 2 (the ``GPL'').
#
# Software distributed under the License is distributed
# on an ``AS IS'' basis, WITHOUT WARRANTY OF ANY KIND, either
# express or implied. See the GPL for the specific language
# governing rights and limitations.
#
# You should have received a copy of the GPL along with this
# program. If not, go to http://www.gnu.org/licenses/gpl.html
# or write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
from PyQt5 import QtCore, QtGui, uic, QtWidgets
from opensnitch.rule import Rule
import queue
import sys
import os


# TODO: Implement tray icon and menu.
# TODO: Implement rules editor.
RESOURCES_PATH = "%s/resources/" % os.path.dirname(
    sys.modules[__name__].__file__)
DIALOG_UI_PATH = "%s/dialog_hi.ui" % RESOURCES_PATH


class QtApp:
    def __init__(self, connection_futures):
        self.app = QtWidgets.QApplication([])
        self.connection_queue = queue.Queue()
        self.dialog = Dialog(self.connection_queue, connection_futures)

    def run(self):
        self.app.exec()

    def prompt_user(self, connection):
        self.connection_queue.put(connection)
        self.dialog.add_connection_signal.emit()


class Dialog(QtWidgets.QDialog, uic.loadUiType(DIALOG_UI_PATH)[0]):

    DEFAULT_RESULT = (Rule.ONCE, Rule.ACCEPT, False)
    MESSAGE_TEMPLATE = "<b>%s</b> (pid=%s) wants to connect to <b>%s</b> on <b>%s port %s%s</b>"  # noqa

    add_connection_signal = QtCore.pyqtSignal()

    def __init__(self, connection_queue, connection_futures, parent=None):
        self.connection_queue = connection_queue
        self.connection = None
        QtWidgets.QDialog.__init__(self, parent,
                                   QtCore.Qt.WindowStaysOnTopHint)
        self.setupUi(self)
        self.init_widgets()
        self.start_listeners()

        self.connection_futures = connection_futures
        self.add_connection_signal.connect(self.handle_connection)

    @QtCore.pyqtSlot()
    def handle_connection(self):
        # This method will get called again after the user took action
        # on the currently handled connection
        if self.connection is not None:
            return

        try:
            self.connection = self.connection_queue.get_nowait()
        except queue.Empty:
            return

        self.setup_labels()
        self.setup_icon()
        self.setup_extra()
        self.result = Dialog.DEFAULT_RESULT
        self.show()

    def setup_labels(self):
        self.app_name_label.setText(self.connection.app.name)

        message = self.MESSAGE_TEMPLATE % (
                    self.connection.get_app_name_and_cmdline(),
                    self.connection.app.pid,
                    self.connection.hostname,
                    self.connection.proto.upper(),
                    self.connection.dst_port,
                    " (%s)" % self.connection.service or '')
        self.message_label.setText(message)

    def init_widgets(self):
        self.app_name_label = self.findChild(QtWidgets.QLabel,
                                             "appNameLabel")
        self.message_label = self.findChild(QtWidgets.QLabel,
                                            "messageLabel")
        self.action_combo_box = self.findChild(QtWidgets.QComboBox,
                                               "actionComboBox")
        self.allow_button = self.findChild(QtWidgets.QPushButton,
                                           "allowButton")
        self.deny_button = self.findChild(QtWidgets.QPushButton,
                                          "denyButton")
        self.whitelist_button = self.findChild(QtWidgets.QPushButton,
                                               "whitelistButton")
        self.block_button = self.findChild(QtWidgets.QPushButton,
                                           "blockButton")
        self.icon_label = self.findChild(QtWidgets.QLabel, "iconLabel")

    def start_listeners(self):
        self.allow_button.clicked.connect(self._allow_action)
        self.deny_button.clicked.connect(self._deny_action)
        self.whitelist_button.clicked.connect(self._whitelist_action)
        self.block_button.clicked.connect(self._block_action)
        self.action_combo_box.currentIndexChanged[str].connect(
            self._action_changed)

    def setup_icon(self):
        if self.connection.app.icon is not None:
            icon = QtGui.QIcon().fromTheme(self.connection.app.icon)
            pixmap = icon.pixmap(icon.actualSize(QtCore.QSize(48, 48)))
            self.icon_label.setPixmap(pixmap)

    def setup_extra(self):
        self._action_changed()

    def _action_changed(self):
        s_option = self.action_combo_box.currentText()
        if s_option == "Until Quit" or s_option == "Forever":
            self.whitelist_button.show()
            self.block_button.show()
        elif s_option == "Once":
            self.whitelist_button.hide()
            self.block_button.hide()

    def _allow_action(self):
        self._action(Rule.ACCEPT, False)

    def _deny_action(self):
        self._action(Rule.DROP, False)

    def _whitelist_action(self):
        self._action(Rule.ACCEPT, True)

    def _block_action(self):
        self._action(Rule.DROP, True)

    def _action(self, verdict, apply_to_all=False):
        s_option = self.action_combo_box.currentText()

        if s_option == "Once":
            option = Rule.ONCE
        elif s_option == "Until Quit":
            option = Rule.UNTIL_QUIT
        elif s_option == "Forever":
            option = Rule.FOREVER

        # Set result future
        try:
            fut = self.connection_futures[self.connection.id]
        except KeyError:
            pass
        else:
            fut.set_result((option, verdict, apply_to_all))

        # Check if we have any unhandled connections on the queue
        self.connection = None  # Indicate that next connection can be handled
        self.hide()
        self.handle_connection()
