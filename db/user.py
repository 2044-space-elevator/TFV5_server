from db.tool import Db
from crypto import sha256, pwd_verify
import re
import json

email_regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

class UserDb(Db):
    def __init__(self, hasher, path : str, port_api : int, port_tcp : int):
        super().__init__(path, port_api, port_tcp)
        self.hasher = hasher
    
    def verify_user(self,  uid, password):
        lst = self.uid_query(uid)
        if pwd_verify(self.hasher, lst[0][3], password):
            return True
        return False
    
    def user_create(self, username, password, create_time, email=None):
        """
        创建新的用户
        需注意用户名、邮箱不能重复，且长度不超过 20，不少于 4
        
        :param username: 用户名
        :param password: 密码
        :param create_time: 创建时间（使用时间戳）
        :param email: 邮箱地址
        """
        if len(username) > 20 or len(username) < 4:
            return False
        
        if " " in username:
            return False

        if self.username_query(username):
            return False
        
        if email and not re.fullmatch(email_regex, email):
            return False

        if email and self.email_query(email):
            return False

        uid = self.query("SELECT MAX(uid) from users")[0][0]
        if uid == None:
            uid = 0
        else:
            uid += 1
        
        pwd_hash = self.hasher.hash(password) 
        try:
            if email:
                self.execute("INSERT INTO users (uid, username, pwd_hash, create_time, email) VALUES (?, ?, ?, ?, ?)", (uid, username, pwd_hash, create_time, email))
            else:
                self.execute("INSERT INTO users (uid, username, pwd_hash, create_time) VALUES (?, ?, ?, ?)", (uid, username, pwd_hash, create_time))
            return True
        except Exception as e:
            print(e)

    def uid_query(self, uid : int):
        """
        依据 uid 查询用户基本信息
        """
        return self.query("SELECT * FROM users WHERE uid = ?",  (uid,))

    def username_query(self, username : str):
        return self.query("SELECT * FROM users WHERE username = ?",  (username,))

    def email_query(self, email : str):
        """
        根据邮箱查询用户基本信息
        """
        return self.query("SELECT * FROM users WHERE email = ?",  (email,))

    def create_user_table(self):
        cmd = """
    CREATE TABLE IF NOT EXISTS users (
        uid INTEGER UNIQUE NOT NULL,
        username TEXT COLLATE NOCASE UNIQUE NOT NULL,
        email TEXT UNIQUE,
        pwd_hash TEXT NOT NULL,
        stat TEXT DEFAULT 'user',
        create_time TEXT REAL,
        sign TEXT,
        introduction TEXT
    )
    """
        self.execute(cmd)
    
    def change_pwd(self, uid : int, new_pwd : str):
        pwd_hash = self.hasher.hash(new_pwd)
        self.execute("UPDATE users SET pwd_hash = ? where uid = ?", (pwd_hash, uid))

    def change_auth(self, oped : int, new_auth : str):
        self.execute("UPDATE users SET stat = ? where uid = ?", (new_auth, oped))
    
    def change_email(self, oped : int, new_email : str):
        self.execute("UPDATE users SET email = ? where uid = ?", (new_email, oped))