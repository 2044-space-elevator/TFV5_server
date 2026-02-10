"""
没错，只是为了放验证码和邮箱验证的程序
"""

import os
import json
from random import choices, randint
import smtplib
from string import ascii_letters, digits
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
from time import time

MAX_DELAY = 300

def login_email(sender_email : str, password : str):
    """
    password 是登录密码或者授权码，视邮件提供商要求
    """
    server = sender_email.split('@')[1]
    smtp_server = 'smtp.' + server
    smtp_port = 465 
    server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=1e5)
    server.login(sender_email, password)
    return server

def send_email(server, sender_email : str, receiver_email : str, subject : str, content : str):
    """
    server 是 smtplib.SMTP_SSL 对象
    """
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = receiver_email
    msg["Subject"] = Header(subject, 'utf-8')
    msg.attach(MIMEText(content, "plain", "utf-8"))
    try:
        server.sendmail(sender_email, receiver_email, msg.as_string())
    except:
        return False
    return True

def delete_old_captcha(port_api : int):
    folder_path = "res/{}/captcha".format(port_api)
    current_time = time()
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if "captcha.json" in file_path:
            continue
        if os.path.isfile(file_path):
            try:
                create_time = int(filename.split('.')[0])
                if current_time - create_time > MAX_DELAY:
                    os.remove(file_path)
            except:
                continue

def generate_captcha(port_api : int, Imgcaptcha):
    """
    生成验证码
    ImgCaptcha 是 captcha.ImageCaptcha 对象
    返回的是验证码时间戳，可以当做是 token
    """
    delete_old_captcha(port_api)
    chars = ascii_letters + digits
    answer =  choices(chars, k=6)
    captcha_text = ''.join(answer)
    time_now = int(time())
    Imgcaptcha.write(captcha_text, 'res/{}/captcha/{}.png'.format(port_api, time_now))
    with open("res/{}/captcha/captcha.json".format(port_api), "r+") as file:
        cap = json.load(file)
        cap[str(time_now)] = captcha_text
    
    with open("res/{}/captcha/captcha.json".format(port_api), "w+") as file:
        json.dump(cap, file)
    return time_now

def verify_captcha(port_api : int, time_stamp : int, verify_text : str):
    if time() - int(time_stamp) > MAX_DELAY:
        return False
    folder_path = "res/{}/captcha".format(port_api)
    if "{}.png".format(time_stamp) not in os.listdir(folder_path):
        return False
    with open(folder_path + '/captcha.json', "r+") as file:
        lst = json.load(file)
        if (lst[str(time_stamp)].lower() == verify_text.lower()):
            return True
        else:
            return False

def email_code(sender_email : str, port_api : int, email : str, password : str):
    session = login_email(sender_email, password)
    folder_path = "res/{}".format(port_api)
    with open(folder_path + '/config.json', 'r+') as file:
        sender = sender_email
        server_name = json.load(file)["server_name"]
    verify_code = randint(100000, 999999)
    with open(folder_path + '/activate.json', 'r+') as file:
        activate_lst = json.load(file)
    activate_lst[email] = verify_code  
    with open(folder_path + '/activate.json', 'r+') as file:
        json.dump(activate_lst, file)
    return send_email(session, sender, email, "{} 验证码".format(server_name), "欢迎使用 {}，您的验证码是 {}。".format(server_name, verify_code))

def verify_email(port_api : int, email : str, code : int):
    folder_path = "res/{}/".format(port_api)
    with open(folder_path + '/activate.json', 'r+') as file:
        code_lst = json.load(file)
        if not email in code_lst.keys():
            return False
        activate_code = code_lst[email]

    code_lst[email] = -1
    with open(folder_path + '/activate.json', 'w+') as file:
        json.dump(code_lst, file)
    
    if activate_code == code:
        return True
    return False
