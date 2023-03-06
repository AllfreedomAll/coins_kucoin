"""
    Author: Israel Dryer
    Modified: 2021-12-11
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json
import threading
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from tb.kuc_main import BackMeUp
from tb.llogger import log
from tb.my_queue import login_queue
from tb.my_redis import cur_redis
import uuid
import requests
from kucoin.client import User, Market
from requests.exceptions import ReadTimeout, ConnectionError
from urllib3.exceptions import ConnectTimeoutError
from pathlib import Path

logger = log.logger
AUTH_URL = "https://test.supervpnserver.com/te/"
REDIS_PREFIX = "KUCOIN:"


# AUTH_URL = "http://127.0.0.1:8222/te/"

def get_mac_address():
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    return ":".join([mac[e:e + 2] for e in range(0, 11, 2)])


def get_inst(client):
    try:
        ret = client.get_currencies()
        if ret.status_code == 200:
            data = ret.json().get("data")
            i_list = []
            for i in data:
                v = i.get("currency")
                if v and v != 'USDT':
                    i_list.append(f"{v}-USDT")
            return i_list
        logger.error(f"获取交易对失败,{str(ret.text)}")
        return None
    except ConnectionError as e:
        logger.error(f"获取交易对失败,网络不通,{str(e)}")
        return None


def get_kucoin_bal(client):
    for i in range(3):
        try:
            ret = client.get_account_list("USDT", "trade")
            return ret
        except ConnectionError as e:
            logger.error(f"获取余额失败,网络不通,{str(e)}")
            return 0
        except ConnectTimeoutError as e:
            logger.error(f"获取余额失败,网络不通,{str(e)}")
            return 0
        except Exception as e:
            logger.error(f"获取余额失败,重试第{i}次:{str(e)}")
            continue
    logger.error("获取余额失败多次")
    return None


def ee():
    re_try = 3
    while re_try:
        try:
            re_try -= 1
            headers = {"CCP": "aug05"}
            proxy = {}
            if cur_redis.get(f"{REDIS_PREFIX}proxy_mode") == "1":
                logger.info("设置代理1080")
                proxy = {
                    "http": "socks5://127.0.0.1:1080",
                    "https": "socks5h://127.0.0.1:1080",
                }
            mac_addr = get_mac_address()
            ret = requests.post(AUTH_URL, json={"e": mac_addr}, timeout=5,
                                headers=headers, proxies=proxy)
            if ret.status_code == 200:
                res = ret.json()
                if res.get("code") == 0:
                    return res.get("data") or True
        except Exception as e:
            logger.error(f"获取验证失败:{str(e)}")
            continue
    return False


class CusThread(threading.Thread):
    def __init__(self, func, args, name=''):
        threading.Thread.__init__(self)
        self.name = name
        self.func = func
        self.args = args
        self.result = self.func(*self.args)

    def get_result(self):
        try:
            return self.result
        except Exception:
            return None


class DataEntryForm(ttk.Frame):

    def __init__(self, master):
        super().__init__(master, padding=(10, 5))
        self.pack(fill=BOTH, expand=YES)
        self.master = master
        self.sub_btn = None
        self.master.after(100, self.show_msg)
        self.api_key = ttk.StringVar(value="")
        self.secret = ttk.StringVar(value="")
        self.passphrase = ttk.StringVar(value="")
        self.record_ks_var = ttk.StringVar(value="")
        self.proxy_mode = ttk.StringVar(value="")
        if cur_redis.get(f"{REDIS_PREFIX}proxy_mode") == "1":
            self.proxy_mode.set("1")
        if cur_redis.get(f"{REDIS_PREFIX}recordKS") == "1":
            self.record_ks_var.set(1)
            k_s = cur_redis.get(f"{REDIS_PREFIX}k&s")
            if k_s:
                k_s = json.loads(k_s)
                k = k_s.get("k")
                s = k_s.get("s")
                p = k_s.get("p")
                if k:
                    self.api_key.set(k)
                if s:
                    self.secret.set(s)
                if p:
                    self.passphrase.set(p)
        # form header
        hdr_txt = "请输入相关密钥,开启代理模式设置端口1080"
        hdr = ttk.Label(master=self, text=hdr_txt, width=50)
        hdr.pack(fill=X, pady=10)

        # form entries
        self.create_form_entry("ApiKey", self.api_key)
        self.create_form_entry("Secret", self.secret)
        self.create_form_entry("Passphrase", self.passphrase)
        self.create_buttonbox()

    def record_ks(self):
        key = f"{REDIS_PREFIX}recordKS"
        cur_redis.set(key, self.record_ks_var.get())

    def switch_proxy(self):
        key = f"{REDIS_PREFIX}proxy_mode"
        cur_redis.set(key, self.proxy_mode.get())

    def create_form_entry(self, label, variable):
        """Create a single form entry"""
        container = ttk.Frame(self)
        container.pack(fill=X, expand=YES, pady=5)

        lbl = ttk.Label(master=container, text=label.title(), width=10)
        lbl.pack(side=LEFT, padx=5)

        ent = ttk.Entry(master=container, textvariable=variable)
        ent.pack(side=LEFT, padx=5, fill=X, expand=YES)

    def show_msg(self):
        while not login_queue.empty():
            content = login_queue.get()
            if content.get("error"):
                Messagebox.show_info(content.get("error"))
                self.sub_btn.configure(state=ACTIVE)
            else:
                logger.info("进入主界面")
                data = content.get("sucess")
                self.quit()
                widget_list = all_children(self.master)
                for item in widget_list:
                    item.pack_forget()
                width = 1300
                height = 700
                screen_width = self.master.winfo_screenwidth()
                screen_height = self.master.winfo_screenheight()
                window_size = f'{width}x{height}+{round((screen_width - width) / 2)}+{round((screen_height - height) / 2)}'
                self.master.geometry(window_size)

                self.master.resizable(height=True, width=True)
                instid_data = data.get("instid")
                if isinstance(instid_data, list):
                    BackMeUp(self.master, data.get("cashBal"), instids=instid_data)
                else:
                    BackMeUp(self.master, data.get("cashBal"))
                style = ttk.Style()
                style.configure("Treeview.Heading", background='olive')
                style.configure('Treeview', rowheight=20)
                self.master.mainloop()
        self.master.after(100, self.show_msg)

    def create_buttonbox(self):
        """Create the application buttonbox"""
        container = ttk.Frame(self)
        container.pack(fill=X, expand=YES, pady=(15, 10))

        self.sub_btn = ttk.Button(
            master=container,
            text="进入",
            command=self.on_submit,
            bootstyle=SUCCESS,
            width=6,
        )
        self.sub_btn.pack(side=RIGHT, padx=5)
        self.sub_btn.focus_set()

        cnl_btn = ttk.Button(
            master=container,
            text="取消",
            command=self.on_cancel,
            bootstyle=DANGER,
            width=6,
        )
        cnl_btn.pack(side=RIGHT, padx=5)

        record_ck = ttk.Checkbutton(master=container, text="记住输入", bootstyle="round-toggle",
                                    variable=self.record_ks_var,
                                    command=self.record_ks).pack(
            side=LEFT, padx=5)

        ttk.Checkbutton(master=container, text="代理模式", bootstyle="round-toggle",
                        variable=self.proxy_mode,
                        command=self.switch_proxy).pack(
            side=LEFT, padx=5)

    def check_kucoin_connect(self, api_key, secret_key, passphrase):
        try:
            logger.info("点击登录按钮")
            user_client = User(api_key, secret_key, passphrase)
            market_client = Market(api_key, secret_key, passphrase)
            logger.info("初始化client")
            bal_task = CusThread(get_kucoin_bal, (user_client,))
            inst_task = CusThread(get_inst, (market_client,))
            ee_task = CusThread(ee, ())
            logger.info("请求ku-coin...")
            bal_task.start()
            inst_task.start()
            ee_task.start()
            bal_result = bal_task.get_result()
            ee_result = ee_task.get_result()
            inst_result = inst_task.get_result()
            logger.info("请求ku-coin完成")
            logger.info(f"bal:{bal_result}")
            if not ee_result:
                login_queue.write({"error": "网络不通"})

            elif bal_result==0:
                login_queue.write({"error": "Kucoin网络不通"})
            else:
                if bal_result.status_code==200:
                    try:
                        data = bal_result.json()
                        if data.get("code") != "200000":
                            login_queue.write({"error": f"{bal_result.text}"})
                        else:
                            cashBal = data.get("data", [{}])[0].get("balance") or "0"
                            login_queue.write({"sucess": {"cashBal": cashBal, "instid": inst_result}})
                            # if cur_redis.get(f"{REDIS_PREFIX}recordKS") == "1":
                            data = {
                                "k": api_key,
                                "s": secret_key,
                                "p": passphrase,
                            }
                            cur_redis.set(f"{REDIS_PREFIX}k&s", json.dumps(data))
                    except ValueError:
                        login_queue.write({"error": f"{bal_result.text}"})
                else:
                    logger.error(f"kucoin返回错误:{bal_result.text}")
                    login_queue.write({"error": f"kucoin返回错误{bal_result.status_code}"})

        except Exception as e:
            logger.error(f"login ERROR:{e}")
            login_queue.write({"error": "Kucoin网络不通"})

    def on_submit(self):
        """Print the contents to console and return the values."""
        try:
            api_key = self.api_key.get().strip(" ").strip("\n")
            secret_key = self.secret.get().strip(" ").strip("\n")
            passphrase = self.passphrase.get().strip(" ").strip("\n")
            if not api_key or not secret_key or not passphrase:
                Messagebox.show_info(message="输入有误,请检查", position=(
                    round((screen_width - width) / 2) + 100, round((screen_height - height) / 2) + 50))
                return
            t = threading.Thread(target=self.check_kucoin_connect, args=(api_key, secret_key, passphrase))
            t.start()
            self.sub_btn.configure(state=DISABLED)
        except Exception as e:
            logger.error(f"login input error:{e}")
            Messagebox.show_info(message="输入有误或网络不通,无法连接kucoin,请检查", position=(
                round((screen_width - width) / 2) + 100, round((screen_height - height) / 2) + 50))
            return

    def on_cancel(self):
        # self.master.withdraw()

        """Cancel and close the application."""

        # os.system(r'python /Users/ling/Downloads/okex-core/tb/back_me_up.py')
        self.quit()


def all_children(window):
    _list = window.winfo_children()

    for item in _list:
        if item.winfo_children():
            _list.extend(item.winfo_children())
    return _list


if __name__ == "__main__":
    try:
        cur_redis.config_set("stop-writes-on-bgsave-error", "no")
    except:
        pass
    import os
    app = ttk.Window("Ku-Coin", "superhero", resizable=(False, False))
    imgpath = os.path.dirname(os.path.abspath(__file__))+'/ku-icon.jpeg'
    img = ttk.PhotoImage(name="icon", file=imgpath)
    app.iconphoto(False, img)
    width = 500
    height = 250
    screen_width = app.winfo_screenwidth()
    screen_height = app.winfo_screenheight()
    window_size = f'{width}x{height}+{round((screen_width - width) / 2)}+{round((screen_height - height) / 2)}'
    app.geometry(window_size)
    app.resizable(height=False, width=False)
    DataEntryForm(app)

    app.mainloop()
