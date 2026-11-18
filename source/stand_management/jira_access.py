"""Read-only, session-bound Jira board access detection. No passwords or API tokens."""
import os
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

class JiraAccess:
    HOST="mercedes-benz.atlassian.net"
    SITE_ID="05dc64f1-70f7-4b24-b219-30f47e3e9585"
    BOARD_IDS={"Allgemein":45869,"Testing-Grundmotor":48241,"Testing-OBD":48242,"Testing-Sensorik":48243}

    @classmethod
    def url(cls,name):
        return f"https://{cls.HOST}/jira/software/c/projects/DEVOTTOSIL/boards/{cls.BOARD_IDS[name]}"

    @classmethod
    def browser(cls):
        from selenium import webdriver
        from ..silEinrichten import SilEinrichten
        options=webdriver.EdgeOptions()
        profile=Path(os.environ.get("LOCALAPPDATA",str(Path.home())))/"siLAssistent"/"JiraProfile"
        profile.mkdir(parents=True,exist_ok=True)
        options.add_argument("--user-data-dir="+str(profile))
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach",True)
        driver=SilEinrichten.create_edge_driver(options)
        driver.set_page_load_timeout(45)
        driver.set_script_timeout(12)
        return driver

    @classmethod
    def page_state(cls,url,text):
        parsed=urlsplit(url);body=text.casefold()
        if parsed.scheme=="https" and parsed.hostname=="id.atlassian.com" and parsed.path.rstrip("/")=="/join/user-access":
            query=parse_qs(parsed.query)
            resource=query.get("resource",[""])[0]
            destination=urlsplit(query.get("continue",[""])[0])
            valid_paths={urlsplit(cls.url(name)).path for name in cls.BOARD_IDS}
            if resource=="ari:cloud:jira::site/"+cls.SITE_ID and destination.scheme=="https" and destination.hostname==cls.HOST and destination.path.rstrip("/") in valid_paths:
                return "site_access_pending"
        if parsed.hostname in ("id.atlassian.com","login.microsoftonline.com","login.mercedes-benz.com") or any(marker in body for marker in ("einloggen, um fortzufahren","log in to continue")):
            return "login_required"
        if parsed.hostname!=cls.HOST:return "unknown"
        if any(marker in body for marker in ("sie treten jira bei","you're joining jira","you’re joining jira","joining jira")):
            return "joining"
        return "unknown"

    @classmethod
    def classify(cls,board_id,page,user,board):
        if page in ("login_required","site_access_pending"):return page
        user=user or {};board=board or {}
        authenticated=user.get("status")==200 and user.get("json") is True and user.get("authenticated") is True
        if not authenticated:
            if user.get("status")==401:return "login_required"
            if user.get("status")==429:return "rate_limited"
            if user.get("status",0)>=500:return "service_error"
            return "joining" if page=="joining" else "unknown"
        if board.get("status")==401:return "login_required"
        # Only authenticated, non-redirected Jira JSON 403 is a permission denial.
        if board.get("status")==403 and board.get("json") is True and board.get("jira_error") is True:return "denied"
        if board.get("status")==404 and board.get("json") is True and board.get("jira_error") is True:return "not_visible_or_missing"
        if board.get("status")==429:return "rate_limited"
        if board.get("status",0)>=500:return "service_error"
        if page=="joining":return "joining"
        if board.get("status")==200 and board.get("json") is True and str(board.get("id"))==str(board_id) and board.get("type") in ("scrum","kanban","simple") and board.get("private") is not True and board.get("named") is True and board.get("project")=="DEVOTTOSIL":
            return "allowed"
        return "unknown"

    @classmethod
    def snapshot(cls,driver,board_id):
        from selenium.webdriver.common.by import By
        url=driver.current_url
        phase=cls.page_state(url,driver.find_element(By.TAG_NAME,"body").text)
        if phase=="login_required" or urlsplit(url).hostname!=cls.HOST:
            return cls.classify(board_id,phase,None,None)
        result=driver.execute_async_script(r"""
            const id=arguments[0], done=arguments[arguments.length-1];
            const read=async(path,kind)=>{
                const controller=new AbortController();
                const timer=setTimeout(()=>controller.abort(),8000);
                try {
                    const r=await fetch(path,{credentials:'same-origin',redirect:'error',cache:'no-store',headers:{Accept:'application/json'},signal:controller.signal});
                    if(new URL(r.url).origin!==location.origin || new URL(r.url).pathname!==path)return {};
                    const json=(r.headers.get('content-type')||'').includes('application/json');
                    const value=json?await r.json():{};
                    return kind==='user'?{status:r.status,json,authenticated:!!value.accountId}:
                        {status:r.status,json,id:value.id,type:value.type,private:value.isPrivate,named:typeof value.name==='string' && value.name.trim().length>0,project:value.location?.projectKey,jira_error:Array.isArray(value.errorMessages) || (!!value.errors && typeof value.errors==='object')};
                } catch(e){return {status:0,json:false};}
                finally{clearTimeout(timer);}
            };
            Promise.all([read('/rest/api/3/myself','user'),read('/rest/agile/1.0/board/'+id,'board')])
                .then(([user,board])=>done({user,board})).catch(()=>done({}));
        """,int(board_id)) or {}
        return cls.classify(board_id,phase,result.get("user"),result.get("board"))
