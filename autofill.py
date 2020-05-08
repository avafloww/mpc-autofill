from selenium.common.exceptions import NoAlertPresentException
from selenium.common.exceptions import NoSuchElementException
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.support.ui import Select
import time
import os
import xml.etree.ElementTree as ET
from selenium.webdriver.support.expected_conditions import invisibility_of_element
from selenium.webdriver.support.ui import WebDriverWait
from google_drive_downloader import GoogleDriveDownloader as gdd
import filetype
import threading
from requests.exceptions import ConnectionError

"""
TODO:
- Downloading too fast from Google Drive - how can we get around this?
- Handle the popup "your internet connection is slow so this'll take a while
- Would be nice to have a way of deselecting text bc sometimes the script selects a bunch of content on the page and
  it's slightly ugly
"""


def fill_cards(root):
    with webdriver.Chrome() as driver:
        driver.set_window_size(1200, 900)
        # Set implicit wait for driver
        driver.implicitly_wait(5)

        # Load Custom Game Cards (63mm x 88mm) page
        driver.get("https://www.makeplayingcards.com/design/custom-blank-card.html")

        # Select card stock
        stock_dropdown = Select(driver.find_element_by_id("dro_paper_type"))
        stock_dropdown.select_by_visible_text(root[0][2].text)

        # Select number of cards
        qty_dropdown = Select(driver.find_element_by_id("dro_choosesize"))
        qty_dropdown.select_by_value(root[0][1].text)

        # Accept current settings and move to next step
        driver.execute_script(
            "javascript:doPersonalize('https://www.makeplayingcards.com/products/pro_item_process_flow.aspx')")

        # Key in the desired number of cards, then move to the next step
        driver.switch_to.frame("sysifm_loginFrame")
        qtyField = driver.find_element_by_id("txt_card_number")
        qtyField.clear()
        qtyField.send_keys(root[0][0].text)

        # Select "different images" for front
        driver.execute_script("javascript:setMode('ImageText', 0);")
        driver.switch_to.default_content()

        # Insert card fronts
        fronts_slot = [x[1].text.strip("][").replace(" ", "").split(",") for x in root[1]]
        autofillBtn = driver.find_element_by_class_name("autoFill")
        for i in range(0, len(root[1])):
            elem = upload_card(driver, root[1][i][0].text)
            try:
                if len(fronts_slot[i]) > 1:
                    for slot in fronts_slot[i]:
                        # drag and drop card into each slot
                        drag_drop_card(driver, elem, slot)
                elif len(fronts_slot[i+1]) > 1:
                    # click autofill button
                    autofillBtn.click()
                    wait(driver)
            except IndexError:
                # click autofill button
                autofillBtn.click()
                wait(driver)

            time.sleep(0.3)

        # Page through to backs
        driver.execute_script("javascript:oDesign.setNextStep();")
        try:
            alert = driver.switch_to.alert
            alert.accept()
        except NoAlertPresentException:
            pass

        # Page over to the next step from "add text to fronts"
        wait(driver)
        driver.execute_script("javascript:oDesign.setNextStep();")

        # Select "different images" for backs
        wait(driver)
        driver.switch_to.frame("sysifm_loginFrame")

        if len(root[2]) == 0:
            # Same cardback for every card
            driver.execute_script("javascript:setMode('ImageText', 1);")
            driver.switch_to.default_content()
            autofillBtn = driver.find_element_by_class_name("autoFill")
            upload_card(driver, root[3].text)
            autofillBtn.click()
        else:
            # Different cardbacks
            driver.execute_script("javascript:setMode('ImageText', 0);")
            driver.switch_to.default_content()

            # Insert specified cardbacks
            cards_with_backs = []
            total_cards = int(root[0][0].text)
            for card in root[2]:
                # Append current cardbacks
                cards_with_backs.extend(card[1].text.strip('][').replace(" ", "").split(','))
                upload_and_insert_card(driver, card[0].text, card[1].text.strip('][').replace(" ", "").split(','))

            # Cards that need cardbacks are in range(0, total_cards) - card indexes that already have backs
            cards_with_backs = {int(x) for x in cards_with_backs}
            cards_needing_backs = [x for x in range(0, total_cards) if x not in cards_with_backs]
            upload_and_insert_card(driver, root[3].text, cards_needing_backs)

        # Page through to finalise project
        driver.execute_script("javascript:oDesign.setNextStep();")
        try:
            alert = driver.switch_to.alert
            alert.accept()
        except NoAlertPresentException:
            pass

        wait(driver)
        driver.execute_script("javascript:oDesign.setNextStep();")

        input("Press enter to finish up.")


