import json
from argon2 import PasswordHasher
from captcha.image import ImageCaptcha
import threading
import web
import db
import logging
from crypto import generate_rsa_keys, load_pub, load_pri
import time
import os

ASCII_LOGO = """
####### #######    #     # #######   ##  #####                                     ##   
   #    #          #     # #        #   #     # ###### #####  #    # ###### #####    #  
   #    #          #     # #       #    #       #      #    # #    # #      #    #    # 
   #    #####      #     # ######  #     #####  #####  #    # #    # #####  #    #    # 
   #    #           #   #        # #          # #      #####  #    # #      #####     # 
   #    #            # #   #     #  #   #     # #      #   #   #  #  #      #   #    #  
   #    #             #     #####    ##  #####  ###### #    #   ##   ###### #    # ##   
"""

COLORS = \
{
	"black": 0,
	"red": 1,
	"green": 2,
	"yellow": 3,
	"blue": 4,
	"magenta": 5,
	"cyan": 6,
	"white": 7
}

# 染色函数

def dye(text, color_code):
	if color_code:
		return "\033[0m\033[1;3{}m{}\033[8;30m\033[0m".format(COLORS[color_code], text)
	return text

def prt(plain, color=None):
	print(dye(plain, color))

PORT_API = None
PORT_TCP = None
PUB_KEY = None
PRI_KEY = None
FLASK_APP = None
FLASK_THREAD = None
IMGCAPTCHA = None
HASHER = None

# Sql 游标
# 节省资源，一个游标用到天荒地老

FORUM_CURSOR = None
USER_CURSOR = None


def create_new_server():
    global HASHER
    global PUB_KEY, PRI_KEY
    global PORT_API
    global PORT_TCP
    global USER_CURSOR

    HASHER = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=24,
        salt_len=16
    )
    PORT_API = input("请输入新服务器的 API 端口号（0~65535且不受防火墙阻挡）：")
    PORT_TCP = input("请输入新服务器的 TCP 端口号（0~65535且不受防火墙阻挡且不与上者重复）：")
    pri, pub, pri_pem, pub_pem, has = generate_rsa_keys()
    prt("你的 RSA 公钥 SHA256 哈希值：{}，为防止中间人攻击导致的危险，请务必将其公布于受信任处以让使用者校对！".format(has), "yellow")
    if not os.path.exists("res/{}/secret".format(PORT_API)):
        os.makedirs("res/{}/secret".format(PORT_API))

    if not os.path.exists("res/{}/captcha".format(PORT_API)):
        os.makedirs("res/{}/captcha".format(PORT_API))

    with open("res/{}/secret/pub.pem".format(PORT_API), "wb") as file:
        file.write(pub_pem)
    with open("res/{}/secret/pri.pem".format(PORT_API), "wb") as file:
        file.write(pri_pem)
    
    with open("server_config.json", "a+") as file:
        try:
            config = json.load(file)
            config[str(len(config))] = [PORT_API, PORT_TCP]
        except Exception as e: 
            config = dict()
            config["0"] = [PORT_API, PORT_TCP]

    with open("server_config.json", "w+") as file:    
        json.dump(config, file)

    print("创建数据库与配置文件……")
    if not os.path.exists("res/{}/db".format(PORT_API)):
        os.makedirs("res/{}/db".format(PORT_API))

    cfg = {
        "server_name" : "TouchFish",
        "port_api" : PORT_API,
        "port_tcp" : PORT_TCP,
        "email_activate" : "",
        "captcha" : False,
        "email_password" : ""
    }
    with open("res/{}/config.json".format(PORT_API), "w+") as file:
        json.dump(cfg, file) 

    with open("res/{}/captcha/captcha.json".format(PORT_API), "w+") as file:
        file.write("{}") 

    with open("res/{}/activate.json".format(PORT_API), "w+") as file:
        file.write("{}") 

    USER_CURSOR = db.UserDb(HASHER, "res/{}/db/user.db".format(PORT_API), PORT_API, PORT_TCP)
    USER_CURSOR.create_user_table()
    print("[INFO] user.db 创建完毕！")
    FORUM_CURSOR = db.ForumDb('res/{}/db/forum.db'.format(PORT_API), PORT_API, PORT_TCP)
    FORUM_CURSOR.create_forum_table()
    print("[INFO] forum.db 创建完毕！")
    

    root_username = input("输入 root 用户的用户名：")
    root_password = input("输入 root 用户的密码：")
    USER_CURSOR.user_create(root_username, root_password, time.time())
    USER_CURSOR.change_auth(0, "root")
    
def flask_thread():
    FLASK_APP.run(debug=False, use_reloader=False)

def main():
    global IMGCAPTCHA
    global FLASK_THREAD
    global PORT_API
    global PORT_TCP
    global PUB_KEY
    global HASHER
    global PRI_KEY
    global USER_CURSOR
    global FLASK_APP

    IMGCAPTCHA = ImageCaptcha()
    HASHER = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=24,
        salt_len=16
    )
    print(ASCII_LOGO)
    prt("欢迎来到 TouchFish V5 服务器！", "green")
    chosen = 0
    try:
        with open("server_config.json", "r+") as file:
            server_lst = json.load(file)
        cnt = len(server_lst.keys())
        for keys in server_lst.keys():
            print("[{}] API_PORT: {}, TCP_PORT : {}".format(keys, server_lst[keys][0], server_lst[keys][1]))
        print("[{}] 创建新的服务器".format(cnt))
    except:
        prt("未找到初始服务器配置！", "red")
        create_new_server()
        chosen = -1
    
    if chosen == 0:
        chosen = input("选择配置：")
        if chosen == str(cnt):
            create_new_server()
        else:
            PORT_API, PORT_TCP = server_lst[chosen]

    PORT_API = int(PORT_API)
    PORT_TCP = int(PORT_TCP)
    if not (0 <= PORT_API <= 65535 and 0 <= PORT_TCP <= 65535):
        prt("端口不符合要求！", "red")
        raise
    print("服务器在 PORT_API={}, PORT_TCP={} 上部署。".format(PORT_API, PORT_TCP))

    PUB_KEY = load_pub("res/{}/secret/pub.pem".format(PORT_API))
    PRI_KEY = load_pri("res/{}/secret/pri.pem".format(PORT_API))
    pub_pem = open("res/{}/secret/pub.pem".format(PORT_API), "rb")

    USER_CURSOR = db.UserDb(HASHER, "res/{}/db/user.db".format(PORT_API), PORT_API, PORT_TCP)
    FLASK_APP = web.main(PORT_API, PORT_TCP, pub_pem, PRI_KEY, IMGCAPTCHA, USER_CURSOR)
    prt("注意：生产环境内不要显式启动 api 服务器！", "yellow")
    stat = input("是否直接显式启动 api 服务器？[Y]")
    if stat == 'Y' or stat == 'y':
        print("启动 API 服务器")
        log = logging.getLogger("werkzeug")
        log.disabled = True
        FLASK_THREAD = threading.Thread(target=flask_thread)
    print("启动 TCP 服务器")


if __name__ == '__main__':
    try:
        main()
        if FLASK_THREAD:
            FLASK_THREAD.start()
    except Exception as e:
        prt(e, "red")
        prt("运行或操作错误，程序终止", "red")
        exit()