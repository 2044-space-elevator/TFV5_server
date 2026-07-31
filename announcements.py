from time import time
from json_store import read_json, update_json

def edit_announcement(port_api : int, time_stamp : str, content : str, lock):
    with lock:
        def edit(cfg):
            if time_stamp not in cfg:
                return False
            cfg[time_stamp]["content"] = content
            return True
        return update_json("res/{}/announcement.json".format(port_api), edit)

def upload_announcement(port_api : int, sender : int, content : str, lock): 
    time_stamp = str(time())
    with lock:
        update_json(
            "res/{}/announcement.json".format(port_api),
            lambda cfg: cfg.__setitem__(time_stamp, {"content" : content, "sender" : sender}),
        )
    return time_stamp

def delete_announcement(port_api : int, time_stamp : str, lock):
    with lock:
        def delete(cfg):
            if time_stamp not in cfg:
                return False
            del cfg[time_stamp]
            return True
        return update_json("res/{}/announcement.json".format(port_api), delete)

def query_all(port_api : int, lock):
    with lock:
        cfg = read_json("res/{}/announcement.json".format(port_api))
    return cfg

def query_single(port_api :int, time_stamp : str, lock):
    with lock:
        cfg = read_json("res/{}/announcement.json".format(port_api))
    if time_stamp not in cfg.keys():
        return {}
    return cfg[time_stamp]
