from flask import Flask, send_file, request as flask_request
import json
import register_tool
import base64
from db import *
import avatar
import file
from sqlite3 import OperationalError
import announcements
from crypto import generate_rsa_keys, return_app_route
from rate_limiter import RateLimiter
import time
import threading

def bool_res() -> tuple: 
    return (str(time.time()) + "False", str(time.time()) + "True")

def main(port_api : int, port_tcp : int, pub_pem, pri, ImgCaptcha, user_cursor, forum_cursor, file_cursor, notification_cursor, group_cursor, instant_contact):
    """
    pri 是 cryptography 库的私钥对象
    pub_pem 是二进制 pem 文件路径
    ImgCaptcha 是 captcha.ImageCaptcha 对象
    ~_cursor 表示 db.tool.Db 对象
    """
    app = Flask(__name__)
    api = return_app_route(app, pri)
    limiter = RateLimiter(port_api)
    manager_auths = {"admin", "root"}
    managed_auths = {"user", "banned", "admin", "root"}
    locks = {
        'config': threading.Lock(),
        'activate': threading.Lock(),
        'queue': threading.Lock(),
        'captcha': threading.Lock(),
        'announcement': threading.Lock(),
    }

    def build_notification(event : str, title : str, content : str, sender=None, meta=None):
        return {
            "event" : event,
            "title" : title,
            "content" : content,
            "sender" : sender,
            "meta" : meta or {}
        }

    def run_side_effect(action : str, callback):
        try:
            return callback()
        except Exception as e:
            print("[WARN] 副作用失败({}): {}".format(action, e))
            return None

    def run_notification_side_effect(action : str, callback):
        return run_side_effect("notification/{}".format(action), callback)

    def ensure_notification_table(target_uid : int):
        try:
            notification_cursor.create_user_table(target_uid)
            return True
        except Exception as e:
            print("[WARN] 创建通知表失败(uid={}): {}".format(target_uid, e))
            return False

    def notify_user(target_uid : int, event : str, title : str, content : str, sender=None, meta=None):
        def callback():
            if not user_cursor.uid_query(target_uid):
                return None
            return instant_contact.notify_user(target_uid, build_notification(event, title, content, sender, meta))
        return run_notification_side_effect("notify_user/{}".format(event), callback)

    def notify_users(target_uids, event : str, title : str, content : str, sender=None, meta=None):
        def callback():
            sent = set()
            records = []
            for target_uid in target_uids:
                if target_uid in sent or target_uid is None:
                    continue
                sent.add(target_uid)
                record = notify_user(target_uid, event, title, content, sender, meta)
                if record is not None:
                    records.append(record)
            return records
        records = run_notification_side_effect("notify_users/{}".format(event), callback)
        if records is None:
            return []
        return records

    def all_user_ids():
        ret = run_notification_side_effect("all_user_ids", lambda: [row[0] for row in user_cursor.query("SELECT uid FROM users")])
        if ret is None:
            return []
        return ret

    def extract_mentioned_uids(comment : str):
        mentioned_uids = set()
        for block in comment.split():
            if not block.startswith('@') or len(block) < 2:
                continue
            username = block[1:].strip(".,!?，。！？:：;；)]】}>\"'")
            if not username:
                continue
            info = user_cursor.username_query(username)
            if info:
                mentioned_uids.add(info[0][0])
        return mentioned_uids

    def query_forum(fid):
        try:
            return forum_cursor.query_forum_fid(fid) or []
        except Exception:
            return []

    def query_post(fid, pid):
        try:
            return forum_cursor.query_post_pid(fid, pid) or []
        except Exception:
            return []

    def get_comment_thread(comments : dict, fid, pid):
        forum_comments = comments.get(str(fid))
        if not isinstance(forum_comments, dict):
            return None
        post_comments = forum_comments.get(str(pid))
        if not isinstance(post_comments, dict):
            return None
        return post_comments

    def serialize_notifications(rows):
        return json.dumps(notification_cursor.serialize_rows(rows), ensure_ascii=False)

    def get_user_row(uid):
        info = user_cursor.uid_query(uid)
        if not info:
            return None
        return info[0]

    def verify_manager(uid, pwd):
        if not user_cursor.verify_user(uid, pwd):
            return None
        operator = get_user_row(uid)
        if operator is None:
            return None
        if operator[4] not in manager_auths:
            return None
        return operator

    def can_manage_auth(operator_auth : str, target_auth : str):
        if operator_auth == "root":
            return target_auth in managed_auths
        if operator_auth == "admin":
            return target_auth in {"user", "banned"}
        return False

    def resolve_managed_target(operator_auth : str, target_uid : int, next_auth=None, deleting=False):
        target = get_user_row(target_uid)
        if target is None:
            return None

        target_auth = target[4]
        if not can_manage_auth(operator_auth, target_auth):
            return None
        if next_auth is not None and not can_manage_auth(operator_auth, next_auth):
            return None
        return target

    def collect_managed_updates(req):
        updates = {}
        if "username" in req:
            updates["username"] = req["username"]
        if "target_password" in req:
            updates["password"] = req["target_password"]
        if "email" in req:
            updates["email"] = req["email"]
        if "new_auth" in req:
            updates["stat"] = req["new_auth"]
        if "sign" in req:
            updates["sign"] = req["sign"]
        if "introduction" in req:
            updates["introduction"] = req["introduction"]
        return updates

    def cleanup_forum_queue(target_uid : int):
        target_uid = int(target_uid)
        with locks['queue']:
            with open("res/{}/forum/queue.json".format(port_api), "r+", encoding="utf-8") as file:
                queue = json.load(file)

            removed_keys = [
                key
                for key, value in queue.items()
                if key.isdigit() and isinstance(value, dict) and value.get("creater") == target_uid
            ]

            if not removed_keys:
                return True

            for key in removed_keys:
                del queue[key]

            queue["queue_num"] = max(queue.get("queue_num", 0) - len(removed_keys), 0)

            with open("res/{}/forum/queue.json".format(port_api), "w+", encoding="utf-8") as file:
                json.dump(queue, file)

        return True

    def clean_deleted_user_state(target_uid : int):
        target_uid = int(target_uid)
        deleted_group_ids = [row[0] for row in group_cursor.query_creater(target_uid)]
        deleted_forum_ids = [row[0] for row in forum_cursor.query_forum_creater(target_uid)]

        avatar.clean_avatar(port_api, target_uid, "user")
        for gid in deleted_group_ids:
            avatar.clean_avatar(port_api, gid, "group")
        for fid in deleted_forum_ids:
            avatar.clean_avatar(port_api, fid, "forum")

        file.clean_user_files(port_api, target_uid, file_cursor)
        group_cursor.clean_user_membership(target_uid)
        forum_cursor.clean_user_content(target_uid)
        cleanup_forum_queue(target_uid)
        return True

    def perform_managed_auth_change(uid : int, pwd : str, target_uid : int, new_auth : str):
        operator = verify_manager(uid, pwd)
        if operator is None:
            return False

        target = resolve_managed_target(operator[4], target_uid, next_auth=new_auth)
        if target is None:
            return False

        if not user_cursor.update_user_with_root_guard(target_uid, stat=new_auth):
            return False

        notify_user(target_uid, "auth.stat.changed", "账号状态已变更", "你的账号状态已更新为 {}。".format(new_auth), sender=uid, meta={"new_auth" : new_auth})
        return True
    
    @app.before_request
    def check_rate_limit():
        ip = flask_request.remote_addr
        endpoint = flask_request.path
        if not limiter.is_allowed(ip, endpoint):
            return "Too Many Requests", 429

    @app.route("/get_rsa_pub")
    def get_rsa_key():
        return send_file("res/{}/secret/pub.pem".format(port_api), download_name="{}.pem".format(port_api))

    @api("/auth/login", methods=["POST"])
    def login(req):
        try:
            uid = req["uid"]
            pwd = req["password"]
            return bool_res()[user_cursor.verify_user(uid, pwd)]
        except:
            return bool_res()[False]
    

    @api("/auth/change_pwd", methods=["POST"])
    def change_pwd(req):
        try:
            uid = req["uid"]
            pwd = req["password"]
            new_pwd = req["new_pwd"]
            if not user_cursor.verify_user(uid, pwd):
                return bool_res()[False]
            user_cursor.change_pwd(uid, new_pwd)
            return bool_res()[True]
        except:
            return bool_res()[False]

    @app.route('/auth/captcha')
    def get_captcha():
        with locks['config']:
            with open("res/{}/config.json".format(port_api), "r+") as file:
                captcha = json.load(file)["captcha"]
        if not captcha:
            return {}
        token = register_tool.generate_captcha(port_api, ImgCaptcha, locks['captcha'])
        file_path = 'res/{}/captcha/{}.png'.format(port_api, token)
        with open(file_path, "rb") as file:
            ret_b64 = file.read()
        ret_b64 = base64.b64encode(ret_b64).decode("utf-8")
        return {"pic" : ret_b64, "stamp" : token}
    
    @api("/auth/change_email_verify", methods=['POST'])
    def change_email_verify(req):
        uid = req["uid"]
        pwd = req["password"]

        if not user_cursor.verify_user(uid, pwd):
            return bool_res()[False]
        if not user_cursor.uid_query(uid)[0][4] == 'root':
            return bool_res()[False]
        
        new_stat = req["change_to"]
        with locks['config']:
            with open("res/{}/config.json".format(port_api), "r+") as file:
                cfg = json.load(file)

            if new_stat == False:
                cfg["email_activate"] = ""
                cfg["email_password"] = ""
            else:
                cfg["email_activate"] = req["verify_email"]
                cfg["email_password"] = req["email_password"]

            with open("res/{}/config.json".format(port_api), "w+") as file:
                json.dump(cfg, file)
        return bool_res()[True]
        
    @app.route("/auth/uid/<uid>")
    def query_uid(uid):
        info = user_cursor.uid_query(uid)
        if not len(info):
            return {}
        ret = {
            "uid" : info[0][0],
            "username" : info[0][1],
            "email" : info[0][2],
            "stat" : info[0][4],
            "create_time" : info[0][5],
            "personal_sign" : info[0][6],
            "introduction" : info[0][7]
        } 
        return ret

    @app.route("/auth/username/<username>")
    def query_username(username):
        info = user_cursor.username_query(username)
        if not len(info):
            return {}
        ret = {
            "uid" : info[0][0],
            "username" : info[0][1],
            "email" : info[0][2],
            "stat" : info[0][4],
            "create_time" : info[0][5],
            "personal_sign" : info[0][6],
            "introduction" : info[0][7]
        }
        return ret

    @api("/auth/change_email", methods=['POST'])
    def change_email(req):
        uid = req["uid"]
        pwd = req["password"]
        if not user_cursor.verify_user(uid, pwd):
            return bool_res()[False]
        new_email = req["new_email"]
        return bool_res()[user_cursor.change_email(uid, new_email)]

    @api("/auth/register", methods=['POST'])
    def register(req):
        username = req["username"]
        password = req["password"]
        is_captcha = False
        with locks['config']:
            with open("res/{}/config.json".format(port_api), "r+") as file:
                cfg = json.load(file)
                is_captcha = cfg['captcha']
                is_email_activate = cfg["email_activate"]
        
        if is_captcha:
            captcha_stamp = req["captcha_stamp"]
            captcha_code = req["captcha_code"]
            if not register_tool.verify_captcha(port_api, captcha_stamp, captcha_code, locks['captcha']):
                return bool_res()[False]
        
        email = None
        if "email" in req.keys():
            email = req["email"] 
        
        if is_email_activate:
            sender_email = cfg["email_activate"]
            if not email:
                return bool_res()[False]
            email_pwd = cfg["email_password"]
            if not register_tool.email_code(sender_email, port_api, email, email_pwd, locks['config'], locks['activate']):
                return bool_res()[False]

        succeeded = user_cursor.user_create(username, password, time.time(), email)
        if not succeeded:
            return bool_res()[False]
        target_uid = user_cursor.username_query(username)[0][0]
        if is_email_activate and succeeded:
            user_cursor.change_auth(target_uid, "banned")
        if not ensure_notification_table(target_uid):
            user_cursor.delete_user(target_uid)
            return bool_res()[False]
        return bool_res()[True]

    @api("/auth/activate", methods=["POST"])
    def activate(req):
        uid = req["uid"]
        activate_code = req["activate_code"]
        email = user_cursor.uid_query(uid)[0][2]
        with locks['activate']:
            with open("res/{}/activate.json".format(port_api), "r+") as file:
                if not email in json.load(file).keys():
                    return bool_res()[True]
        if register_tool.verify_email(port_api, email, activate_code, locks['activate']):
            user_cursor.change_auth(uid, "user")
            return bool_res()[True]
        return bool_res()[False]
     

    @api("/auth/change_auth", methods=["POST"])
    def change_auth(req):
        try:
            uid = req["uid"]
            pwd = req["password"]
            oped = req["change_uid"]
            new_auth = req["new_auth"]
            return bool_res()[perform_managed_auth_change(uid, pwd, oped, new_auth)]
        except:
            return bool_res()[False]

    @api("/auth/manage/create", methods=["POST"])
    def manage_create_user(req):
        try:
            uid = req["uid"]
            pwd = req["password"]
            username = req["username"]
            target_password = req["target_password"]
            new_auth = req.get("new_auth", "user")
            email = req["email"] if "email" in req else None

            operator = verify_manager(uid, pwd)
            if operator is None:
                return bool_res()[False]
            if not can_manage_auth(operator[4], new_auth):
                return bool_res()[False]

            if not user_cursor.user_create(username, target_password, time.time(), email, stat=new_auth):
                return bool_res()[False]

            target = user_cursor.username_query(username)
            if not target:
                return bool_res()[False]

            target_uid = target[0][0]
            extra_updates = {}
            if "sign" in req:
                extra_updates["sign"] = req["sign"]
            if "introduction" in req:
                extra_updates["introduction"] = req["introduction"]

            if extra_updates and not user_cursor.update_user(target_uid, **extra_updates):
                user_cursor.delete_user(target_uid)
                return bool_res()[False]

            if not ensure_notification_table(target_uid):
                user_cursor.delete_user(target_uid)
                return bool_res()[False]
            return bool_res()[True]
        except:
            return bool_res()[False]

    @api("/auth/manage/update", methods=["POST"])
    def manage_update_user(req):
        try:
            uid = req["uid"]
            pwd = req["password"]
            target_uid = req["change_uid"]
            next_auth = req["new_auth"] if "new_auth" in req else None

            operator = verify_manager(uid, pwd)
            if operator is None:
                return bool_res()[False]

            target = resolve_managed_target(operator[4], target_uid, next_auth=next_auth)
            if target is None:
                return bool_res()[False]

            updates = collect_managed_updates(req)
            if not updates:
                return bool_res()[False]

            if not user_cursor.update_user_with_root_guard(target_uid, **updates):
                return bool_res()[False]

            if "new_auth" in req:
                notify_user(target_uid, "auth.stat.changed", "账号状态已变更", "你的账号状态已更新为 {}。".format(req["new_auth"]), sender=uid, meta={"new_auth" : req["new_auth"]})
            return bool_res()[True]
        except:
            return bool_res()[False]

    @api("/auth/manage/ban", methods=["POST"])
    def manage_ban_user(req):
        try:
            uid = req["uid"]
            pwd = req["password"]
            target_uid = req["change_uid"]
            return bool_res()[perform_managed_auth_change(uid, pwd, target_uid, "banned")]
        except:
            return bool_res()[False]

    @api("/auth/manage/delete", methods=["POST"])
    def manage_delete_user(req):
        try:
            uid = req["uid"]
            pwd = req["password"]
            target_uid = int(req["change_uid"])

            operator = verify_manager(uid, pwd)
            if operator is None:
                return bool_res()[False]

            target = resolve_managed_target(operator[4], target_uid, deleting=True)
            if target is None:
                return bool_res()[False]

            if target[4] == "root" and user_cursor.count_users_with_stat("root") <= 1:
                return bool_res()[False]

            if not user_cursor.delete_user_with_root_guard(target_uid):
                return bool_res()[False]

            run_side_effect(
                "disconnect_deleted_user",
                lambda: instant_contact.disconnect_user(target_uid)
            )
            run_side_effect(
                "clean_deleted_user_state",
                lambda: clean_deleted_user_state(target_uid)
            )
            run_side_effect(
                "delete_user_notification_table",
                lambda: notification_cursor.delete_user_table(target_uid)
            )
            return bool_res()[True]
        except:
            return bool_res()[False]
    
    @api("/auth/change_sign", methods=['POST'])
    def change_sign(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        new_sign = req["new_sign"]
        user_cursor.change_sign(uid, new_sign)
        return bool_res()[True]
    
    @api("/auth/change_introduction", methods=["POST"])
    def change_introduction(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        new_intro = req["new_introduction"]
        user_cursor.change_introduction(uid, new_intro)
        return bool_res()[True]
    
    @api("/auth/change_captcha", methods=['POST'])
    def change_captcha(req):
        uid = req["uid"]
        pwd = req["password"]
        final_stat = req["change_to"]
        if not user_cursor.verify_user(uid, pwd):
            return bool_res()[False]
        if not user_cursor.uid_query(uid)[0][4] == 'root':
            return bool_res()[False]
        with locks['config']:
            with open("res/{}/config.json".format(port_api), "r+") as file:
                cfg = json.load(file)
            cfg["captcha"] = final_stat
            with open("res/{}/config.json".format(port_api), "w+") as file:
                json.dump(cfg, file)
        return bool_res()[True]

    @api("/auth/change_rate_limits", methods=['POST'])
    def change_rate_limits(req):
        """
        更新端点速率限制配置。
        仅 root 用户可操作。
        
        请求体示例：
        {
            "uid": 0,
            "password": "xxx",
            "rate_limits": {
                "default":        {"requests": 60, "range": 60},
                "/auth/login":    {"requests": 10, "range": 60},
                "/auth/register": {"requests": 5,  "range": 300}
            }
        }
        传入 null 可清空所有速率限制。
        """
        uid = req["uid"]
        pwd = req["password"]
        if not user_cursor.verify_user(uid, pwd):
            return bool_res()[False]
        if not user_cursor.uid_query(uid)[0][4] == 'root':
            return bool_res()[False]
        new_limits = req.get("rate_limits")
        if new_limits is not None and not isinstance(new_limits, dict):
            return bool_res()[False]
        with locks['config']:
            with open("res/{}/config.json".format(port_api), "r+") as f:
                cfg = json.load(f)
            if new_limits is None:
                cfg.pop("rate_limits", None)
            else:
                cfg["rate_limits"] = new_limits
            with open("res/{}/config.json".format(port_api), "w+") as f:
                json.dump(cfg, f)
        return bool_res()[True]

    @api("/notification/query_all", methods=['POST'])
    def query_all_notifications(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        return serialize_notifications(notification_cursor.query_all_events(uid))

    @api("/notification/query_after", methods=['POST'])
    def query_notifications_after(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        try:
            time_stamp = float(req.get("time_stamp", 0))
        except (TypeError, ValueError):
            return bool_res()[False]
        return serialize_notifications(notification_cursor.query_events_after(uid, time_stamp))

    @api("/notification/delete_before", methods=['POST'])
    def delete_notifications_before(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        try:
            time_stamp = float(req["time_stamp"])
        except (KeyError, TypeError, ValueError):
            return bool_res()[False]
        return bool_res()[notification_cursor.delete_events_before(uid, time_stamp)]

    @api("/notification/delete_all", methods=['POST'])
    def delete_all_notifications(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        return bool_res()[notification_cursor.delete_all_events(uid)]

    @app.route("/info")
    def info():
        with locks['config']:
            with open("res/{}/config.json".format(port_api), "r+") as file:
                cfg = json.load(file)
        ret = {}
        ret["server_name"] = cfg["server_name"]
        ret["port_api"] = port_api
        ret["port_tcp"] = port_tcp
        ret["captcha"] = cfg["captcha"]
        ret["file_last_time"] = cfg["file_last_time"]
        ret["groups_limit"] = cfg["groups_limit"]
        ret["single_group_max_people"] = cfg["single_group_max_people"]
        if cfg["email_activate"]:
            ret["email_activate"] = True
        else:
            ret["email_activate"] = False
        return ret

    @api("/forum/create_forum", methods=["POST"])
    def create_forum(req):
        uid = req["uid"]
        password = req["password"]
        forum_name = req["forum_name"]
        introduction = req["introduction"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        with locks['queue']:
            with open("res/{}/forum/queue.json".format(port_api), "r+") as file:
                queue = json.load(file)
            qid = queue['queue_num'] + 1
            queue["queue_num"] = qid
            for i in queue.keys():
                if i.isdigit():
                    qid = max(qid, int(i) + 1)
            queue[qid] = {
                "creater" : uid,
                "forumname" : forum_name,
                "introduction" : introduction
            } 
            with open("res/{}/forum/queue.json".format(port_api), "w+") as file:
                json.dump(queue, file)
        return bool_res()[True]
        
    @api("/forum/get_approving_forum_list", methods=['POST'])
    def get_approving_forum_list(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ["admin", "root"]:
            return bool_res()[False]
        with locks['queue']:
            return json.dumps(json.load(open("res/{}/forum/queue.json".format(port_api), "r+")), ensure_ascii=False)
    
    @api("/forum/approve_forum", methods=["POST"])
    def approve_forum(req):
        uid = req["uid"]
        password = req["password"]
        qid = req["qid"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ["admin", "root"]:
            return bool_res()[False]
        with locks['queue']:
            with open("res/{}/forum/queue.json".format(port_api), "r+") as file:
                queue = json.load(file)
            if str(qid) not in queue:
                return bool_res()[False]
            fchosen = queue[str(qid)]
            fid = forum_cursor.create_forum(fchosen["forumname"], fchosen["creater"], fchosen["introduction"]) 
            del queue[str(qid)]
            queue["queue_num"] = max(queue["queue_num"] - 1, 0)
            with open("res/{}/forum/queue.json".format(port_api), "w+") as file:
                json.dump(queue, file)
        notify_user(fchosen["creater"], "forum.approved", "论坛已通过审核", "你创建的论坛 {} 已通过审核。".format(fchosen["forumname"]), sender=uid, meta={"fid" : fid, "forum_name" : fchosen["forumname"]})
        return bool_res()[True]

    @api("/forum/reject_forum", methods=["POST"])
    def reject_forum(req):
        uid = req["uid"]
        password = req["password"]
        qid = req["qid"]
        reason = req.get("reason")
        if not isinstance(reason, str):
            reason = ""
        reason = reason.strip()
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ["admin", "root"]:
            return bool_res()[False]
        with locks['queue']:
            with open("res/{}/forum/queue.json".format(port_api), "r+") as file:
                queue = json.load(file)
            if str(qid) not in queue:
                return bool_res()[False]
            fchosen = queue[str(qid)]
            del queue[str(qid)]
            queue["queue_num"] = max(queue["queue_num"] - 1, 0)
            with open("res/{}/forum/queue.json".format(port_api), "w+") as file:
                json.dump(queue, file)
        reason_suffix = "原因：{}".format(reason) if reason else ""
        notify_user(fchosen["creater"], "forum.rejected", "论坛未通过审核", "你创建的论坛 {} 未通过审核。{}".format(fchosen["forumname"], reason_suffix), sender=uid, meta={"qid" : qid, "forum_name" : fchosen["forumname"], "reason" : reason})
        return bool_res()[True]

    @app.route("/forum/get_forum_list")
    def get_forum_list():
        return forum_cursor.query_all_forums()
    
    @api("/forum/send_post", methods=["POST"])
    def send_post(req):
        uid = req["uid"]
        password = req["password"]
        fid = req["fid"]
        if not isinstance(fid, int):
            return {}
        title = req["title"]
        content = req["content"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        if not query_forum(fid):
            return bool_res()[False]
        return bool_res()[forum_cursor.send_post(fid, uid, title, content)]


    @app.route("/forum/get_post_list/<fid>")
    def get_post_list(fid : str):
        if not fid.isdigit():
            return {}
        try:
            return forum_cursor.query_all_post(int(fid))
        except OperationalError as e:
            return {}
    
    @api("/forum/remove_forum", methods=["POST"])
    def remove_forum(req):
        uid = req["uid"]
        password = req["password"]
        fid = req["fid"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        forum_info = query_forum(fid)
        if not forum_info:
            return bool_res()[False]
        creater = forum_info[0][2]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not (user_stat in ["admin", "root"] or uid == creater):
            return bool_res()[False]
        try:
            avatar.clean_avatar(port_api, fid, "forum")
        except Exception:
            return bool_res()[False]
        forum_cursor.delete_forum(fid)
        return bool_res()[True]
    
    @api("/forum/remove_post", methods=['POST'])
    def remove_post(req):
        uid = req["uid"]
        password = req["password"]
        fid = req["fid"]
        pid = req["pid"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        forum_info = query_forum(fid)
        post_info = query_post(fid, pid)
        if not forum_info or not post_info:
            return bool_res()[False]
        creater = forum_info[0][2]
        creater_post = post_info[0][2]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not (user_stat in ["admin", "root"] or uid == creater or uid == creater_post):
            return bool_res()[False]
        forum_cursor.delete_post(fid, pid)
        return bool_res()[True]

    @api("/forum/comment", methods=["POST"])
    def comment(req):
        uid = req["uid"]
        if not isinstance(uid, int):
            return bool_res()[False]
        password = req["password"]
        fid = req["fid"]
        pid = req["pid"]
        comment : str = req["comment"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        comment_time = str(time.time())
        def add_comment(comments):
            thread = get_comment_thread(comments, fid, pid)
            if thread is None:
                return False
            thread[comment_time] = [uid, comment]
            return True

        if not update_comments(port_api, add_comment):
            return bool_res()[False]

        def send_comment_notifications():
            sender_name = user_cursor.uid_query(uid)[0][1]
            forum_info = forum_cursor.query_forum_fid(fid)
            post_info = forum_cursor.query_post_pid(fid, pid)
            notified_uids = set()
            forum_name = forum_info[0][1] if forum_info else str(fid)
            post_title = post_info[0][1] if post_info else str(pid)
            if post_info:
                post_creater = post_info[0][2]
                if post_creater != uid:
                    notify_user(post_creater, "forum.comment.created", "你的帖子收到新评论", "{} 评论了你的帖子《{}》。".format(sender_name, post_title), sender=uid, meta={"fid" : fid, "pid" : pid, "comment_time" : comment_time})
                    notified_uids.add(post_creater)
            for mentioned_uid in extract_mentioned_uids(comment):
                if mentioned_uid == uid or mentioned_uid in notified_uids:
                    continue
                notify_user(mentioned_uid, "forum.comment.mentioned", "你在评论中被提及", "{} 在论坛 {} 的评论中提到了你。".format(sender_name, forum_name), sender=uid, meta={"fid" : fid, "pid" : pid, "comment_time" : comment_time})
                notified_uids.add(mentioned_uid)

        run_notification_side_effect("forum.comment", send_comment_notifications)

        return bool_res()[True]

    @app.route("/forum/get_all_comments/<fid>/<pid>")
    def get_all_comments(fid, pid):
        if not fid.isdigit() or not pid.isdigit():
            return {}
        fid = int(fid)
        pid = int(pid)
        comments = read_comments(port_api)
        thread = get_comment_thread(comments, fid, pid)
        if thread is None:
            return {}
        return thread
    
    @api("/forum/remove_comment", methods=['POST'])
    def remove_comment(req):
        uid = req["uid"]
        if not isinstance(uid, int):
            return bool_res()[False]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        fid = req["fid"]
        pid = req["pid"]
        time_stamp = req["send_time"]
        user_stat = user_cursor.uid_query(uid)[0][4]

        def remove_comment_entry(comments):
            thread = get_comment_thread(comments, fid, pid)
            if thread is None or time_stamp not in thread:
                return False
            creater = thread[time_stamp][0]
            if not (creater == uid or user_stat in ['admin', 'root']):
                return False
            del thread[time_stamp]
            return True

        if not update_comments(port_api, remove_comment_entry):
            return bool_res()[False]
        return bool_res()[True]

    @app.route("/avatar/get_avatar/<typ>/<tid>")
    def get_avatar(typ, tid):
        if not tid.isdigit():
            return 
        if not typ in ["forum", "user", "group"]:
            return 
        return send_file(avatar.get_avatar(port_api, tid, typ))
    
    @app.route("/avatar/get_logo")
    def get_logo():
        return send_file("res/{}/avatar/logo.png".format(port_api))
    
    @api("/avatar/upload_forum_avatar", methods=['POST'])
    def upload_forum_avatar(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        fid = req["fid"]
        pic_b64 = req["pic"]
        user_stat = user_cursor.uid_query(uid)[0][4]
        forum_info = query_forum(fid)
        if not forum_info:
            return bool_res()[False]
        creater = forum_info[0][2]
        if uid == creater or user_stat in ['admin', 'root']:
            avatar.upload_avatar(port_api, fid, pic_b64, 'forum')
            return bool_res()[True]
        return bool_res()[False]
        
    @api("/avatar/upload_user_avatar", methods=['POST'])
    def upload_user_avatar(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        pic_b64 = req["pic"]
        avatar.upload_avatar(port_api, uid, pic_b64, 'user')
        return bool_res()[True]
    
    @api('/avatar/upload_group_avatar', methods=['POST'])
    def upload_group_avatar(req):
        """
        TODO

        上传群聊 logo
        """
    
    @api('/avatar/upload_logo', methods=['POST'])
    def upload_logo(req):
        uid = req["uid"]
        password = req["password"]
        pic_b64 = req["pic"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ['admin', 'root']:
            return bool_res()[False]
        with open("res/{}/avatar/logo.png".format(port_api), 'wb') as file:
            file.write(base64.b64decode(pic_b64))
        return bool_res()[True]
        
    @api('/file/upload_file', methods=['POST'])
    def upload_file(req):
        uid = req["uid"]
        password = req["password"]
        filename = req["filename"]
        file_b64 = req["file_b64"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        with locks['config']:
            with open("res/{}/config.json".format(port_api), "r+") as f:
                max_file_size = json.load(f).get("max_file_size", 0)
        if max_file_size != -1 and len(base64.b64decode(file_b64)) > max_file_size:
            return bool_res()[False]
        file.upload_file(port_api, uid, file_b64, filename, file_cursor)
        return bool_res()[True]

    @app.route('/file/get_file_info/<hashes>')
    def get_file_info(hashes):
        qry = file_cursor.return_file(hashes)
        if not qry:
            return {}
        qry = qry[0]
        return {
            "sender" : qry[0],
            "file_name" : qry[1],
            "send_time" : qry[3],
            "active" : qry[4]
        }
    
    @app.route("/file/get_file/<hashes>")
    def get_file(hashes : str):
        qry = file_cursor.return_file(hashes)
        if (not qry) or qry[0][4] == False:
            return 
        return send_file("res/{}/file/{}.file".format(port_api, hashes), download_name=qry[0][1], as_attachment=True)
    
    @api("/announcement/upload_announcement", methods=['POST'])
    def upload_announcement(req):
        uid = req["uid"]
        password = req["password"]
        content = req["content"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ['admin', 'root']:
            return bool_res()[False]
        time_stamp = announcements.upload_announcement(port_api, uid, content, locks['announcement'])
        notify_users(all_user_ids(), "announcement.created", "收到新公告", content, sender=uid, meta={"time_stamp" : time_stamp})
        return bool_res()[True]
    
    @api("/announcement/edit_announcement", methods=['POST'])
    def edit_announcement(req):
        uid = req["uid"]
        password = req["password"]
        time_stamp = req["time_stamp"]
        content = req["content"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ['admin', 'root']:
            return bool_res()[False]
        succeeded = announcements.edit_announcement(port_api, time_stamp, content, locks['announcement'])
        if succeeded:
            notify_users(all_user_ids(), "announcement.edited", "公告已更新", content, sender=uid, meta={"time_stamp" : time_stamp})
        return bool_res()[succeeded] 
    
    @api("/announcement/delete_announcement", methods=['POST'])
    def delete_announcement(req):
        uid = req["uid"]
        password = req["password"]
        time_stamp = req["time_stamp"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ['admin', 'root']:
            return bool_res()[False]
        succeeded = announcements.delete_announcement(port_api, time_stamp, locks['announcement'])
        if succeeded:
            notify_users(all_user_ids(), "announcement.deleted", "公告已删除", "编号为 {} 的公告已被删除。".format(time_stamp), sender=uid, meta={"time_stamp" : time_stamp})
        return bool_res()[succeeded]
    
    @app.route("/announcement/query_all")
    def query_all():
        return announcements.query_all(port_api, locks['announcement'])
    
    @app.route("/announcement/query_single/<time_stamp>")
    def query_single(time_stamp : str):
        return announcements.query_single(port_api, time_stamp, locks['announcement'])
 

    @api("/group/create_group", methods=['POST'])
    def create_group(req):
        uid = req["uid"]
        password = req["password"]
        groupname = req["groupname"]
        introduction = req["introduction"]
        if not "enter_hint" in req:
            enter_hint = ""
        else:
            enter_hint = req["enter_hint"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        return bool_res()[group_cursor.create_group(uid, groupname, enter_hint, introduction)]
    
    @app.route("/group/group_info/<gid>")
    def group_info(gid : str): 
        if not gid.isdigit():
            return {}
        qry = group_cursor.query_gid(gid)
        if len(qry) < 1:
            return {}
        return list(qry[0])
        
    @app.route("/group/groupname_search/<groupname>")
    def groupname_search(groupname : str):
        return group_cursor.groupname_search(groupname)        

    @api("/group/add_admin", methods=['POST'])
    def add_admin(req):
        uid = req["uid"]
        password = req["password"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        gid = req["gid"]
        added = req["added"]
        stat = group_cursor.is_admin(gid, uid)
        if stat != 2:
            return bool_res()[False]
        succeeded = group_cursor.add_admin(gid, added)
        if succeeded:
            run_notification_side_effect(
                "group.admin.added",
                lambda: notify_user(added, "group.admin.added", "你已成为群管理员", "你已成为群 {} 的管理员。".format(group_cursor.query_gid(gid)[0][2] if group_cursor.query_gid(gid) else str(gid)), sender=uid, meta={"gid" : gid})
            )
        return bool_res()[succeeded]
    
    # @api("/group/invite_member", methods=['POST'])
    # def invite_member(req):
    #     uid = req['uid']
    #     password = req['password']
    #     if not user_cursor.verify_user(uid, password):
    #         return bool_res()[False]
    # TODO 这里应该有好友检查
    #     gid = req['gid']
    #     added = req['added']
    #     if not user_cursor.uid_query(added):
    #         return bool_res()[False]
    #     return bool_res()[group_cursor.add_member(gid, added)]

    @api("/group/remove_member", methods=['POST'])
    def remove_member(req):
        uid = req["uid"]
        password = req["password"]
        gid = req["gid"]
        removed = req["removed"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        oper = group_cursor.is_admin(gid, uid)
        oped = group_cursor.is_admin(gid, removed)
        if not oper > oped:
            return bool_res()[False]
        succeeded = group_cursor.remove_member(gid, removed)
        if succeeded:
            run_notification_side_effect(
                "group.member.removed",
                lambda: notify_user(removed, "group.member.removed", "你已被移出群聊", "你已被移出群 {}。".format(group_cursor.query_gid(gid)[0][2] if group_cursor.query_gid(gid) else str(gid)), sender=uid, meta={"gid" : gid})
            )
        return bool_res()[succeeded]
    
    @api("/group/remove_admin", methods=['POST'])
    def remove_admin(req):
        uid = req["uid"]
        password = req["password"]
        gid = req["gid"]
        removed = req["removed"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        if not group_cursor.is_admin(gid, uid) == 2:
            return bool_res()[False]
        succeeded = group_cursor.remove_admin(gid, removed)
        if succeeded:
            run_notification_side_effect(
                "group.admin.removed",
                lambda: notify_user(removed, "group.admin.removed", "你的管理员权限已被移除", "你在群 {} 的管理员权限已被移除。".format(group_cursor.query_gid(gid)[0][2] if group_cursor.query_gid(gid) else str(gid)), sender=uid, meta={"gid" : gid})
            )
        return bool_res()[succeeded]

    @api("/group/delete_group", methods=['POST'])
    def delete_group(req):
        uid = req["uid"]
        password = req["password"]
        gid = req["gid"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        if not group_cursor.is_admin(gid, uid) == 2:
            return bool_res()[False]
        group_info = group_cursor.query_gid(gid)
        if group_info:
            group_info = group_info[0]
            group_name = group_info[2]
            target_uids = json.loads(group_info[3]) + json.loads(group_info[4]) + [group_info[1]]
        else:
            group_name = str(gid)
            target_uids = []
        try:
            avatar.clean_avatar(port_api, gid, "group")
        except Exception:
            return bool_res()[False]
        group_cursor.delete_group(gid)
        notify_users([target_uid for target_uid in target_uids if target_uid != uid], "group.deleted", "群聊已解散", "群 {} 已被解散。".format(group_name), sender=uid, meta={"gid" : gid})
        return bool_res()[True]
    
    @api("/friend/add_friend", methods=['POST'])
    def add_friend(req):
        """
        TODO 
        """
        uid = req["uid"]
        password = req["password"]
        added = req["added"]
        req_word = req["req_word"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
    
    @api("/friend/deal_ship", methods=['POST'])
    def deal_ship(req):
        """
        TODO 
        """
        uid = req["uid"]
        password = req["password"]
        dealt = req["dealt"]
        stat = req["stat"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        if not stat in ["allow", "reject"]:
            return bool_res()[False]
    
    return app

# pri, pub, pri_pem, pub_pem, has = generate_rsa_keys()
# with open("res/7001/secret/pub.pem", "wb") as file:
#     file.write(pub_pem)
# usr_obj = UserDb("res/7001/db/user.db", 7001, 1145)
# app = main(7001, 1145, pub_pem, pri, usr_obj)
# app.run(debug=True)