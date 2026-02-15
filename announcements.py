from time import time
import json

def edit_announcement(port_api : int, time_stamp : str, content : str):
    with open("res/{}/announcement.json".format(port_api), "r+") as file:
        cfg = json.load(file)
    if time_stamp not in cfg.keys():
        return False
    cfg[time_stamp]["content"] = content
    with open("res/{}/announcement.json".format(port_api), "w+") as file:
        json.dump(cfg, file)
    return True

def upload_announcement(port_api : int, sender : int, content : str): 
    with open("res/{}/announcement.json".format(port_api), "r+") as file:
        cfg = json.load(file)
    cfg[str(time())] = {"content" : content, "sender" : sender}
    with open("res/{}/announcement.json".format(port_api), "w+") as file:
        json.dump(cfg, file)

def delete_announcement(port_api : int, time_stamp : str):
    with open("res/{}/announcement.json".format(port_api), "r+") as file:
        cfg = json.load(file)
    if time_stamp not in cfg.keys():
        return False
    del cfg[time_stamp]
    with open("res/{}/announcement.json".format(port_api), "w+") as file:
        json.dump(cfg, file)
    return True

def query_all(port_api : int):
    with open("res/{}/announcement.json".format(port_api), "r+") as file:
        cfg = json.load(file)
    return cfg

def query_single(port_api :int, time_stamp : str):
    with open("res/{}/announcement.json".format(port_api), "r+") as file:
        cfg = json.load(file)
    if time_stamp not in cfg.keys():
        return {}
    return cfg[time_stamp]