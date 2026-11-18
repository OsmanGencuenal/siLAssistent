"""Prepare ALICE role search only. Role selection and submission remain manual."""
import time
from urllib.parse import urlsplit
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException,TimeoutException

class JiraAlice:
    URL="https://alice.mercedes-benz.com/access/access-request/myself"
    HOST="alice.mercedes-benz.com"
    QUERY="devottosil"
    SEARCH_LABEL="Suche nach Rollen-ID, Name oder Beschreibung"
    ROLES=("DEVOTTOSIL | Jira | ADMIN","DEVOTTOSIL | Jira | READER","DEVOTTOSIL | Jira | USER")
    SEARCH_BUTTON=".//button[@aria-label='search' or normalize-space(.)='search']"

    @classmethod
    def role_input(cls,driver):
        if urlsplit(driver.current_url).hostname!=cls.HOST:return None
        # Use the semantic role-search label, not dynamic React IDs or screen coordinates.
        fields=[]
        for field in driver.find_elements(By.CSS_SELECTOR,"input[role='combobox']"):
            if field.is_displayed() and field.is_enabled() and field.accessible_name==cls.SEARCH_LABEL:
                fields.append(field)
        if len(fields)>1:raise RuntimeError("ALICE-Rollensuche ist nicht eindeutig.")
        return fields[0] if fields else None

    @classmethod
    def search(cls,field):
        field.clear()
        field.send_keys(cls.QUERY)
        if field.get_attribute("value")!=cls.QUERY:
            raise RuntimeError("ALICE-Suchbegriff wurde nicht vollständig übernommen.")
        # The nearest search-control container has only the role field's search icon.
        scope=field.find_element(By.XPATH,"ancestor::*[.//button[@aria-label='search' or normalize-space(.)='search']][1]")
        buttons=[button for button in scope.find_elements(By.XPATH,cls.SEARCH_BUTTON) if button.is_displayed() and button.is_enabled()]
        if len(buttons)!=1:raise RuntimeError("ALICE-Suchbutton wurde nicht eindeutig gefunden.")
        buttons[0].click()

    @classmethod
    def roles_visible(cls,driver):
        if urlsplit(driver.current_url).hostname!=cls.HOST:return False
        return all(any(element.is_displayed() for element in driver.find_elements(By.XPATH,"//*[normalize-space(.)='"+role+"']")) for role in cls.ROLES)

    @classmethod
    def prepare(cls,driver,stopped,notify,interrupted=None):
        notify("role_preparing")
        try:driver.get(cls.URL)
        except TimeoutException:pass
        deadline=time.monotonic()+600
        searched=False
        last=None
        while not stopped.is_set() and time.monotonic()<deadline:
            if interrupted and interrupted():return
            try:
                field=cls.role_input(driver)
                if field is not None:
                    if not searched:
                        cls.search(field)
                        searched=True
                        deadline=time.monotonic()+120
                    if cls.roles_visible(driver):
                        notify("role_ready")
                        return
                    state="role_preparing"
                else:
                    state="role_login_required" if urlsplit(driver.current_url).hostname!=cls.HOST else "role_preparing"
                if state!=last:notify(state);last=state
            except StaleElementReferenceException:
                pass
            stopped.wait(0.5)
        if not stopped.is_set():notify("role_timeout")
