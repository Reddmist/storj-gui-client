import xml.etree.cElementTree as ET
from log_manager import logger

ACCOUNT_FILE = "storj_account_conf.xml"


class AccountManager:

    def __init__(self, login_email=None, password=None):
        self.login_email = login_email
        self.password = password

    def save_account_credentials(self):
        root = ET.Element("account")
        doc = ET.SubElement(root, "credentials")

        ET.SubElement(doc, "login_email").text = str(self.login_email)
        ET.SubElement(doc, "password").text = str(self.password)
        ET.SubElement(doc, "logged_in").text = "1"
        tree = ET.ElementTree(root)
        tree.write("storj_account_conf.xml")

    def if_logged_in(self):
        """Return True if user has already logged in with these credentials"""
        logged_in = "0"
        try:
            et = ET.parse("storj_account_conf.xml")
            for tags in et.iter('logged_in'):
                logged_in = tags.text
        except IOError:
            logged_in = "0"
            logger.error("Error in Account Manager login")
            logger.error("Function: if_logged_in")
            logger.error("Credentials file not existing")
            return False

        if logged_in == "1":
            return True
        else:
            return False

    def logout(self):
        logger.debug("TODO")
        logger.debug("1")

    def get_user_password(self):
        password = ""
        try:
            et = ET.parse("storj_account_conf.xml")
            for tags in et.iter('password'):
                password = tags.text
        except IOError:
            logger.error("Error in Account Manager get password")
            logger.error("Credentials file not existing")
        return password

    def get_user_email(self):
        email = ""
        try:
            et = ET.parse("storj_account_conf.xml")
            for tags in et.iter('login_email'):
                email = tags.text
        except IOError:
            logger.error("Error in Account Manager get email")
            logger.error("Credentials file not existing")
        return email
