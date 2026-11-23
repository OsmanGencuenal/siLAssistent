"""Developer Compass license checks and preparation up to order review."""
import os
import threading
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException,ElementClickInterceptedException,ElementNotInteractableException,StaleElementReferenceException

class GitLicense:
    LICENSES = "https://developer-compass.i.mercedes-benz.com/myWorkspace/licenses"
    MARKETPLACE = "https://developer-compass.i.mercedes-benz.com/marketplace"
    PRODUCT = "GitHub Enterprise User License"
    LICENSE = "GitHub Enterprise Cloud User License"
    OU = "059"
    COST_CENTER = "3059-0629"
    INTERNAL_ORDER = "305900135547"
    _lock = threading.Lock()
    _visible_browser = None
    PROFILE_PENDING_MESSAGE = ("Die Profil-/E-Mail-Bestätigung in Developer Compass ist noch offen. Die Browsersitzung bleibt geöffnet. "
                               "Bestätigen Sie die E-Mail bzw. vervollständigen Sie Ihr Profil und klicken Sie anschließend erneut auf Git User Lizenz beantragen.")
    PROFILE_WAIT_SECONDS = 900
    PROFILE_MESSAGE = ("Developer Compass benötigt zuerst die Bestätigung Ihres Profils bzw. Ihrer E-Mail-Adresse. "
                       "Öffnen Sie die Mail von Developer Compass und klicken Sie selbst auf Confirm my email address. "
                       "Kehren Sie danach zu diesem Hinweis zurück und klicken Sie auf Bestätigt – weiter. "
                       "Die Lizenzprüfung und der Antrag werden anschließend in derselben Browsersitzung fortgesetzt.")

    @classmethod
    def browser(cls, visible=False):
        from ..silEinrichten import SilEinrichten
        if visible and cls.live_browser():return cls._visible_browser
        options = webdriver.EdgeOptions()
        profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "siLAssistent" / "CompassProfile"
        profile.mkdir(parents=True,exist_ok=True)
        address=cls.debugger_address(profile) if visible else None
        if address:options.add_experimental_option("debuggerAddress",address)
        else:options.add_argument("--user-data-dir=" + str(profile))
        options.add_argument("--start-maximized" if visible else "--headless=new")
        if visible:
            options.add_experimental_option("detach",True)
        driver=SilEinrichten.create_edge_driver(options)
        driver.set_page_load_timeout(45)
        if visible:cls._visible_browser=driver
        return driver

    @classmethod
    def classify(cls, driver):
        from urllib.parse import urlsplit
        current=driver.current_url
        if not isinstance(current,str):return "unknown"
        url=urlsplit(current)
        if url.hostname=="developer-compass.i.mercedes-benz.com" and url.path.rstrip('/').startswith('/profile'):
            text=driver.find_element(By.TAG_NAME,"body").text
            if not isinstance(text,str):return "unknown"
            lowered=text.casefold()
            if any(marker in lowered for marker in ('email verification needed','confirm your email address','verify your email address','e-mail-adresse bestätigen','e-mail bestätigen')):
                return "profile_verification_required"
            return "profile_setup_required" if 'profile settings' in lowered or 'personal settings' in lowered else "unknown"
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
        empty=("You have no licenses", "No licenses found", "No licenses available", "You do not have any licenses", "Oh, no licenses yet!")
        if any(line in lines for line in empty) and cls.LICENSE not in lines and cls.PRODUCT not in lines:
            return "absent"
        return "unknown"

    @classmethod
    def live_browser(cls):
        driver=cls._visible_browser
        if driver is None:return False
        try:
            if isinstance(driver.session_id,str) and driver.window_handles:return True
        except Exception:pass
        cls._visible_browser=None
        return False

    @classmethod
    def debugger_address(cls,profile):
        # Reattach only to our dedicated Compass profile, never another Edge.
        import psutil
        try:
            port=int((profile/'DevToolsActivePort').read_text().splitlines()[0])
            if not 0<port<65536:return None
            expected=os.path.normcase(str(profile.resolve()))
            for process in psutil.process_iter(['name','cmdline']):
                if (process.info['name'] or '').casefold()!='msedge.exe':continue
                args=process.info['cmdline'] or []
                values=[arg.split('=',1)[1].strip('"') for arg in args if arg.startswith('--user-data-dir=')]
                if not any(os.path.normcase(str(Path(value).resolve()))==expected for value in values):continue
                if any(item.status=='LISTEN' and item.laddr.port==port and item.laddr.ip in ('127.0.0.1','::1') for item in process.net_connections('tcp')):
                    return '127.0.0.1:'+str(port)
        except (OSError,ValueError,IndexError,psutil.Error):pass
        return None

    @classmethod
    def diagnostic(cls,stage,driver=None,error=None):
        from ..core.runtime import Runtime
        import json,time
        from urllib.parse import urlsplit
        event={'time':time.strftime('%Y-%m-%d %H:%M:%S'),'stage':stage}
        if driver is not None:
            try:
                url=urlsplit(driver.current_url)
                event['page']=url.scheme+'://'+str(url.hostname)+url.path
            except Exception:pass
        if error is not None:
            event['error_type']=type(error).__name__
            # Do not put authentication URLs/tokens in the support diagnostic.
            import re
            event['error']=re.sub(r'https?://[^\s]+','[URL]',str(error))[:800]
        try:
            root=Runtime.log_root()
            (root/'git_license_diagnose.json').write_text(json.dumps(event,indent=2),encoding='utf-8')
            with (root/'git_license.log').open('a',encoding='utf-8') as log:log.write(json.dumps(event)+'\n')
        except OSError:pass

    @classmethod
    def profile_confirmation(cls,driver,notify,deadline):
        import time
        cls.diagnostic('profile_verification_required',driver)
        if notify is None:return False
        resume=threading.Event();cancel=threading.Event()
        notify({'license':'profile_verification_required','reason':cls.PROFILE_MESSAGE,'resume':resume,'cancel':cancel})
        while time.monotonic()<deadline:
            if cancel.is_set():return False
            if resume.wait(.25):
                cls.diagnostic('profile_recheck_requested',driver)
                return True
            if not driver.window_handles:return False
        cls.diagnostic('profile_verification_pending',driver)
        return False

    @classmethod
    def check(cls, visible=False, for_order=False, notify=None):
        if not cls._lock.acquire(blocking=False):
            return {"license":"unknown","reason":"Lizenzbrowser wird bereits verwendet."}
        driver=None
        try:
            if not visible and cls.live_browser():
                return {'license':'unknown','reason':'Der sichtbare Lizenzbrowser wird für einen manuellen Schritt verwendet.'}
            driver=cls.browser(visible)
            driver.get(cls.LICENSES)
            import time
            deadline=time.monotonic()+cls.PROFILE_WAIT_SECONDS
            while True:
                state=WebDriverWait(driver,180 if visible else 20).until(lambda d:state if (state:=cls.classify(d))!="unknown" else False)
                cls.diagnostic('license_'+state,driver)
                if state in ('profile_verification_required','profile_setup_required'):
                    if not visible or not cls.profile_confirmation(driver,notify,deadline):
                        return {'license':'profile_pending','reason':cls.PROFILE_PENDING_MESSAGE}
                    # Email links may open in Outlook's default browser. Recheck
                    # server-side profile readiness in this exact session.
                    driver.get(cls.LICENSES)
                    continue
                return {"license":state, **({"_browser":driver} if visible and (state=="present" or (for_order and state=="absent")) else {})}
        except Exception as error:
            cls.diagnostic('license_check_failed',driver,error)
            return {"license":"unknown","reason":"Lizenz nicht prüfbar. Bitte Anmeldung, Profilbestätigung und Verbindung prüfen. Details: git_license.log."}
        finally:
            try:
                if driver and not visible:driver.quit()
                elif driver:cls._visible_browser=driver
            except Exception as error:cls.diagnostic('license_browser_cleanup_failed',driver,error)
            finally:cls._lock.release()

    @classmethod
    def close_confirmation_browser(cls, result):
        driver=result.pop("_browser",None)
        if driver is not None:
            if cls._visible_browser is driver:cls._visible_browser=None
            try:
                driver.quit()
            except Exception:
                # The user may already have closed this dedicated browser session.
                try:driver.service.stop()
                except Exception as error:cls.diagnostic('license_browser_cleanup_failed',driver,error)

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
    def catalog(cls,driver):
        # Both the old catalog and the new empty-license overview are supported.
        def ready(d):
            headings=[e for e in d.find_elements(By.XPATH,"//*[normalize-space(text())='"+cls.PRODUCT+"']") if e.is_displayed()]
            searches=[e for e in d.find_elements(By.XPATH,"//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search') or @type='search']") if e.is_displayed() and e.is_enabled()]
            additions=[e for e in d.find_elements(By.XPATH,"//*[self::button or self::a][contains(normalize-space(.),'Add licenses to your profile') or normalize-space(.)='Add license' or normalize-space(.)='Add licenses']") if e.is_displayed() and e.is_enabled()]
            return (headings,searches,additions) if headings or searches or additions else False
        headings,searches,additions=WebDriverWait(driver,180).until(ready)
        if additions and not headings and not searches:
            additions[0].click()
            headings,searches,_=WebDriverWait(driver,40).until(lambda d:result if (result:=ready(d)) and (result[0] or result[1]) else False)
        if searches:
            if len(searches)!=1:raise RuntimeError("Lizenzsuche nicht eindeutig.")
            from selenium.webdriver.common.keys import Keys
            searches[0].clear();searches[0].send_keys("git");searches[0].send_keys(Keys.ENTER)
        return WebDriverWait(driver,40).until(lambda d:next((e for e in d.find_elements(By.XPATH,"//*[normalize-space(text())='"+cls.PRODUCT+"']") if e.is_displayed()),False))

    @classmethod
    def add_to_cart(cls,heading):
        cards=heading.find_elements(By.XPATH,"ancestor::*[.//*[self::button or self::a][.//*[local-name()='svg' or local-name()='mat-icon'] or contains(@aria-label,'cart') or contains(@title,'cart')]][1]")
        if len(cards)!=1:raise RuntimeError("Lizenzkarte nicht eindeutig. Bitte im sichtbaren Browser prüfen.")
        candidates=cards[0].find_elements(By.XPATH,".//*[self::button or self::a][.//*[local-name()='svg' or local-name()='mat-icon'] or contains(@aria-label,'cart') or contains(@title,'cart')]")
        visible=[e for e in candidates if e.is_displayed()]
        carts=[e for e in visible if 'cart' in ((e.get_attribute('aria-label') or '')+' '+(e.get_attribute('title') or '')+' '+e.text).casefold()]
        if not carts:
            carts=[e for e in visible if not e.text.strip()]
        if len(carts)!=1:raise RuntimeError("Warenkorb-Schaltfläche nicht eindeutig.")
        # A disabled cart may mean this exact product is already selected.
        if carts[0].is_enabled():carts[0].click()

    CHECKOUT_MESSAGE="BITTE KLICKEN SIE IM BROWSER AUF DEN CHECKOUT-BUTTON. DER ASSISTENT FÄHRT ANSCHLIESSEND AUTOMATISCH FORT."

    @classmethod
    def cart_panel(cls,driver):
        panels=driver.find_elements(By.XPATH,"//*[normalize-space(text())='Shopping Cart']/ancestor::*[.//*[self::button or self::a][contains(normalize-space(.),'Checkout')]][1]")
        return next((panel for panel in panels if panel.is_displayed() and cls.PRODUCT in panel.text),False)

    @classmethod
    def checkout_to_details(cls,driver,notify=None):
        try:
            panel=cls.cart_panel(driver)
            if not panel:
                checkout=WebDriverWait(driver,40).until(lambda d:next((e for e in d.find_elements(By.XPATH,"//*[self::button or self::a][contains(normalize-space(.),'Checkout')]") if e.is_displayed() and e.is_enabled() and any(c.isdigit() and c!='0' for c in e.text)),False))
                checkout.click()
                # The heading can appear before the asynchronously loaded products.
                panel=WebDriverWait(driver,40).until(cls.cart_panel)
            if cls.PRODUCT not in panel.text:raise TimeoutException("GitHub-Lizenz im Warenkorb noch nicht geladen.")
            removals=panel.find_elements(By.XPATH,".//button[contains(@aria-label,'Delete') or contains(@aria-label,'Remove') or contains(@title,'Remove')]")
            if len(removals)>1:raise RuntimeError("Weitere Warenkorbpositionen vorhanden. Bitte manuell prüfen.")
            buttons=[e for e in panel.find_elements(By.XPATH,".//*[self::button or self::a][contains(normalize-space(.),'Checkout')]") if e.is_displayed() and e.is_enabled()]
            if len(buttons)!=1:raise TimeoutException("Checkout im Warenkorb noch nicht eindeutig verfügbar.")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});",buttons[0])
            buttons[0].click()
            WebDriverWait(driver,40).until(lambda d:"Select license details" in d.find_element(By.TAG_NAME,"body").text)
            return True
        except (TimeoutException,ElementClickInterceptedException,ElementNotInteractableException,StaleElementReferenceException):
            if notify is None:return False
            notify({"license":"checkout_required","reason":cls.CHECKOUT_MESSAGE})
            # Keep this session alive while the user clicks in the browser.
            WebDriverWait(driver,180).until(lambda d:"Select license details" in d.find_element(By.TAG_NAME,"body").text)
            return True

    @classmethod
    def prepare_order(cls, driver=None, notify=None):
        if not cls._lock.acquire(blocking=False):
            raise RuntimeError("Lizenzbrowser wird bereits verwendet.")
        try:
            if driver is None:
                driver=cls.browser(True)
                driver.get(cls.MARKETPLACE)
            # Direct orders can also be redirected to profile verification.
            import time
            deadline=time.monotonic()+cls.PROFILE_WAIT_SECONDS
            while cls.classify(driver) in ('profile_verification_required','profile_setup_required'):
                if not cls.profile_confirmation(driver,notify,deadline):
                    return {'license':'profile_pending','reason':cls.PROFILE_PENDING_MESSAGE}
                driver.get(cls.MARKETPLACE)
            # Login may be completed by the user; never collect credentials.
            heading=cls.catalog(driver)
            cls.add_to_cart(heading)
            if not cls.checkout_to_details(driver,notify=notify):
                return {"license":"checkout_required","reason":cls.CHECKOUT_MESSAGE}
            cls.fill(driver,"OU -",cls.OU)
            cls.fill(driver,"CC -",cls.COST_CENTER)
            cls.fill(driver,"CO -",cls.INTERNAL_ORDER)
            cls.click(driver,"Review order")
            WebDriverWait(driver,40).until(lambda d: any(e.is_displayed() for e in d.find_elements(By.XPATH,"//h1[contains(normalize-space(.),'Review')] | //h2[contains(normalize-space(.),'Review')]")))
            return {"license":"review","reason":"Bitte im Browser die Nutzungsbedingungen akzeptieren und anschließend auf Submit Order klicken. Die Bestellung wurde noch nicht abgesendet."}
        except Exception as error:
            cls.diagnostic('license_order_failed',driver,error)
            raise
        finally:
            if driver:
                # Keep the live session for retries/manual review; stopping only
                # the service strands a detached Edge with a locked profile.
                cls._visible_browser=driver
            cls._lock.release()
