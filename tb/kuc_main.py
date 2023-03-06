import json
import logging
import threading
import time
from pathlib import Path
from tkinter.filedialog import askdirectory
from tkinter.scrolledtext import ScrolledText
from operator import itemgetter
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.style import Bootstyle
import datetime
from tb.my_queue import domain_queue as main_queue
from tb.my_redis import cur_redis
from tb.llogger import PyLogger
from ttkbootstrap.dialogs.dialogs import Messagebox
import math
from tb.instid_backup import instid_list
from kucoin.client import Trade, User

log = PyLogger('ku_coin.log', level='debug')

PATH = Path(__file__).parent / 'assets'
REDIS_PREFIX = "KUCOIN:"
EVENT_START_TO = 1
EVENT_STDOUT = 2
EVENT_REQ_INFO = 3
EVENT_MAKER_SUCCESS = 4
EVENT_ = 3
# redis key
HASH_ARGS_RECORD_KEY = f"{REDIS_PREFIX}:record_args"  # hash record args
RECORD_SWITCH_KEY = f"{REDIS_PREFIX}:main_record"  # record switch
KUCOIN_API_KEY = f"{REDIS_PREFIX}k&s"


class BackMeUp(ttk.Frame):

    def set_value_before_choose(self):
        """
        选择前根据文本框的内容筛选符合条件的数据
        :return:
        """

        global base_server_data
        new_select_data = []
        for i in self.instids:
            try:
                c_u = self.getvar("instId") or ""
            except:
                c_u = ""
            if c_u and c_u.upper() in i:  # 关键字在该选项中则追加到新的list中
                new_select_data.append(i)
        if new_select_data:
            self.lbl_instId["value"] = new_select_data  # 重新给下拉框赋值

    def switch_lbl_state(self, state):
        self.lbl_af_stop.configure(state=state)
        self.lbl_instId.configure(state=state)
        self.px_enter.configure(state=state)
        self.sz_entry.configure(state=state)
        self.buy_r.configure(state=state)
        self.sell_r.configure(state=state)
        self.start_btn.configure(state=state)
        self.maker_stop.configure(state=state)
        self.lbl_bt.configure(state=state)
        if state == DISABLED:
            self.switch_update_order = 0.5
            self.switch_update_bal = 0.5
        else:
            self.switch_update_order = 1
            self.switch_update_bal = 1

    def _update_balance(self):
        while self.switch_update_bal:
            try:
                now = time.time()
                # log.logger.info("开始更新余额")
                ret = self.accountAPI.get_account_list("USDT", "trade")
                # log.logger.info(f"更新余额耗时:{time.time() - now},ret:{ret.text}")
                ret = ret.json()
                code = ret.get("code")
                if code == "200000":
                    data = ret.get("data")
                    try:
                        cashBal = data[0].get("balance") or "0"
                    except:
                        cashBal = "0"
                    self.cash_balance = cashBal
                    self.setvar('balance', "%.6f" % float(self.cash_balance) + " USDT")
                else:
                    main_queue.put({"type": EVENT_STDOUT, "data": f"更新余额失败:{ret}", "tag": "info"})
            except Exception as e:
                log.logger.error(f"更新余额失败:{e}")
            finally:
                time.sleep(self.switch_update_bal)

    def _update_order(self):
        while self.switch_update_order:
            try:
                now = time.time()
                # log.logger.info("开始更新订单")
                if self.nb.index(self.nb.select()) == 0:
                    ret = self.tradeAPI.get_order_list(status="active")
                    tv = self.tv
                else:
                    ret = self.tradeAPI.get_order_list()
                    tv = self.tv2
                # log.logger.info(f"更新订单耗时:{time.time() - now},ret:{ret.text}")
                ret = ret.json()
                code = ret.get("code")
                if code == "200000":
                    data = ret.get("data").get("items")
                    sorted(data, key=itemgetter("createdAt"))
                    for i in tv.get_children():
                        tv.delete(i)
                    row_number = 0
                    for i in data[::-1]:
                        ctime = int(i.get("createdAt"))
                        ctime_format = datetime.datetime.fromtimestamp(ctime / 1000).strftime("%Y-%m-%d %H:%M:%S")
                        side = i.get("side")
                        side = "买入" if side == "buy" else "卖出"
                        instId = i.get("symbol")
                        instId_sp = instId.split("-")
                        b1, b2 = instId_sp[0], instId_sp[1]
                        order_state = "未成交"
                        size = i.get("size")  # 委托数量
                        price = i.get("price")  # 委托价格
                        dealSize = i.get("dealSize")  # 成交数量
                        dealFunds = i.get("dealFunds")  # 已成交价格
                        dealFunds_avg = "0"
                        if dealSize != "0":
                            order_state = "部分成交"
                            dealFunds_avg = "%.6f" % (float(dealFunds) / float(dealSize))
                        if size == dealSize:
                            order_state = "完全成交"
                        if i.get("cancelExist"):
                            order_state = "已取消"
                        # ['委托时间', '品种', '方向', '成交均价', '委托价', '已成交数量', '委托总量', '已成交价值', '状态']

                        tv.insert("", 0, row_number, values=(
                            ctime_format,  # 委托时间
                            instId,  # 品种
                            side,  # 方向
                            dealFunds_avg,  # 成交均价
                            f'{price} {b2}',  # 委托价
                            f'{dealSize} {b1}',  # 已成交数量
                            f'{size} {b1}',  # 委托总量
                            dealFunds,  # 已成交价值
                            order_state,  # 状态
                            ctime,))
                        row_number += 1
                else:
                    log.logger.error(f"更新订单失败:{ret.text}")
            except Exception as e:
                log.logger.error(f"更新订单失败:{e}")
            finally:
                time.sleep(self.switch_update_order)

    def queue_execute(self, times=0):
        if self.start_ts:
            if times % 20 == 0:
                dt = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
                self.st_view.insert(INSERT,
                                    f'{dt} 请求次数{self.success_times + self.failed_times},失败请求:{self.failed_times}\n')
        while not main_queue.empty():
            content = main_queue.get()
            event_type = content.get("type")
            data = content.get("data")
            tag = content.get("tag")
            if event_type == EVENT_START_TO:
                t = threading.Thread(target=self.start_to_maker_order, args=(data,))
                t.start()
                break
            elif event_type == EVENT_STDOUT:
                dt = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
                self.st_view.insert(END, f'{dt} {data}\n', tag)
                self.st_view.see(END)
                break
            elif event_type == EVENT_MAKER_SUCCESS:
                dt = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
                self.st_view.insert(END, f'{dt} {data}\n', "success")
                self.st_view.see(END)
                break
            elif event_type == EVENT_REQ_INFO and self.start_ts:
                dt = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
                self.st_view.insert(END, f'{dt} {data}\n', 'info')
                self.st_view.see(END)

        times += 1
        self.after(100, self.queue_execute, times)

    def init_args(self):
        if cur_redis.get(RECORD_SWITCH_KEY) == "1":
            data = cur_redis.hgetall(HASH_ARGS_RECORD_KEY)
            px = float(data.get("price", 0))
            sz = float(data.get("size", 0))
            side = 0 if data.get("side") == "buy" else 1
            self.stop_success.set(int(data.get("stop_success", 0)))
            self.setvar("instId", data.get("symbol", ""))
            self.setvar("px", px)
            self.setvar("sz", sz)
            self.setvar("stop_ms", int(data.get("stop_af_ts", 0)))
            self.site.set(side)
            self.setvar('allz', px * sz)

    def _cancel_order(self):
        try:
            ret = self.tradeAPI.cancel_all_orders()
            ret = ret.json()
            code = ret.get("code")
            order_ids = []
            if code == "200000":
                data = ret.get("data", {}).get("cancelledOrderIds")
                print(data)
                order_count = len(data)
                if not order_count:
                    main_queue.put({"type": EVENT_STDOUT, "data": f"无订单可撤单", "tag": "info"})
                    return
                main_queue.put({"type": EVENT_STDOUT, "data": f"撤单成功:{order_count}条", "tag": "success"})
                for i in self.tv.get_children():
                    self.tv.delete(i)
            else:
                main_queue.put({"type": EVENT_STDOUT, "data": f"撤单请求失败:{ret}", "tag": "info"})
        except Exception as e:
            main_queue.put({"type": EVENT_STDOUT, "data": f"撤单请求失败:{str(e)}", "tag": "info"})

    def cancel_order(self):
        r = Messagebox.yesno("确认撤单？", position=(self.winfo_pointerx(), self.winfo_pointery() - 130))
        if r == "Yes" or r == "确认":
            main_queue.put({"type": EVENT_STDOUT, "data": f"正在撤单"})
            t = threading.Thread(target=self._cancel_order)
            t.start()

    def __init__(self, master, cashBal=0, bal=0, instids=[], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instids = instids or instid_list
        self.tv_items = []
        self.switch_update_order = 10
        self.switch_update_bal = 10
        self.acc_balance = bal
        self.cash_balance = "%.6f" % float(cashBal)
        self.pack(fill=BOTH, expand=YES)
        self.col_ = {'委托时间': 90, '品种': 27, '方向': 0, '成交均价': 85, '委托价': 70, '已成交数量': 40, '委托总量': 40,
                     '已成交价值': 70, '状态': 0}
        self.site = ttk.IntVar()
        self.stop_success = ttk.IntVar()
        self.record_args = ttk.IntVar()
        if cur_redis.get(RECORD_SWITCH_KEY) == "1":
            self.record_args.set(1)
        else:
            self.record_args.set(0)
        self.start_ts = 0
        self.success_times = 0
        self.failed_times = 0
        self.after(10, self.queue_execute)
        k_s = cur_redis.get(KUCOIN_API_KEY)
        k_s = json.loads(k_s)
        self.k = k_s.get("k")
        self.s = k_s.get("s")
        self.p = k_s.get("p")
        self.tradeAPI = Trade(key=self.k, secret=self.s, passphrase=self.p)
        self.accountAPI = User(key=self.k, secret=self.s, passphrase=self.p)

        image_files = {
            'properties-dark': 'icons8_settings_24px.png',
            'properties-light': 'icons8_settings_24px_2.png',
            'add-to-backup-dark': 'icons8_add_folder_24px.png',
            'add-to-backup-light': 'icons8_add_book_24px.png',
            'stop-backup-dark': 'icons8_cancel_24px.png',
            'stop-backup-light': 'icons8_cancel_24px_1.png',
            'play': 'icons8_play_24px_1.png',
            'refresh': 'icons8_refresh_24px_1.png',
            'stop-dark': 'icons8_stop_24px.png',
            'stop-light': 'icons8_stop_24px_1.png',
        }

        self.photoimages = []
        imgpath = Path(__file__).parent / 'assets'
        for key, val in image_files.items():
            _path = imgpath / val
            self.photoimages.append(ttk.PhotoImage(name=key, file=_path))
        # TOP 1 buttonbar start
        buttonbar = ttk.Frame(self, style='primary.TFrame')
        buttonbar.pack(fill=X, pady=0, side=TOP)

        ## backup
        _func = self.start_to
        self.start_btn = ttk.Button(
            master=buttonbar,
            text='开始挂单',
            image='play',
            compound=LEFT,
            command=_func,
            bootstyle=SUCCESS,

        )
        self.start_btn.pack(side=LEFT, ipadx=5, ipady=5, padx=0, pady=0)

        btn = ttk.Button(
            master=buttonbar,
            text='结束挂单',
            image='stop-light',
            compound=LEFT,
            command=self.stop_button,
            bootstyle=DANGER
        )
        btn.pack(side=LEFT, ipadx=5, ipady=5, padx=0, pady=0)

        # settings
        self.lbl_bt = ttk.Button(
            master=buttonbar,
            text='一键撤单',
            image='refresh',
            compound=LEFT,
            command=self.cancel_order,
            bootstyle=DARK
        )
        self.lbl_bt.pack(side=LEFT, ipadx=5, ipady=5, padx=0, pady=0)
        # TOP 1 buttonbar end ---------------------------------

        # TOP 2 Frame start ----------------------------------
        top2_frame = ttk.Frame(self, style='bg.TFrame')
        top2_frame.pack(fill=X, pady=0, side=TOP)

        # left panel
        left_panel = ttk.Frame(top2_frame, style='bg.TFrame')
        left_panel.pack(side=LEFT, fill=Y)

        ## backup summary (collapsible)
        bus_cf = CollapsingFrame(left_panel)
        bus_cf.pack(fill=X, pady=1)

        ## container
        bus_frm = ttk.Frame(bus_cf, padding=5)
        bus_frm.columnconfigure(1, weight=1)
        bus_cf.add(
            child=bus_frm,
            title='挂单操作',
            bootstyle=SECONDARY)
        digit_func = bus_frm.register(self.validate_number)
        alpha_func = bus_frm.register(self.validate_alpha)
        ## destination
        lbl = ttk.Label(bus_frm, text='交易对:')
        lbl.grid(row=0, column=0, sticky=W, pady=2)
        self.lbl_instId = ttk.Combobox(
            bus_frm,
            textvariable='instId',
            values=self.instids,
            postcommand=self.set_value_before_choose
        )
        self.lbl_instId.grid(row=0, column=1, sticky=EW, padx=5, pady=2)
        # self.setvar('destination', 'd:/test/')

        ## last run
        lbl = ttk.Label(bus_frm, text='单价:')
        lbl.grid(row=1, column=0, sticky=W, pady=2)
        self.px_enter = ttk.Entry(bus_frm, textvariable='px', validate="focus", validatecommand=(digit_func, '%P'))
        self.px_enter.bind('<FocusOut>', self.check_all_px)
        self.px_enter.grid(row=1, column=1, sticky=EW, padx=5, pady=2)
        # self.setvar('px', '14.06.2021 19:34:43')

        ## files Identical
        lbl = ttk.Label(bus_frm, text='数量:')
        lbl.grid(row=2, column=0, sticky=W, pady=2)
        self.sz_entry = ttk.Entry(bus_frm, textvariable='sz', validate="focus", validatecommand=(digit_func, '%P'))
        self.sz_entry.bind('<FocusOut>', self.check_all_px)
        self.sz_entry.grid(row=2, column=1, sticky=EW, padx=5, pady=2)
        # sz_entry.configure(state=DISABLED)
        # self.setvar('filesidentical', '15%')

        ## files Identical
        lbl = ttk.Label(bus_frm, text='总价:')
        lbl.grid(row=3, column=0, sticky=W, pady=2)
        lbl = ttk.Label(bus_frm, textvariable='allz')
        lbl.grid(row=3, column=1, sticky=EW, pady=2)
        self.setvar('allz', 0)
        # lbl = ttk.Label(bus_frm, text='总价:')
        # lbl.grid(row=3, column=0, sticky=W, pady=2)
        # lbl = ttk.Entry(bus_frm, textvariable='allz')
        # lbl.grid(row=3, column=1, sticky=EW, padx=5, pady=2)
        self.setvar("stop_ms", 0)
        lbl = ttk.Label(bus_frm, text='多少秒后停止:')
        lbl.grid(row=4, column=0, sticky=W, pady=2)
        self.lbl_af_stop = ttk.Entry(bus_frm, textvariable='stop_ms', validate="focus",
                                     validatecommand=(digit_func, '%P'))
        self.lbl_af_stop.grid(row=4, column=1, sticky=EW, padx=5, pady=2)

        # ## files Identical
        # lbl1 = ttk.Frame(bus_frm)
        # lbl1.grid(row=4, column=0, columnspan=2,sticky=W, pady=2)
        #
        # lbl = ttk.Label(lbl1, text='可用余额:')
        # lbl.grid(row=0, column=0, sticky=W, pady=2)
        # lbl = ttk.Combobox(lbl1, )
        # lbl.grid(row=0, column=1, sticky=W, padx=5, pady=2)
        # lbl = ttk.Label(lbl1, text='09090909000000000000000000')
        # lbl.grid(row=0, column=2, sticky=S, padx=5, pady=2)

        ## section separator
        sep = ttk.Separator(bus_frm, bootstyle=SECONDARY)
        sep.grid(row=5, column=0, columnspan=2, pady=10, sticky=EW)

        # 买 or 卖

        self.buy_r = ttk.Radiobutton(bus_frm, text="买", variable=self.site, value=0)
        self.buy_r.grid(row=6, column=0, sticky=W, pady=2)
        self.sell_r = ttk.Radiobutton(bus_frm, text="卖", variable=self.site, value=1)
        self.sell_r.grid(row=6, column=1, sticky=E, pady=2)

        # maker success stop
        self.maker_stop = ttk.Checkbutton(bus_frm, text="挂单成功后停止", variable=self.stop_success)
        self.maker_stop.grid(row=7, column=0, sticky=W, pady=20)
        self.maker_stop.invoke()

        record_arg = ttk.Checkbutton(bus_frm, text="记住参数", variable=self.record_args, command=self.record_args_redis)
        record_arg.grid(row=8, column=0, sticky=W, pady=10)
        # record_arg.invoke()
        # balance
        lbl = ttk.Label(bus_frm, text='余额:')
        lbl.grid(row=9, column=0, sticky=W, pady=2)
        lbl = ttk.Label(bus_frm, textvariable='balance')
        lbl.grid(row=9, column=1, sticky=W, pady=2)
        self.setvar('balance', self.cash_balance)

        # self.lbl_bt = ttk.Button(
        #     bus_frm,
        #     text="一键撤单",
        #     command=self.cancel_order
        # )
        # self.lbl_bt.grid(row=10, column=0, sticky=W, pady=20)

        # right panel
        right_panel = ttk.Frame(top2_frame, padding=(2, 1))
        right_panel.pack(side=RIGHT, fill=BOTH, expand=YES)

        ## scrolling text output
        scroll_cf = CollapsingFrame(right_panel)
        scroll_cf.pack(fill=BOTH, expand=YES)

        output_container = ttk.Frame(scroll_cf, padding=1)
        _value = '日志'
        self.setvar('scroll-message', _value)
        self.st_view = ScrolledText(output_container, foreground='red')
        self.st_view.tag_config("info", foreground='red')
        self.st_view.tag_config("success", foreground='lightgreen')
        self.st_view.bind("<Button-1>", lambda a: "break")
        self.st_view.bind("<B1-Motion>", lambda a: "break")
        self.st_view.pack(fill=BOTH, expand=YES)
        scroll_cf.add(output_container, textvariable='scroll-message')

        #  bottom Frame start ----------------------------------
        bottom_frame = ttk.Frame(self, style='bg.TFrame')
        bottom_frame.pack(fill=BOTH, pady=0, side=TOP, expand=YES)

        self.nb = ttk.Notebook(bottom_frame)
        tb_current = ttk.Frame(self.nb)
        tb_history = ttk.Frame(self.nb)

        self.nb.add(tb_current, text='当前委托')
        self.nb.add(tb_history, text='历史委托')
        self.nb.pack(fill=BOTH, pady=1, expand=YES)

        ## Treeview
        self.tv = ttk.Treeview(tb_current, show='headings', height=10)
        self.tv2 = ttk.Treeview(tb_history, show='headings', height=10)
        self.tv.configure(columns=list(self.col_.keys()))
        self.tv2.configure(columns=list(self.col_.keys()))
        # self.tv.column('下单时间', width=120, stretch=True)

        for col, width in self.col_.items():
            self.tv.column(col, stretch=True, width=width, anchor=E)
            self.tv2.column(col, stretch=True, width=width, anchor=E)

        for col in self.tv['columns']:
            self.tv.heading(col, text=col.title(), anchor=E)
            self.tv2.heading(col, text=col.title(), anchor=E)

        self.tv.pack(fill=BOTH, pady=1, expand=True)
        self.tv2.pack(fill=BOTH, pady=1, expand=True)

        t = threading.Thread(target=self._update_order)
        t.setDaemon(True)
        t.start()
        bal_t = threading.Thread(target=self._update_balance)
        bal_t.setDaemon(True)
        bal_t.start()
        self.init_args()

    def record_args_redis(self):
        cur_redis.set(RECORD_SWITCH_KEY, self.record_args.get())

    def stop_button(self):
        self.start_ts = 0
        self.switch_lbl_state(state=ACTIVE)

    def start_to_maker_order(self, data):
        stop_af_ts = data.get("stop_af_ts")
        stop_success = data.get("stop_success")
        req_args = data.get("req_args")
        ts = int(time.time() * 1000)
        self.start_ts = ts
        # while self.start_ts % 1000 != 995:
        #     self.start_ts = int(time.time() * 1000)

        times = 0
        t0 = ts

        while self.start_ts:
            t = int(time.time() * 1000)
            if t - t0 < 134:# 133ms发送2次请求
                continue
            used = t - self.start_ts
            if stop_af_ts and used / 1000 >= stop_af_ts:
                print("------", used)
                main_queue.put(
                    {"type": EVENT_STDOUT, "data": "停止挂单:设定时间到"})
                break
            if stop_success and cur_redis.exists(f"{REDIS_PREFIX}:m:{ts}"):
                main_queue.put(
                    {"type": EVENT_MAKER_SUCCESS, "data": "停止挂单:挂单成功"})
                break

            if (int(used / 1000 / 3) + 1) * 40 <= times:
                continue

            task = []
            for i in range(2):
                t = threading.Thread(target=self.execute_to, kwargs={
                    "data": req_args,
                    "ts": ts,
                })
                task.append(t)
            for i in task:
                i.start()
            t0 = int(time.time() * 1000)
            times += 2
            # main_queue.put({"type": EVENT_STDOUT,
            #                 "data": f"{times},{self.start_ts},{self.success_times},{self.failed_times}"})
        else:
            main_queue.put(
                {"type": EVENT_STDOUT, "data": "停止挂单:点击停止按钮"})
        self.switch_lbl_state(ACTIVE)
        self.start_ts = 0
        self.success_times = 0
        self.failed_times = 0
        cur_redis.delete(f"{REDIS_PREFIX}:start")

    def validate_number(self, x) -> bool:
        """Validates that the input is a number"""
        if x == "":
            return True
        try:
            float(x)
            return True
        except:
            return False

    def validate_alpha(self, x) -> bool:
        """Validates that the input is alpha"""
        if x.isdigit():
            return False
        elif x == "":
            return True
        else:
            return True

    def check_args(self):
        try:
            instId = self.getvar("instId")
        except:
            Messagebox.ok("请输入正确的交易对")
            return
        try:
            px = self.getvar("px")
            px = float(px)
        except:
            Messagebox.ok("请输入正确单价")
            return
        try:
            sz = self.getvar("sz")
            sz = float(sz)
        except:
            Messagebox.ok("请输入正确卖/买数量")
            return
        # if px*sz<=0.1:
        #     Messagebox.ok("库币要求总价必须大于0.1")
        #     return

        try:
            if self.getvar("stop_ms"):
                stop_af_ts = int(self.getvar("stop_ms"))
        except:
            Messagebox.ok("请输入正确的停止秒数")
            return

        ret = {
            "size": sz,
            "price": px,
            "symbol": instId,
        }
        side = self.site.get()

        ret["side"] = "sell" if side else "buy"

        return ret

    def execute_to(self, data, ts):
        try:
            print(data)
            data.update({
                "tdMode": "cash",
                "ordType": "limit",
            })

            log.logger.info(f"LING,发送请求,{self.success_times}")
            result = self.tradeAPI.create_limit_order(**data)
            result = result.json()
            if result.get("code") == "200000":
                cur_redis.set(f"{REDIS_PREFIX}:m:{ts}", 1, ex=60 * 5)
                main_queue.put(
                    {"type": EVENT_MAKER_SUCCESS, "data": f"成功挂单:{result}"})
            else:
                log.logger.info(f"请求ku_coin:result{result}")
                if cur_redis.set(REDIS_PREFIX + str(result)[0:35], 1, ex=2, nx=True):
                    main_queue.put(
                        {"type": EVENT_REQ_INFO, "data": f"失败请求:{result}"})
            self.success_times += 1
        except Exception as e:
            log.logger.error(f"请求ku_coin:result{e}")
            if cur_redis.set(REDIS_PREFIX + str(e)[0:35], 1, ex=2, nx=True):
                main_queue.put(
                    {"type": EVENT_REQ_INFO, "data": f"请求错误:{e}"})
            self.failed_times += 1

    def start_to(self):
        ret = self.check_args()
        if not ret:
            return
        stop_success = self.stop_success.get()
        stop_af_ts = int(self.getvar("stop_ms") or 0)
        event = {
            "type": EVENT_START_TO,
            "data": {
                "stop_success": stop_success,
                "stop_af_ts": stop_af_ts,
                "req_args": ret,
            }
        }
        if self.record_args:
            data = {
                "stop_success": stop_success,
                "stop_af_ts": stop_af_ts,
                "size": ret["size"],
                "price": ret["price"],
                "symbol": ret["symbol"],
                "side": ret["side"],

            }
            cur_redis.hmset(HASH_ARGS_RECORD_KEY, data)
        self.switch_lbl_state(DISABLED)
        main_queue.put(event)
        main_queue.put({"type": EVENT_STDOUT, "data": "开始挂单"})

    def check_all_px(self, event):
        try:
            px = self.getvar("px")
            sz = self.getvar("sz")
            all = float(px) * float(sz)
            self.setvar("allz", all)
        except:
            self.setvar("allz", 0)

    def get_directory(self):
        """Open dialogue to get directory and update variable"""
        self.update_idletasks()
        d = askdirectory()
        if d:
            self.setvar('folder-path', d)


class CollapsingFrame(ttk.Frame):
    """A collapsible frame widget that opens and closes with a click."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        self.cumulative_rows = 0

        # widget images
        self.images = [
            ttk.PhotoImage(file=PATH / 'icons8_double_up_24px.png'),
            ttk.PhotoImage(file=PATH / 'icons8_double_right_24px.png')
        ]

    def add(self, child, title="", bootstyle=PRIMARY, **kwargs):
        """Add a child to the collapsible frame

        Parameters:

            child (Frame):
                The child frame to add to the widget.

            title (str):
                The title appearing on the collapsible section header.

            bootstyle (str):
                The style to apply to the collapsible section header.

            **kwargs (Dict):
                Other optional keyword arguments.
        """
        if child.winfo_class() != 'TFrame':
            return

        style_color = Bootstyle.ttkstyle_widget_color(bootstyle)
        frm = ttk.Frame(self, bootstyle=style_color)
        frm.grid(row=self.cumulative_rows, column=0, sticky=EW)

        # header title
        header = ttk.Label(
            master=frm,
            text=title,
            bootstyle=(style_color, INVERSE)
        )
        if kwargs.get('textvariable'):
            header.configure(textvariable=kwargs.get('textvariable'))
        header.pack(side=LEFT, fill=BOTH, padx=10)

        # header toggle button
        def _func(c=child):
            return self._toggle_open_close(c)

        btn = ttk.Button(
            master=frm,
            image=self.images[0],
            bootstyle=style_color,
            command=_func
        )
        btn.pack(side=RIGHT)

        # assign toggle button to child so that it can be toggled
        child.btn = btn
        child.grid(row=self.cumulative_rows + 1, column=0, sticky=NSEW)

        # increment the row assignment
        self.cumulative_rows += 2

    def _toggle_open_close(self, child):
        """Open or close the section and change the toggle button 
        image accordingly.

        Parameters:
            
            child (Frame):
                The child element to add or remove from grid manager.
        """
        if child.winfo_viewable():
            child.grid_remove()
            child.btn.configure(image=self.images[1])
        else:
            child.grid()
            child.btn.configure(image=self.images[0])


if __name__ == '__main__':
    app = ttk.Window("KU-COIN")
    BackMeUp(app)
    style = ttk.Style()
    style.configure("Treeview.Heading", background='olive')

    style.configure('Treeview', rowheight=20)
    app.mainloop()
