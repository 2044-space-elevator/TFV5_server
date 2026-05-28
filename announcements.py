from time import time
import json

def edit_announcement(port_api : int, time_stamp : str, content : str, lock):
    with lock:
        with open("res/{}/announcement.json".format(port_api), "r+") as file:
            cfg = json.load(file)
        if time_stamp not in cfg.keys():
            return False
        cfg[time_stamp]["content"] = content
        with open("res/{}/announcement.json".format(port_api), "w+") as file:
            json.dump(cfg, file)
    return True

def upload_announcement(port_api : int, sender : int, content : str, lock): 
    time_stamp = str(time())
    with lock:
        with open("res/{}/announcement.json".format(port_api), "r+") as file:
            cfg = json.load(file)
        cfg[time_stamp] = {"content" : content, "sender" : sender}
        with open("res/{}/announcement.json".format(port_api), "w+") as file:
            json.dump(cfg, file)
    return time_stamp

def delete_announcement(port_api : int, time_stamp : str, lock):
    with lock:
        with open("res/{}/announcement.json".format(port_api), "r+") as file:
            cfg = json.load(file)
        if time_stamp not in cfg.keys():
            return False
        del cfg[time_stamp]
        with open("res/{}/announcement.json".format(port_api), "w+") as file:
            json.dump(cfg, file)
    return True

def query_all(port_api : int, lock):
    with lock:
        with open("res/{}/announcement.json".format(port_api), "r+") as file:
            cfg = json.load(file)
    return cfg

def query_single(port_api :int, time_stamp : str, lock):
    with lock:
        with open("res/{}/announcement.json".format(port_api), "r+") as file:
            cfg = json.load(file)
    if time_stamp not in cfg.keys():
        return {}
    return cfg[time_stamp]