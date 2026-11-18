"""Developer Compass license checks and preparation up to order review."""
import os
import threading
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

class GitLicense:
    LICENSES = "https://developer-compass.i.mercedes-benz.com/myWorkspace/licenses"
    MARKETPLACE = "https://developer-compass.i.mercedes-benz.com/marketplace"
    PRODUCT = "GitHub Enterprise User License"
    LICENSE = "GitHub Enterprise Cloud User License"
    OU = "059"
    COST_CENTER = "3059-0629"
    INTERNAL_ORDER = "305900135547"
    _lock = threading.Lock()

    @classmethod
    def browser(cls, visible=False):
        from ..silEinrichten import SilEinrichten
        options = webdriver.EdgeOptions()
        profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "siLAssistent" / "CompassProfile"
        profile.mkdir(parents=True,exist_ok=True)
        options.add_argument("--user-data-dir=" + str(profile))
        options.add_argument("--start-maximized" if visible else "--headless=new")
        if visible:
            options.add_experimental_option("detach",True)
        driver=SilEinrichten.create_edge_driver(options)
        driver.set_page_load_timeout(45)
        return driver

    @classmethod
    def classify(cls, driver):
        from urllib.parse import urlsplit
        url=urlsplit(driver.current_url)
        if url.hostname != "developer-compass.i.mercedes-benz.com" or url.path.rstrip("/") != "/myWorkspace/licenses":
            return "unknown"
        text=driver.find_element(By.TAG_NAME,"body").text
        lines={line.strip() for line in text.splitlines()}
        # Only an assigned license card with a Completed status proves possession.
        if cls.LICENSE in lines:
            cards=driver.find_elements(By.XPATH,"//*[normalize-space(text())='GitHub Enterprise Cloud User License']/parent::*[.//*[normalize-space(text())='Completed']] | //*[normalize-space(text())='GitHub Enterprise Cloud User License']/parent::*/parent::*[.//*[normalize-space(text())='Completed']]")
            if any(card.is_displayed() for card in cards):
                return "present"
        # Absence is only accepted with an explicit empty-state message.
        empty=("You have no licenses", "No licenses found", "No licenses available", "You do not have any licenses")
        if any(line in lines for line in empty) and cls.LICENSE not in lines and cls.PRODUCT not in lines:
            return "absent"
        return "unknown"

    @classmethod
    def check(cls, visible=False):
        if not cls._lock.acquire(blocking=False):
            return {"license":"unknown","reason":"Lizenzbrowser wird bereits verwendet."}
        driver=None
        keep_until_message=False
        try:
            driver=cls.browser(visible)
            driver.get(cls.LICENSES)
            state=WebDriverWait(driver,180 if visible else 20).until(lambda d: cls.classify(d) if cls.classify(d)!="unknown" else False)
            keep_until_message=visible and state=="present"
            return {"license":state, **({"_browser":driver} if keep_until_message else {})}
        except Exception:
            return {"license":"unknown","reason":"Lizenz nicht prüfbar. Anmeldung oder Seitenstruktur prüfen."}
        finally:
            if driver and not keep_until_message:
                if visible:
                    driver.service.stop()
                else:
                    driver.quit()
            cls._lock.release()

    @classmethod
    def close_confirmation_browser(cls, result):
        driver=result.pop("_browser",None)
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                # The user may already have closed this dedicated browser session.
                driver.service.stop()

    @classmethod
    def click(cls, driver, text):
        xpath="//*[self::button or self::a][normalize-space(.)='"+text+"']"
        elements=WebDriverWait(driver,40).until(lambda d:[e for e in d.find_elements(By.XPATH,xpath) if e.is_displayed() and e.is_enabled()])
        if len(elements)!=1:
            raise RuntimeError("Schaltfläche nicht eindeutig: " + text)
        elements[0].click()

    @classmethod
    def fill(cls, driver, label_prefix, value):
        labels=driver.find_elements(By.XPATH,"//label[starts-with(normalize-space(.),'"+label_prefix+"')]")
        labels=[label for label in labels if label.is_displayed()]
        if len(labels)!=1:
            raise RuntimeError("Formularfeld nicht eindeutig: " + label_prefix)
        label=labels[0]
        field_id=label.get_attribute("for")
        fields=driver.find_elements(By.ID,field_id) if field_id else label.find_elements(By.XPATH,".//input | ../input | ../div/input")
        fields=[field for field in fields if field.is_displayed() and field.is_enabled()]
        if len(fields)!=1:
            raise RuntimeError("Eingabefeld nicht eindeutig: " + label_prefix)
        field=fields[0]
        field.clear()
        field.send_keys(value)
        from selenium.webdriver.common.keys import Keys
        field.send_keys(Keys.TAB)
        if field.get_attribute("value")!=value:
            raise RuntimeError("Formularwert nicht übernommen: " + label_prefix)

    @classmethod
    def prepare_order(cls):
        if not cls._lock.acquire(blocking=False):
            raise RuntimeError("Lizenzbrowser wird bereits verwendet.")
        driver=None
        try:
            driver=cls.browser(True)
            driver.get(cls.MARKETPLACE)
            # Login may be completed by the user; never collect credentials.
            heading=WebDriverWait(driver,180).until(lambda d: next((e for e in d.find_elements(By.XPATH,"//*[normalize-space(text())='GitHub Enterprise User License']") if e.is_displayed()),False))
            cards=heading.find_elements(By.XPATH,"ancestor::*[.//button[.//*[name()='svg']]][1]")
            if len(cards)!=1:
                raise RuntimeError("Lizenzkarte nicht eindeutig. Bitte im sichtbaren Browser prüfen.")
            buttons=cards[0].find_elements(By.XPATH,".//button[.//*[name()='svg']]/*[name()='svg']/..")
            buttons=[e for e in buttons if e.is_displayed() and e.is_enabled()]
            if len(buttons)!=1:
                raise RuntimeError("Warenkorb-Schaltfläche nicht eindeutig.")
            buttons[0].click()
            checkout=WebDriverWait(driver,40).until(lambda d: next((e for e in d.find_elements(By.XPATH,"//button[contains(normalize-space(.),'Checkout')]") if e.is_displayed() and any(c.isdigit() and c!='0' for c in e.text)),False))
            checkout.click()
            panel=WebDriverWait(driver,40).until(lambda d: next((e for e in d.find_elements(By.XPATH,"//*[normalize-space(text())='Shopping Cart']/ancestor::*[.//button[normalize-space(.)='Checkout']][1]") if e.is_displayed()),False))
            if cls.PRODUCT not in panel.text:
                raise RuntimeError("GitHub-Lizenz wurde nicht im Warenkorb bestätigt.")
            # Do not carry unrelated products into the billing step.
            removals=panel.find_elements(By.XPATH,".//button[contains(@aria-label,'Delete') or contains(@aria-label,'Remove') or contains(@title,'Remove')]")
            if len(removals)>1:
                raise RuntimeError("Weitere Warenkorbpositionen vorhanden. Bitte manuell prüfen.")
            panel_buttons=[button for button in panel.find_elements(By.XPATH,".//button[normalize-space(.)='Checkout']") if button.is_displayed() and button.is_enabled()]
            if len(panel_buttons)!=1:
                raise RuntimeError("Checkout im Warenkorb nicht eindeutig.")
            panel_buttons[0].click()
            WebDriverWait(driver,40).until(lambda d: "Select license details" in d.find_element(By.TAG_NAME,"body").text)
            cls.fill(driver,"OU -",cls.OU)
            cls.fill(driver,"CC -",cls.COST_CENTER)
            cls.fill(driver,"CO -",cls.INTERNAL_ORDER)
            cls.click(driver,"Review order")
            WebDriverWait(driver,40).until(lambda d: any(e.is_displayed() for e in d.find_elements(By.XPATH,"//h1[contains(normalize-space(.),'Review')] | //h2[contains(normalize-space(.),'Review')]")))
            return {"license":"review","reason":"Bestellung vorbereitet. Bitte im Browser prüfen; noch nicht abgesendet."}
        finally:
            if driver:
                # Keep visible review/error page open, stop only the driver service.
                driver.service.stop()
            cls._lock.release()
