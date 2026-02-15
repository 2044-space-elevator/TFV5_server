from flask import Flask, send_file
import register_tool
import base64
from db import *
import avatar
import file
from sqlite3 import OperationalError
import announcements
from crypto import generate_rsa_keys, return_app_route
import time

def bool_res() -> tuple: 
    return (str(time.time()) + "False", str(time.time()) + "True")

def main(port_api : int, port_tcp : int, pub_pem, pri, ImgCaptcha, user_cursor, forum_cursor, file_cursor):
    """
    pri 是 cryptography 库的私钥对象
    pub_pem 是二进制 pem 文件路径
    ImgCaptcha 是 captcha.ImageCaptcha 对象
    ~_cursor 表示 db.tool.Db 对象
    """
    app = Flask(__name__)
    api = return_app_route(app, pri)
    
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
        with open("res/{}/config.json".format(port_api), "r+") as file:
            captcha = json.load(file)["captcha"]
        if not captcha:
            return {}
        token = register_tool.generate_captcha(port_api, ImgCaptcha)
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
        user_cursor.change_email(uid, new_email)
        return bool_res()[True]

    @api("/auth/register", methods=['POST'])
    def register(req):
        username = req["username"]
        password = req["password"]
        is_captcha = False
        with open("res/{}/config.json".format(port_api), "r+") as file:
            cfg = json.load(file)
            is_captcha = cfg['captcha']
            is_email_activate = cfg["email_activate"]
        
        if is_captcha:
            captcha_stamp = req["captcha_stamp"]
            captcha_code = req["captcha_code"]
            if not register_tool.verify_captcha(port_api, captcha_stamp, captcha_code):
                return bool_res()[False]
        
        email = None
        if "email" in req.keys():
            email = req["email"] 
        
        if is_email_activate:
            sender_email = cfg["email_activate"]
            if not email:
                return bool_res()[False]
            email_pwd = cfg["email_password"]
            if not register_tool.email_code(sender_email, port_api, email, email_pwd):
                return bool_res()[False]

        user_cursor.user_create(username, password, time.time(), email)
        if is_email_activate:
            user_cursor.change_auth(user_cursor.username_query(username)[0][0], "banned")
        return bool_res()[True]

    @api("/auth/activate", methods=["POST"])
    def activate(req):
        uid = req["uid"]
        activate_code = req["activate_code"]
        email = user_cursor.uid_query(uid)[0][2]
        with open("res/{}/activate.json".format(port_api), "r+") as file:
            if not email in json.load(file).keys():
                return bool_res()[True]
        if register_tool.verify_email(port_api, email, activate_code):
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
            if not new_auth in ["user", "banned", "admin"]:
                return bool_res()[False]

            if not user_cursor.verify_user(uid, pwd):
                return bool_res()[False]

            op_auth = user_cursor.uid_query(uid)[0][4]
            oped_auth = user_cursor.uid_query(oped)[0][4]
            if op_auth == 'user' or op_auth == 'banned':
                return bool_res()[False]
            
            if op_auth == "admin":
                if oped_auth == "admin" or oped_auth == "root":
                    return bool_res()[False]
                if new_auth == "admin":
                    return bool_res()[False]
            
            if op_auth == "root":
                if oped_auth == "root":
                    return bool_res()[False]
            
            user_cursor.change_auth(oped, new_auth)
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
        with open("res/{}/config.json".format(port_api), "r+") as file:
            cfg = json.load(file)
        cfg["captcha"] = final_stat
        with open("res/{}/config.json".format(port_api), "w+") as file:
            json.dump(cfg, file)
        return bool_res()[True]

    @app.route("/info")
    def info():
        with open("res/{}/config.json".format(port_api), "r+") as file:
            cfg = json.load(file)
        ret = {}
        ret["server_name"] = cfg["server_name"]
        ret["port_api"] = port_api
        ret["port_tcp"] = port_tcp
        ret["captcha"] = cfg["captcha"]
        if cfg["email_activate"]:
            ret["email_activate"] = True
        else:
            ret["email_activate"] = False
        return ret

    @api("/forum/create_forum", methods=["POST"])
    def create_forum(req):
        uid = req["uid"]
        password = req["password"]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        forum_name = req["forum_name"]
        introduction = req["introduction"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
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
        with open("res/{}/forum/queue.json".format(port_api), "r+") as file:
            queue = json.load(file)
        fchosen = queue[str(qid)]
        forum_cursor.create_forum(fchosen["forumname"], fchosen["creater"], fchosen["introduction"]) 
        del queue[str(qid)]
        queue["queue_num"] -= 1
        with open("res/{}/forum/queue.json".format(port_api), "w+") as file:
            json.dump(queue, file)
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
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        forum_cursor.send_post(fid, uid, title, content)
        return bool_res()[True]


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
        creater = forum_cursor.query_forum_fid(fid)[0][2]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not (user_stat in ["admin", "root"] or uid == creater):
            return bool_res()[False]
        forum_cursor.delete_forum(fid)
        return bool_res()[True]
    
    @api("/forum/remove_post", methods=['POST'])
    def remove_post(req):
        uid = req["uid"]
        password = req["password"]
        fid = req["fid"]
        creater = forum_cursor.query_forum_fid(fid)[0][2]
        pid = req["pid"]
        creater_post = forum_cursor.query_post_pid(fid, pid)[0][2]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not (user_stat in ["admin", "root"] or uid == creater or uid == creater_post):
            return bool_res()[False]
        forum_cursor.delete_post(fid, pid)
        return bool_res()[True]

    @api("/forum/comment", methods=["POST"])
    def comment(req):
        """
        TODO

        等到 TCP 模块写完，考虑写一个 @ 通知。
        """
        uid = req["uid"]
        if not isinstance(uid, int):
            return bool_res()[False]
        password = req["password"]
        fid = req["fid"]
        pid = req["pid"]
        comment = req["comment"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if user_stat == 'banned':
            return bool_res()[False]
        with open("res/{}/forum/comments.json".format(port_api), "r+") as file:
            comments = json.load(file)
        comments[str(fid)][str(pid)][str(time.time())] = [uid, comment]
        with open("res/{}/forum/comments.json".format(port_api), "w+") as file:
            json.dump(comments, file)
        return bool_res()[True]

    @app.route("/forum/get_all_comments/<fid>/<pid>")
    def get_all_comments(fid, pid):
        if not fid.isdigit() or not pid.isdigit():
            return {}
        fid = int(fid)
        pid = int(pid)
        with open("res/{}/forum/comments.json".format(port_api), "r+") as file:
            comments = json.load(file)
        return comments[str(fid)][str(pid)]
    
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
        with open("res/{}/forum/comments.json".format(port_api), "r+") as file:
            comments = json.load(file)
        creater = comments[str(fid)][str(pid)][time_stamp][0]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not (creater == uid or user_stat in ['admin', 'root']):
            return bool_res()[False]
        del comments[str(fid)][str(pid)][time_stamp]
        with open("res/{}/forum/comments.json".format(port_api), "w+") as file:
            json.dump(comments, file)
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
        creater = forum_cursor.query_forum_fid(fid)[0][2]
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
        """
        TODO

        发送公告提醒
        """
        uid = req["uid"]
        password = req["password"]
        content = req["content"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ['admin', 'root']:
            return bool_res()[False]
        announcements.upload_announcement(port_api, uid, content)
        return bool_res()[True]
    
    @api("/announcement/edit_announcement", methods=['POST'])
    def edit_announcement(req):
        """
        TODO

        发送公告提醒
        """
        uid = req["uid"]
        password = req["password"]
        time_stamp = req["time_stamp"]
        content = req["content"]
        if not user_cursor.verify_user(uid, password):
            return bool_res()[False]
        user_stat = user_cursor.uid_query(uid)[0][4]
        if not user_stat in ['admin', 'root']:
            return bool_res()[False]
        return bool_res()[announcements.edit_announcement(port_api, time_stamp, content)] 
    
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
        return bool_res()[announcements.delete_announcement(port_api, time_stamp)]
    
    @app.route("/announcement/query_all")
    def query_all():
        return announcements.query_all(port_api)
    
    @app.route("/announcement/query_single/<time_stamp>")
    def query_single(time_stamp : str):
        return announcements.query_single(port_api, time_stamp)
 
    return app

# pri, pub, pri_pem, pub_pem, has = generate_rsa_keys()
# with open("res/7001/secret/pub.pem", "wb") as file:
#     file.write(pub_pem)
# usr_obj = UserDb("res/7001/db/user.db", 7001, 1145)
# app = main(7001, 1145, pub_pem, pri, usr_obj)
# app.run(debug=True)