def wait(driver):
    try:
        wait_elem = driver.find_element_by_id("sysimg_wait")
        WebDriverWait(driver, 100).until(invisibility_of_element(wait_elem))
    except NoSuchElementException:
        return


def download_card(driveID):
    filepath = os.getcwd() + "\cards\{}.png".format(driveID)
    while True:
        if os.path.exists(filepath):
            return
        try:
            gdd.download_file_from_google_drive(file_id=driveID,
                                                dest_path=filepath)
            guessed_filetype = filetype.guess(filepath)
            while not guessed_filetype:
                print("Downloading too fast - retrying")
                os.remove(filepath)
                time.sleep(60)
                gdd.download_file_from_google_drive(file_id=driveID,
                                                    dest_path=filepath,
                                                    overwrite=True)
                guessed_filetype = filetype.guess(filepath)
            return
        except ConnectionError:
            pass


def upload_card(driver, driveID):
    filepath = os.getcwd() + "\cards\{}.png".format(driveID)
    while not os.path.exists(filepath):
        time.sleep(1)

    if os.path.isfile(filepath):

        # filepath = download_card(driveID)
        num_elems = len(driver.find_elements_by_xpath("//*[contains(@id, 'upload_')]"))
        driver.find_element_by_xpath('//*[@id="uploadId"]').send_keys(filepath)

        while True:
            # Wait until the image has finished uploading
            elem = driver.find_elements_by_xpath("//*[contains(@id, 'upload_')]")
            if len(elem) > num_elems:
                print("New card uploaded")
                time.sleep(1)
                return elem[-1]

    else:
        return ValueError("Yo something broke")


def upload_and_insert_card(driver, driveID, slots):
    elem = upload_card(driver, driveID)
    if type(elem) != list:
        elem = [elem]

    # Insert card into the appropriate slots
    time.sleep(1)
    for slot in slots:
        drag_drop_card(driver, elem[-1], slot)


def drag_drop_card(driver, cardElement, slotNumber):
    elem_slot = driver.find_element_by_id("fmItem{}_0".format(slotNumber))
    elem_visible = driver.find_element_by_id("bnbox{}_0_0".format(slotNumber))
    current_y = elem_slot.location['y']
    driver.execute_script("arguments[0].scrollIntoView();", elem_slot)
    ActionChains(driver).click_and_hold(cardElement).move_to_element(elem_slot).release(elem_slot).perform()
    wait(driver)
    while driver.find_element_by_id("dnImg{}_0_0".format(slotNumber)) is None:
        time.sleep(0.3)
        ActionChains(driver).click_and_hold(cardElement).move_to_element(elem_slot).release(elem_slot).perform()
        wait(driver)


class CardDownloadThread(threading.Thread):
    def __init__(self, driveIDs):
        threading.Thread.__init__(self)
        self.driveIDs = driveIDs

    def run(self):
        print("Kicking off Google Drive downloader thread")
        for driveID in self.driveIDs:
            download_card(driveID)
        print("Downloaded all cards in the order")


class WebDriverThread(threading.Thread):
    def __init__(self, root):
        threading.Thread.__init__(self)
        self.root = root

    def run(self):
        print("Kicking off webdriver thread")
        fill_cards(self.root)


if __name__ == "__main__":
    # parse XML doc
    tree = ET.parse("cards.xml")
    root = tree.getroot()

    # retrieve google drive IDs for downloader thread
    driveIDs = [x[0].text for x in root[1]]
    driveIDs.extend([x[0].text for x in root[2]])
    driveIDs.extend([root[-1].text])

    # create each thread
    download_thread = CardDownloadThread(driveIDs=driveIDs)
    webdriver_thread = WebDriverThread(root)

    # start each thread
    download_thread.start()
    webdriver_thread.start()

    # join threads
    download_thread.join()
    webdriver_thread.join()