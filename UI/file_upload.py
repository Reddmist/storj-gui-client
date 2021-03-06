import json
import logging
import os

import requests
from PyQt4 import QtCore, QtGui

import time
from PyQt4.QtCore import SIGNAL
from PyQt4.QtGui import QFileDialog
from PyQt4.QtGui import QMessageBox
from PyQt4.QtGui import QProgressBar

from UI.crypto.file_crypto_tools import FileCrypto
from UI.utilities.backend_config import Configuration
from UI.utilities.tools import Tools
from qt_interfaces.single_file_upload_ui import Ui_SingleFileUpload
from engine import StorjEngine
import storj
from crypto.crypto_tools import CryptoTools
import hashlib
import threading
import magic

from sys import platform

import storj.model
# import storj.exception

from utilities.log_manager import logger
# from logs_backend import LogHandler, logger

from resources.html_strings import html_format_begin, html_format_end
from utilities.account_manager import AccountManager


"""
######################### Logging ####################
def get_global_logger(handler):
    class GlobalLogger(logging.getLoggerClass()):
        def __init__(self, name):
            logging.getLoggerClass().__init__(self, name)
            self.addHandler(handler)
    return GlobalLogger

######################################################
"""


class SingleFileUploadUI(QtGui.QMainWindow):

    def __init__(self, parent=None, bucketid=None, fileid=None):
        QtGui.QWidget.__init__(self, parent)
        self.ui_single_file_upload = Ui_SingleFileUpload()
        self.ui_single_file_upload.setupUi(self)
        QtCore.QObject.connect(self.ui_single_file_upload.start_upload_bt, QtCore.SIGNAL("clicked()"),
                               self.createNewUploadThread)  # open bucket manager
        QtCore.QObject.connect(self.ui_single_file_upload.file_path_select_bt, QtCore.SIGNAL("clicked()"),
                               self.select_file_path)  # open file select dialog
        QtCore.QObject.connect(self.ui_single_file_upload.tmp_path_select_bt, QtCore.SIGNAL("clicked()"),
                               self.select_tmp_directory)  # open tmp directory select dialog
        self.storj_engine = StorjEngine()  # init StorjEngine

        self.initialize_upload_queue_table()

        # init loggers
        # self.log_handler = LogHandler()
        # logging.setLoggerClass(get_global_logger(self.log_handler))
        # logger.addHandler(self.log_handler)

        self.account_manager = AccountManager()  # init AccountManager

        self.user_password = self.account_manager.get_user_password()

        if platform == "linux" or platform == "linux2":
            # linux
            self.ui_single_file_upload.tmp_path.setText(str("/tmp/"))
        elif platform == "darwin":
            # OS X
            self.ui_single_file_upload.tmp_path.setText(str("/tmp/"))
        elif platform == "win32":
            # Windows
            self.ui_single_file_upload.tmp_path.setText(str("C://Windows/temp/"))

        # initialize variables
        self.shards_already_uploaded = 0
        self.uploaded_shards_count = 0
        self.upload_queue_progressbar_list = []

        self.connect(self, SIGNAL("addRowToUploadQueueTable"), self.add_row_upload_queue_table)

        self.connect(self, SIGNAL("incrementShardsProgressCounters"), self.increment_shards_progress_counters)
        self.connect(self, SIGNAL("updateUploadTaskState"), self.update_upload_task_state)
        self.connect(self, SIGNAL("updateShardUploadProgress"), self.update_shard_upload_progess)
        self.connect(self, SIGNAL("showFileNotSelectedError"), self.show_error_not_selected_file)
        self.connect(self, SIGNAL("showInvalidPathError"), self.show_error_invalid_file_path)
        self.connect(self, SIGNAL("showInvalidTemporaryPathError"), self.show_error_invalid_temporary_path)
        self.connect(self, SIGNAL("refreshOverallProgress"), self.refresh_overall_progress)
        self.connect(self, SIGNAL("showFileUploadedSuccessfully"), self.show_upload_finished_message)

        self.createBucketResolveThread()  # resolve buckets and put to buckets combobox

        # file_pointers = self.storj_engine.storj_client.file_pointers("6acfcdc62499144929cf9b4a", "dfba26ab34466b1211c60d02")

        # self.emit(SIGNAL("addRowToUploadQueueTable"), "important", "information")
        # self.emit(SIGNAL("addRowToUploadQueueTable"), "important", "information")
        # self.emit(SIGNAL("incrementShardsProgressCounters"))

        self.max_retries_upload_to_same_farmer = 3
        self.max_retries_negotiate_contract = 10

        #
        # print self.config.max_retries_upload_to_same_farmer

        # self.initialize_shard_queue_table(file_pointers)

        self.shard_upload_percent_list = []

        self.ui_single_file_upload.overall_progress.setValue(0)

    def show_upload_finished_message(self):
        QMessageBox.information(self, "Success!", "File uploaded successfully!")

    def refresh_overall_progress(self, base_percent):
        total_percent_to_upload = self.all_shards_count * 100
        total_percent_uploaded = sum(self.shard_upload_percent_list) * 100

        actual_percent_uploaded = total_percent_uploaded / total_percent_to_upload

        total_percent = (base_percent * 100) + (0.90 * actual_percent_uploaded)

        logger.info(str(actual_percent_uploaded) + str(base_percent) +
                    "total_percent_uploaded")

        # actual_upload_progressbar_value = self.ui_single_file_upload.overall_progress.value()

        self.ui_single_file_upload.overall_progress.setValue(int(total_percent))

    def update_shard_upload_progess(self, row_position_index, value):
        self.upload_queue_progressbar_list[row_position_index].setValue(value)
        logger.debug("kotek")
        return 1

    def update_upload_task_state(self, row_position, state):
        self.ui_single_file_upload.shard_queue_table_widget.setItem(int(row_position), 3, QtGui.QTableWidgetItem(str(state)))

    def show_error_not_selected_file(self):
        QMessageBox.about(self, "Error", "Please select file which you want to upload!")

    def show_error_invalid_file_path(self):
        QMessageBox.about(self, "Error", "File path seems to be invalid!")

    def show_error_invalid_temporary_path(self):
        QMessageBox.about(self, "Error", "Temporary path seems to be invalid!")

    def createBucketResolveThread(self):
        bucket_resolve_thread = threading.Thread(target=self.initialize_buckets_select_list, args=())
        bucket_resolve_thread.start()

    def initialize_buckets_select_list(self):
        logger.warning(str({"log_event_type": "info", "title": "Buckets", "description": "Resolving buckets from Bridge to buckets combobox..."}))

        self.buckets_list = []
        self.bucket_id_list = []
        self.storj_engine = StorjEngine()  # init StorjEngine
        i = 0
        try:
            for bucket in self.storj_engine.storj_client.bucket_list():
                self.buckets_list.append(str(bucket.name))  # append buckets to list
                self.bucket_id_list.append(str(bucket.id))  # append buckets to list
                i = i + 1
        except storj.exception.StorjBridgeApiError as e:
            QMessageBox.about(self, "Unhandled bucket resolving exception", "Exception: " + str(e))

        self.ui_single_file_upload.save_to_bucket_select.addItems(self.buckets_list)

    def increment_shards_progress_counters(self):
        self.shards_already_uploaded += 1
        self.ui_single_file_upload.shards_uploaded.setText(html_format_begin + str(self.shards_already_uploaded) + html_format_end)

    def add_row_upload_queue_table(self, row_data):
        self.upload_queue_progressbar_list.append(QProgressBar())

        self.upload_queue_table_row_count = self.ui_single_file_upload.shard_queue_table_widget.rowCount()

        self.ui_single_file_upload.shard_queue_table_widget.setRowCount(self.upload_queue_table_row_count + 1)

        self.ui_single_file_upload.shard_queue_table_widget.setCellWidget(self.upload_queue_table_row_count, 0, self.upload_queue_progressbar_list[self.upload_queue_table_row_count])
        self.ui_single_file_upload.shard_queue_table_widget.setItem(self.upload_queue_table_row_count, 1, QtGui.QTableWidgetItem(row_data["hash"]))
        self.ui_single_file_upload.shard_queue_table_widget.setItem(self.upload_queue_table_row_count, 2, QtGui.QTableWidgetItem(str(row_data["farmer_address"]) + ":" + str(row_data["farmer_port"])))
        self.ui_single_file_upload.shard_queue_table_widget.setItem(self.upload_queue_table_row_count, 3, QtGui.QTableWidgetItem(str(row_data["state"])))
        self.ui_single_file_upload.shard_queue_table_widget.setItem(self.upload_queue_table_row_count, 4, QtGui.QTableWidgetItem(str(row_data["token"])))
        self.ui_single_file_upload.shard_queue_table_widget.setItem(self.upload_queue_table_row_count, 5, QtGui.QTableWidgetItem(str(row_data["shard_index"])))

        self.upload_queue_progressbar_list[self.upload_queue_table_row_count].setValue(0)

        logger.info(row_data)

    def select_tmp_directory(self):
        self.selected_tmp_dir = QtGui.QFileDialog.getExistingDirectory(None, 'Select a folder:', '',
                                                                       QtGui.QFileDialog.ShowDirsOnly)
        self.ui_single_file_upload.tmp_path.setText(str(self.selected_tmp_dir))

    def select_file_path(self):
        self.ui_single_file_upload.file_path.setText(QFileDialog.getOpenFileName())

    def createNewUploadThread(self):
        # self.download_thread = DownloadTaskQtThread(url, filelocation, options_chain, progress_bars_list)
        # self.download_thread.start()
        # self.download_thread.connect(self.download_thread, SIGNAL('setStatus'), self.test1, Qt.QueuedConnection)
        # self.download_thread.tick.connect(progress_bars_list.setValue)

        # Refactor to QtTrhead
        upload_thread = threading.Thread(target=self.file_upload_begin, args=())
        upload_thread.start()

    def initialize_upload_queue_table(self):

        # initialize variables
        self.shards_already_uploaded = 0
        self.uploaded_shards_count = 0
        self.upload_queue_progressbar_list = []

        self.upload_queue_table_header = ['Progress', 'Hash', 'Farmer', 'State', 'Token', 'Shard index']
        self.ui_single_file_upload.shard_queue_table_widget.setColumnCount(6)
        self.ui_single_file_upload.shard_queue_table_widget.setRowCount(0)
        horHeaders = self.upload_queue_table_header
        self.ui_single_file_upload.shard_queue_table_widget.setHorizontalHeaderLabels(horHeaders)
        self.ui_single_file_upload.shard_queue_table_widget.resizeColumnsToContents()
        self.ui_single_file_upload.shard_queue_table_widget.resizeRowsToContents()

        self.ui_single_file_upload.shard_queue_table_widget.horizontalHeader().setResizeMode(QtGui.QHeaderView.Stretch)

    def set_current_status(self, current_status):
        self.ui_single_file_upload.current_state.setText(html_format_begin + current_status + html_format_end)

    def createNewShardUploadThread(self, shard, chapters, frame, file_name):
        # another worker thread for single shard uploading and it will retry if download fail
        upload_thread = threading.Thread(target=self.upload_shard(shard=shard, chapters=chapters, frame=frame, file_name_ready_to_shard_upload=file_name), args=())
        upload_thread.start()

    def upload_shard(self, shard, chapters, frame, file_name_ready_to_shard_upload):

        self.uploadblocksize = 4096

        def read_in_chunks(file_object, shard_size, rowposition, blocksize=self.uploadblocksize, chunks=-1, shard_index=None):
            """Lazy function (generator) to read a file piece by piece.
            Default chunk size: 1k."""

            i = 0
            while chunks:
                data = file_object.read(blocksize)
                if not data:
                    break
                yield data
                i += 1
                t1 = float(shard_size) / float((self.uploadblocksize))
                if shard_size <= (self.uploadblocksize):
                    t1 = 1

                percent_uploaded = int(round((100.0 * i) / t1))

                logger.debug(i)
                chunks -= 1
                self.emit(SIGNAL("updateShardUploadProgress"), int(rowposition), percent_uploaded)  # update progress bar in upload queue table
                self.shard_upload_percent_list[shard_index] = percent_uploaded
                self.emit(SIGNAL("refreshOverallProgress"), 0.1)  # update overall progress bar

        it = 0
        contract_negotiation_tries = 0
        while self.max_retries_negotiate_contract > contract_negotiation_tries:
            contract_negotiation_tries += 1

            # emit signal to add row to upload queue table
            # self.emit(SIGNAL("addRowToUploadQueueTable"), "important", "information")

            self.ui_single_file_upload.current_state.setText(
                html_format_begin + "Adding shard " + str(
                    chapters) + " to file frame and getting contract..." + html_format_end)

            # logger.warning('"log_event_type": "debug"')
            logger.warning('"title": "Negotiating contract"')
            logger.warning('"description": "Trying to negotiate storage \
                    contract for shard at inxed " + str(chapters) + "..."')
            # logger.warning(str({"log_event_type": "debug", "title": "Negotiating contract",
            #                     "description": "Trying to negotiate storage contract for shard at inxed " + str(chapters) + "..."}))

            try:
                frame_content = self.storj_engine.storj_client.frame_add_shard(shard, frame.id)

                # Add items to shard queue table view

                tablerowdata = {}
                tablerowdata["farmer_address"] = frame_content["farmer"]["address"]
                tablerowdata["farmer_port"] = frame_content["farmer"]["port"]
                tablerowdata["hash"] = str(shard.hash)
                tablerowdata["state"] = "Uploading..."
                tablerowdata["token"] = frame_content["token"]
                tablerowdata["shard_index"] = str(chapters)

                # logger.warning('"log_event_type": "debug"')
                logger.warning('"title": "Contract negotiated"')
                logger.warning('"description": "Storage contract negotiated with: "' +
                               str(frame_content["farmer"]["address"]) + ":" +
                               str(frame_content["farmer"]["port"]))
                # logger.warning(str({"log_event_type": "debug", "title": "Contract negotiated",
                #                     "description": "Storage contract negotiated with: " + str(frame_content["farmer"]["address"] + ":" + str(frame_content["farmer"]["port"]))}))

                self.emit(SIGNAL("addRowToUploadQueueTable"), tablerowdata)  # add row to table

                rowcount = self.ui_single_file_upload.shard_queue_table_widget.rowCount()

                logger.debug(frame_content)
                logger.debug(shard)
                logger.debug(frame_content["farmer"]["address"])

                farmerNodeID = frame_content["farmer"]["nodeID"]

                url = "http://" + frame_content["farmer"]["address"] + ":" +\
                      str(frame_content["farmer"]["port"]) + "/shards/" +\
                      frame_content["hash"] + "?token=" +\
                      frame_content["token"]
                logger.debug(url)

                # files = {'file': open(file_path + '.part%s' % chapters)}
                # headers = {'content-type: application/octet-stream', 'x-storj-node-id: ' + str(farmerNodeID)}

                self.set_current_status("Uploading shard " + str(chapters + 1) + " to farmer...")

                # begin recording exchange report
                exchange_report = storj.model.ExchangeReport()

                current_timestamp = int(time.time())

                exchange_report.exchangeStart = str(current_timestamp)
                exchange_report.farmerId = str(farmerNodeID)
                exchange_report.dataHash = str(shard.hash)

                shard_size = int(shard.size)

                rowposition = rowcount
                farmer_tries = 0
                response = None
                while self.max_retries_upload_to_same_farmer > farmer_tries:
                    farmer_tries += 1
                    try:
                        logger.warning(str({"log_event_type": "debug", "title": "Uploading shard",
                                            "description": "Uploading shard at index " + str(shard.index) + " to " + str(
                                                frame_content["farmer"]["address"] + ":" + str(frame_content["farmer"][
                                                    "port"]))}))

                        with open(self.parametrs.tmpPath + file_name_ready_to_shard_upload + '-' + str(chapters + 1),
                                  'rb') as f:
                            response = requests.post(url, data=read_in_chunks(f, shard_size, rowposition, shard_index=chapters), timeout=1)

                        j = json.loads(str(response.content))
                        if (j["result"] == "The supplied token is not accepted"):
                            raise storj.exception.StorjFarmerError(
                                storj.exception.StorjFarmerError.SUPPLIED_TOKEN_NOT_ACCEPTED)

                    except storj.exception.StorjFarmerError as e:
                        # upload failed due to Farmer Failure
                        logger.error(e)
                        if str(e) == str(storj.exception.StorjFarmerError.SUPPLIED_TOKEN_NOT_ACCEPTED):
                            logger.error("The supplied token not accepted")
                        # print "Exception raised while trying to negitiate contract: " + str(e)
                        continue

                    except Exception as e:
                        self.emit(SIGNAL("updateUploadTaskState"), rowposition,
                                  "First try failed. Retrying... (" + str(farmer_tries) + ")")  # update shard upload state

                        # logger.warning('"log_event_type": "warning"')
                        logger.warning('"title": "Shard upload error"')
                        logger.warning('"description": "Error while uploading \
                                       shard to: "' +
                                       frame_content["farmer"]["address"] +
                                       ":" +
                                       str(frame_content["farmer"]["port"]) +
                                       " Retrying... (" + str(farmer_tries) +
                                       ")")
                        # logger.warning(str({"log_event_type": "warning", "title": "Shard upload error",
                        #                    "description": "Error while uploading shard to: " + str(
                        #                         frame_content["farmer"]["address"] + ":" + str(frame_content["farmer"][
                        #                             "port"])) + " Retrying... (" + str(farmer_tries) + ")"}))
                        logger.error(e)
                        continue
                    else:
                        self.emit(SIGNAL("incrementShardsProgressCounters"))  # update already uploaded shards count
                        logger.warning(str({"log_event_type": "success", "title": "Uploading shard",
                                            "description": "Shard uploaded successfully to " + str(
                                                frame_content["farmer"]["address"] + ":" + str(frame_content["farmer"][
                                                    "port"]))}))

                        self.emit(SIGNAL("updateUploadTaskState"), rowposition,
                                  "Uploaded!")  # update shard upload state

                        logger.debug(str(self.all_shards_count) + "wszystkie" +
                                     str(self.shards_already_uploaded) + "wyslane")
                        if int(self.all_shards_count) <= int(self.shards_already_uploaded + 1):
                            self.emit(SIGNAL("finishUpload"))  # send signal to save to bucket after all files are uploaded
                        break

                logger.debug(response.content)

                j = json.loads(str(response.content))
                if (j["result"] == "The supplied token is not accepted"):
                    raise storj.exception.StorjFarmerError(storj.exception.StorjFarmerError.SUPPLIED_TOKEN_NOT_ACCEPTED)

                firstiteration = False
                it += 1

            except storj.exception.StorjBridgeApiError as e:
                # upload failed due to Storj Bridge failure
                logger.error("Exception raised while trying to negitiate \
                             contract: " + str(e))
                # logger.warning('"log_event_type": "error"')
                logger.warning('"title": "Bridge exception"')
                logger.warning('"description": "Exception raised while trying \
                               to negotiate storage contract for shard at index\
                               "' + str(chapters))
                # logger.warning(str({"log_event_type": "error", "title": "Bridge exception",
                #                     "description": "Exception raised while trying to negitiate storage contract for shard at index " + str(
                #                         chapters)}))
                continue
            except Exception as e:
                # now send Exchange Report
                # upload failed probably while sending data to farmer
                logger.error("Error occured while trying to upload shard or\
                             negotiate contract. Retrying... " + str(e))
                # logger.warning('"log_event_type": "error"')
                logger.warning('"title": "Unhandled exception"')
                logger.warning('"description": "Unhandled exception occured\
                               while trying to upload shard or negotiate \
                               contract for shard at index "' +
                               str(chapters) +
                               " . Retrying...")
                # logger.warning(str({"log_event_type": "error", "title": "Unhandled exception",
                #                     "description": "Unhandled exception occured while trying to upload shard or negotiate contract for shard at index " + str(chapters) + " . Retrying..."}))
                current_timestamp = int(time.time())

                exchange_report.exchangeEnd = str(current_timestamp)
                exchange_report.exchangeResultCode = (exchange_report.FAILURE)
                exchange_report.exchangeResultMessage = (exchange_report.STORJ_REPORT_UPLOAD_ERROR)
                self.set_current_status("Sending Exchange Report for shard " + str(chapters + 1))
                # self.storj_engine.storj_client.send_exchange_report(exchange_report) # send exchange report
                continue
            else:
                # uploaded with success
                current_timestamp = int(time.time())
                # prepare second half of exchange heport
                exchange_report.exchangeEnd = str(current_timestamp)
                exchange_report.exchangeResultCode = (exchange_report.SUCCESS)
                exchange_report.exchangeResultMessage = (exchange_report.STORJ_REPORT_SHARD_UPLOADED)
                self.set_current_status("Sending Exchange Report for shard " + str(chapters + 1))
                # logger.warning('"log_event_type": "debug"')
                logger.debug('"title":"Shard added"')
                logger.info('"description": "Shard "' + str(chapters + 1) +
                            " successfully added and exchange report sent.")
                # logger.warning(str({"log_event_type": "debug", "title": "Shard added",
                #                     "description": "Shard " + str(chapters + 1) + " successfully added and exchange report sent."}))
                # self.storj_engine.storj_client.send_exchange_report(exchange_report) # send exchange report
                break

    def file_upload_begin(self):
        self.ui_single_file_upload.overall_progress.setValue(0)
        # upload finish function #

        def finish_upload(self):
            self.crypto_tools = CryptoTools()
            self.ui_single_file_upload.current_state.setText(
                html_format_begin + "Generating SHA5212 HMAC..." + html_format_end)
            logger.warning(str({"log_event_type": "debug", "title": "HMAC",
                                "description": "Generating HMAC..."}))
            hash_sha512_hmac_b64 = self.crypto_tools.prepare_bucket_entry_hmac(shards_manager.shards)
            hash_sha512_hmac = hashlib.sha224(str(hash_sha512_hmac_b64["SHA-512"])).hexdigest()
            logger.debug(hash_sha512_hmac)
            # save

            # import magic
            # mime = magic.Magic(mime=True)
            # mime.from_file(file_path)

            logger.debug(frame.id)
            logger.debug("Now upload file")

            data = {
                'x-token': push_token.id,
                'x-filesize': str(file_size),
                'frame': frame.id,
                'mimetype': file_mime_type,
                'filename': str(bname),
                'hmac': {
                    'type': "sha512",
                    # 'value': hash_sha512_hmac["sha512_checksum"]
                    'value': hash_sha512_hmac
                },
            }
            self.ui_single_file_upload.current_state.setText(
                html_format_begin + "Adding file to bucket..." + html_format_end)

            # logger.warning('"log_event_type": "debug"')
            logger.debug('"title": "Finishing upload"')
            logger.debug('"description": "Adding file "' +
                         str(bname) + " to bucket...")
            # logger.warning(str({"log_event_type": "debug", "title": "Finishing upload",
            #                     "description": "Adding file " + str(bname) + " to bucket..."}))

            success = False
            try:
                response = self.storj_engine.storj_client._request(
                    method='POST', path='/buckets/%s/files' % bucket_id,
                    # files={'file' : file},
                    headers={
                        'x-token': push_token.id,
                        'x-filesize': str(file_size),
                    },
                    json=data,
                )
                success = True
            except storj.exception.StorjBridgeApiError as e:
                QMessageBox.about(self, "Unhandled bridge exception", "Exception: " + str(e))
            if success:
                self.ui_single_file_upload.current_state.setText(
                    html_format_begin + "Upload success! Waiting for user..." + html_format_end)
                logger.warning(str({"log_event_type": "success", "title": "File uploaded",
                                    "description": "File uploaded successfully!"}))
                self.emit(SIGNAL("showFileUploadedSuccessfully"))

        self.connect(self, SIGNAL("finishUpload"), lambda: finish_upload(self))

        # end upload finishing function #

        file_path = None
        self.validation = {}

        self.initialize_upload_queue_table()

        # item = ProgressWidgetItem()
        # self.ui_single_file_upload.shard_queue_table_widget.setItem(1, 1, item)
        # item.updateValue(1)

        # progress.valueChanged.connect(item.updateValue)

        encryption_enabled = True
        self.parametrs = storj.model.StorjParametrs()

        # get temporary files path
        if self.ui_single_file_upload.tmp_path.text() == "":
            self.parametrs.tmpPath = "/tmp/"
        else:
            self.parametrs.tmpPath = str(self.ui_single_file_upload.tmp_path.text())

        self.configuration = Configuration()

        # get temporary files path
        if self.ui_single_file_upload.file_path.text() == "":
            self.validation["file_path"] = False
            self.emit(SIGNAL("showFileNotSelectedError"))  # show error missing file path
        else:
            self.validation["file_path"] = True
            file_path = str(self.ui_single_file_upload.file_path.text())

        if self.validation["file_path"]:

            self.current_bucket_index = self.ui_single_file_upload.save_to_bucket_select.currentIndex()
            self.current_selected_bucket_id = self.bucket_id_list[self.current_bucket_index]
            bucket_id = str(self.current_selected_bucket_id)

            bname = os.path.split(file_path)[1]

            logger.debug(bname + "npliku")

            mime = magic.Magic(mime=True)
            file_mime_type = str(mime.from_file(str(file_path)))
            file_mime_type = "text/plain"
            logger.debug(file_mime_type)
            # file_mime_type = str("A")

            file_existence_in_bucket = False

            # if self.configuration.sameFileNamePrompt or self.configuration.sameFileHashPrompt:
            # file_existence_in_bucket = self.storj_engine.storj_client.check_file_existence_in_bucket(bucket_id=bucket_id, filepath=file_path) # chech if exist file with same file name

            if file_existence_in_bucket == 1:
                # QInputDialog.getText(self, 'Warning!', 'File with name ' + str(bname) + " already exist in bucket! Please use different name:", "test" )
                logger.warning("Same file exist!")

            if self.ui_single_file_upload.encrypt_files_checkbox.isChecked():
                # encrypt file
                self.set_current_status("Encrypting file...")
                # logger.warning('"log_event_type": "debug"')
                logger.debug('"title": "Encryption"')
                logger.debug('"description": "Encrypting file..."')

                file_crypto_tools = FileCrypto()
                file_crypto_tools.encrypt_file("AES", str(file_path), self.parametrs.tmpPath + "/" + bname + ".encrypted",
                                               str(self.user_password))  # begin file encryption
                file_path_ready = self.parametrs.tmpPath + "/" + bname +\
                    ".encrypted"  # get path to encrypted file in temp dir
                file_name_ready_to_shard_upload = bname + ".encrypted"
            else:
                file_path_ready = file_path
                file_name_ready_to_shard_upload = bname

            logger.debug(self.parametrs.tmpPath)
            logger.debug(file_path_ready + "sciezka2")

            def get_size(file_like_object):
                return os.stat(file_like_object.name).st_size

            # file_size = get_size(file)

            file_size = os.stat(file_path).st_size

            tools = Tools()

            self.ui_single_file_upload.file_size.setText(html_format_begin + str(tools.human_size(int(file_size))) + html_format_end)

            self.ui_single_file_upload.current_state.setText(
                html_format_begin + "Resolving PUSH token..." + html_format_end)

            # logger.warning('"log_event_type": "debug"')
            logger.debug('"title": "PUSH token"')
            logger.debug('"description": "Resolving PUSH Token for upload..."')
            # logger.warning(str({"log_event_type": "debug", "title": "PUSH token",
            #                     "description": "Resolving PUSH Token for upload..."}))

            push_token = None

            try:
                push_token = self.storj_engine.storj_client.token_create(bucket_id,
                                                                         'PUSH')  # get the PUSH token from Storj Bridge
            except storj.exception.StorjBridgeApiError as e:
                QMessageBox.about(self, "Unhandled PUSH token create exception", "Exception: " + str(e))

            self.ui_single_file_upload.push_token.setText(
                html_format_begin + str(push_token.id) + html_format_end)  # set the PUSH Token

            logger.debug(push_token.id)

            self.ui_single_file_upload.current_state.setText(
                html_format_begin + "Resolving frame for file..." + html_format_end)

            # logger.warning('"log_event_type": "debug"')
            logger.debug('"title": "Frame"')
            logger.debug('"description": "Resolving frame for file upload..."')
            # logger.warning(str({"log_event_type": "debug", "title": "Frame",
            #                     "description": "Resolving frame for file upload..."}))

            frame = None  # initialize variable
            try:
                frame = self.storj_engine.storj_client.frame_create()  # Create file frame
            except storj.exception.StorjBridgeApiError as e:
                QMessageBox.about(self, "Unhandled exception while creating file staging frame", "Exception: " + str(e))
                # logger.warning('"log_event_type": "error"')
                logger.debug('"title": "Frame"')
                logger.debug('"description": "Error while resolving frame for\
                    file upload..."')
                # logger.warning(str({"log_event_type": "error", "title": "Frame",
                #                     "description": "Error while resolving frame for file upload..."}))

            self.ui_single_file_upload.file_frame_id.setText(html_format_begin + str(frame.id) + html_format_end)

            logger.debug(frame.id)
            # Now encrypt file
            logger.debug(file_path_ready + "sciezka")

            # Now generate shards
            self.set_current_status("Splitting file to shards...")
            logger.warning(str({"log_event_type": "debug", "title": "Sharding",
                                "description": "Splitting file to shards..."}))
            shards_manager = storj.model.ShardManager(filepath=str(file_path_ready), tmp_path=self.parametrs.tmpPath)

            # self.ui_single_file_upload.current_state.setText(html_format_begin + "Generating shards..." + html_format_end)
            # shards_manager._make_shards()
            shards_count = shards_manager.index
            # create file hash
            self.storj_engine.storj_client.logger.debug('file_upload() push_token=%s', push_token)

            # upload shards to frame
            logger.debug(shards_count)

            # set shards count
            self.ui_single_file_upload.shards_count.setText(html_format_begin + str(shards_count) + html_format_end)
            self.all_shards_count = shards_count

            chapters = 0
            firstiteration = True

            for shard in shards_manager.shards:
                self.shard_upload_percent_list.append(0)
                self.createNewShardUploadThread(shard, chapters, frame, file_name_ready_to_shard_upload)
                chapters += 1

                # delete encrypted file TODO

        # self.emit(SIGNAL("finishUpload")) # send signal to save to bucket after all filea are uploaded

        # finish_upload(self)
